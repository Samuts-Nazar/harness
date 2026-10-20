"""Game session: runs turns on the engine in a worker thread and publishes an ordered event
stream (word by word) that any number of clients can read, resume and replay.

Events are plain dicts with a global increasing `seq`. Only the current/last turn's events are
kept; finished turns live in `transcript`, so a page reload or a phone coming back from the
background gets `transcript` + the events it missed.
"""
from __future__ import annotations

import threading
import time
from typing import Any, Callable

from harness.models import PLAYER, format_time
from harness.streaming import InterruptHandle

from harness.outcome import CampaignEnded

from .campaigns import Campaign

CATEGORY_UK = {"injury": "тіло", "clothing": "одяг", "inventory": "речі",
               "equipment": "спорядження", "internal": "відчуття", "appearance": "вигляд"}


class Busy(RuntimeError):
    pass


class Ended(RuntimeError):
    """The player character is dead: the campaign is read-only."""


def clock(t: int) -> str:
    day, rem = divmod(t, 24 * 60)
    return f"день {day + 1} · {rem // 60:02d}:{rem % 60:02d}"


def explain(e: BaseException) -> str:
    """A short player-facing message; never includes keys or long bodies."""
    name = type(e).__name__
    status = getattr(getattr(e, "response", None), "status_code", None)
    if status:
        return f"Модель відповіла помилкою HTTP {status}. Спробуйте ще раз."
    if name in ("ConnectError", "ReadTimeout", "ConnectTimeout", "TimeoutException"):
        return "Немає зв'язку з моделлю (мережа або таймаут). Спробуйте ще раз."
    if name == "BudgetExceeded":
        return "Вичерпано ліміт витрат на цей запуск."
    return f"Не вдалося виконати хід ({name}): {str(e)[:200]}"


