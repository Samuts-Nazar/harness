"""Turn pipeline: narrator -> per-NPC calls -> extractor -> validation -> commit.
Also live and retroactive interruption."""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from typing import Callable, Sequence

from .agents import AgentRegistry, Intents, OffscreenUpdater, StubOffscreenUpdater
from .context import ContextBuilder
from .db import connect
from .eventlog import EventLog
from .extractor import DiffValidationError, FactDraft, parse_diff, validate_diff
from .facts import FactStore
from .judge import Judge, StubJudge
from .models import (
    INTERRUPTION,
    NARRATION,
    PLAYER,
    UTTERANCE,
    WITNESSED,
    CharacterProfile,
    Event,
    Scene,
)
from .providers import Provider
from .streaming import InterruptHandle, StreamResult, run_stream


class InterruptionError(RuntimeError):
    """A retroactive interrupt outside the allowed window."""


class ExtractionRejected(RuntimeError):
    """The extractor never produced a valid diff; the turn was rolled back."""


@dataclass(frozen=True)
class ModelConfig:
    narrator: str = "narrator"
    npc: str = "npc"
    extractor: str = "extractor"


@dataclass
class TurnResult:
    narration: str
    utterances: list[Event] = field(default_factory=list)
    fact_ids: list[int] = field(default_factory=list)
    interrupted: bool = False


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
        minutes_per_turn: int = 5,
        extract_retries: int = 1,
        pace: float = 0.0,
    ) -> None:
        self.conn = conn or connect()
        self.provider, self.models, self.scene = provider, models, scene
        self.judge = judge or StubJudge()  # slot for typed judgments; unused by the skeleton
        self.updater = updater or StubOffscreenUpdater()
        self.minutes_per_turn, self.extract_retries, self.pace = (
            minutes_per_turn,
            extract_retries,
            pace,
        )
        self.profiles = {p.id: p for p in profiles}
        self.log = EventLog(self.conn)
        self.facts = FactStore(self.conn)
        self.agents = AgentRegistry(self.log)
        self.intents = Intents(self.log)
        self.ctx = ContextBuilder(self.log, self.facts, self.intents, self.profiles)

    # -- helpers --------------------------------------------------------
    def _event(self, type: str, participants: Sequence[str], payload: dict, **kw) -> Event:  # type: ignore[type-arg]
        return self.log.append(
            type,
            game_time=self.scene.time,
            location=self.scene.location,
            participants=participants,
            witnesses=self.scene.present,
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

    def _extract(self, segments: list[tuple[str, str]]) -> list[FactDraft]:
        messages = self.ctx.extractor(self.scene, segments)
        sources = {k for k, _ in segments}
        last: Exception | None = None
        for _ in range(self.extract_retries + 1):
            raw = self.provider.complete(self.models.extractor, messages)
            try:
                return validate_diff(parse_diff(raw), present=self.scene.present, sources=sources)
            except DiffValidationError as e:
                last = e
        raise ExtractionRejected(str(last))

    def _commit(self, drafts: list[FactDraft], source_events: dict[str, Event]) -> list[int]:
        ids = []
        for d in drafts:
            ev = source_events[d.source]
            ids.append(
                self.facts.add_campaign(
                    d.content,
                    source_event_id=ev.id,
                    game_time=self.scene.time,
                    location=d.location or self.scene.location,
                    notability=d.notability,
                    knowers=d.knowers,
                )
            )
        return ids

    # -- the turn -------------------------------------------------------
    def turn(
        self,
        player_text: str,
        speakers: Sequence[str] = (),
        *,
        handle: InterruptHandle | None = None,
        on_word: Callable[[str, str], None] | None = None,
    ) -> TurnResult:
        """Run one turn. `speakers` (which NPCs talk) is chosen by the caller; deciding
        that automatically is not specified yet. `on_word(speaker, word)` receives the
        streamed words; a handle fired from inside it interrupts live."""
        sc = self.scene
        for s in speakers:
            if s not in sc.present or s == PLAYER:
                raise ValueError(f"{s!r} cannot speak: not an NPC in the scene")
        turn_events: list[Event] = []
        try:
            player_ev = self._utterance(PLAYER, player_text)
            turn_events.append(player_ev)

            narration = self.provider.complete(
                self.models.narrator, self.ctx.narrator(sc, player_text)
            ).strip()
            narr_ev = self._event(NARRATION, [], {"text": narration}, notability=0.4)
            turn_events.append(narr_ev)

            sources = {PLAYER: player_ev, "narration": narr_ev}
            segments = [(PLAYER, player_text), ("narration", narration)]
            result = TurnResult(narration)
            for npc in speakers:
                cb = (lambda w, n=npc: on_word(n, w)) if on_word else None
                sr = run_stream(
                    self.provider.stream(self.models.npc, self.ctx.character(npc, sc)),
                    handle,
                    cb,
                    self.pace,
                )
                ev = self._utterance(npc, sr.spoken_text, interrupted=sr.interrupted)
                turn_events.append(ev)
                result.utterances.append(ev)
                sources[npc] = ev
                segments.append((npc, sr.spoken_text))
                if sr.interrupted:
                    turn_events += self._record_interruption(ev, sr)
                    result.interrupted = True
                    break

            drafts = self._extract(segments)
            result.fact_ids = self._commit(drafts, sources)
        except Exception:
            for e in turn_events:
                self.log.rollback(e.id, "turn failed")
            raise
        for u in result.utterances:
            self.agents.promote(u.payload["speaker"], sc)
        sc.time += self.minutes_per_turn
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
            knowers=[(c, WITNESSED) for c in self.scene.present],
        )
        made = [ev]
        if sr.tail:
            made.append(self.intents.set(npc, sr.tail_text, self.scene))
        return made

    def interrupt_retroactive(self, after_words: int) -> Event:
        """Cut the last NPC utterance after `after_words` words.

        Allowed only for the most recent NPC utterance, once. Everything derived from
        that utterance is rolled back; facts are re-extracted from the kept part only
        (the extractor cannot tell which fact came from which words, so we are
        conservative). Returns the new, truncated utterance event.
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
            drafts = self._extract([(npc, sr.spoken_text)])
            self._commit(drafts, {npc: kept})
        except ExtractionRejected:
            pass  # keep the cut; simply record no facts from the kept part
        return kept

    # -- off-screen -----------------------------------------------------
    def advance_offscreen(self, minutes: int) -> None:
        start = self.scene.time
        self.scene.time += minutes
        for a in self.agents.agents():
            if a not in self.scene.present:
                self.updater.update(a, start, self.scene.time)
