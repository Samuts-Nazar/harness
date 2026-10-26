"""Turn pipeline: narrator (structured) -> per-NPC calls (each output-checked) -> extractor ->
validation -> perception computed in code -> commit. Also live and retroactive interruption,
scene entry, live-state perception, and regeneration of the per-character memory files."""
from __future__ import annotations

import json
import random
import re
import sqlite3
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path
from typing import Any, Callable, Sequence

from .agents import AgentRegistry, Intents, OffscreenUpdater, StubOffscreenUpdater
from .attitudes import Attitudes, Notices
from .belief import BeliefFn, neutral_belief
from .context import PLAYER_CHARACTER_RULE, ContextBuilder, NpcView
from .db import connect
from .decisions import DecisionCount, count_since
from .director import (
    EXCHANGE_HEADER, NOBODY, PLAYER_FLOOR, decide_first_step, decide_next, decide_speakers,
    parse_actions,
)
from .eventlog import EventLog
from .relations import SEED_VALUES
from .extractor import Diff, DiffValidationError, parse_diff, validate_diff
from .facts import FactStore
from .glossary import Glossary
from .judge import (
    Judge, JudgeError, JudgmentLog, LoggingJudge, choice_q, default_fake_judge, score_q, yes_no_q,
)
from . import knowledge, relations
from .memory import CharacterMemory, MemoryDeriver, MemoryWriter
from .names import INTRODUCED, OVERHEARD, PLAYER_SAID, TOLD as NAME_TOLD, Names
from .player_guard import PLAYER_ACT_Q, flag_player_acts, split_sentences, strip_player_quotes
from .player_input import (
    ACTION as PART_ACTION, SPEECH as SPEECH_PART, Part, has_action, render_for_model, split_input,
)
from .models import (
    ACTION as ACTION_EVENT,
    CORRECTION,
    INTERRUPTION,
    NARRATION,
    PLAYER,
    PORTRAIT_LEAK,
    RELATION,
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
    NarrationError, NarratorOutput, clean_npc_line, has_dash_speech, has_quotes, has_speaker_line,
    parse_narration,
    strip_speech,
)
from .npcgen import NpcSpec, VitalsBook, generate_npc, short_portrait, taken_names, with_core
from .outcome import (
    CHARACTER_DEATH, FAILS, OUTCOME, CampaignEnded, Outcome, OutcomeJudge, record_death, record_outcome,
)
from .perception import ACTION, DESCRIPTION, SPEECH, perceivers
from .policy import (
    DEFAULT_EXTRACTOR, DEFAULT_JUDGE_LLM, DEFAULT_NARRATOR, DEFAULT_NPC, FALLBACKS,
)
from .providers import Provider, ProviderError
from .stylehits import count_by_kind, style_hits
from .portrait import PortraitError, copy_overlap, load_world_portraits, parse_portrait
from .repetition import WINDOW as REPETITION_WINDOW, measure_turn, sentences
from .profile import WorldProfile, distance, profile_of_lines
from .settings import (
    DEFAULT_DIALOGUE, DEFAULT_NARRATION, DEFAULT_OUTPUT_LANGUAGE, DEFAULT_RECORD_LANGUAGE,
    FAST_ROLES, FAST_TIMEOUT_S, MAX_EXCHANGE_LINES, MAX_SPEAKERS, NPC_REJECT_P,
)
from .shape import (SPEECH_SHAPES, Shape, beat_wanted, fit_to_shape, sample_shape, shape_prior,
                    shape_weights, word_bounds)
from . import items
from .state import LiveState, StateChange, check_change, payload as change_payload
from .streaming import InterruptHandle, StreamResult, run_stream
from .style import (Style, beat_as_action, cut_foreign, foreign_runs, foreign_voice,
                    manner_messages, parse_manner, split_npc_output, tidy_speaker)

ATTITUDE_MIN_NOTABILITY = 0.6  # only notable facts get attitude judgments (cost control)
FALLBACK_LINE = "I don't know what to tell you."  # no longer shown: the least suspicious candidate is
UNKNOWN_CLAIM_Q = (
    "Does the line assert a fact about the world or other people that this "
    "character had no channel to learn from what they know? Ignore greetings, "
    "questions, opinions and general common sense.")

_OBSERVED = {  # how an observer sees a newly observable element
    "injury": "{who} is visibly injured: {item}",
    "clothing": "{who} is wearing {item}",
    "inventory": "{who} is carrying {item}",
    "equipment": "{who} has {item} in hand or at the belt",
    "internal": "{who} visibly shows {item}",
    "appearance": "{who} has {item}",
}


@dataclass
class Challenge:
    """The answer to "how does he know that?". verdict: "channel" (the character could know it:
    `public` says how in a few words, `detail` is the full event), "no_channel" (the line was
    regenerated if it was the last one: `regenerated`, `text`, `new_event`) or "unavailable" (no
    judge answered; nothing changed)."""
    verdict: str
    npc: str = ""
    event: int = 0
    public: str = ""
    detail: str = ""
    regenerated: bool = False
    text: str = ""
    new_event: int | None = None
    withdrawn: bool = False  # the line was removed and nothing replaced it (the NPC says nothing)


class InterruptionError(RuntimeError):
    """A retroactive interrupt outside the allowed window."""


class ExtractionRejected(RuntimeError):
    """The extractor never produced a valid diff; the turn was rolled back."""


MAX_PORTRAITS_PER_SETTLE = 2  # short portraits made per slow lane; the rest wait for the next


@dataclass(frozen=True)
class ModelConfig:
    narrator: str = "narrator"
    npc: str = "npc"
    extractor: str = "extractor"
    judge: str = "judge"  # LLM used for judge escalation (read by whoever builds the judge)
    # Used when a call to the primary model fails after retries (None: no fallback).
    narrator_fallback: str | None = None
    npc_fallback: str | None = None
    extractor_fallback: str | None = None
    judge_fallback: str | None = None
    assistant: str = "assistant"  # the turn assistant's suggestions (harness/assistant.py)
    assistant_fallback: str | None = None

    @classmethod
    def live(cls) -> "ModelConfig":
        """The models chosen by the task 7 bake-off, each with a fallback from another vendor."""
        return cls(DEFAULT_NARRATOR, DEFAULT_NPC, DEFAULT_EXTRACTOR, DEFAULT_JUDGE_LLM,
                   FALLBACKS["narrator"], FALLBACKS["npc"], FALLBACKS["extractor"],
                   FALLBACKS["judge_llm"], assistant=DEFAULT_NPC,
                   assistant_fallback=FALLBACKS["npc"])


class _Timeout(RuntimeError):
    """A fast-lane call did not answer within `Engine.fast_timeout`."""


@dataclass
class _Captured:
    """What a worker thread produced; merged into the engine's logs by the main thread."""
    value: Any = None
    error: Exception | None = None
    notes: list[dict[str, Any]] = field(default_factory=list)
    judgments: list[dict[str, Any]] = field(default_factory=list)


@dataclass
class _NpcPrep:
    """Everything an NPC chain needs, read from the database on the main thread."""
    npc: str
    mem: CharacterMemory
    view: NpcView
    known_names: frozenset[str] = frozenset()  # snapshot of the names this NPC knows
    player_known: frozenset[str] = frozenset()  # and the player character's
    instruction: str | None = None  # the closing instruction with a response shape (living mode)

    def messages(self, heard: Sequence[str] = (),
                 notes: Sequence[str] = ()) -> list[dict[str, str]]:
        return self.view.messages(heard, notes, self.instruction)

    def check_prefix(self, heard: Sequence[str] = ()) -> str:
        return self.view.check_prefix(heard)  # judge state up to "Line: "


@dataclass
class _Launch:
    out: NarratorOutput
    events: list[Event]  # narration + action events, in order
    sources: dict[str, Event]
    segments: list[tuple[str, str]]
    speakers: list[str]
    speech: Future[_Captured] | None = None
    heard: dict[str, list[str]] = field(default_factory=dict)
    chains: dict[str, tuple[_NpcPrep, Future[_Captured]]] = field(default_factory=dict)
    # living mode: what the exchange director reads, fixed before the narration is written
    director: list[str] = field(default_factory=list)
    npcs: dict[str, str] = field(default_factory=dict)
    first: Future[_Captured] | None = None  # the first step, asked in a worker (parallel mode)
    # the first step, already answered (no narration): (floor, shape, the decider's shape dist)
    first_step: tuple[str, Shape, dict[Shape, float]] | None = None


@dataclass
class _Job:
    """A judge question set whose network call can run in a worker; applied on the main thread."""
    ask: Callable[[], Any]
    meta: dict[str, Any] = field(default_factory=dict)


@dataclass
class _Slow:
    """The slow lane of one turn (task 19): extraction and everything derived from it. The
    network call (`raw`) may already run in a worker; every write happens in `Engine.settle`, in
    a fixed order, on one thread at a time."""
    segments: list[tuple[str, str]]
    sources: dict[str, Event]
    outcomes: list[Outcome]
    turn_events: list[Event]
    result: "TurnResult"
    player_event: Event
    time: int  # the scene time the turn's facts carry
    messages: list[dict[str, str]]
    raw: Future[_Captured] | None = None
    fast_s: float = 0.0
    marks: tuple[int, int, int] = (0, 0, 0)  # judgments, provider calls, devlog at turn start


