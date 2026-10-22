"""Game session: runs turns on the engine in a worker thread and publishes an ordered event
stream (word by word) that any number of clients can read, resume and replay.

Events are plain dicts with a global increasing `seq`. Only the current/last turn's events are
kept; finished turns live in `transcript`, so a page reload or a phone coming back from the
background gets `transcript` + the events it missed.
"""
from __future__ import annotations

import re
import threading
import time
from typing import Any, Callable

from harness import assistant
from harness.decisions import DecisionCount, aggregate, count_since
from harness.models import ACTION, NARRATION, PLAYER, UTTERANCE, format_time
from harness.streaming import InterruptHandle

from harness.outcome import CampaignEnded
from harness.pipeline import InterruptionError

from .campaigns import Campaign
from .inks import INK_RE, assign_ink

CATEGORY_UK = {"injury": "тіло", "clothing": "одяг", "inventory": "речі",
               "equipment": "спорядження", "internal": "відчуття", "appearance": "вигляд"}


class Busy(RuntimeError):
    pass


class Refused(ValueError):
    """The correction is not allowed now; the message is shown to the player."""


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


_PLAYER_WORDS = re.compile(
    r"(?<!\w)(?:the\s+)?player(?:\s+character)?(?!\w)|(?<!\w)гравц(?:ем|еві|ю|я|і)(?!\w)"
    r"|(?<!\w)гравець(?!\w)", re.IGNORECASE)
# the oblique cases of the player as «ви»: no name has to be declined
_VY = {"ем": "вами", "еві": "вам", "ю": "вам", "я": "вас", "і": "вас"}


def _as_the_character(text: str, name: str = "") -> str:
    """A record's wording for the player («гравцем», «Гравець», "the player") as the player
    character in what the people drawer shows. The nominative («Гравець», "the player") becomes
    the name, so the singular verb agrees («Рагнар бачив»); «ви» when there is no name. The
    oblique cases become pronouns, which need no agreement (гравцем -> вами, гравцеві/гравцю ->
    вам, гравця/на гравці -> вас)."""
    if not text:
        return text

    def sub(m: "re.Match[str]") -> str:
        w = m.group(0).lower()
        if w.startswith("гравц") and not w.startswith("гравець"):
            return _VY[w[5:]]
        return name or "ви"

    out = _PLAYER_WORDS.sub(sub, text)
    return out[:1].upper() + out[1:] if text[:1].isupper() else out


