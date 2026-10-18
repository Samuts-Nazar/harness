"""Turn pipeline: narrator (structured) -> per-NPC calls (each output-checked) -> extractor ->
validation -> perception computed in code -> commit. Also live and retroactive interruption,
scene entry, live-state perception, and regeneration of the per-character memory files."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Sequence

from .agents import AgentRegistry, Intents, OffscreenUpdater, StubOffscreenUpdater
from .attitudes import Attitudes, Notices
from .belief import BeliefFn, neutral_belief
from .context import ContextBuilder
from .db import connect
from .eventlog import EventLog
from .extractor import Diff, DiffValidationError, parse_diff, validate_diff
from .facts import FactStore
from .judge import (
    Judge, JudgeError, JudgmentLog, LoggingJudge, choice_q, default_fake_judge, score_q, yes_no_q,
)
from .memory import CharacterMemory, MemoryDeriver, MemoryWriter
from .models import (
    ACTION as ACTION_EVENT,
    INTERRUPTION,
    NARRATION,
    PLAYER,
    SCENE_ENTRY,
    SCRIPTED,
    STATE_CHANGE,
    UTTERANCE,
    WITNESSED,
    CharacterProfile,
    Event,
    Scene,
)
from .narrator import (
    NarrationError, NarratorOutput, clean_npc_line, has_quotes, has_speaker_line, parse_narration,
    strip_speech,
)
from .perception import ACTION, DESCRIPTION, SPEECH, perceivers
from .providers import Provider
from .state import LiveState, StateChange, check_change, payload as change_payload
from .streaming import InterruptHandle, StreamResult, run_stream

ATTITUDE_MIN_NOTABILITY = 0.6  # only notable facts get attitude judgments (cost control)
FALLBACK_LINE = "I don't know what to tell you."

_OBSERVED = {  # how an observer sees a newly observable element
    "injury": "{who} is visibly injured: {item}",
    "clothing": "{who} is wearing {item}",
    "inventory": "{who} is carrying {item}",
    "equipment": "{who} has {item} in hand or at the belt",
    "internal": "{who} visibly shows {item}",
}


class InterruptionError(RuntimeError):
    """A retroactive interrupt outside the allowed window."""


class ExtractionRejected(RuntimeError):
    """The extractor never produced a valid diff; the turn was rolled back."""


@dataclass(frozen=True)
class ModelConfig:
    narrator: str = "narrator"
    npc: str = "npc"
    extractor: str = "extractor"
    judge: str = "judge"  # LLM used for judge escalation (read by whoever builds the judge)


@dataclass
class TurnResult:
    narration: str
    utterances: list[Event] = field(default_factory=list)
    fact_ids: list[int] = field(default_factory=list)
    interrupted: bool = False
    actions: list[str] = field(default_factory=list)


class Engine:
    def __init__(
        self,
        provider: Provider,
        profiles: Sequence[CharacterProfile],
        scene: Scene,
        *,
        conn: sqlite3.Connection | None = None,
        models: ModelConfig = ModelConfig(),
        judge: Judge | None = None,
        updater: OffscreenUpdater | None = None,
        belief: BeliefFn = neutral_belief,
        campaign_dir: Path | str | None = None,
        minutes_per_turn: int = 5,
        extract_retries: int = 1,
        narrate_retries: int = 2,
        check_retries: int = 2,
        pace: float = 0.0,
    ) -> None:
        self.conn = conn or connect()
        self.provider, self.models, self.scene = provider, models, scene
        self.campaign_dir = Path(campaign_dir) if campaign_dir else None
        self.judgments = JudgmentLog(self.campaign_dir / "judgments.jsonl" if self.campaign_dir
                                     else None)
        self.judge: Judge = LoggingJudge(judge or default_fake_judge(), self.judgments)
        self.updater = updater or StubOffscreenUpdater()
        self.minutes_per_turn, self.extract_retries, self.pace = (
            minutes_per_turn, extract_retries, pace)
        self.narrate_retries, self.check_retries = narrate_retries, check_retries
        self.devlog: list[dict[str, Any]] = []  # engine-side events for the debug view
        self.profiles = {p.id: p for p in profiles}
        self.log = EventLog(self.conn)
        self.facts = FactStore(self.conn)
        self.agents = AgentRegistry(self.log)
        self.intents = Intents(self.log)
        self.live = LiveState(self.log)
        self.attitudes = Attitudes(self.log, self.facts)
        self.notices = Notices(self.log, self.facts)
        self.deriver = MemoryDeriver(self.facts, self.intents, self.live, self.attitudes,
                                     self.notices, belief)
        self.ctx = ContextBuilder(self.log, self.facts, self.intents, self.profiles, self.live,
                                  self.deriver)
        self.memory = (MemoryWriter(self.campaign_dir / "memory", self.deriver, self.log,
                                    self.profiles, self.agents) if self.campaign_dir else None)

    # -- helpers --------------------------------------------------------
    def _note(self, kind: str, **info: Any) -> None:
        self.devlog.append({"kind": kind, **info})

    def _event(self, type: str, participants: Sequence[str], payload: dict, *,  # type: ignore[type-arg]
               witnesses: Sequence[str] | None = None, **kw) -> Event:
        return self.log.append(
            type,
            game_time=self.scene.time,
            location=self.scene.location,
            participants=participants,
            witnesses=self.scene.present if witnesses is None else witnesses,
            payload=payload,
            **kw,
        )

    def _utterance(self, speaker: str, text: str, **extra: object) -> Event:
        return self._event(
            UTTERANCE,
            [speaker],
            {"speaker": speaker, "text": text, **extra},
            notability=0.4,
        )

    def refresh_memory(self) -> None:
        """Rewrite the per-character memory files from the log."""
        if self.memory is not None:
            self.memory.regenerate(self.scene.time)

    def rollback(self, event_id: int, reason: str = "rollback") -> list[int]:
        done = self.log.rollback(event_id, reason)
        self.refresh_memory()
        return done

    @property
    def _npc_names(self) -> list[str]:
        return [p.name for c, p in self.profiles.items() if c != PLAYER] + [
            c for c in self.profiles if c != PLAYER]

    # -- narrator -------------------------------------------------------
    def _narrator_speech(self, out: NarratorOutput) -> bool:
        text = "\n".join(out.texts())
        if has_speaker_line(text, self._npc_names):
            return True
        if not has_quotes(text):
            return False
        try:
            return bool(self.judge.yes_no(
                "Does the text contain words spoken aloud by a character other than the "
                "player character?",
                f"Player character: {self.ctx.name(PLAYER)}\nText: {text}",
                tag="narrator_speech").answer)
        except JudgeError as e:
            self._note("narrator_speech_check_failed", error=str(e))
            return True  # quotes and no verdict: treat as speech

    def _narrate(self, player_text: str) -> NarratorOutput:
        """Structured narrator output. NPC speech is rejected and regenerated (at most
        `narrate_retries` times); after that the speech is stripped and logged."""
        sc = self.scene
        raw, parsed = "", None
        for attempt in range(self.narrate_retries + 1):
            raw = self.provider.complete(
                self.models.narrator, self.ctx.narrator(sc, player_text)).strip()
            try:
                out = parse_narration(raw)
            except NarrationError as e:
                self._note("narrator_malformed", attempt=attempt, error=str(e))
                continue
            parsed = out
            if not self._narrator_speech(out):
                return self._valid_speakers(out)
            self._note("narrator_speech_rejected", attempt=attempt, text=out.description)
        names = self._npc_names
        if parsed is None:
            parsed = NarratorOutput(raw)
        stripped = NarratorOutput(
            strip_speech(parsed.description, names),
            [a for a in (strip_speech(a, names) for a in parsed.actions) if a],
            parsed.speakers,
        )
        if not stripped.description:
            stripped.description = "..."
        self._note("narrator_speech_stripped", before=parsed.description,
                   after=stripped.description)
        return self._valid_speakers(stripped)

    def _valid_speakers(self, out: NarratorOutput) -> NarratorOutput:
        ok = [s for s in out.speakers if s in self.scene.present and s != PLAYER]
        if len(ok) != len(out.speakers):
            self._note("narrator_bad_speakers", proposed=out.speakers, kept=ok)
        out.speakers = ok
        return out

    # -- NPC lines ------------------------------------------------------
    def _unknown_claim(self, npc: str, mem: CharacterMemory, line: str) -> bool:
        """Does the line contain a claim the NPC had no channel to learn?"""
        witnessed = [self.ctx._seen(e) for e in
                     self.log.recent_dialogue(witnessed_by=npc, limit=self.ctx.history_limit)]
        known = (self.ctx.knowledge_lines(mem) + witnessed
                 + [f"- (own condition) {e.category}: {e.item}" for e in mem.state]
                 + [f"- (just noticed) {f.content}" for _, f in mem.noticed])
        try:
            return bool(self.judge.yes_no(
                "Does the line assert a fact about the world or other people that this "
                "character had no channel to learn from what they know? Ignore greetings, "
                "questions, opinions and general common sense.",
                f"Character: {self.ctx.name(npc)}\nWhat the character knows:\n"
                + ("\n".join(known) or "- (nothing)") + f"\nLine: {line}",
                tag="unknown_claim").answer)
        except JudgeError as e:
            self._note("npc_check_unavailable", npc=npc, error=str(e))
            return False

    def _npc_line(self, npc: str, mem: CharacterMemory) -> str:
        """Generate and output-check one NPC line (regenerate up to `check_retries` times; then
        fall back to a minimal in-character non-answer)."""
        rejected: list[str] = []
        for _ in range(self.check_retries + 1):
            text = clean_npc_line(self.provider.complete(
                self.models.npc, self.ctx.character(npc, self.scene, mem)))
            if not self._unknown_claim(npc, mem, text):
                return text
            rejected.append(text)
            self._note("npc_line_rejected", npc=npc, text=text)
        self._note("npc_fallback", npc=npc, rejected=rejected)
        return FALLBACK_LINE

    # -- extraction -----------------------------------------------------
    def _extract(self, segments: list[tuple[str, str]]) -> Diff:
        messages = self.ctx.extractor(self.scene, segments)
        sources = {k for k, _ in segments}
        sc = self.scene
        everyone = set(self.profiles) | set(sc.present) | set(sc.outside)
        last: Exception | None = None
        for _ in range(self.extract_retries + 1):
            raw = self.provider.complete(self.models.extractor, messages)
            try:
                return validate_diff(parse_diff(raw), present=sc.present, sources=sources,
                                     state=self.live.snapshot(), characters=everyone)
            except DiffValidationError as e:
                last = e
        raise ExtractionRejected(str(last))

    @staticmethod
    def _segment_kind(key: str) -> tuple[str, str | None]:
        """(perception kind, speaker) of an extractor segment key."""
        if key == "narration":
            return DESCRIPTION, None
        if key.startswith("action") and key[6:].isdigit():
            return ACTION, None
        return SPEECH, key  # "player" or an NPC id

    def _commit(self, diff: Diff, source_events: dict[str, Event]) -> list[int]:
        """Store facts with perception computed from scene state, then apply state changes."""
        ids = []
        for d in diff.facts:
            kind, speaker = self._segment_kind(d.source)
            ps = perceivers(self.scene, kind, d.notability, speaker)
            ids.append(
                self.facts.add_campaign(
                    d.content,
                    source_event_id=source_events[d.source].id,
                    game_time=self.scene.time,
                    location=d.location or self.scene.location,
                    notability=d.notability,
                    knowers=[(p.character, p.how, p.source) for p in ps],
                )
            )
        for ch in diff.changes:
            self._apply_change(ch, source_events[ch.source])
        self._assess_attitudes(ids)
        return ids

    # -- live state and its perception ---------------------------------
    def _apply_change(self, ch: StateChange, cause: Event) -> Event:
        was = self.live.snapshot().get(ch.character, {}).get((ch.category, ch.item))
        ev = self.log.append(
            STATE_CHANGE,
            game_time=self.scene.time,
            location=self.scene.location,
            participants=[ch.character],
            witnesses=[],
            payload=change_payload(ch),
            cause_id=cause.id,
        )
        who = self.ctx.name(ch.character)
        # only someone in the room can be seen; an absent character's change waits for entry
        observers = ([c for c in self.scene.present if c != ch.character]
                     if ch.character in self.scene.present else [])
        if ch.op == "add" and ch.observable or ch.op == "reveal":
            self._observe(_OBSERVED[ch.category].format(who=who, item=ch.item), observers, ev)
        elif ch.op == "remove" and was:
            self._observe(f"{who} no longer has {ch.item}", observers, ev)
        return ev

    def _observe(self, text: str, observers: Sequence[str], cause: Event) -> int | None:
        """Every observer perceives `text` (directly); a salience judgment per observer decides
        whether it is surfaced as noteworthy in that NPC's next context."""
        if not observers:
            return None
        fid = self.facts.add_campaign(
            text,
            source_event_id=cause.id,
            game_time=self.scene.time,
            location=self.scene.location,
            notability=0.4,
            knowers=[(o, WITNESSED, None) for o in observers],
        )
        npcs = [o for o in observers if o != PLAYER]  # the player needs no NPC context
        if npcs:
            qs = {}
            for o in npcs:
                p = self.profiles.get(o)
                qs[o] = yes_no_q(
                    f"Would {self.ctx.name(o)}{' (' + p.description + ')' if p and p.description else ''}"
                    " notice this and find it worth reacting to?", tag="salience")
            try:
                verdicts = {o: bool(j.answer) for o, j in self.judge.ask(
                    [f"Observation: {text}", f"Place: {self.scene.location}"], qs).items()}
            except JudgeError as e:
                self._note("salience_unavailable", error=str(e))
                verdicts = {o: False for o in npcs}
            for o in npcs:
                self.notices.add(o, fid, verdicts.get(o, False), self.scene, cause.id)
        return fid

    def apply_state_change(self, ch: StateChange) -> Event:
        """Code-side state change (setup, scripted events). Validated like an extractor one;
        observable changes are perceived by whoever is present."""
        check_change(self.live.snapshot(), ch)
        # a scripted marker event is the cause, so rolling it back removes the change
        cause = self._event(SCRIPTED, [ch.character], {"text": f"{ch.op} {ch.item}"},
                            witnesses=[], notability=0.3)
        ev = self._apply_change(ch, cause)
        self.refresh_memory()
        return ev

    def enter_scene(self, character: str) -> Event:
        """A character walks in: the room perceives their observable state, and they perceive
        everyone else's."""
        sc = self.scene
        if character in sc.present:
            raise ValueError(f"{character!r} is already in the scene")
        others = [c for c in sc.present]
        sc.outside = tuple(c for c in sc.outside if c != character)
        ev = self._event(SCENE_ENTRY, [character], {"character": character}, notability=0.4)
        sc.present = sc.present + (character,)
        snap = self.live.snapshot()
        for (cat, item), obs in snap.get(character, {}).items():
            if obs:
                self._observe(_OBSERVED[cat].format(who=self.ctx.name(character), item=item),
                              others, ev)
        for other in others:
            for (cat, item), obs in snap.get(other, {}).items():
                if obs:
                    self._observe(_OBSERVED[cat].format(who=self.ctx.name(other), item=item),
                                  [character], ev)
        self.refresh_memory()
        return ev

    def leave_scene(self, character: str, *, stay_nearby: bool = True) -> None:
        sc = self.scene
        sc.present = tuple(c for c in sc.present if c != character)
        if stay_nearby:
            sc.outside = sc.outside + (character,)
        self.refresh_memory()

    # -- attitudes ------------------------------------------------------
    def _assess_attitudes(self, fact_ids: Sequence[int]) -> None:
        for fid in fact_ids:
            f = self.facts.get(fid)
            if f is None or f.notability < ATTITUDE_MIN_NOTABILITY:
                continue
            npcs = [k.character for k in f.knowers if k.character != PLAYER]
            if not npcs:
                continue
            qs = {}
            for c in npcs:
                n = self.ctx.name(c)
                qs[f"{c}:dir"] = choice_q(
                    f"How does {n} feel about this?",
                    {"positive": "approves or is pleased", "neutral": "indifferent",
                     "negative": "disapproves, is afraid or hostile"}, tag="attitude_direction")
                qs[f"{c}:mag"] = score_q(
                    f"How strongly does {n} feel about this?", legend=(
                        "not at all", "slightly", "noticeably", "strongly"),
                    tag="relationship_magnitude")
            try:
                got = self.judge.ask([f"Event: {f.content}"], qs)
            except JudgeError as e:
                self._note("attitude_unavailable", fact=fid, error=str(e))
                continue
            for c in npcs:
                stance = str(got[f"{c}:dir"].answer)
                mag = float(got[f"{c}:mag"].answer)
                if stance != "neutral" and mag > 0:
                    self.attitudes.set(c, fid, stance, round(mag, 2), self.scene,
                                       f.source_event_id)  # type: ignore[arg-type]

    # -- the turn -------------------------------------------------------
    def turn(
        self,
        player_text: str,
        speakers: Sequence[str] | None = None,
        *,
        handle: InterruptHandle | None = None,
        on_word: Callable[[str, str], None] | None = None,
    ) -> TurnResult:
        """Run one turn. The narrator proposes who speaks next; `speakers` overrides that.
        `on_word(speaker, word)` receives the delivered words; a handle fired from inside it
        interrupts live."""
        sc = self.scene
        for s in speakers or ():
            if s not in sc.present or s == PLAYER:
                raise ValueError(f"{s!r} cannot speak: not an NPC in the scene")
        turn_events: list[Event] = []
        try:
            player_ev = self._utterance(PLAYER, player_text)
            turn_events.append(player_ev)

            out = self._narrate(player_text)
            narr_ev = self._event(NARRATION, [], {"text": out.description}, witnesses=[],
                                  notability=0.4)
            turn_events.append(narr_ev)
            sources = {PLAYER: player_ev, "narration": narr_ev}
            segments = [(PLAYER, player_text), ("narration", out.description)]
            for i, act in enumerate(out.actions, 1):
                ev = self._event(ACTION_EVENT, [], {"text": act}, notability=0.4)
                turn_events.append(ev)
                sources[f"action{i}"] = ev
                segments.append((f"action{i}", act))

            result = TurnResult(out.description, actions=list(out.actions))
            for npc in (list(speakers) if speakers is not None else out.speakers):
                mem = self.deriver.derive(npc, sc.time)
                text = self._npc_line(npc, mem)
                for notice, _ in mem.noticed:  # surfaced now, so not again next turn
                    turn_events.append(self.notices.mark_shown(notice, sc))
                cb = (lambda w, n=npc: on_word(n, w)) if on_word else None
                sr = run_stream(iter([text]), handle, cb, self.pace)
                ev = self._utterance(npc, sr.spoken_text, interrupted=sr.interrupted)
                turn_events.append(ev)
                result.utterances.append(ev)
                sources[npc] = ev
                segments.append((npc, sr.spoken_text))
                if sr.interrupted:
                    turn_events += self._record_interruption(ev, sr)
                    result.interrupted = True
                    break

            result.fact_ids = self._commit(self._extract(segments), sources)
        except Exception:
            for e in turn_events:
                self.log.rollback(e.id, "turn failed")
            self.refresh_memory()
            raise
        for u in result.utterances:
            self.agents.promote(u.payload["speaker"], sc)
        sc.time += self.minutes_per_turn
        self.refresh_memory()
        return result

    # -- interruption ---------------------------------------------------
    def _record_interruption(self, spoken_ev: Event, sr: StreamResult) -> list[Event]:
        npc = spoken_ev.payload["speaker"]
        n = len(sr.spoken)
        ev = self._event(
            INTERRUPTION,
            [PLAYER, npc],
            {"interrupted": npc, "after_words": n, "utterance_event": spoken_ev.id},
            notability=0.5,
        )
        self.facts.add_campaign(
            f"{self.ctx.name(PLAYER)} interrupted {self.ctx.name(npc)} after "
            f"{n} words: \"{sr.spoken_text}\"",
            source_event_id=ev.id,
            game_time=self.scene.time,
            location=self.scene.location,
            notability=0.5,
            knowers=[(p.character, p.how, p.source)
                     for p in perceivers(self.scene, ACTION, 0.5)],  # normal perception rules
        )
        made = [ev]
        if sr.tail:
            made.append(self.intents.set(npc, sr.tail_text, self.scene))
        return made

    def interrupt_retroactive(self, after_words: int) -> Event:
        """Cut the last NPC utterance after `after_words` words.

        Allowed only for the most recent NPC utterance, once. Everything derived from
        that utterance (facts, state changes and their perceptions) is rolled back; facts are
        re-extracted from the kept part only (the extractor cannot tell which fact came from
        which words, so we are conservative). Returns the new, truncated utterance event.
        """
        last = self.log.last_npc_utterance()
        if last is None:
            raise InterruptionError("no NPC utterance to interrupt")
        if last.payload.get("interrupted"):
            raise InterruptionError("this utterance was already interrupted")
        words = last.payload["text"].split()
        if not 0 < after_words < len(words):
            raise InterruptionError("cut point must fall inside the utterance")
        npc = last.payload["speaker"]
        sr = StreamResult(tuple(words[:after_words]), tuple(words[after_words:]), True)

        self.log.rollback(last.id, f"retroactive interrupt of {npc}")
        kept = self._utterance(npc, sr.spoken_text, interrupted=True, replaces=last.id)
        self._record_interruption(kept, sr)
        try:
            self._commit(self._extract([(npc, sr.spoken_text)]), {npc: kept})
        except ExtractionRejected:
            pass  # keep the cut; simply record no facts from the kept part
        self.refresh_memory()
        return kept

    # -- off-screen -----------------------------------------------------
    def advance_offscreen(self, minutes: int) -> None:
        start = self.scene.time
        self.scene.time += minutes
        for a in self.agents.agents():
            if a not in self.scene.present:
                self.updater.update(a, start, self.scene.time)