class Game:
    def __init__(self, open_campaign: Callable[[bool], Campaign], pace: float = 0.25) -> None:
        """`open_campaign(new)`: the saved current campaign (new=False) or a fresh one."""
        self._open = open_campaign
        self.pace = pace
        self.lock = threading.RLock()
        self.visible = threading.Event()
        self.visible.set()
        self.seq = 0
        self.events: list[dict[str, Any]] = []
        self.thread: threading.Thread | None = None
        self.threads: list[threading.Thread] = []
        self.challenging = False
        self.reset(new=False)

    # -- campaign ---------------------------------------------------------------------------
    def reset(self, new: bool = True) -> None:
        """Start a new campaign (the saved one stays on disk), or with new=False continue the
        current one. Refused while a turn runs."""
        with self.lock:
            if self.running or self.challenging:
                raise Busy("a turn is running")
            self.camp = self._open(new)
            self.transcript: list[dict[str, Any]] = self.camp.transcript()
            self.phase = "idle"  # idle | thinking | narrating | speaking
            self.handle: InterruptHandle | None = None
            self.skip_narration = False
            self.debug: dict[str, Any] = {}
            self.events = []
            self._panel = self._compute_panel()
            self.turn_start_seq = self.seq
            self._emit("reset")
            self.turn_start_seq = self.seq

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    @property
    def eng(self):  # type: ignore[no-untyped-def]
        return self.camp.engine

    # -- events -----------------------------------------------------------------------------
    def _emit(self, type: str, **data: Any) -> dict[str, Any]:
        with self.lock:
            self.seq += 1
            ev = {"seq": self.seq, "type": type, **data}
            self.events.append(ev)
            return ev

    def events_after(self, after: int) -> list[dict[str, Any]]:
        with self.lock:
            return [e for e in self.events if e["seq"] > after]

    # -- views ------------------------------------------------------------------------------
    def panel(self) -> dict[str, Any]:
        """Cached view (recomputed only when no turn runs, so the DB has a single user)."""
        return self._panel

    def _compute_panel(self) -> dict[str, Any]:
        """The player character's state as the character perceives it: chips for live state
        (own body is perceived, hidden or not) and a few sentences from what the character knows.
        Nothing the character did not perceive can appear: it is read from the character's own
        derived memory."""
        mem = self.eng.deriver.derive(PLAYER, self.eng.scene.time)
        items = [e.item for e in mem.state]
        prose = [self.eng.ctx.mask(PLAYER, it.fact.content).rstrip(".") + "."
                 for it in mem.knows[-4:]]
        tr = self.camp.translate  # records are English; the panel is shown in Ukrainian
        if tr is not None:
            both = tr(items + prose)
            items, prose = both[: len(items)], both[len(items):]
        chips = [{"text": t, "category": e.category, "label": CATEGORY_UK[e.category],
                  "observable": e.observable} for t, e in zip(items, mem.state)]
        return {"name": self.eng.profiles[PLAYER].name, "chips": chips, "prose": prose}

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "title": self.camp.title, "live": self.camp.live, "clock": self.clock(),
                "transcript": list(self.transcript), "panel": self.panel(),
                "running": self.running, "phase": self.phase,
                "ended": self.eng.ended, "chronicle": self.chronicle() if self.eng.ended else [],
                # a client replays everything after this; for an idle game that is nothing
                "resume_after": self.turn_start_seq if self.running else self.seq,
                "pending_turn": getattr(self, "pending", None) if self.running else None,
            }

    def clock(self) -> str:
        return clock(self.eng.scene.time)

    def chronicle(self) -> list[dict[str, Any]]:
        """The final chronicle screen after the death of the player character."""
        from harness.outcome import chronicle
        return chronicle(self.eng)

    # -- presence (the world pauses while the app is in the background) ---------------------
    def set_visible(self, visible: bool) -> None:
        (self.visible.set if visible else self.visible.clear)()

    # -- turn -------------------------------------------------------------------------------
    def start_turn(self, text: str) -> None:
        text = text.strip()
        if not text:
            raise ValueError("empty input")
        with self.lock:
            if self.eng.ended:
                raise Ended("the character is dead; the campaign is read-only")
            # a turn may start while the slow lane of the last one still runs (it waits for it)
            if self.phase != "idle" or self.challenging:
                raise Busy("a turn is already running")
            self.pending = text
            self.phase = "thinking"
            self.turn_start_seq = self.seq
            self.events = []
            self._emit("turn_start", text=text)
            self.thread = threading.Thread(target=self._run, args=(text,), daemon=True)
            self.threads = [t for t in self.threads if t.is_alive()] + [self.thread]
            self.thread.start()

    # -- "how does he know that?" ------------------------------------------------------------
    def challenge(self, event: int, explanation: str = "") -> dict[str, Any]:
        """The player marks an NPC line as impossible. No channel: the line is regenerated with
        the explanation (if it is the last one) and the feed is updated; a channel: the answer says
        how the character knows (type and rough time; the full event for the spoiler tap)."""
        from dataclasses import asdict

        with self.lock:
            if self.running or self.challenging:
                raise Busy("a turn is running")
            self.challenging = True
        try:
            res = self.eng.challenge_line(event, explanation)
            out = asdict(res)
            if res.regenerated:
                for en in self.transcript:
                    if en.get("kind") == "npc" and en.get("event") == event:
                        en.update(text=res.text, event=res.new_event)
                        en.pop("cut", None)
                self._panel = self._compute_panel()
            self.debug = {**self.debug, "challenge": out,
                          "notes": self.debug.get("notes", []) + self.eng.devlog[-3:]}
            return out
        finally:
            self.challenging = False

    def knowledge(self) -> dict[str, Any]:
        """The debug view: per character, what they know and from where."""
        with self.lock:
            if self.running or self.challenging:
                raise Busy("a turn is running")
            eng = self.eng
            return {c: {"name": eng.profiles[c].name, "label": eng.names.label(c),
                        "items": eng.knowledge_report(c)} for c in eng.profiles}

    def interrupt(self) -> str:
        """The interrupt button. Returns what was interrupted."""
        with self.lock:
            if self.phase == "speaking" and self.handle is not None:
                self.handle.request()
                return "speech"
            if self.phase == "narrating":
                self.skip_narration = True
                return "narration"
            return "none"

    def _pace(self) -> None:
        self.visible.wait()  # nothing is "said" while the app is in the background
        if self.pace:
            time.sleep(self.pace)

    def _run(self, text: str) -> None:
        eng, rec, spend = self.eng, self.camp.recorder, self.camp.spend
        t0 = time.monotonic()
        eng._settle_for_next_turn()  # the slow lane of the last turn, if it is still running
        waited = round(time.monotonic() - t0, 2)
        marks = {"calls": len(rec.calls), "dev": len(eng.devlog),
                 "judg": len(eng.judgments.entries), "cost": getattr(spend, "total", 0.0)}
        first_word: list[float] = []
        new_events: list[dict[str, Any]] = []
        entries: list[dict[str, Any]] = [{"kind": "player", "text": text}]
        narr_words: list[str] = []
        cur: dict[str, Any] = {"who": None}

        def stamp() -> None:
            if not first_word:
                first_word.append(round(time.monotonic() - t0, 2))

        def on_event(ev) -> None:  # type: ignore[no-untyped-def]
            new_events.append({"id": ev.id, "type": ev.type, "game_time": ev.game_time,
                               "payload": ev.payload, "participants": list(ev.participants)})

        def on_narration(narration: str) -> None:
            self._stream_narration(narration, narr_words, stamp)

        def on_word(npc: str, w: str) -> None:
            self.visible.wait()
            if cur["who"] != npc:
                cur["who"] = npc
                self.phase = "speaking"
                name = eng.ctx.label(PLAYER, npc)  # a stranger stays "a stout grey-haired man"
                self._emit("speaker", who=npc, name=name)
                entries.append({"kind": "npc", "who": npc, "name": name, "text": ""})
            stamp()
            entries[-1]["text"] = (entries[-1]["text"] + " " + w).strip()
            self._emit("word", who=npc, w=w)
            if self.pace:
                time.sleep(self.pace)

        world = getattr(self.camp, "world", None)
        since = max((e.id for e in eng.log.active()), default=0)
        unsubscribe = eng.log.subscribe(on_event)
        self.handle = InterruptHandle()
        self.skip_narration = False
        try:
            if world is not None:  # the world interprets the turn (trip, wait) and catches up
                r = world.play(text, defer_slow=True, handle=self.handle, on_word=on_word,
                               on_narration=on_narration).result
            else:
                r = eng.turn(text, handle=self.handle, on_word=on_word, on_narration=on_narration,
                             defer_slow=True)
        except BaseException as e:  # noqa: BLE001 - shown to the player, the input is kept
            self.phase = "idle"
            self._emit("error", message=explain(e), text=text, detail=type(e).__name__)
            self._save_debug(marks, new_events, t0, first_word, error=repr(e)[:300])
            if isinstance(e, CampaignEnded):
                self._emit("ended", chronicle=self.chronicle())
            return
        finally:
            unsubscribe()
        if r.interrupted and entries[-1]["kind"] == "npc":
            entries[-1]["cut"] = True
        line_events = iter(u.id for u in r.utterances)
        for en in entries:  # lets the player question a line afterwards ("how does he know?")
            if en["kind"] == "npc":
                en["event"] = next(line_events, None)
        if narr_words:
            entries.insert(1, {"kind": "narr", "text": " ".join(narr_words)})
        fast_s = round(time.monotonic() - t0, 2)
        with self.lock:
            self.transcript += entries
            self.phase = "idle"  # the player can read and type now; bookkeeping goes on below
            self._emit("turn_done", interrupted=r.interrupted, clock=self.clock(),
                       panel=self._panel, lines=[u.id for u in r.utterances], settling=True)
        # the slow lane: extraction, salience, attitudes, world catch-up (while the player reads)
        eng.settle()
        failure, eng.slow_failure = eng.slow_failure, None
        with self.lock:
            if failure is not None:
                del self.transcript[len(self.transcript) - len(entries) - (1 if narr_words else 0):]
                self._save_debug(marks, new_events, t0, first_word, error=repr(failure)[:300])
                self._emit("retract", message=explain(failure), text=text)
                return
            self._save_debug(marks, new_events, t0, first_word, report=eng.reports[-1],
                             fast_s=fast_s, waited=waited)
            if world is not None:
                self.debug = {**self.debug, "world": world.report(since)}
            self._panel = self._compute_panel()
            self._emit("settled", panel=self._panel, clock=self.clock())
            if eng.ended:
                self._emit("ended", chronicle=self.chronicle())

    def _stream_narration(self, text: str, spoken: list[str], stamp: Callable[[], None]) -> None:
        self.phase = "narrating"
        self._emit("narr_start")
        for w in text.split():
            if self.skip_narration:
                break
            self.visible.wait()
            stamp()
            spoken.append(w)
            self._emit("narr_word", w=w)
            if self.pace:
                time.sleep(self.pace)
        self._emit("narr_end", cut=self.skip_narration)
        self.phase = "thinking"

    def _save_debug(self, marks: dict[str, Any], new_events: list[dict[str, Any]], t0: float,
                    first_word: list[float], error: str | None = None,
                    report: dict[str, Any] | None = None, fast_s: float | None = None,
                    waited: float = 0.0) -> None:
        eng, rec, spend = self.eng, self.camp.recorder, self.camp.spend
        self.debug = {
            "events": new_events,
            "judgments": eng.judgments.entries[marks["judg"]:],
            "calls": rec.calls[marks["calls"]:],
            "notes": eng.devlog[marks["dev"]:],
            "timing": {"first_word_s": first_word[0] if first_word else None,
                       # total_s: until the player has everything to read; slow_s: the slow lane
                       "total_s": fast_s if fast_s is not None else round(time.monotonic() - t0, 2),
                       "slow_s": round(time.monotonic() - t0 - fast_s, 2) if fast_s else 0.0,
                       "waited_s": waited},
            "lanes": eng.lane_stats[-1] if eng.lane_stats else None,
            "cost": round(getattr(spend, "total", 0.0) - marks["cost"], 6),
            "error": error,
            "repetition": (report or {}).get("repetition"),
            "names": (report or {}).get("names"),
            "parallel": eng.parallel,
        }

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Until the turn and its slow lane are done."""
        for t in list(self.threads) or ([self.thread] if self.thread else []):
            t.join(timeout)