class Game:
    def __init__(self, open_campaign: Callable[[bool], Campaign], pace: float = 0.25,
                 suggestions: bool = True,
                 open_package: Callable[[Any], Campaign] | None = None) -> None:
        """`open_campaign(new)`: the saved current campaign (new=False) or a fresh one.
        `open_package(pkg)`: a new campaign from a game package (app/newgame.py)."""
        self._open = open_campaign
        self.open_package = open_package
        self.suggest_on = suggestions  # off for replays: the assistant's calls are not recorded
        self.base_pace = pace
        self.pace = pace  # `skip()` sets it to 0 for the rest of the turn
        self.start_lock = threading.Lock()  # one start_turn at a time (interrupt, wait, start)
        self.lock = threading.RLock()
        # the event list has its own small lock: the SSE stream reads it without ever waiting
        # for the game's lock (which a turn's bookkeeping may hold)
        self._ev_lock = threading.Lock()
        self.visible = threading.Event()
        self.visible.set()
        self.seq = 0
        self.events: list[dict[str, Any]] = []
        self.thread: threading.Thread | None = None
        self.threads: list[threading.Thread] = []
        self.challenging = False
        self.building = False  # a new campaign is being made (outside the lock: it is slow)
        self.turn_no = 0  # every turn's events carry its id, so a client scopes them per turn
        self._tl = threading.local()  # the turn id of the running thread
        self.reset(new=False)

    # -- campaign ---------------------------------------------------------------------------
    def reset(self, new: bool = True,
              opener: Callable[[bool], Campaign] | None = None) -> None:
        """Start a new campaign (the saved one stays on disk), or with new=False continue the
        current one. `opener`: how to make it instead of the default (a game package). Refused
        while a turn runs."""
        with self.lock:
            if self.running or self.challenging or self.building:
                raise Busy("a turn is running")
            self.building = True
        try:  # the build (a model call, the database) and the first views (translations) run
            # without the lock: state() still answers with the campaign before
            camp = (opener or self._open)(new)
            ended = camp.engine.ended
            transcript: list[dict[str, Any]] = camp.transcript()
            seen: list[str] = camp.speaker_ids()  # characters met, first seen first
            recency: list[str] = []  # tokens, least recently active first
            for t in transcript:
                if t.get("tok"):
                    self._touch(t["tok"], recency)
            panel = self._compute_panel(camp)
            cast = self._compute_cast(camp, seen, recency)
            known = self._compute_known(cast, camp)
            camp.inks.flush()
        finally:
            with self.lock:
                self.building = False
        with self.lock:
            self.camp = camp
            self._ended = ended  # read again whenever no turn's thread uses the database
            self.transcript = transcript
            self.phase = "idle"  # idle | thinking | narrating | speaking
            self.handle: InterruptHandle | None = None
            self.skip_narration = False
            self.debug: dict[str, Any] = {}
            self.decision_log: list[tuple[str, DecisionCount]] = []  # (location, turn count)
            with self._ev_lock:
                self.events = []
            self._sugg: dict[str, Any] | None = None  # the turn's suggestions (see _suggest)
            self._panel = panel
            self._seen = seen
            self._recency = recency
            self._cast = cast
            self._known: dict[str, list[str]] = known
            self.turn_start_seq = self.seq
            self._emit("reset")
            self.turn_start_seq = self.seq

    def start_package(self, pkg: Any) -> None:
        """A new campaign from a validated game package (Busy while a turn runs)."""
        if self.open_package is None:
            raise RuntimeError("no game package support in this app")
        self.reset(True, opener=lambda _new: self.open_package(pkg))  # type: ignore[misc]

    @property
    def running(self) -> bool:
        return self.thread is not None and self.thread.is_alive()

    @property
    def eng(self):  # type: ignore[no-untyped-def]
        return self.camp.engine

    def _is_ended(self) -> bool:
        """Is the player character dead? Read from the database only while no turn's thread is
        alive and no correction runs (one SQLite connection must not be used from two threads at
        once); otherwise the value left by the last user. Call with `self.lock` held."""
        if not self.running and not self.challenging:
            self._ended = self.eng.ended
        return self._ended

    # -- events -----------------------------------------------------------------------------
    def _emit(self, type: str, **data: Any) -> dict[str, Any]:
        turn = getattr(self._tl, "turn", None)
        if turn is not None:
            data.setdefault("turn", turn)
        with self._ev_lock:
            self.seq += 1
            ev = {"seq": self.seq, "type": type, **data}
            self.events.append(ev)
            return ev

    def events_after(self, after: int) -> list[dict[str, Any]]:
        """Never waits for the game's lock: only for the event list's own, held for a moment."""
        with self._ev_lock:
            return [e for e in self.events if e["seq"] > after]

    # -- cast and inks ------------------------------------------------------------------------
    def _touch(self, tok: str, recency: list[str] | None = None) -> None:
        rec = self._recency if recency is None else recency
        if tok in rec:
            rec.remove(tok)
        rec.append(tok)

    def _note_speaker(self, cid: str) -> str:
        """A character spoke or acted: they join the cast and become the most recent. Returns the
        opaque token. Called from the turn's thread (the only user of the database then)."""
        with self.lock:
            tok = self.camp.tok(cid)
            if cid not in self._seen:
                self._seen.append(cid)
            self._touch(tok)
            self._cast = self._compute_cast()
            return tok

    def _compute_cast(self, camp: Campaign | None = None, seen: list[str] | None = None,
                      recency: list[str] | None = None) -> list[dict[str, Any]]:
        """Who the player character has met or sees now: token, the label the character perceives
        (a stranger by appearance), ink and presence. Inks are assigned on first sight; only the
        characters present now compete for distinct inks. Reads the database (labels): call it
        on the thread that may use it."""
        camp = camp or self.camp
        eng, book = camp.engine, camp.inks
        seen = self._seen if seen is None else seen
        recency = list(self._recency if recency is None else recency)
        present = set(eng.scene.present)
        ids = [c for c in seen if c != PLAYER]
        ids += [c for c in eng.scene.present if c != PLAYER and c not in ids]
        toks = {c: camp.tok(c) for c in ids}
        labels = {c: eng.ctx.label(PLAYER, c) for c in ids}
        with book.lock:
            for c in ids:
                t = toks[c]
                if t not in book.inks:
                    others = [toks[o] for o in ids if o != c and o in present]
                    book.set(t, assign_ink(others, book.inks, recency))
            return [{"tok": toks[c], "label": labels[c], "ink": book.inks[toks[c]],
                     "present": c in present} for c in ids]

    def _swap_cast(self, cast: list[dict[str, Any]]) -> None:
        """Put a cast computed outside the lock in place; an ink the player picked meanwhile
        wins. Call with `self.lock` held."""
        book = self.camp.inks
        for c in cast:
            c["ink"] = book.get(c["tok"]) or c["ink"]
        self._cast = cast

    def cast(self) -> list[dict[str, Any]]:
        with self.lock:
            return [dict(c) for c in self._cast]

    def set_ink(self, tok: str, ink: str) -> None:
        """The player picks a character's ink (any character of the campaign, by token)."""
        if not isinstance(ink, str) or not INK_RE.match(ink):
            raise ValueError("bad ink")
        with self.lock:  # the cast is the request thread's view: no database read here
            if not any(c["tok"] == tok for c in self._cast):
                raise KeyError(tok)
            self.camp.inks.set(tok, ink.lower())
            for c in self._cast:
                if c["tok"] == tok:
                    c["ink"] = ink.lower()
            self._emit("ink", tok=tok, ink=ink.lower())
        self.camp.inks.flush()

    def _compute_known(self, cast: list[dict[str, Any]] | None = None,
                       camp: Campaign | None = None) -> dict[str, list[str]]:
        """Per cast token, a few short things the player character knows about that person,
        from the character's own derived memory and masked like everything the player sees.
        A fact counts as about a person when it mentions their name or appearance. The records'
        wording for the player («гравець», "the player") becomes the character's own name. All
        translations go in one call. Reads the database and may call a model: never under the
        game's lock."""
        camp = camp or self.camp
        cast = self._cast if cast is None else cast
        eng = camp.engine
        mem = eng.deriver.derive(PLAYER, eng.scene.time)
        raw = [it.fact.content for it in mem.knows]
        by_tok = {camp.tok(i): i for i in eng.profiles}
        out: dict[str, list[str]] = {}
        for c in cast:
            cid = by_tok.get(c["tok"])
            if cid is None:
                continue
            p = eng.profiles[cid]
            keys = [k.lower() for k in (p.name, p.appearance) if k]
            hidden = not eng.names.knows(PLAYER, cid)
            facts = []
            for text in raw:
                if not any(k in text.lower() for k in keys):
                    continue
                shown = eng.ctx.mask(PLAYER, text).rstrip(".") + "."
                if hidden and p.name.lower() in shown.lower():
                    continue  # the mask missed a form of the name: better nothing than a leak
                if shown not in facts:
                    facts.append(shown)
            out[c["tok"]] = facts[-4:]
        tr = camp.translate
        flat = [f for facts in out.values() for f in facts]
        if tr is not None and flat:
            done = iter(eng.ctx.mask(PLAYER, t) for t in tr(flat))  # again: see _compute_panel
            out = {t: [next(done) for _ in facts] for t, facts in out.items()}
        me = eng.profiles[PLAYER].name if PLAYER in eng.profiles else ""
        return {t: [_as_the_character(f, me) for f in facts] for t, facts in out.items()}

    def people(self) -> list[dict[str, Any]]:
        with self.lock:
            return [{**c, "known": list(self._known.get(c["tok"], []))} for c in self._cast]

    # -- views ------------------------------------------------------------------------------
    def panel(self) -> dict[str, Any]:
        """Cached view (recomputed only when no turn runs, so the DB has a single user)."""
        return self._panel

    def _compute_panel(self, camp: Campaign | None = None) -> dict[str, Any]:
        """The player character's state as the character perceives it: chips for live state
        (own body is perceived, hidden or not) and a few sentences from what the character knows.
        Nothing the character did not perceive can appear: it is read from the character's own
        derived memory. Reads the database and may call a model: never under the game's lock."""
        camp = camp or self.camp
        eng = camp.engine
        mem = eng.deriver.derive(PLAYER, eng.scene.time)
        items = [e.item for e in mem.state]
        prose = [eng.ctx.mask(PLAYER, it.fact.content).rstrip(".") + "."
                 for it in mem.knows[-4:]]
        tr = camp.translate  # records are English; the panel is shown in Ukrainian
        if tr is not None:
            both = tr(items + prose)
            # the records may spell a name in Latin, which the mask does not know; the translator
            # turns it into the Ukrainian one: mask the translated text again
            both = [eng.ctx.mask(PLAYER, t) for t in both]
            items, prose = both[: len(items)], both[len(items):]
        chips = [{"text": t, "category": e.category, "label": CATEGORY_UK[e.category],
                  "observable": e.observable} for t, e in zip(items, mem.state)]
        return {"name": eng.profiles[PLAYER].name, "chips": chips, "prose": prose}

    def state(self) -> dict[str, Any]:
        with self.lock:
            return {
                "title": self.camp.title, "live": self.camp.live, "clock": self.clock(),
                "transcript": list(self.transcript), "panel": self.panel(),
                "running": self.running, "phase": self.phase, "turn": self.turn_no,
                "ended": self._is_ended(), "assistant": self.camp.assistant,
                # what the server supports; the client offers them when it is not busy (a
                # correction asked for in the slow lane waits for it, see _begin_edit)
                "actions": self.actions(),
                "chronicle": self.chronicle() if self._is_ended() and not self.running else [],
                # a client replays everything after this; for an idle game that is nothing
                "resume_after": self.turn_start_seq if self.running else self.seq,
                "pending_turn": getattr(self, "pending", None) if self.running else None,
            }

    def actions(self) -> list[str]:
        """The optional line actions this server supports (none once the campaign ended).
        Call with `self.lock` held."""
        return [] if self._is_ended() else ["model_error", "cut"]

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
    def start_turn(self, text: str, wait: float = 60.0) -> None:
        """Start a turn. While one runs, the new text cuts in: the running turn is interrupted at
        its current point, this waits until the player is free to read again (the slow lane may
        go on), then the new turn starts."""
        text = text.strip()
        if not text:
            raise ValueError("empty input")
        with self.start_lock:
            with self.lock:
                if self._is_ended():
                    raise Ended("the character is dead; the campaign is read-only")
                if self.challenging or self.building:
                    raise Busy("a challenge is running")
                if self.phase != "idle":
                    self.interrupt(any_phase=True)
            end = time.monotonic() + wait
            while self.phase != "idle":  # the interrupted turn finishes within a word or a step
                if time.monotonic() > end:
                    raise Busy("the running turn did not stop")
                time.sleep(0.01)
            with self.lock:
                if self._is_ended():
                    raise Ended("the character is dead; the campaign is read-only")
                if self.challenging or self.building:  # began while this waited
                    raise Busy("a challenge is running")
                self.pending = text
                self._sugg = None  # suggestions of the turn before are stale from now on
                self.phase = "thinking"
                self.pace = self.base_pace
                self.handle = InterruptHandle()
                self.skip_narration = False
                # keep the turn before (from its start): a client polling the stream must still
                # get its turn_done when this new text cut it in a moment ago
                with self._ev_lock:
                    self.events = [e for e in self.events if e["seq"] > self.turn_start_seq]
                self.turn_start_seq = self.seq
                self.turn_no += 1
                self._emit("turn_start", text=text, turn=self.turn_no)
                # the last turn's thread may still be in its slow lane and bookkeeping: the new
                # one waits for it before it touches the engine
                self.thread = threading.Thread(
                    target=self._run, args=(text, self.handle, self.thread, self.turn_no),
                    daemon=True)
                self.threads = [t for t in self.threads if t.is_alive()] + [self.thread]
                self.thread.start()

    # -- "how does he know that?" ------------------------------------------------------------
    def challenge(self, event: int, explanation: str = "") -> dict[str, Any]:
        """The player marks an NPC line as impossible. No channel: the line is regenerated with
        the explanation (if it is the last one) and the feed is updated; a channel: the answer says
        how the character knows (type and rough time; the full event for the spoiler tap)."""
        from dataclasses import asdict

        self._claim(check_ended=False)
        try:
            res = self.eng.challenge_line(event, explanation)
            out = asdict(res)
            self._apply_regen(res, event, "npc")
            self.debug = {**self.debug, "challenge": out,
                          "notes": self.debug.get("notes", []) + self.eng.devlog[-3:]}
            return out
        finally:
            self.challenging = False

    def _apply_regen(self, res: Any, event: int, kind: str) -> None:
        """Show a regenerated (or withdrawn) output in the transcript and refresh what depends
        on the log. Call with `challenging` set (no turn thread uses the database)."""
        if res.regenerated:
            for en in self.transcript:
                if en.get("kind") == kind and en.get("event") == event:
                    en.update(text=res.text, event=res.new_event)
                    en.pop("cut", None)
        elif res.withdrawn:  # the line is gone and nothing replaces it: no empty bubble
            self.transcript[:] = [en for en in self.transcript
                                  if not (en.get("kind") == kind and en.get("event") == event)]
        else:
            return
        self._refresh_after_edit()

    def _refresh_after_edit(self) -> None:
        """Called with `challenging` set (this thread is the database's only user): the views
        and the assistant's context are computed outside the lock, then swapped in."""
        panel, cast, known = self._views()
        ctx = self._assistant_context(self.turn_no)
        with self.lock:
            self._panel = panel
            self._swap_cast(cast)
            self._known = known
            self._sugg = None  # the suggestions were made for the output that changed
            self._start_suggestions(self.turn_no, ctx)

    def _views(self) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, list[str]]]:
        """Panel, cast and what the character knows about each person. Reads the database and
        may call the translator: only on the thread that is the database's user, without the
        lock (so the stream and the other requests keep answering)."""
        panel = self._compute_panel()
        cast = self._compute_cast()
        return panel, cast, self._compute_known(cast)

    def _claim(self, wait: float = 60.0, check_ended: bool = True) -> None:
        """Take the engine for a correction. Busy while a turn is being told or another
        correction or a build runs. In a turn's slow lane (the player is reading) this waits
        for it, up to `wait` seconds, like a new turn would."""
        with self.start_lock:  # no new turn starts while this waits
            end = time.monotonic() + wait
            while True:
                with self.lock:
                    if self.challenging or self.building or self.phase != "idle":
                        raise Busy("a turn is running")
                    if not self.running:
                        if check_ended and self._is_ended():
                            raise Ended("the character is dead; the campaign is read-only")
                        self.challenging = True
                        return
                if time.monotonic() > end:
                    raise Busy("the turn's bookkeeping did not finish")
                time.sleep(0.02)

    def _begin_edit(self) -> None:
        self._claim()

    def model_error(self, event: int | None, explanation: str) -> dict[str, Any]:
        """«Помилка моделі»: only the last world output is regenerated with the player's
        explanation (stored per campaign, fed to later generations); the turn stays. `event`
        None: the last narration passage."""
        from dataclasses import asdict

        explanation = explanation.strip()
        if not explanation:
            raise ValueError("the explanation is required")
        self._begin_edit()
        try:
            last_player = max((i for i, en in enumerate(self.transcript)
                               if en["kind"] == "player"), default=-1)
            world = [en for en in self.transcript[last_player + 1:]
                     if en["kind"] in ("narr", "npc", "npc_act")]
            tail = world[-1] if world else None
            if (tail is None or tail.get("event") is None
                    or (event is not None and tail.get("event") != event)
                    or (event is None and tail["kind"] != "narr")):  # null: the narration
                raise Refused("Помилку моделі можна позначити лише на останньому, що сказав чи "
                              "описав світ (репліка або опис). Це вже не воно.")
            event, kind = tail["event"], tail["kind"]
            try:
                res = self.eng.model_error(event, explanation)
            except ValueError as e:
                raise Refused("Це вже не останнє, що сказав чи описав світ.") from e
            out = asdict(res)
            if kind == "npc_act":  # the transcript shows the gesture as the player sees it
                res.text = self.eng.ctx.mask(PLAYER, res.text).strip()
            self._apply_regen(res, event, kind)
            self.debug = {**self.debug, "model_error": out,
                          "notes": self.debug.get("notes", []) + self.eng.devlog[-3:]}
            return out
        finally:
            self.challenging = False

    def cut(self, event: int, after_words: int) -> dict[str, Any]:
        """Retroactive interruption of the last NPC line after `after_words` words: what follows
        was never said (facts from it are rolled back by the engine), the NPC keeps the rest as a
        private intent. Allowed only while that line is the last thing in the story."""
        self._begin_edit()
        try:
            tail = self.transcript[-1] if self.transcript else {}
            if tail.get("kind") != "npc" or tail.get("event") != event or tail.get("cut"):
                raise ValueError("only the last NPC line, once")
            try:
                kept = self.eng.interrupt_retroactive(int(after_words))
            except InterruptionError as e:
                raise ValueError(str(e)) from e
            tail.update(text=kept.payload["text"], event=kept.id, cut=True)
            self._refresh_after_edit()
            return {"event": kept.id, "text": kept.payload["text"], "cut": True}
        finally:
            self.challenging = False

    def places(self) -> list[dict[str, Any]]:
        """Where the player character can go from here: the world map's other places with the
        walking minutes, nearest first. [] when the campaign has no world."""
        with self.lock:
            world = getattr(self.camp, "world", None)
            if world is None:
                return []
            wmap = world.map
            here = wmap.resolve(self.eng.scene.location)
            if here is not None and not wmap.edges.get(here.id):
                return []  # a start place off the map (added unlinked): no made-up distances
            out = []
            for p in wmap.places.values():
                if here is not None and p.id == here.id:
                    continue
                item: dict[str, Any] = {"name": p.name,
                                        "go": ("Іду " + p.to) if p.to else f"Іду: {p.name}"}
                if here is not None:  # without a known position no distance is shown
                    item["minutes"] = wmap.minutes(here.id, p.id)
                out.append(item)
            return sorted(out, key=lambda x: (x.get("minutes", 0), x["name"]))

    def knowledge(self) -> dict[str, Any]:
        """The debug view: per character, what they know and from where."""
        with self.lock:
            if self.running or self.challenging or self.building:
                raise Busy("a turn is running")
            eng = self.eng
            return {c: {"name": eng.profiles[c].name, "label": eng.names.label(c),
                        "items": eng.knowledge_report(c)} for c in eng.profiles}

    def interrupt(self, any_phase: bool = False) -> str:
        """The interrupt button. Returns what was interrupted. `any_phase`: also while the world
        is still thinking (typing a new text cuts the running turn wherever it is)."""
        with self.lock:
            if self.phase == "speaking" and self.handle is not None:
                self.handle.request()
                return "speech"
            if self.phase == "narrating":
                self.skip_narration = True
                if any_phase and self.handle is not None:
                    self.handle.request()
                return "narration"
            if any_phase and self.phase == "thinking" and self.handle is not None:
                self.handle.request()
                self.skip_narration = True
                return "turn"
            return "none"

    def skip(self) -> bool:
        """Tap to skip the pace: the rest of this turn's words arrive at once. Not an interrupt:
        nothing is cut. The pace comes back with the next turn."""
        with self.lock:
            if self.phase == "idle":
                return False
            self.pace = 0
            return True

    def _pace(self) -> None:
        self.visible.wait()  # nothing is "said" while the app is in the background
        if self.pace:
            time.sleep(self.pace)

    def _run(self, text: str, handle: InterruptHandle,
             last: threading.Thread | None = None, turn: int | None = None) -> None:
        eng, rec, spend = self.eng, self.camp.recorder, self.camp.spend
        t0 = time.monotonic()
        self._tl.turn = turn  # every event this thread emits belongs to this turn
        if last is not None and last is not threading.current_thread():
            last.join()  # one thread on the engine and its database at a time
        try:
            self._turn(text, handle, eng, rec, spend, t0)
        finally:
            self._ended = eng.ended  # this thread is the database's only user here
            self.camp.inks.flush()  # inks given to new characters this turn (no lock held)

    def _turn(self, text: str, handle: InterruptHandle, eng: Any, rec: Any, spend: Any,
              t0: float) -> None:
        eng._settle_for_next_turn()  # the slow lane of the last turn, if it is still running
        waited = round(time.monotonic() - t0, 2)
        marks = {"calls": len(rec.calls), "dev": len(eng.devlog),
                 "judg": len(eng.judgments.entries), "where": eng.scene.location,
                 "llm": len(eng.llm_calls),
                 "cost": getattr(spend, "total", 0.0)}
        first_word: list[float] = []
        new_events: list[dict[str, Any]] = []
        narr_ids: list[int] = []
        entries: list[dict[str, Any]] = [{"kind": "player", "text": text}]
        cur: dict[str, Any] = {"who": None}  # the NPC whose block the next word extends

        def stamp() -> None:
            if not first_word:
                first_word.append(round(time.monotonic() - t0, 2))

        def on_event(ev) -> None:  # type: ignore[no-untyped-def]
            new_events.append({"id": ev.id, "type": ev.type, "game_time": ev.game_time,
                               "payload": ev.payload, "participants": list(ev.participants)})
            if ev.type == NARRATION and str(ev.payload.get("text", "")).strip():
                narr_ids.append(ev.id)
            if ev.type == UTTERANCE:
                cur["who"] = None  # the line is over: the next word starts a new block
            elif ev.type == ACTION and ev.payload.get("gesture"):
                # a gesture-only step of an NPC: shown as their action, in its place in the talk
                who = ev.payload.get("by") or (ev.participants[0] if ev.participants else "")
                label = eng.ctx.label(PLAYER, who)
                act = eng.ctx.mask(PLAYER, str(ev.payload.get("text", ""))).strip()
                if act:
                    tok = self._note_speaker(who)
                    entries.append({"kind": "npc_act", "tok": tok, "label": label, "text": act,
                                    "event": ev.id})
                    self._emit("npc_act", tok=tok, label=label, text=act, event=ev.id)
                cur["who"] = None

        def on_narration(narration: str) -> None:
            spoken: list[str] = []
            self._stream_narration(narration, spoken, stamp)
            if spoken:
                entries.append({"kind": "narr", "text": " ".join(spoken)})

        def on_word(npc: str, w: str) -> None:
            self.visible.wait()
            if cur["who"] != npc or entries[-1]["kind"] != "npc":
                cur["who"] = npc
                self.phase = "speaking"
                label = eng.ctx.label(PLAYER, npc)  # a stranger stays "a stout grey-haired man"
                tok = self._note_speaker(npc)
                self._emit("speaker", tok=tok, label=label)
                entries.append({"kind": "npc", "tok": tok, "label": label, "text": ""})
            stamp()
            entries[-1]["text"] = (entries[-1]["text"] + " " + w).strip()
            self._emit("word", tok=self.camp.tok(npc), w=w)
            pace = self.pace  # a tap on the stream sets it to 0 mid-turn
            if pace:
                time.sleep(pace)

        world = getattr(self.camp, "world", None)
        since = max((e.id for e in eng.log.active()), default=0)
        unsubscribe = eng.log.subscribe(on_event)
        try:
            if world is not None:  # the world interprets the turn (trip, wait) and catches up
                r = world.play(text, defer_slow=True, handle=handle, on_word=on_word,
                               on_narration=on_narration).result
            else:
                r = eng.turn(text, handle=handle, on_word=on_word, on_narration=on_narration,
                             defer_slow=True)
        except BaseException as e:  # noqa: BLE001 - shown to the player, the input is kept
            self._ended = eng.ended
            self.phase = "idle"
            self._emit("error", message=explain(e), text=text, detail=type(e).__name__)
            self._save_debug(marks, new_events, t0, first_word, error=repr(e)[:300])
            if isinstance(e, CampaignEnded):
                self._emit("ended", chronicle=self.chronicle())
            return
        finally:
            unsubscribe()
        # lines that were really delivered (a line cut before its first word has no block)
        shown = [u for u in r.utterances if u.payload.get("text", "").strip()]
        npc_entries = [en for en in entries if en["kind"] == "npc"]
        for en, u in zip(npc_entries, shown):  # lets the player question a line afterwards
            en["event"] = u.id
            if u.payload.get("interrupted"):
                en["cut"] = True
        line_ids = [en["event"] for en in npc_entries if "event" in en]
        cut_ids = [en["event"] for en in npc_entries if en.get("cut") and "event" in en]
        for en, nid in zip([en for en in entries if en["kind"] == "narr"], narr_ids):
            en["event"] = nid  # lets the player say what is wrong with the narration
        turn_id = getattr(self._tl, "turn", None)
        for en in entries:
            en["turn"] = turn_id  # a reloaded client matches its replay by this
        fast_s = round(time.monotonic() - t0, 2)
        with self.lock:
            self.transcript += entries
            self._ended = eng.ended  # before the player is free: a death shows at once
            self.phase = "idle"  # the player can read and type now; bookkeeping goes on below
            self._emit("turn_done", interrupted=r.interrupted, clock=self.clock(),
                       panel=self._panel, lines=line_ids, cut_lines=cut_ids, settling=True)
        # the slow lane: extraction, salience, attitudes, world catch-up (while the player reads)
        eng.settle()
        failure, eng.slow_failure = eng.slow_failure, None
        with self.lock:
            if failure is not None:
                del self.transcript[len(self.transcript) - len(entries):]
                self._save_debug(marks, new_events, t0, first_word, error=repr(failure)[:300])
                self._emit("retract", message=explain(failure), text=text)
                return
            self._save_debug(marks, new_events, t0, first_word, report=eng.reports[-1],
                             fast_s=fast_s, waited=waited)
            if world is not None:
                self.debug = {**self.debug, "world": world.report(since)}
        # this thread is the database's only user until it ends: the views (one translator call
        # each), the chronicle and the assistant's context are made without the lock, so the
        # stream and the other requests keep answering meanwhile
        panel, cast, known = self._views()  # labels may have changed: a name was learned
        turn = getattr(self._tl, "turn", None)
        ended = eng.ended
        chron = self.chronicle() if ended else None
        ctx = None if ended else self._assistant_context(turn)
        with self.lock:
            self._ended = ended
            self._panel = panel
            self._swap_cast(cast)
            self._known = known
            self._emit("settled", panel=self._panel, clock=self.clock(), actions=self.actions())
            if ended:
                self._emit("ended", chronicle=chron)
            else:
                self._start_suggestions(turn, ctx)

    # -- turn assistant ---------------------------------------------------------------------
    def _assistant_context(self, turn: int | None) -> Any:
        """The player character's view for the turn assistant, rendered on the thread that is
        the database's only user (the turn's, or a correction's), without the lock. None: no
        suggestions for this turn."""
        if (not self.suggest_on or not self.camp.assistant or turn is None
                or turn != self.turn_no):
            return None
        try:
            return assistant.context(self.eng)
        except Exception:  # noqa: BLE001 - suggestions are optional; the turn is already done
            return None

    def _start_suggestions(self, turn: int | None, ctx: Any) -> None:
        """Ask the model for suggestions on a thread of its own, from a context rendered before
        (`_assistant_context`). The next turn does not wait for it. Call with `self.lock` held."""
        if ctx is None or turn is None or turn != self.turn_no:
            return
        state: dict[str, Any] = {"turn": turn, "ctx": ctx, "items": []}
        self._sugg = state
        th = threading.Thread(target=self._suggest, args=(state, self.camp), daemon=True)
        self.threads = [t for t in self.threads if t.is_alive()] + [th]
        th.start()

    def _suggest(self, state: dict[str, Any], camp: Campaign) -> None:
        try:
            items = assistant.ask(camp.engine, state["ctx"], 3)
        except Exception:  # noqa: BLE001 - no suggestions is a normal outcome
            return
        with self.lock:
            if self._sugg is not state or self.camp is not camp or not items:
                return  # a new turn (or campaign) began meanwhile: the answer is stale
            state["items"] += items
            self._emit("suggestions", turn=state["turn"], items=list(items))

    def suggestions(self, more: bool = False, n: int = 3) -> dict[str, Any]:
        """The shown suggestions of the last turn; `more`: n new ones that avoid the shown."""
        with self.lock:
            state = self._sugg
            if state is None:
                return {"turn": self.turn_no, "items": []}
            shown = list(state["items"])
            if not more:
                return {"turn": state["turn"], "items": shown}
            camp = self.camp
        items = assistant.ask(camp.engine, state["ctx"], n, shown)  # no database access
        with self.lock:
            if self._sugg is not state or self.camp is not camp:
                return {"turn": self.turn_no, "items": []}
            items = [i for i in items if i not in state["items"]]
            state["items"] += items
            return {"turn": state["turn"], "items": items}

    def _stream_narration(self, text: str, spoken: list[str], stamp: Callable[[], None]) -> None:
        if not text.strip():  # an empty narration is never a bubble
            return
        self.phase = "narrating"
        self._emit("narr_start")
        for w in text.split():
            if self.skip_narration:
                break
            self.visible.wait()
            stamp()
            spoken.append(w)
            self._emit("narr_word", w=w)
            pace = self.pace
            if pace:
                time.sleep(pace)
        self._emit("narr_end", cut=self.skip_narration)
        self.phase = "thinking"

    def _decisions(self, turn: DecisionCount | None, where: str) -> dict[str, Any] | None:
        """The turn's decision count with the running scene (same location) and session totals."""
        if turn is None:
            return None
        self.decision_log.append((where, turn))
        scene = []
        for loc, d in reversed(self.decision_log):
            if loc != where:
                break
            scene.append(d)
        return {"turn": turn.as_dict(), "scene": aggregate(scene).as_dict(),
                "session": aggregate(d for _, d in self.decision_log).as_dict()}

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
            "dialogue": eng.dialogue_report(),
            "names": (report or {}).get("names"),
            "parallel": eng.parallel,
            "assistant_calls": len(eng.assistant_calls),  # session total, apart from decisions
            "decisions": self._decisions(
                count_since(eng, 0, marks["judg"], marks["llm"], marks["dev"]), marks["where"]),
        }

    def wait_idle(self, timeout: float = 30.0) -> None:
        """Until the turn and its slow lane are done."""
        end = time.monotonic() + timeout
        while True:  # a finishing turn starts its suggestion thread: look again after each join
            alive = [t for t in (list(self.threads) or ([self.thread] if self.thread else []))
                     if t.is_alive()]
            if not alive or time.monotonic() > end:
                return
            alive[0].join(max(end - time.monotonic(), 0.01))