@dataclass
class TurnResult:
    narration: str
    utterances: list[Event] = field(default_factory=list)
    fact_ids: list[int] = field(default_factory=list)
    interrupted: bool = False
    actions: list[str] = field(default_factory=list)
    repetition: dict[str, Any] = field(default_factory=dict)  # see harness/repetition.py
    names: dict[str, Any] = field(default_factory=dict)  # glossary report of the turn
    style: dict[str, Any] = field(default_factory=dict)  # prose-quality hits (harness/stylehits.py)
    decisions: DecisionCount | None = None  # set when the slow lane settles (harness/decisions.py)
    # why the NPCs stopped talking: "player_addressed", "nobody", "cap" or "interrupted" (living
    # mode); classic mode sets only "interrupted"
    stop_reason: str = ""
    # living mode: the NPC the director found the player's input addressed to ("" if none)
    addressee: str = ""
    # living mode, in order: ("line", npc, delivered text), ("gesture", npc, the action as the
    # player sees it) or ("silence", npc, "")
    exchange: list[tuple[str, str, str]] = field(default_factory=list)


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
        parallel: bool | None = None,
        npc_reject_p: float = NPC_REJECT_P,
        fast_timeout: float | None = FAST_TIMEOUT_S,
        output_language: str | None = DEFAULT_OUTPUT_LANGUAGE,
        record_language: str | None = DEFAULT_RECORD_LANGUAGE,
        narration: str = DEFAULT_NARRATION,
        glossary: Glossary | None = None,
        max_speakers: int = MAX_SPEAKERS,
        hear_each_other: bool = True,
        style: Style | None = None,
        player_unlimited: bool = False,
        outcomes: bool = False,
        item_ids: bool = False,
        seed: int | str = 0,
        dialogue: str = DEFAULT_DIALOGUE,
        world_profile: WorldProfile | None = None,
        world: str | None = None,
        rung_seeds: dict[str, str] | None = None,
    ) -> None:
        """`player_unlimited` (task 17): the player's declared acts happen as declared; the
        narrator and the extractor must not soften them. `parallel`: run the independent calls of a turn concurrently. None (default): only if
        the provider says it is thread-safe (`parallel_ok`); fake providers are not, so tests
        stay deterministic. `outcomes` (task 19): the world judges whether the player's attempt
        works before the narrator writes (harness/outcome.py); `player_unlimited` is the campaign
        flag `player_unbounded` (the player's own acts always happen, only reactions are judged).
        `npc_reject_p`: an NPC line is rejected at suspicion >= this.
        `fast_timeout`: seconds a narrator or NPC call may take before it is retried once on the
        role's fallback model (the same model when there is none); None: no limit.
        `output_language`: language of narration and NPC speech (player-facing).
        `record_language`: language the extractor writes records in (None: the model's choice).
        `narration`: "prose" (narrator returns free text; speakers and observable actions come
        from the scene director, harness/director.py) or "json" (the task 3 contract).
        `glossary`: canonical names, applied to records, to model output and to every context.
        `max_speakers`: the director names at most this many NPCs per turn.
        `hear_each_other`: an NPC speaking after another in the same turn gets the earlier line in
        its context (False: all NPC lines are generated at once, as in task 9; kept to measure the
        latency cost).
        `style`: Sapkowski-style prompts and exemplars (harness/style.py). With it an NPC line may
        carry the NPC's own beats ("— ..., — озирнувся Горст. — ..."): the line is stored whole, its
        spoken part in `payload['speech']`, and each beat as an observable action of that NPC; a
        profile without manner notes gets them from a cheap model once.
        `dialogue` (living dialogue, task LD-4): "living" (default): in prose mode, when the turn
        does not fix `speakers`, the scene director picks one step at a time who takes the floor
        next and the shape of that response, and NPCs may answer each other, until the player is
        addressed, nobody speaks, `MAX_EXCHANGE_LINES` steps, or an interrupt. "classic": the
        task 12 director (a first speaker and who also speaks, at most `max_speakers`). Explicit
        `speakers` and the json narrator's list are spoken as given in both modes.
        `world_profile`: the world's dialogue numbers (harness/profile.py); the shapes' word
        bounds follow its length bins.
        `world`: the world folder (`worlds/<world>`) whose character portraits NPCs may play
        (harness/portrait.py; `bind_portrait`). `rung_seeds`: each NPC's starting rung toward the
        player (stored with the campaign settings)."""
        if narration not in ("prose", "json"):
            raise ValueError(f"narration must be 'prose' or 'json', not {narration!r}")
        if dialogue not in ("living", "classic"):
            raise ValueError(f"dialogue must be 'living' or 'classic', not {dialogue!r}")
        self.dialogue, self.world_profile = dialogue, world_profile
        self.shape_prior = shape_prior(world_profile)  # "" without a profile
        self.session_lines: list[str] = []  # the NPCs' delivered lines, for the dialogue report
        self._draws = 0  # code draws of shapes and beats (main thread), for a seeded rng
        self.conn = conn or connect()
        self._owns_conn = conn is None
        self.provider, self.models, self.scene = provider, models, scene
        self.campaign_dir = Path(campaign_dir) if campaign_dir else None
        self.judgments = JudgmentLog(self.campaign_dir / "judgments.jsonl" if self.campaign_dir
                                     else None)
        self.judge: Judge = LoggingJudge(judge or default_fake_judge(), self.judgments)
        self.updater = updater or StubOffscreenUpdater()
        self.minutes_per_turn, self.extract_retries, self.pace = (
            minutes_per_turn, extract_retries, pace)
        self.narrate_retries, self.check_retries = narrate_retries, check_retries
        self.parallel = bool(getattr(provider, "parallel_ok", False)) if parallel is None else parallel
        self.npc_reject_p = npc_reject_p
        self.fast_timeout = fast_timeout
        self.output_language, self.record_language = output_language, record_language
        self.narration, self.glossary, self.max_speakers = narration, glossary, max_speakers
        self.hear_each_other = hear_each_other
        self.style = style
        self.outcomes_on = outcomes
        self.seed = seed  # makes non-canon NPCs reproducible (harness/npcgen.py)
        self.vitals = VitalsBook()
        self.outcome_judge = OutcomeJudge(self)
        self.canon_guard: Any = None   # harness.canon.play.CanonGuard: narrated output that contradicts canon is regenerated
        # harness.scene_cast.SceneCast: people the narration brings in are admitted or the
        # narration is regenerated (living dialogue task 9); None: not checked
        self.scene_cast: Any = None
        self._admitted: list[tuple[Event, bool, bool]] = []  # this turn: (entry, new profile, was outside)
        self._fixes: list[dict[str, str]] = []  # glossary replacements of the running turn
        self._fixes_lock = threading.Lock()
        self._tl = threading.local()
        self._slow: _Slow | None = None  # the slow lane of the last turn, not yet applied
        self._last_prep: dict[str, _NpcPrep] = {}  # per NPC: the context read last (leaks)
        self._slow_lock = threading.RLock()
        self.slow_failure: BaseException | None = None
        self.after_settle: list[Callable[[], None]] = []  # run after the slow lane (the world)
        self.assistant_calls: list[str] = []  # turn assistant calls: never inside a turn's counts
        self.llm_calls: list[str] = []  # role of every model call attempt (harness/decisions.py)
        self.last_decisions: DecisionCount | None = None  # of the last settled turn, failed or not
        self.lane_stats: list[dict[str, Any]] = []  # per turn: fast, slow and wait seconds
        self._pool: ThreadPoolExecutor | None = None
        self.devlog: list[dict[str, Any]] = []  # engine-side events for the debug view
        self.reports: list[dict[str, Any]] = []  # per turn: repetition and name reports
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
        self.names = Names(self.log, self.profiles, glossary)
        self.ctx = ContextBuilder(self.log, self.facts, self.intents, self.profiles, self.live,
                                  self.deriver, language=output_language,
                                  record_language=record_language, glossary=glossary,
                                  narration=narration, names=self.names, style=style,
                                  player_unlimited=player_unlimited)
        self.ctx.outcomes = outcomes
        self.ctx.item_ids = item_ids  # the extractor prompt shows item ids and locations
        self.world = world
        self._short_portraits: dict[str, dict | None] = {}  # npc -> generated portrait (None: failed)
        try:  # a broken portrait file must not stop a campaign from opening
            self.ctx.portraits = load_world_portraits(world) if world else {}
        except (OSError, PortraitError) as e:
            self.ctx.portraits = {}
            self._note("portraits_failed", world=world, error=str(e)[:300])
        self.ctx.rung_seeds.update(rung_seeds or {})  # in place: Relations shares the dict
        self.memory = (MemoryWriter(self.campaign_dir / "memory", self.deriver, self.log,
                                    self.profiles, self.agents) if self.campaign_dir else None)
        self._save_scene()

    # -- helpers --------------------------------------------------------
    @property
    def ended(self) -> bool:
        """The player character is dead: the campaign is read-only."""
        return bool(self.log.active([CHARACTER_DEATH]))

    def _scene_header_omniscient(self) -> str:
        return self.ctx._scene_header(self.scene)

    def _note(self, kind: str, **info: Any) -> None:
        buf = getattr(self._tl, "notes", None)  # a worker collects its notes; the main thread merges
        (self.devlog if buf is None else buf).append({"kind": kind, **info})

    # -- model calls, workers -------------------------------------------
    def _call(self, role: str, model: str, messages: list[dict[str, str]]) -> str:
        """`provider.complete`; for a fast-lane role (narrator, NPC) not longer than
        `fast_timeout`. A call that is out of time is abandoned (its late answer is dropped) and
        raises `_Timeout`."""
        if self.fast_timeout is None or role not in FAST_ROLES:
            return self.provider.complete(model, messages)
        box: dict[str, Any] = {}
        done = threading.Event()

        def run() -> None:
            try:
                box["out"] = self.provider.complete(model, messages)
            except BaseException as e:  # noqa: BLE001 - re-raised in the caller's thread
                box["err"] = e
            finally:
                done.set()

        threading.Thread(target=run, daemon=True).start()
        if not done.wait(self.fast_timeout):
            raise _Timeout(f"{model}: no answer in {self.fast_timeout:g} s")
        if "err" in box:
            raise box["err"]
        return box["out"]

    def _complete(self, role: str, messages: list[dict[str, str]]) -> str:
        """One model call for `role`; if it fails after retries, or a fast-lane call is out of
        time (note `model_timeout`), the role's fallback model (the same model once more when
        there is none)."""
        model = getattr(self.models, role)
        fallback = getattr(self.models, role + "_fallback", None)
        self.llm_calls.append(role)  # counted here, so any provider is counted
        try:
            return self._call(role, model, messages)
        except _Timeout as e:
            retry = fallback or model
            self._note("model_timeout", role=role, model=model, seconds=self.fast_timeout,
                       retry_on=retry, error=str(e))
            self.llm_calls.append(role)
            try:
                return self._call(role, retry, messages)
            except _Timeout as e2:
                raise ProviderError(f"{retry}: timed out twice ({e2})") from e2
        except ProviderError as e:
            if not fallback:
                raise
            self._note("model_fallback", role=role, model=model, fallback=fallback, error=str(e))
            self.llm_calls.append(role)
            return self._call(role, fallback, messages)

    def _complete_text(self, role: str, messages: list[dict[str, str]]) -> str:
        """A creative call (narrator, NPC) whose output must stay in the output language's
        script: letters of another script (a stray "天天爱彩票") make it ask once more; if the
        second answer has them too, the foreign runs are cut."""
        text = self._complete(role, messages)
        runs = foreign_runs(text, self.output_language)
        if not runs:
            return text
        self._note("script_regenerated", role=role, runs=runs)
        text = self._complete(role, messages)
        runs = foreign_runs(text, self.output_language)
        if runs:
            self._note("script_cut", role=role, runs=runs)
            text = cut_foreign(text, self.output_language)
        return text

    def _run_captured(self, fn: Callable[..., Any], *args: Any) -> _Captured:
        """Run in a worker: notes and judgments go to private buffers, not to the shared logs."""
        cap = _Captured()
        with self.judgments.capture() as jb:
            self._tl.notes = cap.notes
            try:
                cap.value = fn(*args)
            except Exception as e:  # noqa: BLE001 - re-raised on the main thread by _take
                cap.error = e
            finally:
                self._tl.notes = None
        cap.judgments = jb
        return cap

    def _submit(self, fn: Callable[..., Any], *args: Any) -> Future[_Captured]:
        if self._pool is None:
            self._pool = ThreadPoolExecutor(max_workers=8, thread_name_prefix="harness")
        return self._pool.submit(self._run_captured, fn, *args)

    def _take(self, fut: Future[_Captured]) -> Any:
        """Wait for a worker; merge its notes and judgments (call in a fixed order)."""
        cap = fut.result()
        self.devlog.extend(cap.notes)
        self.judgments.extend(cap.judgments)
        if cap.error is not None:
            raise cap.error
        return cap.value

    def _map(self, fns: Sequence[Callable[[], Any]]) -> list[Any]:
        """Run network-only functions (concurrently when allowed); results in input order."""
        if not self.parallel or len(fns) < 2:
            return [fn() for fn in fns]
        futs = [self._submit(fn) for fn in fns]
        return [self._take(f) for f in futs]

    def close(self) -> None:
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None
        if self._owns_conn:
            self.conn.close()

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
        self._save_scene()

    def rollback(self, event_id: int, reason: str = "rollback") -> list[int]:
        done = self.log.rollback(event_id, reason)
        self.refresh_memory()
        return done

    @property
    def _name_words(self) -> list[str]:
        """Every word of every character's name, and each whole description (a beat shown to a
        player who does not know the name says «жінка в темній хустці ...»; its first word alone
        is not a name), for `split_npc_output(names=...)`: a piece between dashes that names a
        character is a beat, not speech."""
        out = {w for p in self.profiles.values() for w in re.findall(r"[\w'’]+", p.name)
               if len(w) > 2 and w[0].isupper()}
        out |= {p.appearance.strip() for p in self.profiles.values() if p.appearance.strip()}
        return sorted(out)

    @property
    def _npc_names(self) -> list[str]:
        return [p.name for c, p in self.profiles.items() if c != PLAYER] + [
            c for c in self.profiles if c != PLAYER]

    # -- names ----------------------------------------------------------
    def _fix_names(self, text: str, where: str) -> str:
        """The text with every known name variant replaced by its canonical form (glossary).
        Thread-safe; what was replaced is reported at the end of the turn."""
        g = self.glossary
        if g is None or not text:
            return text
        new, found = g.fix(text)
        if found:
            with self._fixes_lock:
                self._fixes.extend({"where": where, "canonical": f.canonical, "form": f.form}
                                   for f in found)
        return new

    def _fix_tree(self, node: Any) -> Any:
        """The glossary over every string value of a parsed JSON diff (not the keys)."""
        if isinstance(node, str):
            return self._fix_names(node, "record")
        if isinstance(node, list):
            return [self._fix_tree(x) for x in node]
        if isinstance(node, dict):
            return {k: self._fix_tree(v) for k, v in node.items()}
        return node

    def _ids_for_names(self, data: Any) -> Any:
        """The extractor sometimes answers with a character's display name where an id is
        required (a "source" or "character" field); map the name back to the id. A source may
        carry a line suffix: «Горст~2» (the display name plus ~N) is the segment `horst~2`."""
        by_name = {p.name.lower(): c for c, p in self.profiles.items()}
        if isinstance(data, dict):
            for key in ("new_facts", "state_changes"):
                for item in data.get(key) or []:
                    if isinstance(item, dict):
                        for f in ("source", "character"):
                            v = item.get(f)
                            if not isinstance(v, str) or v in self.profiles:
                                continue
                            base, sep, n = v.strip().partition("~")
                            if f == "source" and sep and n.strip().isdigit():
                                cid = by_name.get(base.strip().lower())
                                if cid is not None:
                                    item[f] = f"{cid}~{n.strip()}"
                                continue
                            item[f] = by_name.get(v.strip().lower(), v)
        return data

    # -- narrator -------------------------------------------------------
    def _speech_judged(self, text: str) -> bool:
        """The judge's verdict on narrator speech (network only; safe in a worker)."""
        # every output is judged: speech also hides in paraphrase ("he tells of the old mill, how...")
        try:
            return bool(self.judge.yes_no(
                "Does the text state what a character other than the player character says "
                "aloud, either quoted or paraphrased with its content? (Mere mention that "
                "someone speaks, with no content, does not count.)",
                f"Player character: {self.ctx.name(PLAYER)}\nText: {text}",
                tag="narrator_speech").answer)
        except JudgeError as e:
            self._note("narrator_speech_check_failed", error=str(e))
            return has_quotes(text)  # no verdict: quotes are treated as speech

    def _narrator_speech(self, out: NarratorOutput) -> bool:
        text = "\n".join(out.texts())
        if has_speaker_line(text, self._npc_names):
            return True
        return self._speech_judged(text)

    @staticmethod
    def _prose_of(raw: str) -> str:
        """The narrator's free text. Tolerates a code fence, and a model that answers with the old
        JSON object anyway (its description is taken)."""
        text = raw.strip()
        m = re.match(r"^```(?:\w+)?\s*(.*?)\s*```$", text, re.DOTALL)
        if m:
            text = m.group(1).strip()
        if text.startswith("{"):
            try:
                d = json.loads(text)
                if isinstance(d, dict) and isinstance(d.get("description"), str):
                    return d["description"].strip()
            except json.JSONDecodeError:
                pass
        return text

    def _narrate(self, player_text: str,
                 on_candidate: Callable[[NarratorOutput], bool] | None = None,
                 outcome: Outcome | None = None) -> NarratorOutput:
        """Narrator output (free prose, or the task 3 JSON). NPC speech is rejected and
        regenerated (at most `narrate_retries` times); after that the speech is stripped and
        logged. `on_candidate(out)` replaces the judge check: it gets a candidate that passed the
        code heuristics and returns True to accept it (the parallel turn starts the director and
        the NPC chains there, concurrently with the check). In prose mode the returned output has
        no actions or speakers yet: the scene director fills them in."""
        sc = self.scene
        raw, parsed = "", None
        notes: list[str] = []  # why earlier drafts were rejected, when the narrator can fix it
        # the cast review's last draft that passed it, and the last one that drifted (task LD-9)
        cast: dict[str, tuple[NarratorOutput, Any]] = {}
        for attempt in range(self.narrate_retries + 1):
            admitted: list[tuple[Event, bool, bool]] = []
            raw = self._complete_text("narrator", self._with_notes(self.ctx.narrator(
                sc, player_text, outcome.for_narrator() if outcome else None), notes)).strip()
            if self.narration == "prose":
                text = self._prose_of(raw)
                if not text:
                    self._note("narrator_malformed", attempt=attempt, error="empty narration")
                    continue
                out = NarratorOutput(self._fix_names(text, "narration"))
            else:
                try:
                    out = parse_narration(raw)
                except NarrationError as e:
                    self._note("narrator_malformed", attempt=attempt, error=str(e))
                    continue
                out = NarratorOutput(self._fix_names(out.description, "narration"),
                                     [self._fix_names(a, "action") for a in out.actions],
                                     out.speakers)
            parsed = out
            out.description, said = strip_player_quotes(out.description, player_text)
            for q in said:
                self._note("narrator_player_action_dropped", why="player_quote", attempt=attempt,
                           sentence=q)
            acts_fut = self._start_player_act_check(out.description, player_text)
            leaked = self.names.unknown_mentioned(PLAYER, "\n".join(out.texts()))
            if leaked:  # the player character has not learned this name: describe, do not name
                self._note("narrator_unknown_name", attempt=attempt,
                           names=[self.names.real(c) for c in leaked])
                ok = False
            elif (has_speaker_line("\n".join(out.texts()), self._npc_names)
                    or has_dash_speech(out.description)):
                ok = False
            elif self.canon_guard is not None and (
                    why := self.canon_guard.check("\n".join(out.texts()), "narration")) is not None:
                self._note("canon_drift_rejected", attempt=attempt, why=why, text=out.description)
                ok = False
            elif self.scene_cast is not None and (
                    why := self._cast_review(out, admitted, attempt, cast)) is not None:
                notes.append(why)
                ok = False
            elif self._apply_player_act_check(out, acts_fut, attempt):  # nothing left after drops
                notes.append("Do not decide what the player character does or says.")
                ok = False
            elif on_candidate is not None:
                ok = on_candidate(self._valid_speakers(out))
            else:
                ok = not self._speech_judged("\n".join(out.texts()))
            if ok:
                return self._valid_speakers(out)
            self._unadmit(admitted)
            self._note("narrator_speech_rejected", attempt=attempt, text=out.description)
        names = self._npc_names
        late: tuple[NarratorOutput, Any] | None = None  # people to admit into the delivered draft
        if "ok" in cast:  # never deliver a person who cannot be here: the last draft that passed
            parsed, late = cast["ok"][0], cast["ok"]
        elif "drift" in cast:  # every reviewed draft drifted: remove the people, keep the rest
            parsed, late = self._remove_absent(*cast["drift"]), cast["drift"]
        if parsed is None:
            parsed = NarratorOutput(self._fix_names(self._prose_of(raw), "narration"))
        mask = lambda t: self.names.mask(PLAYER, t)  # noqa: E731 - last resort: no unknown name
        stripped = NarratorOutput(
            mask(strip_speech(parsed.description, names)),
            [a for a in (strip_speech(a, names) for a in parsed.actions) if a],
            parsed.speakers,
        )
        if not stripped.description:
            stripped.description = "..."
        self._note("narrator_speech_stripped", before=parsed.description,
                   after=stripped.description)
        if late is not None:
            self._cast_admit(stripped, late[1], [], -1)
        return self._valid_speakers(stripped)

    def _player_act_verdicts(self, sentences: list[str], player_text: str) -> list[bool]:
        """One batched judge call: does each sentence decide something for the player character
        that the player did not write? No verdict (judge down): the sentence is kept."""
        try:
            got = self.judge.ask(
                [f"Player character: {self.ctx.name(PLAYER)}", f"The player wrote: {player_text}"],
                {f"s{i}": yes_no_q(PLAYER_ACT_Q.format(sentence=s), "player_act")
                 for i, s in enumerate(sentences)})
            return [bool(got[f"s{i}"].answer) for i in range(len(sentences))]
        except JudgeError as e:
            self._note("player_act_check_failed", error=str(e))
            return [False] * len(sentences)

    def _start_player_act_check(self, text: str, player_text: str
                                ) -> tuple[list[str], list[int], Any] | None:
        """Flag the sentences about the player character's own acts (code) and start the judge
        check next to the other narrator checks (a worker in parallel mode). None: nothing is
        flagged, no call."""
        sents = split_sentences(text)
        idx = flag_player_acts(sents, self.ctx.name(PLAYER))
        if not idx:
            return None
        flagged = [sents[i] for i in idx]
        if self.parallel:
            return sents, idx, self._submit(self._player_act_verdicts, flagged, player_text)
        return sents, idx, self._player_act_verdicts(flagged, player_text)

    def _apply_player_act_check(self, out: NarratorOutput,
                                check: tuple[list[str], list[int], Any] | None,
                                attempt: int) -> bool:
        """Drop the confirmed sentences from the description. True when nothing is left."""
        if check is None:
            return False
        sents, idx, res = check
        verdicts = self._take(res) if isinstance(res, Future) else res
        drop = {i for i, v in zip(idx, verdicts) if v}
        for i in sorted(drop):
            self._note("narrator_player_action_dropped", why="player_act", attempt=attempt,
                       sentence=sents[i].strip())
        if drop:
            out.description = "".join(s for i, s in enumerate(sents) if i not in drop).strip()
        return bool(drop) and not out.description

    def _guard_player_prose(self, text: str, player_text: str) -> str:
        """The same checks for a short paragraph written outside `_narrate` (resolution)."""
        text, said = strip_player_quotes(text, player_text)
        for q in said:
            self._note("narrator_player_action_dropped", why="player_quote", sentence=q)
        out = NarratorOutput(text)
        self._apply_player_act_check(out, self._start_player_act_check(text, player_text), -1)
        return out.description

    @staticmethod
    def _with_notes(messages: list[dict[str, str]], notes: Sequence[str]
                    ) -> list[dict[str, str]]:
        """The narrator's messages with the reasons earlier drafts were rejected, at the end."""
        if not notes or not messages:
            return messages
        last = messages[-1]
        return [*messages[:-1], {**last, "content": last["content"] + "\n\nNote on your earlier "
                                 "draft: " + " ".join(dict.fromkeys(notes))}]

    def _cast_review(self, out: NarratorOutput, admitted: list[tuple[Event, bool, bool]],
                     attempt: int, cast: dict[str, tuple[NarratorOutput, Any]]) -> str | None:
        """People the narration shows present who are not in the scene (main thread). A person
        who cannot be here (canon calendar, the world, a plausibility judgment) makes the draft
        drift: the reason is returned and the narrator writes again with it. Everyone else enters
        the scene now (`_cast_admit`). `admitted` collects the entries, undone if the draft is
        rejected later. `cast` keeps the last draft that passed ("ok") and the last that drifted
        ("drift"), with their reviews, for the case that every draft is rejected."""
        rv = self.scene_cast.review(self, "\n".join(out.texts()))
        draft = NarratorOutput(out.description, list(out.actions), list(out.speakers))
        if rv.reject is not None:
            cast["drift"] = (draft, rv)
            self._note("narrator_absent_character", attempt=attempt, people=rv.people,
                       absent=rv.absent, why=rv.reject, text=out.description)
            return rv.reject
        cast["ok"] = (draft, rv)
        self._cast_admit(out, rv, admitted, attempt)
        return None

    def _cast_admit(self, out: NarratorOutput, rv: Any, admitted: list[tuple[Event, bool, bool]],
                    attempt: int) -> None:
        """The people a review admits enter the scene (`enter_scene`, a profile from canon or
        npcgen), so they can speak and the director can pick them; a name the player character
        has not learned is replaced by how the person looks."""
        for adm in rv.admit:
            before = set(self.profiles)
            cid = self.scene_cast.character_for(self, adm)
            if cid in self.scene.present:
                continue
            outside = cid in self.scene.outside
            ev = self.enter_scene(cid)
            # only a generated passer-by's profile is dropped on undo; a canon profile stays
            # made (harness/canon/play.py keeps it), as for any canon person of the campaign
            entry = (ev, adm.kind == "passer_by" and cid not in before, outside)
            admitted.append(entry)
            self._admitted.append(entry)
            self._note("character_admitted", attempt=attempt, character=cid, how=adm.kind,
                       mention=adm.mention)
        if admitted:  # names stay knowledge: a newcomer is shown by appearance
            out.description = self.names.mask(PLAYER, out.description)
            out.actions = [self.names.mask(PLAYER, a) for a in out.actions]

    def _remove_absent(self, draft: NarratorOutput, rv: Any) -> NarratorOutput:
        """Last resort after every draft drifted: the sentences that put the absent people here
        are removed in code."""
        from .scene_cast import remove_people

        desc, removed = remove_people(draft.description, rv.absent)
        acts = [a for a in (remove_people(a, rv.absent)[0] for a in draft.actions) if a]
        self._note("narrator_absent_character_removed", absent=rv.absent, removed=removed,
                   before=draft.description, after=desc)
        return NarratorOutput(desc, acts, list(draft.speakers))

    def _unadmit(self, admitted: list[tuple[Event, bool, bool]]) -> None:
        """Undo admissions of a rejected draft (or a failed turn): the entry and what it caused
        are rolled back, the person leaves the scene, a passer-by made for the draft is dropped."""
        for ev, created, outside in reversed(admitted):
            cid = ev.payload["character"]
            self.log.rollback(ev.id, "narration rejected")
            self.scene.present = tuple(c for c in self.scene.present if c != cid)
            if outside and cid not in self.scene.outside:
                self.scene.outside = self.scene.outside + (cid,)
            if created:
                self.profiles.pop(cid, None)
                self.vitals.people.pop(cid, None)
            self._admitted = [x for x in self._admitted if x[0].id != ev.id]
            self._note("character_admission_undone", character=cid)
        if admitted:
            if self._owns_conn:
                self._save_setup()
            self.refresh_memory()
        admitted.clear()

    def _valid_speakers(self, out: NarratorOutput) -> NarratorOutput:
        by_name = {p.name.lower(): c for c, p in self.profiles.items()}
        by_name.update({p.appearance.lower(): c for c, p in self.profiles.items()
                        if p.appearance})  # a stranger is listed by what is seen
        ok: list[str] = []
        for s in out.speakers:  # models answer with the display name, or "id (Name)"
            s = re.sub(r"\s*\(.*\)\s*$", "", s).strip()
            cid = s if s in self.profiles else by_name.get(s.lower(), s)
            if cid in self.scene.present and cid != PLAYER and cid not in ok:
                ok.append(cid)
        if ok != out.speakers:
            self._note("narrator_bad_speakers", proposed=out.speakers, kept=ok)
        out.speakers = ok
        return out

    # -- scene director (prose mode) --------------------------------------
    def _fallback_speakers(self, narration: str) -> list[str]:
        """No decider answered: the NPCs the narration mentions, in order of first mention (at
        most `max_speakers`); if it mentions none, the first NPC present. Silence would stall the
        scene, and a wrong guess only costs one line."""
        npcs = [c for c in self.scene.present if c != PLAYER]
        low = narration.lower()
        forms = {c: [self.ctx.name(c).lower(), self.names.label(c).lower()] if self.names.hidden(c)
                 else [self.ctx.name(c).lower()] for c in npcs}
        hit = sorted((min(low.find(f) for f in forms[c] if f in low), c) for c in npcs
                     if any(f in low for f in forms[c]))
        return ([c for _, c in hit] or npcs[:1])[: self.max_speakers]

    def _decide_speakers(self, state: list[str], npcs: dict[str, str], narration: str
                         ) -> list[str]:
        """Who speaks next (network only; safe in a worker)."""
        try:
            return decide_speakers(self.judge, state, npcs, max_speakers=self.max_speakers)
        except JudgeError as e:
            kept = self._fallback_speakers(narration)
            self._note("director_unavailable", error=str(e), fallback=kept)
            return kept

    def _list_actions(self, messages: list[dict[str, str]]) -> list[str]:
        """Observable actions of the narration (network only; safe in a worker)."""
        try:
            raw = self._complete("extractor", messages)
        except ProviderError as e:
            self._note("actions_unavailable", error=str(e))
            return []
        return [a for a in (self._fix_names(x, "action") for x in parse_actions(raw)) if a]

    def _direct_jobs(self, narration: str, player_text: str, speakers: Sequence[str] | None
                     ) -> tuple[Callable[[], list[str]] | None, Callable[[], list[str]]]:
        """Read the database (main thread) and return the two network-only jobs: the speaker
        decider (None when `speakers` overrides it) and the observable-actions lister."""
        sc = self.scene
        msgs = self.ctx.actions(narration, sc)

        def act() -> list[str]:
            return self._list_actions(msgs)

        if speakers is not None:
            return None, act
        npcs = {c: self.ctx.describe(c) for c in sc.present if c != PLAYER}
        state = self.ctx.director_state(sc, player_text, narration)

        def spk() -> list[str]:
            return self._decide_speakers(state, npcs, narration)

        return spk, act

    def direct(self, narration: str, player_text: str,
               speakers: Sequence[str] | None = None) -> tuple[list[str], list[str]]:
        """The scene director for a finished narration: (speakers in order, observable actions).
        `speakers` overrides the decider. Reusable on its own (a live scene calls it on a
        fragment); inside a turn `_launch` runs the same two jobs concurrently."""
        spk, act = self._direct_jobs(narration, player_text, speakers)
        if self.parallel and spk is not None:
            fs, fa = self._submit(spk), self._submit(act)
            return self._take(fs), self._take(fa)
        return (spk() if spk else list(speakers or ())), act()

    # -- NPC lines ------------------------------------------------------
    def _prep_npc(self, npc: str) -> _NpcPrep:
        """Read an NPC's context and the judge's state from the database (main thread only)."""
        self._ensure_manner(npc)
        mem = self.deriver.derive(npc, self.scene.time)
        prep = _NpcPrep(npc, mem, self.ctx.character_view(npc, self.scene, mem),
                        self.names.known_set(npc), self.names.known_set(PLAYER))
        self._last_prep[npc] = prep
        return prep

    def _ensure_manner(self, npc: str) -> None:
        """Manner notes for an NPC profile that has none, once, from a cheap model (main thread
        only). Failure is noted and the NPC simply has no notes; it is not retried every turn."""
        prof = self.profiles.get(npc)
        if self.style is None or prof is None or prof.manner or npc == PLAYER:
            return
        if self.ctx.portrait_of(npc) is not None:  # the portrait carries the voice
            return
        manner = ""
        try:
            manner = parse_manner(self._complete("extractor", manner_messages(prof, self.style)))
        except Exception as e:  # noqa: BLE001 - a style nicety must never break a turn
            self._note("manner_failed", npc=npc, error=str(e))
        self.profiles[npc] = replace(prof, manner=manner or "-")
        if manner:
            self._note("manner_generated", npc=npc, manner=manner)
        if self._owns_conn:
            self._save_setup()

    def _suspicion(self, prep: _NpcPrep, line: str, heard: Sequence[str] = ()) -> float | None:
        """Probability that the line contains a claim the NPC had no channel to learn (network
        only); None when no judge could answer."""
        try:
            j = self.judge.yes_no(UNKNOWN_CLAIM_Q, prep.check_prefix(heard) + line,
                                  tag="unknown_claim")
        except JudgeError as e:
            self._note("npc_check_unavailable", npc=prep.npc, error=str(e))
            return None
        p = j.probabilities.get("yes")
        return float(p) if p is not None else (j.probability if j.answer else 1 - j.probability)

    def _npc_line(self, prep: _NpcPrep, heard: Sequence[str] = (),
                  notes: Sequence[str] = ()) -> str:
        """Generate and output-check one NPC line. A line is rejected at suspicion >=
        `npc_reject_p`; up to `check_retries` regenerations. If every try is rejected, the least
        suspicious candidate is used (and logged) rather than a canned line. `heard`: lines other
        NPCs said earlier in this turn, which this NPC also heard. `notes`: what to fix from the
        start (a reply that was over its shape)."""
        tried: list[tuple[float, str]] = []
        notes = list(notes)
        for _ in range(self.check_retries + 1):
            text = self._fix_names(
                clean_npc_line(self._complete_text("npc", prep.messages(heard, notes))), "npc_line")
            # without a style there is no book form: only a self-prefix is dropped
            tidy = tidy_speaker(text, [self.names.real(prep.npc), self.names.label(prep.npc)],
                                self._name_words, book_form=self.style is not None)
            if tidy != text:
                self._note("speaker_tidied", npc=prep.npc, before=text, after=tidy)
                text = tidy
            why = (foreign_voice(text, self.ctx.name(prep.npc),
                                 [p.name for p in self.profiles.values()])
                   if self.style is not None else None)
            if why is not None:  # the call wrote for somebody else: not shown, no judge needed
                tried.append((1.0, text))
                self._note("npc_line_rejected", npc=prep.npc, text=text, suspicion=1.0, why=why)
                continue
            # a name this character has no channel to: certain leak, no judge needed
            leaked = self.names.unknown_mentioned(prep.npc, text, prep.view.heard_text(heard),
                                                  prep.known_names)
            if leaked:
                tried.append((1.0, text))
                self._note("npc_name_leak", npc=prep.npc, text=text,
                           names=[self.names.real(c) for c in leaked])
                notes = ["You do not know the name of " + ", ".join(
                    self.names.label(c) for c in leaked) + ": do not use it; address "
                    "or refer to them without a name."]
                continue
            if self.canon_guard is not None and (
                    why := self.canon_guard.check(text, "npc_line", prep.npc)) is not None:
                tried.append((1.0, text))
                self._note("canon_drift_rejected", npc=prep.npc, text=text, why=why)
                notes = ["Your line contradicts established canon (" + why[:200] + "). Say something consistent with it."]
                continue
            p = self._suspicion(prep, text, heard)
            if p is None or p < self.npc_reject_p:
                return self._mask_beats(text, prep)
            tried.append((p, text))
            self._note("npc_line_rejected", npc=prep.npc, text=text, suspicion=round(p, 3))
        best_p, best = min(tried, key=lambda c: c[0])  # ties: the earliest
        if self.names.unknown_mentioned(prep.npc, best, prep.view.heard_text(heard),
                                        prep.known_names):
            best = self.names.mask(prep.npc, best, known=prep.known_names)  # last resort: the name never reaches the player
        self._note("npc_lowest_suspicion", npc=prep.npc, text=best, suspicion=round(best_p, 3),
                   rejected=[t for _, t in tried])
        return self._mask_beats(best, prep)

    def _mask_beats(self, text: str, prep: _NpcPrep) -> str:
        """The NPC's own beats ("Горст покрутив мідяк") are shown to the player: a name the player
        character has not learned is replaced there by what is seen. Spoken words stay literal."""
        if self.style is None or not self.names.mentions(text):
            return text
        parsed = split_npc_output(text, self._name_words)
        if not parsed.has_dash:
            return text
        for beat in [*parsed.beats, *parsed.tags]:  # a bare tag ("відказала Ванда") names too
            masked = self.names.mask(PLAYER, beat, known=prep.player_known)
            if masked != beat:
                text = text.replace(beat, masked)
        return text

    def _npc_chain(self, prep: _NpcPrep, earlier: Sequence[tuple[str, Future[_Captured]]]) -> str:
        """A worker: wait for the lines of the NPCs who speak before this one in the turn, then
        generate and check this NPC's line with those lines in its context."""
        heard: list[str] = []
        for npc, fut in earlier:
            cap = fut.result()
            if cap.error is not None:
                raise cap.error
            # no database read in a worker: use the name-registry snapshot taken in `_prep_npc`
            known = npc == prep.npc or not self.names.hidden(npc) or npc in prep.known_names
            who = self.names.real(npc) if known else self.names.label(npc)
            heard.append(f"{who}: {cap.value}")
        return self._npc_line(prep, heard)

    # -- extraction -----------------------------------------------------
    def _extract(self, segments: list[tuple[str, str]], outcomes: Sequence[Outcome] = (), *,
                 messages: list[dict[str, str]] | None = None,
                 first_raw: str | None = None) -> Diff:
        if messages is None:
            messages = self.ctx.extractor(self.scene, segments,
                                          [o.for_narrator() for o in outcomes])
        sources = {k for k, _ in segments}
        sc = self.scene
        everyone = set(self.profiles) | set(sc.present) | set(sc.outside)
        last: Exception | None = None
        for _ in range(self.extract_retries + 1):
            raw, first_raw = (first_raw, None) if first_raw is not None else (
                self._complete("extractor", messages), None)
            try:
                diff = validate_diff(self._ids_for_names(self._fix_tree(parse_diff(raw))),
                                     present=sc.present, sources=sources,
                                     state=self.live.snapshot(), characters=everyone,
                                     texts=dict(segments))
                for d in diff.dropped:
                    self._note("state_change_dropped", **d)
                return diff
            except DiffValidationError as e:
                last = e
        raise ExtractionRejected(str(last))

    @staticmethod
    def _segment_kind(key: str) -> tuple[str, str | None]:
        """(perception kind, speaker) of an extractor segment key."""
        if key.startswith("narration"):  # "narration", "narration~2" (a resolution paragraph)
            return DESCRIPTION, None
        if key.startswith("action") and key[6:].isdigit():
            return ACTION, None
        if key.startswith("paction") or key.startswith("gesture"):  # the player's own action
            return ACTION, None  # (asterisks), or an NPC's gesture-only turn (living mode)
        # "player~2": a further speech part of the player's input; "horst~2": Horst's second
        # line in this turn's exchange
        return SPEECH, key.split("~", 1)[0]  # "player" or an NPC id

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
        pending: list[_Job] = []  # salience questions: asked together, applied in order
        for ch in diff.changes:
            self._apply_change(ch, source_events[ch.source], defer=pending)
        att = self._attitude_jobs(ids)
        answers = self._map([j.ask for j in pending + att])  # one concurrent wave of judge calls
        for job, got in zip(pending, answers):
            self._salience_apply(job, got)
        for job, got in zip(att, answers[len(pending):]):
            self._attitude_apply(job, got)
        return ids

    # -- live state and its perception ---------------------------------
    def _apply_change(self, ch: StateChange, cause: Event, *,
                      defer: list[_Job] | None = None) -> Event:
        before = self.live.snapshot()
        was = before.get(ch.character, {}).get((ch.category, ch.item))
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
        after = self.live.snapshot()
        # observability is derived (a closed container hides its contents), so the new state
        # decides what is perceived: whatever became observable is observed once
        if ch.op in ("add", "reveal", "move", "open"):
            for el in items.newly_observable(before, after, ch.character):
                self._observe(_OBSERVED[el.category].format(who=who, item=el.item), observers, ev,
                              defer=defer)
        elif ch.op == "remove" and was and items.is_observable(was, before):
            self._observe(f"{who} no longer has {ch.item}", observers, ev, defer=defer)
        return ev

    def _observe(self, text: str, observers: Sequence[str], cause: Event, *,
                 defer: list[_Job] | None = None) -> int | None:
        """Every observer perceives `text` (directly); a salience judgment per observer decides
        whether it is surfaced as noteworthy in that NPC's next context. With `defer`, the
        judgment is not asked yet: the job is appended for the caller to run with others."""
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
            state = [f"Observation: {text}", f"Place: {self.scene.location}"]
            job = _Job(lambda: self._ask_safe(state, qs), {"fid": fid, "npcs": npcs, "cause": cause})
            if defer is not None:
                defer.append(job)
            else:
                self._salience_apply(job, job.ask())
        return fid

    def _ask_safe(self, state: list[str], qs: dict[str, Any]) -> Any:
        try:
            return self.judge.ask(state, qs)
        except JudgeError as e:
            return e

    def _salience_apply(self, job: _Job, got: Any) -> None:
        m = job.meta
        if isinstance(got, JudgeError):
            self._note("salience_unavailable", error=str(got))
            verdicts = {o: False for o in m["npcs"]}
        else:
            verdicts = {o: bool(j.answer) for o, j in got.items()}
        for o in m["npcs"]:
            self.notices.add(o, m["fid"], verdicts.get(o, False), self.scene, m["cause"].id)

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
            if items.is_observable(obs, snap):
                self._observe(_OBSERVED[cat].format(who=self.ctx.name(character), item=item),
                              others, ev)
        for other in others:
            for (cat, item), obs in snap.get(other, {}).items():
                if items.is_observable(obs, snap):
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
    def _attitude_jobs(self, fact_ids: Sequence[int]) -> list[_Job]:
        jobs = []
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
            state = [f"Event: {f.content}"]
            jobs.append(_Job(lambda st=state, q=qs: self._ask_safe(st, q),
                             {"fact": f, "npcs": npcs}))
        return jobs

    def _attitude_apply(self, job: _Job, got: Any) -> None:
        f = job.meta["fact"]
        if isinstance(got, JudgeError):
            self._note("attitude_unavailable", fact=f.id, error=str(got))
            return
        for c in job.meta["npcs"]:
            stance = str(got[f"{c}:dir"].answer)
            mag = float(got[f"{c}:mag"].answer)
            if stance != "neutral" and mag > 0:
                self.attitudes.set(c, f.id, stance, round(mag, 2), self.scene,
                                   f.source_event_id)  # type: ignore[arg-type]

    def _assess_attitudes(self, fact_ids: Sequence[int]) -> None:
        jobs = self._attitude_jobs(fact_ids)
        for job, got in zip(jobs, self._map([j.ask for j in jobs])):
            self._attitude_apply(job, got)

    # -- the turn -------------------------------------------------------
    def _launch(self, out: NarratorOutput, player_text: str, speakers: Sequence[str] | None,
                turn_events: list[Event], *, check: bool,
                first_step: tuple[str, Shape, dict[Shape, float]] | None = None) -> _Launch:
        """Prose mode: run the scene director (speakers and observable actions). Write the
        narration and action events, and (parallel mode) start the speech check and one chain per
        speaking NPC, each chain waiting for the lines of the NPCs before it so that it hears them.
        Event writes stay on this thread, in a fixed order.

        Living mode: no speaker list here; what the exchange director reads is taken now (before
        the narration events are written, so it is the same in both modes), and in parallel
        mode its first step runs in a worker next to the speech check and the actions lister.
        `first_step`: no narration this turn (empty `out`): nothing is written for it, and the
        exchange starts from the first step already answered."""
        speech = None
        bare = first_step is not None
        if self.parallel and check:
            speech = self._submit(self._speech_judged, "\n".join(out.texts()))
        living = self._living(speakers)
        director: list[str] = []
        npcs: dict[str, str] = {}
        first: Future[_Captured] | None = None
        if living:
            npcs = {c: self.ctx.describe(c) for c in self.scene.present if c != PLAYER}
            director = self.ctx.director_state(self.scene, player_text, out.description)
            if self.parallel and not bare:
                first = self._submit(self._decide_next, self._exchange_state(director, []),
                                     npcs, out.description, True)
        if self.narration == "prose" and not bare:
            spk, act = self._direct_jobs(out.description, player_text,
                                         [] if living else speakers)
            if self.parallel:
                fs = self._submit(spk) if spk is not None else None
                fa = self._submit(act)
                got = self._take(fs) if fs is not None else None
                out.actions = self._take(fa)
            else:
                got = spk() if spk is not None else None
                out.actions = act()
            if got is not None:
                out.speakers = got
        evs: list[Event] = []
        sources: dict[str, Event] = {}
        segments: list[tuple[str, str]] = []
        if not bare:
            narr_ev = self._event(NARRATION, [], {"text": out.description}, witnesses=[],
                                  notability=0.4)
            evs.append(narr_ev)
            sources["narration"] = narr_ev
            segments.append(("narration", out.description))
        for i, action in enumerate(out.actions, 1):
            ev = self._event(ACTION_EVENT, [], {"text": action}, notability=0.4)
            evs.append(ev)
            sources[f"action{i}"] = ev
            segments.append((f"action{i}", action))
        turn_events.extend(evs)
        order = list(speakers) if speakers is not None else list(out.speakers)
        launch = _Launch(out, evs, sources, segments, [] if living else order)
        launch.speech = speech
        launch.director, launch.npcs, launch.first = director, npcs, first
        launch.first_step = first_step
        if self.parallel:
            earlier: list[tuple[str, Future[_Captured]]] = []
            for npc in order:
                prep = self._prep_npc(npc)
                fut = self._submit(self._npc_chain, prep, list(earlier) if self.hear_each_other else [])
                launch.chains[npc] = (prep, fut)
                earlier.append((npc, fut))
        return launch

    # -- the NPC exchange (living mode) ------------------------------------------------------
    def _living(self, speakers: Sequence[str] | None) -> bool:
        """The director picks each next line (prose narration, no fixed speakers)."""
        return self.dialogue == "living" and self.narration == "prose" and speakers is None

    def _exchange_state(self, director: list[str], lines: Sequence[str]) -> list[str]:
        """What the exchange director reads at a step: the scene and the player's input (taken
        once, before the turn's events), who the player character is to the others, and every
        line of this exchange so far. Main-thread data only, so the log never depends on timing."""
        who = (f"The player character is {self.ctx.describe(PLAYER)}. Someone who does not know "
               "the name addresses them by how they look or what they seem to be.")
        extra = [who] + ([EXCHANGE_HEADER + "\n" + "\n".join(lines)] if lines else [])
        g = self.glossary
        return [*director, *([g.apply(x) for x in extra] if g else extra)]

    def _decide_next(self, state: list[str], npcs: dict[str, str], narration: str,
                     first: bool) -> tuple[str, Shape, dict[Shape, float]]:
        """One exchange step (network only; safe in a worker): (floor, shape, the decider's
        distribution over shapes). No decider: on the first step the fallback speaker (silence
        would stall the scene), later the floor goes back to the player."""
        try:
            return decide_next(self.judge, state, npcs, self.shape_prior,  # type: ignore[return-value]
                               with_dist=True, first=first)
        except JudgeError as e:
            kept = self._fallback_speakers(narration)[:1] if first else []
            self._note("director_unavailable", error=str(e), fallback=kept)
            return (kept[0], Shape.NORMAL, {}) if kept else (NOBODY, Shape.NORMAL, {})

    def _choose_shape(self, npc: str, shape: Shape, dist: dict[Shape, float],
                      step: int, *, speak: bool = False) -> tuple[Shape, bool | None]:
        """Main thread. With a world profile code samples the step's shape from the decider's
        distribution blended with the profile and leaning against the session's gap
        (`shape.shape_weights`), and draws whether a spoken line carries a beat from the
        profile's `no_beat_share` (`shape.beat_wanted`; only with a style, None otherwise).
        Without a profile: the decider's shape, the beat left to the model. `speak`: the first
        step of a turn whose narration was skipped; silence and gesture are left out of the
        draw (a short line instead without a profile), so the turn is never empty."""
        prof = self.world_profile
        if speak:
            dist = {s: p for s, p in dist.items() if s in SPEECH_SHAPES}
            if shape not in SPEECH_SHAPES:
                self._note("first_step_speaks", npc=npc, decider=shape.value)
                shape = Shape.SHORT
            if not sum(dist.values()):
                dist = {shape: 1.0} if dist or prof is not None else {}
        if prof is None or not prof.length_bins or not dist:
            return shape, None
        rng = random.Random(f"{self.seed}|shape|{self._draws}")
        self._draws += 1
        names = self._name_words
        weights = shape_weights(dist, prof, self.session_lines, names)
        chosen = sample_shape(weights, rng)
        beat = (beat_wanted(prof, self.session_lines, rng, names)
                if chosen in SPEECH_SHAPES and self.style is not None else None)
        self._note("shape_sampled", npc=npc, step=step, decider=shape.value, shape=chosen.value,
                   beat=beat, weights={s.value: round(w, 3) for s, w in weights.items()})
        return chosen, beat

    def _scene_starts(self, turn_events: Sequence[Event]) -> bool:
        """The first turn of a scene: nothing was said or done at this place before this turn
        (the events of this turn are left out)."""
        mine = {e.id for e in turn_events}
        before = [e for e in self.log.active([UTTERANCE, ACTION_EVENT, NARRATION])
                  if e.id not in mine]
        return not before or before[-1].location != self.scene.location

    def _without_narration(self, player_text: str, *, keep: bool = False
                           ) -> tuple[str, Shape, dict[Shape, float]] | None:
        """Living mode: is the moment just talk? One batched call (the need for narration and the
        first exchange step, read without any narration). None: narrate as usual (the director
        says so, or is unavailable). Otherwise the first step, and the narrator is not called.
        `keep`: the turn always keeps its narration (the first turn of a scene, or an action the
        player marked): no question is asked, the narrator is called."""
        if keep:
            self._note("narration_kept", why="scene_start_or_action")
            return None
        npcs = {c: self.ctx.describe(c) for c in self.scene.present if c != PLAYER}
        state = self.ctx.director_state(self.scene, player_text, "")
        try:
            need, nxt, shape, dist = decide_first_step(
                self.judge, self._exchange_state(state, []), npcs, self.shape_prior,
                with_dist=True)
        except JudgeError as e:
            self._note("director_unavailable", error=str(e), fallback="narrate")
            return None
        if need or nxt not in npcs:  # an empty turn (nobody, the player, no NPCs): narrate
            return None
        self._note("narration_skipped", first=nxt, shape=shape.value)
        return nxt, shape, dist

    def _narrate_empty(self, player_text: str, turn_events: list[Event],
                       sources: dict[str, Event], segments: list[tuple[str, str]],
                       result: "TurnResult") -> NarratorOutput:
        """Safety net (main thread): the narration was skipped for an exchange that then
        delivered nothing, so the player would see only their own line. One narrator passage is
        written after the exchange (note `empty_exchange_narrated`)."""
        self._note("empty_exchange_narrated")
        out = self._narrate(player_text)
        ev = self._event(NARRATION, [], {"text": out.description}, witnesses=[], notability=0.4)
        turn_events.append(ev)
        sources["narration"] = ev
        segments.append(("narration", out.description))
        result.narration = out.description
        return out

    def _shaped_line(self, prep: _NpcPrep, shape: Shape, bounds: tuple[int, int],
                     beat: bool | None = None) -> str:
        """An NPC line told its shape, output-checked as every line, and fitted to the same
        bounds: far over them it is asked once more, then cut at a sentence boundary. For a
        gesture the result is the action alone ("" when none came back). `beat`: the line is
        told to carry one small action (True) or none (False); a beat written anyway on a
        no-beat line is cut (note `beat_stripped`)."""
        prof = self.profiles.get(prep.npc) or CharacterProfile(prep.npc, prep.npc)
        prep = replace(prep, instruction=self.ctx.npc_instruction(prof, shape, bounds, beat))
        text = self._npc_line(prep)
        names = self._name_words
        fitted, how = fit_to_shape(text, shape, bounds, names=names)
        if how == "regenerate":
            self._note("shape_regenerated", npc=prep.npc, shape=shape.value, text=text)
            fix = (f"Do not speak: write only the one small thing {prof.name} does."
                   if shape is Shape.GESTURE else
                   f"Your last reply was far too long: say at most {bounds[1]} words.")
            text = self._npc_line(prep, notes=[fix])
            fitted, how = fit_to_shape(text, shape, bounds, allow_trim=True, names=names)
            if how == "trimmed":
                self._note("shape_trimmed", npc=prep.npc, shape=shape.value, before=text,
                           after=fitted)
        if beat is False and shape in SPEECH_SHAPES:
            out = split_npc_output(fitted, names)
            if out.has_dash and out.beats and out.speech:
                self._note("beat_stripped", npc=prep.npc, before=fitted, beats=out.beats)
                fitted = "— " + out.speech
        return fitted

    def _exchange(self, launch: _Launch, result: "TurnResult", turn_events: list[Event],
                  sources: dict[str, Event], segments: list[tuple[str, str]],
                  handle: InterruptHandle | None, on_word: Callable[[str, str], None] | None
                  ) -> None:
        """The NPC exchange of one turn. Each step: the director picks the floor and the shape
        (one batched judge call), the NPC's context is read fresh from the log (so it holds every
        line and name learned so far this turn), its line is generated, checked, fitted and
        delivered, and its events are written. Strictly sequential: each step depends on the
        line before it.

        Stops, checked in this order before each step: the player cut in (the handle fired while
        the previous step was being prepared or delivered: nothing more is asked or written), the
        cap. After the director's answer: the player's floor, nobody, or the NPC who took the
        step just before (any step: line, gesture or silence). One NPC never takes two steps in a
        row; it may speak again only after another NPC has taken a step in between. Such a pick
        ends the exchange as "nobody" (note `same_speaker_stopped`): the speaker has had their
        say and the floor goes back to the player."""
        sc, npcs = self.scene, launch.npcs
        lines: list[str] = []  # as the director reads them
        said: dict[str, int] = {}
        gestures = 0
        last: str | None = None  # the NPC of the step just taken
        for step in range(MAX_EXCHANGE_LINES + 1):
            if handle is not None and handle.requested:
                if launch.first is not None and step == 0:
                    launch.first.cancel()
                result.stop_reason, result.interrupted = "interrupted", True
                self._note("exchange_interrupted", steps=step)
                return
            if step == MAX_EXCHANGE_LINES:
                result.stop_reason = "cap"
                self._note("exchange_cap", steps=step)
                return
            if step == 0 and launch.first_step is not None:
                nxt, shape, dist = launch.first_step
            elif step == 0 and launch.first is not None:
                nxt, shape, dist = self._take(launch.first)
            else:
                nxt, shape, dist = self._decide_next(
                    self._exchange_state(launch.director, lines), npcs, launch.out.description,
                    step == 0)
            if step == 0:
                result.addressee = str(getattr(dist, "addressee", "") or "")
            if nxt == PLAYER_FLOOR:
                result.stop_reason = "player_addressed"
                return
            if nxt == NOBODY or nxt not in npcs:
                result.stop_reason = "nobody"
                return
            if nxt == last:
                result.stop_reason = "nobody"
                self._note("same_speaker_stopped", npc=nxt, step=step + 1)
                return
            last = nxt
            answers = step == 0 and getattr(dist, "addressee", "") == nxt
            if answers:
                self._note("addressee_answers", npc=nxt, decider=shape.value)
            shape, beat = self._choose_shape(
                nxt, shape, dist, step + 1,
                speak=answers or (step == 0 and launch.first_step is not None))
            name = self.names.real(nxt)
            if shape is Shape.SILENCE:
                self._note("silence", npc=nxt, step=step + 1)
                result.exchange.append(("silence", nxt, ""))
                lines.append(f"[{name} says nothing]")
                continue
            prep = self._prep_npc(nxt)
            text = self._shaped_line(prep, shape, word_bounds(shape, self.world_profile), beat)
            if shape is Shape.GESTURE:
                if not text:
                    self._note("silence", npc=nxt, step=step + 1, why="no action came back")
                    result.exchange.append(("silence", nxt, ""))
                    lines.append(f"[{name} says nothing]")
                    continue
                for notice, _ in prep.mem.noticed:
                    turn_events.append(self.notices.mark_shown(notice, sc))
                act = self._fix_names(beat_as_action(text, name, [self.names.label(nxt)]),
                                      "npc_beat")
                ev = self._event(ACTION_EVENT, [nxt], {"text": act, "by": nxt, "gesture": True},
                                 notability=0.3)
                turn_events.append(ev)
                self._record_leak(prep.view, ev)
                gestures += 1
                sources[f"gesture{gestures}"] = ev
                segments.append((f"gesture{gestures}", act))
                seen = self.names.mask(PLAYER, act, known=prep.player_known)
                self._note("gesture", npc=nxt, step=step + 1, text=act)
                result.exchange.append(("gesture", nxt, seen))
                lines.append(f"[{name} does] {act}")
                continue
            said[nxt] = said.get(nxt, 0) + 1
            sr = self._deliver(nxt, prep, text, result, turn_events, sources, segments, handle,
                               on_word, key=nxt if said[nxt] == 1 else f"{nxt}~{said[nxt]}")
            result.exchange.append(("line", nxt, sr.spoken_text))
            lines.append(f"{name}: {sr.spoken_text}")
            if sr.interrupted:
                result.stop_reason = "interrupted"
                return

    def _deliver(self, npc: str, prep: _NpcPrep, text: str, result: "TurnResult",
                 turn_events: list[Event], sources: dict[str, Event],
                 segments: list[tuple[str, str]], handle: InterruptHandle | None,
                 on_word: Callable[[str, str], None] | None, *, key: str | None = None
                 ) -> StreamResult:
        """Stream an NPC line to the player and write its events (main thread): the utterance
        (only the delivered words), names learned from it, the NPC's own beats as actions, the
        interruption if the handle fired. `key`: the extractor segment (default: the NPC id)."""
        sc = self.scene
        for notice, _ in prep.mem.noticed:  # surfaced now, so not again next turn
            turn_events.append(self.notices.mark_shown(notice, sc))
        cb = (lambda w, n=npc: on_word(n, w)) if on_word else None
        sr = run_stream(iter([text]), handle, cb, self.pace)
        if sr.spoken_text.strip():
            self.session_lines.append(sr.spoken_text)
        parsed = (split_npc_output(sr.spoken_text, self._name_words) if self.style is not None
                  else None)
        extra: dict[str, object] = (
            {"speech": parsed.speech} if parsed is not None and parsed.has_dash else {})
        ev = self._utterance(npc, sr.spoken_text, interrupted=sr.interrupted, **extra)
        turn_events.append(ev)
        self._record_leak(prep.view, ev)
        result.utterances.append(ev)
        # only what is said aloud teaches a name, never the NPC's own beats
        self._learn_from_speech(
            ev, npc, parsed.speech if parsed is not None and parsed.has_dash
            else sr.spoken_text)
        if parsed is not None:  # the NPC's own beats, only the delivered part
            for beat in parsed.beats:
                act = self._fix_names(beat_as_action(beat, self.ctx.name(npc),
                                                     [self.names.label(npc)]), "npc_beat")
                if act:
                    turn_events.append(self._event(
                        ACTION_EVENT, [npc], {"text": act, "by": npc}, notability=0.3,
                        cause_id=ev.id))
        if prep.view.examples and copy_overlap(sr.spoken_text, prep.view.examples):
            self._note("portrait_copy", npc=npc, line=sr.spoken_text[:300])
        key = key or npc
        sources[key] = ev
        segments.append((key, sr.spoken_text))
        if sr.interrupted:
            turn_events += self._record_interruption(ev, sr)
            result.interrupted = True
        return sr

    def dialogue_report(self) -> dict[str, Any] | None:
        """The session's NPC speech measured like the world profile (debug view): the rolling
        `profile_of_lines` over every delivered line plus, when the world has a profile, its
        `distance` to it on speech metrics only (a session has no narration paragraphs). None
        before the first line."""
        try:
            prof = profile_of_lines(self.session_lines, self._name_words)
        except ValueError:
            return None
        out: dict[str, Any] = prof.to_dict()
        out["distance"] = (distance(prof, self.world_profile, speech_only=True)
                           if self.world_profile is not None else None)
        return out

    def _discard(self, launch: _Launch) -> None:
        """The narration was rejected after the chains had started: forget it all."""
        for ev in launch.events:
            self.log.rollback(ev.id, "narration rejected")
        for _, fut in launch.chains.values():
            fut.cancel()
        if launch.first is not None:
            launch.first.cancel()
        self._note("speculative_chains_discarded", npcs=list(launch.chains))

    def _prior_outputs(self, before_id: int) -> list[tuple[str, str]]:
        """The player-facing outputs (narration, NPC lines) before an event, oldest first."""
        out: list[tuple[str, str]] = []
        for e in self.log.active([NARRATION, UTTERANCE]):
            if e.id >= before_id:
                break
            if e.type == NARRATION:
                out.append(("narration", e.payload["text"]))
            elif e.payload.get("speaker") != PLAYER:
                out.append(("npc", e.payload["text"]))
        return out[-REPETITION_WINDOW:]

    def _turn_report(self, first_id: int, result: TurnResult) -> None:
        """Repetition across the last outputs and the glossary report of the turn (measured and
        logged for the debug view; nothing is regenerated because of them)."""
        outs = [("narration", result.narration)] + [
            ("npc", u.payload["text"]) for u in result.utterances]
        result.repetition = measure_turn(outs, self._prior_outputs(first_id))
        with self._fixes_lock:
            fixes, self._fixes = self._fixes, []
        g = self.glossary
        near = [m for _, t in outs for m in g.near_misses(t)] if g else []
        result.names = {"fixed": fixes, "near_misses": near,
                        "canonical": sum(g.canonical_count(t) for _, t in outs) if g else 0}
        hits = []
        for who, t in outs:
            for h in style_hits(t):
                hits.append((who, h))
                self._note("style_hit", source=who, hit=h.kind, text=h.text[:160])
        result.style = {"count": len(hits), "by_kind": count_by_kind([h for _, h in hits])}
        self.reports.append({"repetition": result.repetition, "names": result.names,
                             "style": result.style})

    # -- the player's input, names learned from speech ---------------------------------------
    def _player_events(self, parts: list[Part], raw: str) -> list[tuple[str, Event]]:
        """The player's input as events, in order: each action (asterisks) an observable action
        of the player character, each speech part an utterance. The verbatim text is kept in
        `raw` on the first event when the input was split. (segment key, event) pairs."""
        if not parts:
            parts = [Part(SPEECH_PART, raw)]
        split = any(p.kind == PART_ACTION for p in parts)
        out: list[tuple[str, Event]] = []
        n_act = n_sp = 0
        for i, part in enumerate(parts):
            extra: dict[str, Any] = ({"part": i + 1, **({"raw": raw} if i == 0 else {})}
                                     if split else {})
            if part.kind == PART_ACTION:
                n_act += 1
                ev = self._event(ACTION_EVENT, [PLAYER],
                                 {"text": part.text, "actor": PLAYER, **extra}, notability=0.4)
                out.append((f"paction{n_act}", ev))
            else:
                n_sp += 1
                ev = self._utterance(PLAYER, part.text, **extra)
                out.append((PLAYER if n_sp == 1 else f"{PLAYER}~{n_sp}", ev))
        return out

    def _learn_from_player(self, pairs: list[tuple[str, Event]]) -> None:
        """A name the player writes is a name the player character knows (only the player decides
        what the character knows); whoever hears it in speech learns it by the usual rules."""
        for _, ev in pairs:
            for subj in self.names.mentions(ev.payload["text"]):
                self.names.learn(PLAYER, subj, how=PLAYER_SAID, scene=self.scene,
                                 cause_id=ev.id, note="named in the player's own words")
            if ev.type == UTTERANCE:
                self._learn_from_speech(ev, PLAYER, ev.payload["text"])

    def _name_binds(self, speaker: str, subject: str, text: str) -> bool:
        """Does a listener understand that this name belongs to the (present) person? One
        judge question; if no judge answers, the name was said aloud, so it counts."""
        sc = self.scene
        try:
            j = self.judge.yes_no(
                f"In this line, would a listener understand that the name "
                f"\"{self.names.real(subject)}\" belongs to the person described as "
                f"\"{self.names.label(subject)}\"? (An introduction, a direct address or pointing "
                "the person out: yes. Only mentioned in passing, or unclear whom it names: no.)",
                f"Speaker: {self.names.describe(speaker)}\nPresent: "
                + ", ".join(self.names.describe(c) for c in sc.present) + f"\nLine: {text}",
                tag="name_binds")
            return bool(j.answer)
        except JudgeError as e:
            self._note("name_check_unavailable", error=str(e))
            return True

    def _learn_from_speech(self, ev: Event, speaker: str, text: str) -> None:
        """Names said aloud are heard by those present: they learn a name that is attached to a
        person (introduction, address) or belongs to someone absent. The learning event is caused
        by the utterance, so a rollback of the line takes it away too."""
        sc = self.scene
        for subj in self.names.mentions(text):
            listeners = [h for h in sc.present
                         if h != speaker and h != subj and not self.names.knows(h, subj)]
            if not listeners:
                continue
            if subj == speaker:
                how = INTRODUCED
            elif subj in sc.present:
                if not self._name_binds(speaker, subj, text):
                    self._note("name_not_attached", speaker=speaker, subject=subj, text=text)
                    continue
                how = NAME_TOLD
            else:
                how = OVERHEARD  # an absent person named in passing: the name is known, no face
            for h in listeners:
                self.names.learn(
                    h, subj, how=how, scene=sc, source=speaker, cause_id=ev.id,
                    note=f"{self.names.real(speaker)} said the name {self.names.real(subj)}")

    def acquaint(self, a: str, b: str, *, how: str = "acquainted", mutual: bool = True) -> None:
        """Setup: `a` knows `b` by name (and `b` knows `a`): prior acquaintance, own life, canon."""
        self.names.acquaint(a, b, self.scene, how=how, mutual=mutual)

    def turn(
        self,
        player_text: str,
        speakers: Sequence[str] | None = None,
        *,
        handle: InterruptHandle | None = None,
        on_word: Callable[[str, str], None] | None = None,
        on_narration: Callable[[str], None] | None = None,
        defer_slow: bool = False,
    ) -> TurnResult:
        """Run one turn. `defer_slow` (task 19, fast/slow lane): return as soon as the player has
        everything to read; extraction, salience, attitudes and the other bookkeeping run while the
        player reads (`settle()`), and the next turn waits for them only if they are still running. In prose mode the scene director names who speaks next (`speakers`
        overrides it); in json mode the narrator does. `on_word(speaker, word)` receives the
        delivered words; a handle fired from inside it interrupts live. `on_narration(text)` is
        called once with the accepted narration, before the first NPC word (it may block to pace
        the narration out; the parallel work goes on meanwhile).

        Parallel mode (see `parallel`): once the narrator has answered, its speech check, the
        director and then each speaking NPC's chain (line, then the line's check) run
        concurrently. An NPC's chain waits for the lines of the NPCs speaking before it, so
        it hears them. NPC lines are delivered in order, each as soon as it is ready. A speech
        verdict that rejects the narration throws the started chains away and the narrator is
        called again. Event writes never leave this thread, so the log does not depend on timing."""
        sc = self.scene
        if self.ended:
            raise CampaignEnded("the player character is dead; the campaign is read-only")
        t_start = time.monotonic()
        waited = self._settle_for_next_turn()
        marks = (len(self.judgments.entries), len(self.llm_calls), len(self.devlog))
        if self.canon_guard is not None:
            self.canon_guard.refresh(self)
        for s in speakers or ():
            if s not in sc.present or s == PLAYER:
                raise ValueError(f"{s!r} cannot speak: not an NPC in the scene")
        turn_events: list[Event] = []
        launch: _Launch | None = None
        self._admitted = []
        with self._fixes_lock:
            self._fixes = []
        parts = split_input(player_text)
        model_text = render_for_model(parts, player_text)  # what the narrator and director read
        try:
            player_pairs = self._player_events(parts, player_text)
            player_ev = player_pairs[0][1]
            turn_events.extend(ev for _, ev in player_pairs)
            self._learn_from_player(player_pairs)
            outcome: Outcome | None = None
            if self.outcomes_on:  # the world judges the attempt before any prose (task 19)
                judged = self.outcome_judge.player(model_text, unbounded=self.ctx.player_unlimited)
                if judged is not None:
                    outcome, oev = record_outcome(self, judged, player_ev)
                    turn_events.append(oev)
                    if outcome.died:
                        turn_events.append(record_death(self, outcome, player_ev))
            outcomes = [outcome] if outcome else []

            first_step = (self._without_narration(
                              model_text, keep=has_action(parts) or self._scene_starts(turn_events))
                          if outcome is None and self._living(speakers) else None)
            if first_step is not None:
                out = NarratorOutput("")
                launch = self._launch(out, model_text, speakers, turn_events, check=False,
                                      first_step=first_step)
            elif self.parallel:
                def on_candidate(out: NarratorOutput) -> bool:
                    nonlocal launch
                    cand = self._launch(out, model_text, speakers, turn_events, check=True)
                    assert cand.speech is not None
                    if self._take(cand.speech):
                        self._discard(cand)
                        return False
                    launch = cand
                    return True

                out = self._narrate(model_text, on_candidate, outcome)
                if launch is None:  # speech stripped after the retries: nothing left to check
                    launch = self._launch(out, model_text, speakers, turn_events, check=False)
            else:
                out = self._narrate(model_text, outcome=outcome)
                launch = self._launch(out, model_text, speakers, turn_events, check=False)

            turn_events.extend(ev for ev, _, _ in self._admitted)  # undone with the turn
            if on_narration is not None and first_step is None:
                on_narration(out.description)
            sources = {**{k: ev for k, ev in player_pairs}, **launch.sources}
            segments = [*[(k, ev.payload["text"]) for k, ev in player_pairs], *launch.segments]
            result = TurnResult(out.description, actions=list(out.actions))
            if self._living(speakers):
                self._exchange(launch, result, turn_events, sources, segments, handle, on_word)
                if (first_step is not None and not result.interrupted
                        and not any(u.payload.get("text", "").strip() for u in result.utterances)
                        and not any(k == "gesture" for k, _, _ in result.exchange)):
                    out = self._narrate_empty(model_text, turn_events, sources, segments, result)
                    if on_narration is not None:
                        on_narration(out.description)
            for npc in launch.speakers:  # classic, or a fixed list of speakers
                if npc in launch.chains:
                    prep, fut = launch.chains[npc]
                    text = self._take(fut)
                else:  # sequential: this NPC sees what earlier speakers of the turn said
                    prep = self._prep_npc(npc)
                    text = self._npc_line(prep)
                sr = self._deliver(npc, prep, text, result, turn_events, sources, segments,
                                   handle, on_word)
                if sr.interrupted:
                    result.stop_reason = "interrupted"
                    break

            if self.outcomes_on and not result.interrupted:
                outcomes += self._resolve_npc_acts(launch, result, turn_events, sources, segments,
                                                   on_narration)
            slow = _Slow(segments, sources, outcomes, turn_events, result, player_ev, sc.time,
                         self.ctx.extractor(sc, segments, [o.for_narrator() for o in outcomes]))
            slow.fast_s = time.monotonic() - t_start - waited
            slow.marks = marks
        except Exception:
            if launch is not None:
                for _, fut in launch.chains.values():
                    fut.cancel()
                if launch.first is not None:
                    launch.first.cancel()
            for e in turn_events:
                self.log.rollback(e.id, "turn failed")
            self._unadmit(self._admitted)
            self.refresh_memory()
            raise
        if launch is not None and self.parallel:
            unused = [n for n in launch.chains if n not in {u.payload["speaker"]
                                                              for u in result.utterances}]
            for n in unused:
                launch.chains[n][1].cancel()
            if unused:
                self._note("chains_unused_after_interruption", npcs=unused)
        sc.time += self.minutes_per_turn
        with self._slow_lock:
            self._slow = slow
            if defer_slow and self.parallel:
                slow.raw = self._submit(self._complete, "extractor", slow.messages)
        if not defer_slow:
            self.settle()
            if self.slow_failure is not None:
                err, self.slow_failure = self.slow_failure, None
                raise err
        return result

    # -- the slow lane ---------------------------------------------------------------------
    def _settle_for_next_turn(self) -> float:
        """The next turn starts: finish the previous slow lane (it may already be done). Returns
        the seconds this turn waited for it; recorded in `lane_stats`."""
        t0 = time.monotonic()
        with self._slow_lock:  # blocks while another thread is applying the slow lane
            pending = self._slow is not None
            self.settle()
        waited = time.monotonic() - t0
        if self.lane_stats and (pending or waited > 0.05):
            self.lane_stats[-1].update(waited_s=round(waited, 3), needed=waited > 0.05)
        return waited

    def settle(self) -> bool:
        """Apply the slow lane of the last turn: extraction, facts, state changes, salience,
        attitudes, the turn report, agent promotion, memory files, then the hooks in
        `after_settle` (the world). Idempotent, one thread at a time, always in this order, so the
        event log does not depend on timing. A failure rolls the whole turn back and is left in
        `slow_failure` (it is not raised here, because the caller may be the next turn)."""
        with self._slow_lock:
            slow = self._slow
            if slow is None:
                return False
            self._slow = None
            t0 = time.monotonic()
            sc = self.scene
            real_time = sc.time
            sc.time = slow.time  # the facts of the turn carry the time of the turn
            try:
                first = self._take(slow.raw) if slow.raw is not None else None
                diff = self._extract(slow.segments, slow.outcomes, messages=slow.messages,
                                     first_raw=first)
                slow.result.fact_ids = self._commit(diff, slow.sources)
                self._apply_switches(slow)
                self._promote_portraits()
                self._turn_report(slow.player_event.id, slow.result)
                for u in slow.result.utterances:
                    self.agents.promote(u.payload["speaker"], sc)
                self._prefetch()
                sc.time = real_time
                self.process_natural_deaths()
                self.refresh_memory()
                for hook in list(self.after_settle):
                    hook()
                self.after_settle.clear()
            except Exception as e:  # noqa: BLE001 - the turn is undone, the caller decides
                sc.time = real_time
                for ev in slow.turn_events:
                    self.log.rollback(ev.id, "turn failed")
                    if ev.type == SCENE_ENTRY:  # a person the narration brought in (task LD-9)
                        sc.present = tuple(c for c in sc.present
                                           if c != ev.payload["character"])
                sc.time = slow.time  # the turn's minutes did not happen
                self.after_settle.clear()
                self.refresh_memory()
                self.slow_failure = e
                self._note("slow_lane_failed", error=repr(e)[:200])
            # counted whether or not the slow lane succeeded: the calls were made either way
            slow.result.decisions = self.last_decisions = count_since(
                self, slow.player_event.id, slow.marks[0], slow.marks[1], slow.marks[2])
            self.lane_stats.append({"fast_s": round(slow.fast_s, 3),
                                    "slow_s": round(time.monotonic() - t0, 3),
                                    "waited_s": 0.0, "needed": False})
            return True

    # -- portrait switches: the relationship moves on the slow lane --------------------------
    def _switch_npcs(self, slow: _Slow) -> list[str]:
        """Present portrait NPCs with switches the player dealt with this turn: those who spoke
        or gestured, the one the director found addressed, one the player's input names or
        describes, or the only NPC in the scene."""
        others = [c for c in self.scene.present if c != PLAYER]
        acted = ({u.payload["speaker"] for u in slow.result.utterances}
                 | {n for kind, n, _ in slow.result.exchange if kind in ("line", "gesture")}
                 | {slow.result.addressee})
        said = " ".join(e.payload.get("text", "") for e in slow.turn_events
                        if (e.payload.get("speaker") or e.payload.get("actor")) == PLAYER)
        out = []
        for c in others:
            p = self.ctx.portrait_of(c)
            if p is None or not p.switches:
                continue
            if c in acted or len(others) == 1 or self._mentioned(c, said):
                out.append(c)
        return out

    def _mentioned(self, npc: str, text: str) -> bool:
        """`text` names `npc` (any case) or describes them by their label (its longer words, as
        stems: «чорнокосій жінці» for «чорнокоса жінка»)."""
        if not text:
            return False
        if npc in self.names.named_in(text):
            return True
        words = [w for w in re.findall(r"\w+", self.names.label(npc).lower()) if len(w) >= 4]
        have = re.findall(r"\w+", text.lower())
        hits = sum(1 for w in words if any(h.startswith(w[:max(3, len(w) - 2)]) for h in have))
        return bool(words) and hits >= min(2, len(words))

    def _switch_state(self, npc: str, cause_id: int) -> tuple[list[str], list[int]]:
        """The judge's state for one NPC's switch questions (real names: the judge is
        omniscient): the NPC's last line before the turn, then the turn as it stands in the log
        (from the player's input `cause_id` on). Also the ids of this NPC's own lines and
        gestures in it, kept on the relation event."""
        name = self.ctx.name(npc)

        def who(c: str | None) -> str:
            return "The player" if c == PLAYER else self.ctx.name(c) if c else "Narration"

        lines: list[str] = []
        ids: list[int] = []
        before = [e for e in self.log.active([UTTERANCE])
                  if e.id < cause_id and e.payload.get("speaker") == npc]
        if before:
            lines.append(f"(just before) {name}: {before[-1].payload['text']}")
        for e in self.log.active([UTTERANCE, ACTION_EVENT, NARRATION]):
            if e.id < cause_id:
                continue
            p = e.payload
            c = None if e.type == NARRATION else (p.get("speaker") or p.get("actor")
                                                   or p.get("by"))
            mark = " (does)" if e.type == ACTION_EVENT and c else ""
            lines.append(f"{who(c)}{mark}: {p.get('text', '')}")
            if c == npc:
                ids.append(e.id)
        state = [f"The questions are about {name}: \"she\" and \"her\" mean {name} (\"he\" and "
                 f"\"him\" if {name} is a man). Judge what the player did or said this turn "
                 f"(toward her or others present).", "This turn:\n" + "\n".join(lines)]
        return state, ids

    def _judge_switches(self, npcs: Sequence[str], cause_id: int) -> None:
        """One batched yes/no judgment per NPC (a question per switch trigger); the hits move
        the relationship, paced (harness/relations.py `apply`). Every judged turn leaves a
        RELATION event, caused by the player's input `cause_id`, with the scene key and this
        NPC's own lines (so a replaced line can be judged again)."""
        rels = self.ctx.relations
        jobs = []
        for npc in npcs:
            p = self.ctx.portrait_of(npc)
            if p is None or not p.switches:
                continue
            state, ids = self._switch_state(npc, cause_id)
            qs = {sw.id: yes_no_q(sw.trigger, tag="portrait_switch") for sw in p.switches}
            jobs.append(_Job(lambda st=state, q=qs: self._ask_safe(st, q),
                             {"npc": npc, "portrait": p, "ids": ids}))
        for job, got in zip(jobs, self._map([j.ask for j in jobs])):
            npc, p = job.meta["npc"], job.meta["portrait"]
            if isinstance(got, JudgeError):
                self._note("switches_unavailable", npc=npc, error=str(got)[:200])
                continue
            hits = [sw for sw in p.switches if sw.id in got and got[sw.id].answer]
            old = rels.get(npc, PLAYER)
            key = rels.scene_key(npc, self.scene)
            new = relations.apply(old, hits, rels.pace(npc, PLAYER, key))
            rels.set(npc, PLAYER, new.rung, new.warmth, new.trust, new.reason, self.scene,
                     cause_id, lines=job.meta["ids"], key=key, counted=new.counted)
            if hits or (new.rung, new.warmth, new.trust) != (old.rung, old.warmth, old.trust):
                self._note("relation_changed", npc=npc, **{"from": old.rung}, to=new.rung,
                           switches=[sw.id for sw in hits], counted=list(new.counted),
                           warmth=new.warmth, trust=new.trust)

    def _apply_switches(self, slow: _Slow) -> None:
        """The slow lane's relationship step. It never aborts the slow lane: any failure is a
        note and the relationship stays as it was."""
        try:
            self._judge_switches(self._switch_npcs(slow), slow.player_event.id)
        except Exception as e:  # noqa: BLE001 - bookkeeping must not undo the turn
            self._note("switches_failed", error=repr(e)[:200])

    def _revert_relations(self, line_id: int) -> list[tuple[str, int]]:
        """A model error, challenge or cut replaced the NPC's line or gesture `line_id`: the
        relation events judged on it are rolled back. Returns (npc, the turn's player input) to
        judge again once the replacement is in the log."""
        out = []
        for e in self.log.active([RELATION]):
            if line_id in e.payload.get("lines", ()):
                self.log.rollback(e.id, "its line was replaced")
                self._note("relation_reverted", npc=e.payload["npc"], event=e.id, line=line_id)
                if e.cause_id is not None:
                    out.append((e.payload["npc"], e.cause_id))
        return out

    def _rejudge(self, reverted: Sequence[tuple[str, int]]) -> None:
        """Ask the switches again for each reverted NPC, with the new (or restored) line in the
        log: the player keeps what they earned (one judge call per NPC, never on the fast
        lane). A failure is a note; the relationship stays reverted."""
        for npc, cause in reverted:
            try:
                self._judge_switches([npc], cause)
            except Exception as e:  # noqa: BLE001
                self._note("switches_failed", npc=npc, error=repr(e)[:200])

    # -- hidden-layer leaks ------------------------------------------------------------------
    def _leaks_of(self, event_id: int) -> list[Event]:
        return [e for e in self.log.active([PORTRAIT_LEAK]) if e.cause_id == event_id]

    def _record_leak(self, view: NpcView | None, ev: Event, *, leak: str = "",
                     scene: str = "") -> None:
        """A delivered line or gesture made from a prompt that carried a leak uses it for the
        scene: a PORTRAIT_LEAK event caused by that line (a rollback of the line frees it)."""
        leak = leak or (view.leak if view is not None else "")
        scene = scene or (view.leak_scene if view is not None else "")
        if not leak or not ev.payload.get("text", "").strip():
            return
        npc = ev.payload.get("speaker") or ev.payload.get("by")
        self._event(PORTRAIT_LEAK, [npc], {"npc": npc, "scene": scene, "leak": leak},
                    witnesses=[], notability=0.05, cause_id=ev.id)
        self._note("portrait_leak", npc=npc, scene=scene, leak=leak[:120], line=ev.id)

    def _carry_leaks(self, leaks: Sequence[Event], ev: Event) -> None:
        for e in leaks:
            self._record_leak(None, ev, leak=e.payload["leak"], scene=e.payload["scene"])

    def _prefetch(self) -> None:
        """Work for the next turn that does not depend on what the player will write: the manner
        notes of whoever is in the scene (one cheap call, once per NPC)."""
        for npc in self.scene.present:
            if npc != PLAYER:
                self._ensure_manner(npc)

    def _resolve_npc_acts(self, launch: "_Launch", result: "TurnResult", turn_events: list[Event],
                          sources: dict[str, Event], segments: list[tuple[str, str]],
                          on_narration: Callable[[str], None] | None) -> list[Outcome]:
        """Acts of NPCs toward the player (attack, theft, arrest) are judged like the player's
        own: the world decides, then one short paragraph narrates only that. The director has
        already listed the acts, so this is the step after the first narration."""
        acts = [("", a) for a in launch.out.actions]
        names = self._name_words
        acts += [(u.payload["speaker"], b) for u in result.utterances
                 for b in ([] if self.style is None
                           else split_npc_output(u.payload["text"], names).beats)]
        acts += [(npc, t) for kind, npc, t in result.exchange if kind == "gesture"]
        got = self.outcome_judge.npc_acts(acts, unbounded=self.ctx.player_unlimited)
        done: list[Outcome] = []
        for o in got:
            o2, ev = record_outcome(self, o, turn_events[0] if turn_events else None)
            turn_events.append(ev)
            if o2.died:
                turn_events.append(record_death(self, o2, ev))
            done.append(o2)
            para = self._resolution_paragraph(o2)
            if para:
                nev = self._event(NARRATION, [], {"text": para}, witnesses=[], notability=0.4,
                                  cause_id=ev.id)
                turn_events.append(nev)
                key = f"narration~{len(done) + 1}"
                sources[key] = nev
                segments.append((key, para))
                result.narration = result.narration + "\n\n" + para
                if on_narration is not None:
                    on_narration(para)
        return done

    def _resolution_paragraph(self, o: Outcome) -> str:
        sc = self.scene
        user = (self.ctx._scene_header(sc, PLAYER) + "\n\n" + o.for_narrator()
                + "\n\nWrite one to three sentences that narrate only how this resolves, from the "
                "player character's point of view. No speech, no quotation marks, no dialogue "
                "dashes. " + PLAYER_CHARACTER_RULE
                + (f" Write in {self.output_language}." if self.output_language else ""))
        for _ in range(2):
            try:
                text = self._prose_of(self._complete_text("narrator", self.ctx.finish([
                    {"role": "system", "content": "You are the narrator of a role-playing game. "
                     "Write vivid prose." + self.ctx.limits_section()},
                    {"role": "user", "content": user}], PLAYER))).strip()
            except ProviderError as e:
                self._note("resolution_unavailable", error=str(e))
                return ""
            text = self._fix_names(text, "narration")
            if text and not has_speaker_line(text, self._npc_names) and not has_dash_speech(text):
                text = self._guard_player_prose(text, o.text if o.actor == PLAYER else "")
                if text:
                    return self.names.mask(PLAYER, text)
        return ""

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

        leaks = self._leaks_of(last.id)
        self.log.rollback(last.id, f"retroactive interrupt of {npc}")
        reverted = self._revert_relations(last.id)  # judged again on the kept part
        try:
            kept = self._utterance(npc, sr.spoken_text, interrupted=True, replaces=last.id)
            self._carry_leaks(leaks, kept)
            self._record_interruption(kept, sr)
            self._learn_from_speech(kept, npc, sr.spoken_text)
            try:
                self._commit(self._extract([(npc, sr.spoken_text)]), {npc: kept})
            except ExtractionRejected:
                pass  # keep the cut; simply record no facts from the kept part
            self.refresh_memory()
        finally:
            self._rejudge(reverted)
        return kept

    # -- "how does he know that?" (model-error flow for knowledge leaks) -------------------------
    def knowledge_report(self, character: str) -> list[dict[str, Any]]:
        """What `character` knows and from where (debug view)."""
        return knowledge.report(self, character)

    def challenge_line(self, event_id: int, explanation: str = "") -> "Challenge":
        """The player marks an NPC line as impossible ("he could not know this"). The speaker's
        channels are checked for the claim (known facts with their sources, names, what the
        character heard, the character's own background).

        - No channel: the player's note is stored for the campaign and fed to later generations;
          if this is the last NPC line it is regenerated with the note (the player's turn stays).
        - A channel exists: nothing changes; the answer says what kind of channel and roughly when
          (`public`), with the full event in `detail` (shown behind a spoiler tap)."""
        ev = self.log.get(event_id)
        if ev.type != UTTERANCE or ev.payload.get("speaker") == PLAYER or not self.log.is_active(
                event_id):
            raise ValueError("only a line an NPC said can be challenged")
        npc, text = ev.payload["speaker"], ev.payload["text"]
        explanation = explanation.strip()
        # 1. a name the speaker had no channel to (certain: no judge needed)
        known = frozenset(self.names.known_map(npc, before=event_id))
        before_ev = [e for e in self.log.recent_dialogue(witnessed_by=npc, limit=10)
                     if e.id < event_id]
        heard = "\n".join(e.payload["text"] for e in before_ev)
        leaked = self.names.unknown_mentioned(npc, text, heard, known)
        item: knowledge.Item | None = None
        why = ""
        if leaked:
            why = "name: " + ", ".join(self.names.real(c) for c in leaked)
        else:
            items = knowledge.items_for(self, npc, before=event_id)
            try:
                item = self._find_channel(npc, text, explanation, items)
            except JudgeError as e:
                self._note("challenge_unavailable", error=str(e))
                return Challenge("unavailable", npc=npc, event=event_id)
            why = "" if item else "no fact, name, heard line or background explains it"
        if item is not None:
            self._note("challenge_channel", npc=npc, event=event_id, channel=item.text,
                       how=item.how)
            return Challenge("channel", npc=npc, event=event_id,
                             public=knowledge.public_channel(self, item),
                             detail=knowledge.detail(self, item))
        # 2. no channel: store the note, regenerate if this is the last NPC line
        self._event(CORRECTION, [npc], {"npc": npc, "line": text, "explanation": explanation,
                                        "line_event": event_id, "reason": why},
                    witnesses=[], notability=0.1)
        res = Challenge("no_channel", npc=npc, event=event_id, detail=why)
        last = self.log.last_npc_utterance()
        if last is None or last.id != event_id:
            self._note("challenge_not_regenerated", event=event_id,
                       reason="not the last NPC line")
            return res
        self._regenerate(ev, res, explanation)
        return res

    def model_error(self, event_id: int, explanation: str) -> "Challenge":
        """«Помилка моделі»: the player says what is wrong with the last world output. The note
        is stored for the campaign and fed to later generations (NPC lines: to that NPC's lines;
        narration: to the narrator). Only the last world output (`last_world_output`) can be
        marked: it is regenerated and the player's turn stays. Anything older is refused."""
        explanation = explanation.strip()
        if not explanation:
            raise ValueError("a model error needs the player's explanation")
        ev = self.log.get(event_id)
        if not self.log.is_active(event_id):
            raise ValueError("this output is no longer part of the story")
        last = self.last_world_output()
        if last is None or last.id != event_id:
            raise ValueError("only the last world output can be a model error")
        if ev.type == UTTERANCE:
            npc, text = ev.payload["speaker"], ev.payload["text"]
            self._event(CORRECTION, [npc], {"npc": npc, "line": text, "explanation": explanation,
                                            "line_event": event_id, "reason": "model error"},
                        witnesses=[], notability=0.1)
            res = Challenge("model_error", npc=npc, event=event_id)
            self._regenerate(ev, res, explanation)
            return res
        if ev.type == ACTION_EVENT:  # an NPC gesture
            npc, text = ev.payload["by"], ev.payload["text"]
            self._event(CORRECTION, [npc], {"npc": npc, "line": text, "explanation": explanation,
                                            "line_event": event_id, "reason": "model error",
                                            "gesture": True}, witnesses=[], notability=0.1)
            res = Challenge("model_error", npc=npc, event=event_id)
            self._regenerate_gesture(ev, res)
            return res
        if ev.type != NARRATION:
            raise ValueError("only a line or a narration passage can be a model error")
        text = ev.payload["text"]
        self._event(CORRECTION, [], {"npc": None, "line": text, "explanation": explanation,
                                     "line_event": event_id, "reason": "model error",
                                     "narration": True}, witnesses=[], notability=0.1)
        res = Challenge("model_error", event=event_id)
        self._renarrate(ev, res)
        return res

    def last_world_output(self) -> Event | None:
        """The last thing the world said or did that the player saw: a narration passage, an NPC
        line or an NPC gesture."""
        for e in reversed(self.log.active([NARRATION, UTTERANCE, ACTION_EVENT])):
            if e.type == NARRATION or (e.type == UTTERANCE and e.payload.get("speaker") != PLAYER) \
                    or (e.type == ACTION_EVENT and e.payload.get("gesture")):
                return e
            if e.type == UTTERANCE:  # the player's own line: nothing of the world after it
                return None
        return None

    def _turn_input_before(self, old: Event) -> tuple[str, Outcome | None]:
        """The turn's input as the narrator read it (`render_for_model` of the verbatim text) and
        the world's judgment of the player's attempt in that turn, for a narration `old`."""
        mine = [e for e in self.log.active([UTTERANCE, ACTION_EVENT])
                if e.id < old.id and (e.payload.get("speaker") == PLAYER
                                      or (e.type == ACTION_EVENT
                                          and e.payload.get("actor") == PLAYER))]
        if not mine:
            return "", None
        last = mine[-1]
        if last.payload.get("part"):  # a split input: the first part carries the raw text
            first = next((e for e in reversed(mine)
                          if e.payload.get("part") == 1 and "raw" in e.payload), last)
        else:
            first = last
        raw = str(first.payload.get("raw", first.payload["text"]))
        model_text = render_for_model(split_input(raw), raw)
        judged = [e for e in self.log.active([OUTCOME])
                  if first.id < e.id < old.id and e.payload.get("actor", PLAYER) == PLAYER]
        return model_text, (self._outcome_of(judged[-1]) if judged else None)

    @staticmethod
    def _outcome_of(ev: Event) -> Outcome:
        p = ev.payload
        return Outcome(p.get("verdict", FAILS), p.get("reason", "none"), bool(p.get("died")),
                       p.get("actor", PLAYER), p.get("text", ""), bool(p.get("unbounded")), ev.id)

    def _renarrate(self, old: Event, res: "Challenge") -> None:
        """Replace the narration passage `old` by a new one written with the corrections in the
        narrator's context. The player's input stays. Failing puts the old text back."""
        model_text, outcome = self._turn_input_before(old)
        cause = self.log.get(old.cause_id) if old.cause_id is not None else None
        self.log.rollback(old.id, "model error: narration")
        try:
            if cause is not None and cause.type == OUTCOME:  # an NPC act's resolution paragraph
                text = self._resolution_paragraph(self._outcome_of(cause))
                if not text:
                    raise RuntimeError("the resolution could not be narrated again")
            else:
                text = self._narrate(model_text, outcome=outcome).description
        except Exception:
            self._event(NARRATION, [], {"text": old.payload["text"], "replaces": old.id,
                                        "restored": True}, witnesses=[], notability=0.4)
            self.refresh_memory()
            raise
        new = self._event(NARRATION, [], {"text": text, "replaces": old.id, "regenerated": True},
                          witnesses=[], notability=0.4)
        try:
            self._commit(self._extract([("narration", text)]), {"narration": new})
        except ExtractionRejected:
            self._note("regenerated_narration_not_extracted", event=new.id)
        self.refresh_memory()
        res.regenerated, res.text, res.new_event = True, text, new.id

    def _find_channel(self, npc: str, text: str, explanation: str,
                      items: list["knowledge.Item"]) -> "knowledge.Item | None":
        """Which of the character's channels explains the claim, if any (one choice judgment)."""
        if not items:
            return None
        options = {it.key: f"[{it.kind}] {it.text}"[:220] for it in items}
        options["none"] = "no item explains how the speaker could know this"
        prof = self.profiles.get(npc)
        state = [f"Speaker: {self.names.real(npc)}" + (f". {prof.description}" if prof else ""),
                 f"Line: {text}",
                 "The player says the speaker could not have known: "
                 + (explanation or "something in this line")]
        j = self.judge.ask(state, {"c": choice_q(
            "Which one item is the channel through which the speaker learned what the player "
            "says they could not know? Answer none if no item explains it.", options,
            tag="knowledge_channel")})["c"]
        by_key = {it.key: it for it in items}
        return by_key.get(str(j.answer))

    def _still_has(self, npc: str, texts: Sequence[str], old_text: str,
                   explanation: str) -> list[bool]:
        """Typed checks, one question per text in a single judge call: does it still assert or
        allude to the disputed point (the player's explanation is the reference)?"""
        ref = explanation or "the content the player disputed"
        state = [f"Speaker: {self.names.real(npc)}", f"Disputed line: {old_text}",
                 f"The player objects: {ref}"]
        qs = {}
        for i, t in enumerate(texts):
            qs[str(i)] = yes_no_q(
                "Does this line still assert, imply or allude to the disputed point, even in "
                "other words?" + f"\nLine: {t}", tag="challenge_still_has")
        if not qs:
            return []
        got = self.judge.ask(state, qs)
        return [bool(got[str(i)].answer) for i in range(len(texts))]

    def _regenerate_text(self, npc: str, old: Event, explanation: str) -> str | None:
        """A replacement line with the disputed point verified gone: up to `check_retries`+1
        candidates; if all still carry it, the sentences that carry it are dropped (logged). If
        nothing safe is left (or the check cannot run) the line is withdrawn: None."""
        old_text = old.payload["text"]
        notes: list[str] = []
        cands: list[str] = []
        for _ in range(self.check_retries + 1):
            text = self._npc_line(self._prep_npc(npc), notes=notes)
            cands.append(text)
            try:
                present = self._still_has(npc, [text], old_text, explanation)[0]
            except JudgeError as e:
                self._note("challenge_check_unavailable", npc=npc, error=str(e))
                return text
            if not present:
                if len(cands) > 1:
                    self._note("challenge_removed_after_retry", npc=npc, tries=len(cands))
                return text
            self._note("challenge_still_present", npc=npc, text=text)
            notes = ["Your previous try still touched on what the player objected to ("
                     + (explanation or old_text) + "). Leave that point out entirely, in any "
                     "wording."]
        last = cands[-1]
        parts = sentences(last)
        try:
            flags = self._still_has(npc, parts, old_text, explanation)
            kept = [p for p, bad in zip(parts, flags) if not bad]
            joined = " ".join(kept)
            # an allusion can be spread over sentences: verify the remainder as a whole
            if kept and self._still_has(npc, [joined], old_text, explanation)[0]:
                kept = []
        except JudgeError as e:
            self._note("challenge_check_unavailable", npc=npc, error=str(e), stage="drop")
            kept, joined = [], ""
        if not kept:
            self._note("challenge_line_withdrawn", npc=npc, text=last)
            return None
        self._note("challenge_sentences_dropped", npc=npc, before=last,
                   dropped=[p for p, bad in zip(parts, flags) if bad])
        return joined

    def _regenerate(self, old: Event, res: "Challenge", explanation: str = "") -> None:
        """Replace the NPC line `old` by a new one generated with the correction in context. If
        generating fails the old text is put back (the log is append-only, so as a new event).
        Either way the relationship the line was judged on is judged again with what stands."""
        leaks = self._leaks_of(old.id)
        self.log.rollback(old.id, "model error: no channel")
        reverted = self._revert_relations(old.id)
        try:
            self._regenerate_line(old, res, explanation, leaks)
        finally:
            self._rejudge(reverted)

    def _regenerate_line(self, old: Event, res: "Challenge", explanation: str,
                         leaks: Sequence[Event]) -> None:
        npc = old.payload["speaker"]
        try:
            text = self._regenerate_text(npc, old, explanation)
        except Exception:
            back = self._utterance(npc, old.payload["text"], replaces=old.id, restored=True)
            self._carry_leaks(leaks, back)
            self.refresh_memory()
            raise
        if text is None:  # the point cannot be removed from this line: the NPC says nothing
            self.refresh_memory()
            res.withdrawn = True
            return
        new = self._utterance(npc, text, replaces=old.id, regenerated=True)
        prep = self._last_prep.get(npc)
        self._record_leak(prep.view if prep is not None else None, new)
        self._learn_from_speech(new, npc, text)
        try:
            self._commit(self._extract([(npc, text)]), {npc: new})
        except ExtractionRejected:
            self._note("regenerated_line_not_extracted", event=new.id)
        self.refresh_memory()
        res.regenerated, res.text, res.new_event = True, text, new.id

    def _regenerate_gesture(self, old: Event, res: "Challenge") -> None:
        """Replace the NPC gesture `old` by a new one made the way the exchange makes a gesture
        step (same context, gesture shape and name fixing), with the correction in the NPC's
        context. Failing (or no action coming back) puts the old gesture back. Either way the
        relationship it was judged on is judged again."""
        leaks = self._leaks_of(old.id)
        self.log.rollback(old.id, "model error: gesture")
        reverted = self._revert_relations(old.id)
        try:
            self._regenerate_gesture_act(old, res, leaks)
        finally:
            self._rejudge(reverted)

    def _regenerate_gesture_act(self, old: Event, res: "Challenge",
                                leaks: Sequence[Event]) -> None:
        npc = old.payload["by"]
        prep: _NpcPrep | None = None
        try:
            prep = self._prep_npc(npc)
            text = self._shaped_line(prep, Shape.GESTURE,
                                     word_bounds(Shape.GESTURE, self.world_profile))
            if not text:
                raise RuntimeError("the gesture could not be written again")
            act = self._fix_names(beat_as_action(text, self.names.real(npc),
                                                 [self.names.label(npc)]), "npc_beat")
        except Exception:
            back = self._event(ACTION_EVENT, [npc], {"text": old.payload["text"], "by": npc,
                                                     "gesture": True, "replaces": old.id,
                                                     "restored": True}, notability=0.3)
            self._carry_leaks(leaks, back)
            self.refresh_memory()
            raise
        new = self._event(ACTION_EVENT, [npc], {"text": act, "by": npc, "gesture": True,
                                                "replaces": old.id, "regenerated": True},
                          notability=0.3)
        self._record_leak(prep.view if prep is not None else None, new)
        self.refresh_memory()
        res.regenerated, res.text, res.new_event = True, act, new.id

    # -- long-run NPCs (task 19) -----------------------------------------------------------
    def add_npc(self, spec: NpcSpec, *, description: str = "", appearance: str = "") -> CharacterProfile:
        """A generated NPC joins the cast: profile with its immutable core, vitals for aging and
        natural death. The id and the name must be new."""
        if spec.id in self.profiles:
            raise ValueError(f"{spec.id!r} already exists")
        used = taken_names(self.profiles.values())
        if spec.name.lower() in used:
            raise ValueError(f"the name {spec.name!r} is already in the campaign")
        prof = spec.profile(description, appearance)
        self.profiles[spec.id] = prof
        self.vitals.register(spec.vitals)
        if self._owns_conn:
            self._save_setup()
        return prof

    def fresh_npc(self, slot: str | int, culture: str, **kw: Any) -> NpcSpec:
        """A non-canon NPC from the code tables, seeded by the campaign seed and `slot`; the name
        is never one already in the campaign (cast, glossary names)."""
        extra = ([e.canonical for e in self.glossary.entries if e.kind == "person"]
                 if self.glossary else [])
        kw.setdefault("sex_decider", self._decide_sex)
        spec = generate_npc(self.seed, slot, culture=culture,
                            used=[*taken_names(self.profiles.values(), extra)],
                            now_t=self.scene.time, **kw)
        return spec

    def _decide_sex(self, about: str) -> str | None:
        """One decider call for an NPC whose sex the text does not give (the answer is kept in
        the profile by `add_npc`). None when the decider is unavailable."""
        try:
            return str(self.judge.ask([f"A new person in {self.scene.location}: {about}"], {
                "sex": choice_q("Is this person a man or a woman?",
                                {"m": "a man or a boy", "f": "a woman or a girl"},
                                tag="npc_sex")})["sex"].answer)
        except JudgeError as e:
            self._note("npc_sex_unavailable", error=str(e)[:200])
            return None

    def bind_portrait(self, npc: str, portrait: str, rung: str = "stranger") -> None:
        """`npc` plays the world portrait `portrait` and starts on `rung` toward the player."""
        if portrait not in self.ctx.portraits:
            raise ValueError(f"no portrait {portrait!r} in world {self.world!r}")
        if rung not in SEED_VALUES:
            raise ValueError(f"unknown or unseedable rung {rung!r}")
        self.profiles[npc] = replace(self.profiles[npc], portrait=portrait)
        self.ctx.rung_seeds[npc] = rung
        if self.ctx.relations.get(npc, PLAYER).event_id is None:  # never re-seed over play
            self.ctx.relations.seed(npc, PLAYER, rung, self.scene)
        if self._owns_conn:
            self._save_setup()

    # -- short portraits for invented NPCs who matter ---------------------------------------
    def make_short_portrait(self, npc: str, text: str = "", rung: str = "stranger") -> bool:
        """One extractor-role call: a short portrait for the invented NPC `npc` (`text`: the
        author's free-text description), cached in the campaign and played from now on. A failure
        is noted and not retried; the NPC keeps playing by manner. True when it now has one."""
        return self.make_short_portraits([(npc, text, rung)])[0]

    def make_short_portraits(self, items: Sequence[tuple[str, str, str]]) -> list[bool]:
        """`make_short_portrait` for several NPCs (npc, text, rung): the calls run concurrently
        when the engine allows it, the results are installed in order."""
        todo = [(c, t, r) for c, t, r in items if c not in self._short_portraits]

        def job(npc: str, text: str) -> Callable[[], tuple[Any, list[str]]]:
            spec = self._spec_of(npc)

            def run() -> tuple[Any, list[str]]:
                why: list[str] = []
                p = short_portrait(spec, self.style, lambda m: self._complete("extractor", m),
                                   text=text, on_fail=why.append)
                return p, why
            return run

        results = self._map([job(c, t) for c, t, _r in todo])
        for (npc, _t, rung), (p, why) in zip(todo, results):
            self._short_portraits[npc] = asdict(p) if p else None
            if p is None:
                self._note("short_portrait_failed", npc=npc, reason=why[0] if why else "unknown")
            else:
                self.ctx.portraits[p.id] = p
                self.bind_portrait(npc, p.id, rung)
        if todo and self._owns_conn:
            with self.conn:
                self.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                                  ("short_portraits",
                                   json.dumps(self._short_portraits, ensure_ascii=False)))
        return [bool(self._short_portraits.get(c)) and bool(self.profiles[c].portrait)
                for c, _t, _r in items]

    def _spec_of(self, npc: str) -> NpcSpec:
        """What the portrait writer is told about an invented NPC, from the profile and vitals."""
        prof, v = self.profiles[npc], self.vitals.people[npc]
        return NpcSpec(npc, prof.name, v.culture, v.sex, prof.description, (), "", prof.core, v)

    def promote_short_portraits(self) -> list[str]:
        """Present invented NPCs who now matter (the player knows their name, or they came into a
        scene a second time) and have no portrait yet get a short one (slow lane): at most
        `MAX_PORTRAITS_PER_SETTLE` a time, made concurrently; the rest wait for a later settle.
        Canon people, package people with a portrait, and anyone already tried are skipped."""
        entries: dict[str, int] = {}
        for e in self.log.active([SCENE_ENTRY]):
            c = e.payload.get("character")
            entries[c] = entries.get(c, 0) + 1
        due = [c for c in self.scene.present
               if c != PLAYER and c in self.vitals.people and c not in self._short_portraits
               and not self.profiles[c].portrait
               and (self.names.knows(PLAYER, c) or entries.get(c, 0) >= 2)]
        due = due[:MAX_PORTRAITS_PER_SETTLE]
        got = self.make_short_portraits([(c, "", "stranger") for c in due])
        return [c for c, ok in zip(due, got) if ok]

    def _promote_portraits(self) -> None:
        """The slow lane's portrait step; like the switches, it never aborts the slow lane."""
        try:
            self.promote_short_portraits()
        except Exception as e:  # noqa: BLE001 - bookkeeping must not undo the turn
            self._note("short_portraits_failed", error=repr(e)[:200])

    def set_core(self, npc: str, core: str) -> None:
        """Set an NPC's immutable core once (a second, different core is refused)."""
        self.profiles[npc] = with_core(self.profiles[npc], core)
        if self._owns_conn:
            self._save_setup()

    def dead(self) -> set[str]:
        return {e.payload["character"] for e in self.log.active(["npc_death"])}

    def process_natural_deaths(self, now_t: int | None = None) -> list[Event]:
        """Natural deaths due by `now_t` (code, from the vitals tables): the person leaves the
        scene, a fact records it for those who were with them, the model only narrates it later."""
        now = self.scene.time if now_t is None else now_t
        out: list[Event] = []
        for v in self.vitals.due(now, self.dead()):
            who = self.profiles.get(v.character)
            if who is None:
                continue
            ev = self.log.append(
                "npc_death", game_time=v.death_t if v.death_t <= now else now,
                location=self.scene.location, participants=[v.character], witnesses=[],
                notability=0.4, payload={"character": v.character, "age": v.age(v.death_t),
                                         "cause": "natural", "text": f"{who.name} died of old age"})
            knowers = [(c, WITNESSED, None) for c in self.scene.present
                       if v.character in self.scene.present and c != v.character]
            self.facts.add_campaign(f"{who.name} died of natural causes at the age of "
                                    f"{v.age(v.death_t)}", source_event_id=ev.id,
                                    game_time=ev.game_time, location=self.scene.location,
                                    notability=0.4, knowers=knowers)
            if v.character in self.scene.present:
                self.leave_scene(v.character, stay_nearby=False)
            out.append(ev)
        return out

    # -- off-screen -----------------------------------------------------
    def advance_offscreen(self, minutes: int) -> None:
        start = self.scene.time
        self.scene.time += minutes
        for a in self.agents.agents():
            if a not in self.scene.present:
                self.updater.update(a, start, self.scene.time)
        self._save_scene()

    # -- saved campaigns ------------------------------------------------
    def _save_scene(self) -> None:
        """Keep the scene (not derivable from the log) in the database, so a campaign can be
        reopened where it stopped. Cheap; called whenever the scene changes."""
        sc = self.scene
        meta = {"scene": {"location": sc.location, "present": list(sc.present),
                          "outside": list(sc.outside), "time": sc.time}}
        with self.conn:
            for k, v in meta.items():
                self.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                                  (k, json.dumps(v)))

    def _save_setup(self) -> None:
        with self.conn:
            for k, v in {
                "profiles": [[p.id, p.name, p.description, p.manner, p.appearance, p.core, p.sex,
                              p.portrait] for p in self.profiles.values()],
                "settings": {"output_language": self.output_language,
                             "record_language": self.record_language,
                             "narration": self.narration,
                             "minutes_per_turn": self.minutes_per_turn,
                             "player_unlimited": self.ctx.player_unlimited,
                             "outcomes": self.outcomes_on, "item_ids": self.ctx.item_ids, "seed": self.seed,
                             "dialogue": self.dialogue, "world": self.world,
                             "rung_seeds": self.ctx.rung_seeds},
                "vitals": self.vitals.to_json(),
            }.items():
                self.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                                  (k, json.dumps(v)))

    @staticmethod
    def campaign_path(name: str, root: Path | str = "campaigns") -> Path:
        if not name or name != Path(name).name or name in (".", ".."):
            raise ValueError(f"bad campaign name {name!r}")
        return Path(root) / name

    @classmethod
    def create_campaign(cls, name: str, provider: Provider, profiles: Sequence[CharacterProfile],
                        scene: Scene, *, root: Path | str = "campaigns", **kw: Any) -> "Engine":
        """A new file-backed campaign under `<root>/<name>/` (git-ignored): `campaign.db`
        (SQLite, WAL), `memory/`, `judgments.jsonl`. Fails if the campaign exists."""
        d = cls.campaign_path(name, root)
        if (d / "campaign.db").exists():
            raise FileExistsError(f"campaign {name!r} already exists in {root}")
        d.mkdir(parents=True, exist_ok=True)
        eng = cls(provider, profiles, scene, conn=connect(str(d / "campaign.db"),
                  check_same_thread=False), campaign_dir=d, **kw)
        eng._owns_conn = True
        eng._save_setup()
        return eng

    @classmethod
    def open_campaign(cls, name: str, provider: Provider, *, root: Path | str = "campaigns",
                      **kw: Any) -> "Engine":
        """Reopen a saved campaign: events, facts, state and agents come from the log; the scene,
        profiles and language settings from the stored setup. `kw` (models, judge, ...) are
        passed to `Engine`; a setting passed here overrides the stored one."""
        d = cls.campaign_path(name, root)
        if not (d / "campaign.db").exists():
            raise FileNotFoundError(f"no campaign {name!r} in {root}")
        conn = connect(str(d / "campaign.db"), check_same_thread=False)
        meta = {r["key"]: json.loads(r["value"])
                for r in conn.execute("SELECT key, value FROM campaign_meta")}
        if "scene" not in meta or "profiles" not in meta:
            conn.close()
            raise ValueError(f"campaign {name!r} has no saved setup")
        sc = meta["scene"]
        scene = Scene(sc["location"], tuple(sc["present"]), sc["time"], tuple(sc["outside"]))
        profiles = [CharacterProfile(*p) for p in meta["profiles"]]
        for k, v in meta.get("settings", {}).items():
            kw.setdefault(k, v)
        eng = cls(provider, kw.pop("profiles", profiles), scene, conn=conn, campaign_dir=d, **kw)
        eng.vitals = VitalsBook.from_json(meta.get("vitals", []))
        eng._owns_conn = True
        eng._short_portraits = dict(meta.get("short_portraits") or {})
        for pid, raw in eng._short_portraits.items():  # generated portraits: cached, never re-made
            try:  # a bad cached entry must not stop the campaign from opening
                if raw:
                    eng.ctx.portraits[raw["id"]] = parse_portrait(raw, f"npc:{pid}")
            except (PortraitError, KeyError, TypeError) as e:
                eng._note("short_portrait_unreadable", npc=pid, error=str(e)[:200])
                if pid in eng.profiles and eng.profiles[pid].portrait == (raw or {}).get("id"):
                    eng.profiles[pid] = replace(eng.profiles[pid], portrait="")
        eng.refresh_memory()
        return eng

    @staticmethod
    def campaign_exists(name: str, root: Path | str = "campaigns") -> bool:
        return (Engine.campaign_path(name, root) / "campaign.db").exists()
