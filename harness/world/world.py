"""World: the player's place, the world clock, spread of news, collectives, off-screen agents,
authorities and scheduled canon events, around one `Engine` (task 17).

Principles
- Code owns state. Every world fact is an event in the engine's log (types in `news.py`), so a
  rollback of the turn that caused it removes it (news and everything derived have `cause_id`).
- Lazy: a collective's version of a news item is made when it matters (an authority acts on it, or
  the player is where it holds). A person's knowledge of it is made when the player meets them.
- Base mode: no queue. The world waits for the player; time passes with turns, trips and waits, and
  the world catches up in steps (`tick`).
- The player is a being of the world like any other for what the world learns, but the engine never
  judges whether the player's own acts succeed (they are recorded as written).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Sequence

from ..judge import JudgeError, Question, choice_q, score_q, yes_no_q
from ..models import (
    HEARD, PLAYER, UTTERANCE, WITNESSED, CharacterProfile, Event, Fact, Scene,
)
from ..providers import ProviderError
from . import clock as clk
from . import news as nw
from .canon_adapter import CanonSource, NullCanon, ScheduledEvent
from .places import UNLINKED_MINUTES, Place, WorldMap

RECENT_NEWS, RECENT_NEWS_DAYS = 6, 2  # news items offered to the "is this new" judgment
ROUTINE_HOURS = 8  # an agent with a goal and no news gets one judgment this often
STEP_MINUTES, LONG_STEP_MINUTES, LONG_SPAN = 60, 180, 12 * 60
SKIP_STEP_MINUTES, SKIP_SPAN = 720, 3 * 24 * 60  # a skip of days runs in half-day steps
KINDS = ("town", "authority")

# what an off-screen agent can do (the options offered depend on the situation)
A_ROUTINE, A_GOAL, A_REPORT, A_TELL, A_HIDE, A_SEEK = (
    "routine", "goal", "report", "tell_neighbours", "hide", "seek_player")
AGENT_PHRASES = {
    A_ROUTINE: "went back to the usual routine",
    A_GOAL: "worked on their own business",
    A_REPORT: "went to report what happened to {authority}",
    A_TELL: "told neighbours and passers-by what happened",
    A_HIDE: "kept quiet and stayed out of sight",
    A_SEEK: "went looking for the player",
}
AGENT_OPTION_TEXT = {
    A_ROUTINE: "goes on with the usual routine at home or at work",
    A_GOAL: "works toward their own goal",
    A_REPORT: "goes to report it to the authorities",
    A_TELL: "tells neighbours and passers-by what they saw",
    A_HIDE: "keeps quiet and stays out of sight",
    A_SEEK: "goes looking for the player",
}
# an authority's reaction, by scale (the judge picks among the options the scale allows)
R_IGNORE, R_ASK, R_PATROL, R_SEEK = "ignore", "ask_around", "patrol", "seek_player"
REACTION_TEXT = {
    R_IGNORE: "does nothing about it",
    R_ASK: "sends someone to ask questions where it happened",
    R_PATROL: "sends armed men to the place",
    R_SEEK: "orders the person responsible sought and detained",
}
REACTION_PHRASE = {
    R_ASK: "sent someone to ask questions at {place}",
    R_PATROL: "sent armed men to {place}",
    R_SEEK: "ordered the person behind the incident at {place} sought and detained",
}
MUSTER = 10  # minutes to gather men before they walk


@dataclass(frozen=True)
class Collective:
    """A town, a guard, a court: holds one version of each news item and an attitude to it. It is
    registered as a pseudo-character so its knowledge rows and "heard from" lines work like any."""
    id: str
    name: str
    place: str  # its seat (distance for news is measured to here)
    kind: str = "town"  # "town" | "authority"
    covers: tuple[str, ...] = ()  # places whose people share its version; () = its seat only
    up: str | None = None  # the next authority in the chain
    role: str = ""  # one line for the judges

    def covers_place(self, place: str) -> bool:
        return place == self.place or place in self.covers


def pilot_collectives(wmap: WorldMap) -> list[Collective]:
    return [
        Collective("col_town", "городяни Визими", "market", "town", tuple(wmap.places),
                   role="the townsfolk of Vizima: traders, craftsmen, drinkers, gossips"),
        Collective("col_guard", "міська варта", "guardhouse", "authority", ("gate",),
                   up="col_velerad", role="the city guard, practical and wary of trouble"),
        Collective("col_velerad", "Велерад", "palace", "authority", up="col_king",
                   role="Velerad, the king's chief officer for order, cautious and well informed"),
        Collective("col_king", "король Фолтест", "palace", "authority",
                   role="the king of Temeria in his palace"),
    ]


@dataclass
class Plan:
    """What the judge made of a player's turn."""
    duration: str = "minutes"
    move: str = clk.STAY
    wait: str = clk.NO_WAIT


@dataclass
class WorldTurn:
    result: Any  # TurnResult
    plan: Plan
    moved_to: str | None = None
    waited: int = 0
    interrupted_by: str | None = None
    first_event: int = 0  # log id before the turn; `World.report(since=...)` starts here
    news: list[int] = field(default_factory=list)


class World:
    def __init__(self, engine: Any, wmap: WorldMap, *,
                 collectives: Sequence[Collective] | None = None,
                 cast: Mapping[str, str] | None = None,
                 goals: Mapping[str, str] | None = None,
                 canon: CanonSource | None = None,
                 language: str | None = None) -> None:
        """`cast`: character id -> home place id (NPCs who live somewhere; where they are now
        comes from their off-screen updates). `goals`: one sentence per character."""
        self.eng, self.map = engine, wmap
        self.collectives = {c.id: c for c in (collectives if collectives is not None
                                              else pilot_collectives(wmap))}
        self.cast = dict(cast or {})
        self.goals = dict(goals or {})
        self.canon: CanonSource = canon or NullCanon()
        self.language = language or engine.record_language
        for c in self.collectives.values():
            engine.profiles.setdefault(c.id, CharacterProfile(c.id, c.name, c.role))
        if not self._ticks():
            self._log(nw.WORLD_TICK, engine.scene.time, {"to": engine.scene.time})

    # -- small helpers -------------------------------------------------------------------------
    @property
    def now(self) -> int:
        return self.eng.scene.time

    def here(self) -> str | None:
        p = self.map.resolve(self.eng.scene.location)
        return p.id if p else None

    def _log(self, type: str, at: int, payload: dict[str, Any], *, place: str | None = None,
             cause: int | None = None, notability: float = 0.3,
             participants: Sequence[str] = ()) -> Event:
        loc = self.map.name(place) if place else self.eng.scene.location
        return self.eng.log.append(type, game_time=at, location=loc, participants=participants,
                                   witnesses=[], notability=notability,
                                   payload={**payload, "logged_at": self.now}, cause_id=cause)

    def _ask(self, state: list[str], qs: dict[str, Question]) -> Any:
        got = self.eng._ask_safe(state, qs)
        if isinstance(got, JudgeError):
            self.eng._note("world_judge_unavailable", error=str(got))
            return None
        return got

    def _ticks(self) -> list[Event]:
        return self.eng.log.active([nw.WORLD_TICK])

    def _baseline(self) -> int:
        return min((e.payload["to"] for e in self._ticks()), default=self.now)

    def _last_tick(self) -> int:
        ts = self._ticks()
        return max((e.payload["to"] for e in ts), default=self.now)

    def _scene_at(self, place: str | None, at: int) -> Scene:
        return Scene(self.map.name(place) if place else self.eng.scene.location, (), at)

    def _name(self, cid: str) -> str:
        p = self.eng.profiles.get(cid)
        return p.name if p else cid

    # -- news ----------------------------------------------------------------------------------
    def news_events(self) -> list[Event]:
        return self.eng.log.active([nw.WORLD_NEWS])

    def register_news(self, fact_ids: Sequence[int], *, origin: str | None = None) -> list[int]:
        """Facts that are loud enough become news items: they can travel. Quiet ones stay with
        their witnesses. One batched judgment tells a candidate that only restates a recent news
        item (a rumour repeated in a scene is not a new event) from a new matter or a new
        development of an open thread. Returns the ids of the new WORLD_NEWS events."""
        known = {e.payload["fact_id"] for e in self.news_events()}
        cands: list[Fact] = []
        for fid in fact_ids:
            f = self.eng.facts.get(fid)
            if f is None or fid in known or f.notability < nw.NEWS_MIN_NOTABILITY:
                continue
            if not f.knowers:
                continue  # nobody perceived it: nothing to carry
            src = self.eng.log.get(f.source_event_id) if f.source_event_id else None
            if src is not None and src.type == UTTERANCE and f.notability < nw.SPEECH_MIN_NOTABILITY:
                continue  # words are not an event unless they are loud (a proclamation, a threat)
            cands.append(f)
        recent = [e for e in self.news_events() if e.game_time >= self.now - RECENT_NEWS_DAYS * clk.DAY
                  ][-RECENT_NEWS:]
        verdict: dict[int, str] = {}
        if cands and recent:
            qs: dict[str, Question] = {}
            for f in cands:
                opts = {"new": "a new matter, not about any of the listed items"}
                for ne in recent:
                    t = ne.payload["text"][:90]
                    opts[f"same_{ne.id}"] = f"the same event, or only a retelling of or reaction to it: {t}"
                    opts[f"follow_{ne.id}"] = f"a new development of that matter: {t}"
                qs[str(f.id)] = choice_q(f"Is this fact a new matter? Fact: {f.content}", opts,
                                         tag="news_thread")
            got = self._ask(["Recent news items, oldest first."], qs)
            if got:
                verdict = {f.id: str(got[str(f.id)].answer) for f in cands}
        out: list[int] = []
        for f in cands:
            v = verdict.get(f.id, "new")
            if v.startswith("same_"):
                continue  # already news
            thread = None
            if v.startswith("follow_"):
                root = next((e for e in recent if e.id == int(v[7:])), None)
                thread = self.thread_of(root) if root else None
            place = origin or self.here() or self.eng.scene.location
            parts = sorted({k.character for k in f.knowers if k.character not in self.collectives})
            ev = self._log(nw.WORLD_NEWS, f.game_time,
                           {"fact_id": f.id, "origin": place, "notability": f.notability,
                            "text": f.content, "thread": thread, "participants": parts,
                            "unresolved": True},
                           place=place if place in self.map.places else None,
                           cause=f.source_event_id, notability=f.notability)
            out.append(ev.id)
        return out

    # -- threads and the chronicle (hooks for open-threads and a chronicle later) ----------------
    @staticmethod
    def thread_of(ne: Event) -> int:
        return ne.payload.get("thread") or ne.id

    def resolve_thread(self, thread: int, reason: str) -> Event:
        """Mark a thread of events closed (nothing closes threads by itself yet)."""
        return self._log(nw.THREAD_RESOLVED, self.now, {"thread": thread, "reason": reason},
                         cause=thread)

    def open_threads(self, character: str | None = None) -> list[dict[str, Any]]:
        """Unresolved threads, newest development last: [{thread, items, participants, notability,
        text}]; with `character`, only those they take part in."""
        closed = {e.payload["thread"] for e in self.eng.log.active([nw.THREAD_RESOLVED])}
        by: dict[int, list[Event]] = {}
        for ne in self.news_events():
            by.setdefault(self.thread_of(ne), []).append(ne)
        out = []
        for t, items in by.items():
            if t in closed:
                continue
            ps = sorted({p for i in items for p in i.payload.get("participants", [])})
            if character is not None and character not in ps:
                continue
            out.append({"thread": t, "items": [i.id for i in items], "participants": ps,
                        "notability": max(i.payload["notability"] for i in items),
                        "text": items[0].payload["text"]})
        return out

    def chronicle(self, since: int = 0) -> list[dict[str, Any]]:
        """Noteworthy events in order: thread, participants, notability, unresolved."""
        closed = {e.payload["thread"] for e in self.eng.log.active([nw.THREAD_RESOLVED])}
        return [{"id": e.id, "at": e.game_time, "text": e.payload["text"],
                 "thread": self.thread_of(e), "participants": e.payload.get("participants", []),
                 "notability": e.payload["notability"],
                 "unresolved": self.thread_of(e) not in closed}
                for e in self.news_events() if e.id > since]

    def _deliveries(self, news_id: int, col: str) -> list[Event]:
        return [e for e in self.eng.log.active([nw.NEWS_DELIVERY])
                if e.payload["news"] == news_id and e.payload["to"] == col]

    def deliver(self, news: Event, col: str, at: int, carrier: str | None) -> Event:
        return self._log(nw.NEWS_DELIVERY, at, {"news": news.id, "to": col, "at": at,
                                                "carrier": carrier}, cause=news.id)

    def _versions(self, news_id: int) -> dict[str, Event]:
        return {e.payload["holder"]: e for e in self.eng.log.active([nw.NEWS_VERSION])
                if e.payload["news"] == news_id}

    def arrival(self, news: Event, col: Collective) -> tuple[int, str | None, int] | None:
        """(time, source, hops) when the news reaches the collective by the earliest route:
        the spread formula from the origin, or a carrier's delivery. None: it does not."""
        p = news.payload
        cands: list[tuple[int, str | None, int]] = []
        dist = self.map.minutes(p["origin"], col.place)
        d = nw.arrival_delay(p["notability"], dist)
        # a higher authority hears only what the one below passes up (or a carrier brings)
        if d is not None and not any(o.up == col.id for o in self.collectives.values()):
            cands.append((news.game_time + d, self._notional_source(news, col), nw.hops(dist)))
        for e in self._deliveries(news.id, col.id):
            cands.append((e.payload["at"], e.payload["carrier"], 1))
        return min(cands, key=lambda c: c[0]) if cands else None

    def _notional_source(self, news: Event, col: Collective) -> str | None:
        """Who the word notionally came through: the nearest other collective that gets it
        earlier, else one of the witnesses (a non-player if there is one)."""
        p = news.payload
        mine = self.map.minutes(p["origin"], col.place)
        best: tuple[int, str] | None = None
        for o in self.collectives.values():
            if o.id == col.id:
                continue
            od = self.map.minutes(p["origin"], o.place)
            if od < mine and nw.arrival_delay(p["notability"], od) is not None:
                if best is None or od > best[0]:  # the closest one that is still nearer
                    best = (od, o.id)
        if best:
            return best[1]
        f = self.eng.facts.get(p["fact_id"])
        if f:
            ws = [k.character for k in f.knowers if k.how == WITNESSED and k.character != PLAYER
                  and k.character not in self.collectives]
            if ws:
                return ws[0]
        return None

    def resolve(self, upto: int, *, kinds: Sequence[str] = KINDS,
                only: Collective | None = None) -> list[Event]:
        """Make the versions that exist by `upto` and have not been made (lazy). Earlier arrivals
        first, so a later holder can name an earlier one as its source. Authorities that get a
        version react. Returns the NEWS_VERSION events created."""
        created: list[Event] = []
        todo: list[tuple[int, Event, Collective, str | None, int]] = []
        for ne in self.news_events():
            have = self._versions(ne.id)
            for col in ([only] if only else self.collectives.values()):
                if col.kind not in kinds or col.id in have:
                    continue
                arr = self.arrival(ne, col)
                if arr is not None and arr[0] <= upto:
                    todo.append((arr[0], ne, col, arr[1], arr[2]))
        for at, ne, col, source, hop in sorted(todo, key=lambda t: (t[0], t[1].id)):
            ve = self._make_version(ne, col, at, source, hop)
            created.append(ve)
            if col.kind == "authority":
                self._react(ne, col, ve, at)
        return created

    def _make_version(self, ne: Event, col: Collective, at: int, source: str | None,
                      hop: int) -> Event:
        p = ne.payload
        true = nw.about_the_stranger(p["text"])
        origin_name = self.map.name(p["origin"])
        dist = self.map.minutes(p["origin"], col.place)
        state = [f"Event (what truly happened): {true}", f"Where: {origin_name}",
                 f"Notability 0..1: {p['notability']:.2f}",
                 f"Holder: {col.name} ({col.role}), {dist} minutes of walking away, "
                 f"{hop} retelling(s) on the way"]
        got = self._ask(state, {"op": choice_q(
            "When this story is retold on its way to the holder, what most likely happens to it? "
            "Answer none if it is passed on straight (only details are lost).",
            nw.DISTORTIONS, tag="news_operator")})
        op = str(got["op"].answer) if got else nw.NO_DISTORTION
        text, verified = true, True
        if op != nw.NO_DISTORTION:
            written = None
            try:
                raw = self.eng._complete("extractor", nw.writer_messages(
                    true, op, hop, col.name, language=self.language))
                written = nw.clean_version(raw)
            except ProviderError as e:
                self.eng._note("world_version_unavailable", error=str(e))
            if written is None:
                op = nw.NO_DISTORTION
            else:
                text = written
        qs: dict[str, Question] = {
            "stance": choice_q(f"How does {col.name} ({col.role}) take this story?", nw.STANCES,
                               tag="collective_stance"),
            "mag": score_q(f"How strongly does {col.name} feel about it?", legend=(
                "not at all", "slightly", "noticeably", "strongly"), tag="collective_magnitude"),
        }
        if op != nw.NO_DISTORTION:
            qs["derived"] = yes_no_q(
                "Is the retelling the true event with only this change applied: "
                f"{nw.DISTORTIONS[op]}, and nothing else invented?", tag="news_derivable")
        got = self._ask([f"True event: {true}", f"Retelling: {text}"], qs)
        if got and "derived" in got and not got["derived"].answer:
            op, text, verified = nw.NO_DISTORTION, true, False
        ve = self._log(nw.NEWS_VERSION, at, {
            "news": ne.id, "holder": col.id, "place": col.place, "text": text, "operator": op,
            "hops": hop, "source": source, "at": at, "verified": verified},
            place=col.place, cause=ne.id, notability=p["notability"])
        fid = self.eng.facts.add_campaign(
            text, source_event_id=ve.id, game_time=at, location=self.map.name(col.place),
            notability=p["notability"], knowers=[(col.id, HEARD, source)])
        if got:
            stance, mag = str(got["stance"].answer), round(float(got["mag"].answer), 2)
            if stance != "indifference" and mag > 0:
                self.eng.attitudes.set(col.id, fid, stance, mag, self._scene_at(col.place, at),
                                       ve.id)
        return ve

    def version_fact(self, ve: Event) -> Fact | None:
        fs = self.eng.facts.by_source_event(ve.id)
        return fs[0] if fs else None

    # -- people hear (lazy, when the player meets them) -------------------------------------------
    def refresh_place(self) -> list[Event]:
        """The player is at a place: the collectives that cover it make their versions, and the
        NPCs present may have heard one (one yes/no each, batched). Returns NEWS_HEARD events."""
        here = self.here()
        if here is None:
            return []
        for col in self.collectives.values():
            if col.kind == "town" and col.covers_place(here):
                self.resolve(self.now, kinds=("town",), only=col)
        people = [c for c in self.eng.scene.present if c != PLAYER and c not in self.collectives]
        heard: list[Event] = []
        for c in people:
            heard += self._individual_hears(c, here)
        return heard

    def _individual_hears(self, person: str, place: str) -> list[Event]:
        covering = [col for col in self.collectives.values() if col.covers_place(place)]
        out: list[Event] = []
        for ne in self.news_events():
            f = self.eng.facts.get(ne.payload["fact_id"])
            if f is None or any(k.character == person for k in f.knowers):
                continue  # saw it themselves (or told by a witness) already
            versions = self._versions(ne.id)
            options = sorted(((versions[c.id].game_time, c.id, versions[c.id]) for c in covering
                              if c.id in versions), key=lambda t: t[0])
            if not options:
                continue
            at, via, ve = options[0]
            vf = self.version_fact(ve)
            if vf is None or any(k.character == person for k in vf.knowers):
                continue
            prof = self.eng.profiles.get(person)
            bg = self.canon.background(person, ne.payload["text"])
            state = [f"Story going round: {vf.content}", f"Place: {self.map.name(place)}",
                     f"Person: {self._name(person)}"
                     + (f" ({prof.description})" if prof and prof.description else ""),
                     f"It began about {max(self.now - ne.game_time, 0)} minutes ago"
                     + (f"; what they know of such matters: {bg}" if bg else "")]
            got = self._ask(state, {"h": yes_no_q(
                f"Would {self._name(person)} have heard this story by now, given who they are "
                "and what they do all day?", tag="person_heard")})
            if not got or not got["h"].answer:
                continue
            he = self._log(nw.NEWS_HEARD, min(max(at, ne.game_time), self.now),
                           {"news": ne.id, "person": person, "via": via, "fact_id": vf.id},
                           place=place, cause=ve.id, participants=[person])
            self.eng.facts.add_knower(vf.id, person, HEARD, learned_at=he.game_time, source=via,
                                      event_id=he.id)
            out.append(he)
        return out

    # -- authorities -----------------------------------------------------------------------------
    def _react(self, ne: Event, col: Collective, ve: Event, at: int) -> None:
        p = ne.payload
        n = p["notability"]
        opts = [R_IGNORE]
        if n >= 0.65:
            opts.append(R_ASK)
        if n >= 0.75:
            opts.append(R_PATROL)
        if n >= 0.85:
            opts.append(R_SEEK)
        qs: dict[str, Question] = {"act": choice_q(
            f"{col.name} ({col.role}) has just heard this. How does it react, judged by how big "
            "the matter is and who is responsible?",
            {k: REACTION_TEXT[k] for k in opts}, tag="authority_reaction")}
        up = self.collectives.get(col.up) if col.up else None
        if up:
            qs["up"] = yes_no_q(f"Does {col.name} pass this on to {up.name}, who stand above them? "
                                "(Big matters, threats to order and anything magical go up.)",
                                tag="authority_escalate")
        got = self._ask([f"What reached them: {self._version_text(ve)}",
                         f"Where it happened: {self.map.name(p['origin'])}",
                         f"Notability 0..1: {n:.2f}"], qs)
        kind = str(got["act"].answer) if got else (R_ASK if n >= 0.65 else R_IGNORE)
        go_up = bool(got["up"].answer) if got and "up" in got else False
        if up and n >= 0.9:
            go_up = True  # a very big event always reaches the top
        dist = self.map.minutes(col.place, p["origin"])
        if kind != R_IGNORE:
            eta = at + MUSTER + dist
            text = f"{col.name} " + REACTION_PHRASE[kind].format(place=self.map.name(p["origin"]))
            rev = self._log(nw.WORLD_REACTION, at, {
                "news": ne.id, "authority": col.id, "kind": kind, "target": p["origin"],
                "eta": eta, "text": text}, place=col.place, cause=ve.id, notability=0.5)
            self.eng.facts.add_campaign(text, source_event_id=rev.id, game_time=at,
                                        location=self.map.name(col.place), notability=0.5,
                                        knowers=[(col.id, WITNESSED, None)])
        else:
            self._log(nw.WORLD_REACTION, at, {"news": ne.id, "authority": col.id, "kind": R_IGNORE,
                                              "target": None, "eta": None,
                                              "text": f"{col.name} ignored it"},
                      place=col.place, cause=ve.id)
        if go_up and up:
            self.deliver(ne, up.id, at + MUSTER + self.map.minutes(col.place, up.place), col.id)

    def _version_text(self, ve: Event) -> str:
        return ve.payload["text"]

    # -- off-screen agents -----------------------------------------------------------------------
    def updates(self, character: str) -> list[Event]:
        return [e for e in self.eng.log.active([nw.OFFSCREEN_UPDATE])
                if e.payload["character"] == character]

    def where(self, character: str, at: int | None = None) -> str | None:
        """Where a character is now: the place of their latest off-screen update once they have
        arrived (None while in transit), else home."""
        at = self.now if at is None else at
        ups = [u for u in self.updates(character) if u.payload["from"] <= at]
        if ups:
            u = ups[-1]
            return u.payload["place"] if u.payload["arrives"] <= at else None
        return self.cast.get(character)

    def _pending_news(self, c: str, upto: int) -> list[Event]:
        done = {i for u in self.updates(c) for i in u.payload.get("news", [])}
        out = []
        for ne in self.news_events():
            if ne.id in done or ne.game_time > upto or ne.payload["notability"] < nw.NEWS_MIN_NOTABILITY:
                continue
            f = self.eng.facts.get(ne.payload["fact_id"])
            if f and any(k.character == c and k.how == WITNESSED for k in f.knowers):
                out.append(ne)
        return out

    def _eligible(self, upto: int) -> list[str]:
        """Agents the player has dealt with, plus witnesses of loud events, who are not in the
        scene."""
        sc = self.eng.scene
        out = [a for a in self.eng.agents.agents() if a != PLAYER]
        for ne in self.news_events():
            if ne.payload["notability"] >= 0.7:
                f = self.eng.facts.get(ne.payload["fact_id"])
                if f:
                    out += [k.character for k in f.knowers if k.how == WITNESSED
                            and k.character in self.cast]
        return [c for c in dict.fromkeys(out)
                if c not in sc.present and c not in self.collectives and c != PLAYER]

    def _agent_job(self, c: str, start: int, end: int) -> tuple[Any, dict[str, Any]] | None:
        pend = self._pending_news(c, end)
        ups = self.updates(c)
        last = ups[-1].payload["to"] if ups else self._baseline()
        goal = self.goals.get(c)
        routine_due = bool(goal) and end - last >= ROUTINE_HOURS * 60
        if not pend and not routine_due:
            return None
        spot = self.where(c, end)
        auth = next((a for a in self.collectives.values() if a.kind == "authority"), None)
        opts = {A_ROUTINE: AGENT_OPTION_TEXT[A_ROUTINE]}
        if goal:
            opts[A_GOAL] = AGENT_OPTION_TEXT[A_GOAL]
        if pend:
            if auth:
                opts[A_REPORT] = f"goes to report it to {auth.name}"
            opts[A_TELL] = AGENT_OPTION_TEXT[A_TELL]
            opts[A_HIDE] = AGENT_OPTION_TEXT[A_HIDE]
            opts[A_SEEK] = AGENT_OPTION_TEXT[A_SEEK]
        prof = self.eng.profiles.get(c)
        state = [f"Person: {self._name(c)}" + (f" ({prof.description})" if prof and prof.description else ""),
                 f"Goal: {goal or 'none, an ordinary life'}",
                 f"Now: {self.map.name(spot) if spot else 'on the road'}",
                 "What they saw: " + (" | ".join(self.eng.facts.get(n.payload['fact_id']).content  # type: ignore[union-attr]
                                                 for n in pend) or "nothing special"),
                 f"Notability of what they saw (0..1): "
                 + (", ".join(f"{n.payload['notability']:.2f}" for n in pend) or "n/a"),
                 f"Hours since: {(end - start) // 60 or 1}"]
        qs = {"act": choice_q(
            f"What does {self._name(c)} most plausibly do in the next hours? Judge by who they are "
            "and how big what they saw was.", opts, tag="offscreen_act")}
        return (lambda st=state, q=qs: self.eng._ask_safe(st, q)), {"c": c, "pend": pend,
                                                                     "auth": auth, "end": end}

    def _agent_apply(self, meta: dict[str, Any], got: Any) -> Event | None:
        c, pend, end = meta["c"], meta["pend"], meta["end"]
        if isinstance(got, JudgeError):
            self.eng._note("world_judge_unavailable", error=str(got))
            kind = A_ROUTINE
        else:
            kind = str(got["act"].answer)
        spot = self.where(c, end) or self.cast.get(c) or self.here() or "market"
        place, arrives = spot, end
        auth: Collective | None = meta["auth"]
        home = self.cast.get(c, spot)
        phrase = AGENT_PHRASES[kind].format(authority=auth.name if auth else "the authorities")
        if kind == A_ROUTINE:
            place = home
            arrives = end + self.map.minutes(spot, home)
        elif kind == A_REPORT and auth:
            place = auth.place
            arrives = end + self.map.minutes(spot, auth.place)
        elif kind == A_SEEK:
            place = self.here() or spot
            arrives = end + self.map.minutes(spot, place)
        ev = self._log(nw.OFFSCREEN_UPDATE, end, {
            "character": c, "place": place, "arrives": arrives, "kind": kind, "phrase": phrase,
            "from": end, "to": end, "news": [n.id for n in pend]},
            place=spot if spot in self.map.places else None,
            cause=pend[0].id if pend else None, participants=[c])
        if kind == A_REPORT and auth and pend:
            for ne in pend:
                self.deliver(ne, auth.id, arrives, c)
        elif kind == A_TELL and pend:
            town = next((t for t in self.collectives.values()
                         if t.kind == "town" and t.covers_place(spot)), None)
            if town:
                for ne in pend:
                    self.deliver(ne, town.id, end + 15, c)
        if kind in (A_REPORT, A_TELL, A_HIDE, A_SEEK):  # a tellable: something to tell later
            about = self.eng.facts.get(pend[0].payload["fact_id"]).content if pend else ""  # type: ignore[union-attr]
            text = f"{self._name(c)} {phrase} (about: {about})"
            self.eng.facts.add_campaign(text, source_event_id=ev.id, game_time=end,
                                        location=self.map.name(spot), notability=0.4,
                                        knowers=[(c, WITNESSED, None)])
            self.eng.intents.set(c, f"tell the player that I {phrase}",
                                 self._scene_at(spot, end), cause_id=ev.id)
        return ev

    # -- scheduled canon events ------------------------------------------------------------------
    def _executed(self) -> set[str]:
        return {e.payload["canon_id"] for e in self.eng.log.active([nw.CANON_EXECUTED])}

    def _touched(self, ce: ScheduledEvent, place: str) -> list[Event]:
        """News the player's acts made that touch this canon event (same place, or one of its
        people is named)."""
        out = []
        for ne in self.news_events():
            if ne.cause_id is not None and self.eng.log.get(ne.cause_id).type == nw.CANON_EXECUTED:
                continue
            same = ne.payload["origin"] == place
            names = bool(self.eng.names.mentions(ne.payload["text"], list(ce.participants))
                         ) if ce.participants else False
            if same or names:
                out.append(ne)
        return out

    def _place_id(self, ref: str) -> str:
        p = self.map.resolve(ref)
        if p is None:
            p = self.map.add_place(Place(ref, ref))
        return p.id

    def run_canon(self, after: int, upto: int) -> list[Event]:
        done = self._executed()
        out: list[Event] = []
        for ce in sorted(self.canon.scheduled(after, upto), key=lambda e: e.t):
            if ce.id in done:
                continue
            place = self._place_id(ce.place)
            touched = self._touched(ce, place)
            outcome = "as_written"
            if touched:
                got = self._ask(
                    [f"Canon event (planned): {ce.summary}", f"Place: {self.map.name(place)}",
                     "What the player has done since that bears on it: "
                     + " | ".join(t.payload["text"] for t in touched[:5])],
                    {"c": choice_q(
                        "Given what the player did, does this planned event still happen?",
                        {"as_written": "it happens as planned",
                         "differently": "it happens, but differently or with other people",
                         "not_happen": "it does not happen any more"}, tag="canon_event")})
                outcome = str(got["c"].answer) if got else "as_written"
            ev = self._log(nw.CANON_EXECUTED, ce.t, {
                "canon_id": ce.id, "outcome": outcome, "summary": ce.summary,
                "touched": [t.id for t in touched]}, place=place, notability=ce.notability)
            out.append(ev)
            done.add(ce.id)
            if outcome == "not_happen":
                continue
            text = ce.summary + (" (this went differently than first planned)"
                                 if outcome == "differently" else "")
            knowers = [(k, WITNESSED) for k in ce.participants]
            knowers += [(k, HEARD, None) for k in ce.knowers if k not in ce.participants]
            fid = self.eng.facts.add_campaign(
                text, source_event_id=ev.id, game_time=ce.t, location=self.map.name(place),
                notability=ce.notability, knowers=knowers)
            self.register_news([fid], origin=place)
        return out

    # -- advancing time ---------------------------------------------------------------------------
    def tick(self, to: int, *, interruptible: bool = False) -> str | None:
        """Catch the world up to `to` in steps. The clock ends at `to`. Returns why it stopped
        early (an authority's men arrived where the player is), else None."""
        eng = self.eng
        last = self._last_tick()
        if to <= last:
            return None
        span = to - last
        size = (SKIP_STEP_MINUTES if span > SKIP_SPAN
                else LONG_STEP_MINUTES if span > LONG_SPAN else STEP_MINUTES)
        t, stop = last, None
        while t < to:
            end = min(t + size, to)
            eng.scene.time = end
            self.run_canon(t, end)
            self.resolve(end, kinds=("authority",))
            jobs = [(c, j) for c in self._eligible(end) if (j := self._agent_job(c, t, end))]
            for (c, (_, meta)), got in zip(jobs, eng._map([j[0] for _, j in jobs])):
                self._agent_apply(meta, got)
            self.resolve(end, kinds=("authority",))  # deliveries made above may already be due
            self._log(nw.WORLD_TICK, end, {"to": end})
            hit = self._arrivals(t, end)
            t = end
            if hit and interruptible:
                stop = hit
                break
        eng.scene.time = t if stop else to
        eng._save_scene()
        return stop

    def _arrivals(self, start: int, end: int) -> str | None:
        """An authority's men reach the place the player is at: a fact everyone present
        perceives, and the wait stops."""
        here = self.here()
        if here is None:
            return None
        seen = {e.payload["reaction"] for e in self.eng.log.active([nw.WORLD_ARRIVAL])}
        hit = None
        for rev in self.eng.log.active([nw.WORLD_REACTION]):
            p = rev.payload
            if (p["kind"] in (R_ASK, R_PATROL, R_SEEK) and p["target"] == here
                    and start < p["eta"] <= end and rev.id not in seen):
                text = f"{self._name(p['authority'])} men arrive at {self.map.name(here)}: " \
                       + REACTION_PHRASE[p["kind"]].format(place="this place")
                ev = self._log(nw.WORLD_ARRIVAL, p["eta"], {
                    "reaction": rev.id, "text": text}, place=here, cause=rev.id,
                    notability=0.6)
                present = [c for c in self.eng.scene.present]
                self.eng.facts.add_campaign(
                    text, source_event_id=ev.id, game_time=p["eta"],
                    location=self.map.name(here), notability=0.6,
                    knowers=[(c, WITNESSED) for c in present])
                hit = text
        return hit

    # -- the player moves, waits, plays ------------------------------------------------------------
    def go_to(self, dest: str) -> int:
        """The player walks to another place: the scene is left (those present stay behind), the
        time of the trip passes (the world catches up), the new scene is entered by whoever is
        there now. Returns the minutes taken."""
        eng = self.eng
        p = self.map.resolve(dest)
        if p is None:
            raise KeyError(f"unknown place {dest!r}")
        here = self.here()
        minutes = self.map.minutes(here, p.id) if here else UNLINKED_MINUTES
        for c in [c for c in eng.scene.present if c != PLAYER]:
            eng.leave_scene(c, stay_nearby=False)
        eng.scene.outside = ()
        start = self.now
        self._log(nw.WORLD_MOVE, start, {"kind": "travel", "from": here, "to": p.id,
                                         "minutes": minutes}, place=here)
        eng.scene.location = "on the way to " + p.name
        self.tick(start + minutes)
        eng.scene.location = p.name
        eng._save_scene()
        for c in [c for c in self.cast if c != PLAYER and self.where(c) == p.id]:
            if c not in eng.scene.present:
                eng.enter_scene(c)
        self.refresh_place()
        return minutes

    def wait(self, minutes: int) -> str | None:
        """Time passes with the player where they are; stops early if something arrives."""
        start = self.now
        self._log(nw.WORLD_MOVE, start, {"kind": "wait", "from": self.here(), "to": self.here(),
                                         "minutes": minutes}, place=self.here())
        stop = self.tick(start + minutes, interruptible=True)
        for c in [c for c in self.cast if c != PLAYER and self.where(c) == self.here()]:
            if c not in self.eng.scene.present:
                self.eng.enter_scene(c)
        self.refresh_place()
        return stop

    def skip_days(self, days: int) -> dict[str, Any]:
        """Skip `days` of in-world time (the cheap off-screen sim for the known NPCs runs in
        half-day steps), then write, for every agent who did something meanwhile, a derived
        period summary: a record in the agent's own memory, linked to the updates it came from.
        Interruptible like a wait. Years are a hook: see `skip_years`."""
        start = self.now
        stop = self.wait(days * clk.DAY)
        summaries = self.summarise_period(start, self.now)
        return {"from": start, "to": self.now, "stopped": stop, "summaries": summaries}

    def skip_years(self, years: int) -> None:
        """Hook, not built. Would run `skip_days` in season-sized steps, then age the cast,
        decay collective moods and let the canon pull re-judge scheduled events; the same
        period-summary records would be written per agent."""
        raise NotImplementedError("skipping years is a documented hook (task 17)")

    def summarise_period(self, start: int, end: int) -> list[Event]:
        """One derived PERIOD_SUMMARY per agent with updates in [start, end]: code-built from the
        agent's updates (no model call), stored as a fact the agent knows (they lived it), with
        `cause_id` = the first update so a rollback removes it."""
        out: list[Event] = []
        for c in self._eligible(end) + [a for a in self.eng.agents.agents() if a != PLAYER]:
            ups = [u for u in self.updates(c) if start < u.game_time <= end]
            if not ups or any(e.payload["character"] == c and e.payload["from"] == start
                              for e in self.eng.log.active([nw.PERIOD_SUMMARY])):
                continue
            seen: dict[str, int] = {}
            for u in ups:
                if u.payload["kind"] not in (A_ROUTINE, A_GOAL):  # the ordinary is one line
                    seen[u.payload["phrase"]] = seen.get(u.payload["phrase"], 0) + 1
            what = ("; ".join(f"{p}" + (f" ({n} times)" if n > 1 else "") for p, n in seen.items())
                    or "went about the usual routine")
            text = (f"{self._name(c)}, from day {clk.parts(start)['day']} to day "
                    f"{clk.parts(end)['day']}: {what}.")
            ev = self._log(nw.PERIOD_SUMMARY, end, {
                "character": c, "from": start, "to": end, "text": text,
                "sources": [u.id for u in ups]}, cause=ups[0].id, participants=[c])
            self.eng.facts.add_campaign(text, source_event_id=ev.id, game_time=end,
                                        location=self.eng.scene.location, notability=0.3,
                                        knowers=[(c, WITNESSED, None)])
            out.append(ev)
        return out

    def interpret(self, text: str) -> Plan:
        """One batched judgment: duration, a trip, a wait."""
        here = self.here()
        qs = clk.interpret_questions({pid: p.name for pid, p in self.map.places.items()},
                                     here or "")
        got = self._ask([f"The player's turn: {text}", f"Now: {self.eng.scene.location}",
                         f"Time of day: {self.now % clk.DAY // 60:02d}:{self.now % 60:02d}"], qs)
        if not got:
            return Plan()
        return Plan(str(got["duration"].answer), str(got["move"].answer), str(got["wait"].answer))

    def play(self, text: str, **turn_kw: Any) -> WorldTurn:
        """One player turn in the world: interpret it, travel or wait if it says so, let the people
        here hear what has reached them, run the scene turn, register what became news, and let
        the world catch up for the minutes the turn took."""
        eng = self.eng
        first = max((e.id for e in eng.log.active()), default=0)
        plan = self.interpret(text)
        wt = WorldTurn(None, plan, first_event=first)
        moved = plan.move != clk.STAY and plan.move in self.map.places
        if moved:
            wt.moved_to = plan.move
            wt.waited = self.go_to(plan.move)
        elif plan.wait != clk.NO_WAIT:
            mins = (clk.minutes_of(plan.duration) if plan.wait == clk.WAIT_FOR
                    else clk.until_hour(self.now, clk.WAIT_TARGETS[plan.wait][1]))
            before = self.now
            if mins >= 2 * clk.DAY:  # days pass: the cheap sim for the known NPCs and summaries
                sk = self.skip_days(mins // clk.DAY)
                wt.interrupted_by = sk["stopped"]
            else:
                wt.interrupted_by = self.wait(mins)
            wt.waited = self.now - before
        else:
            self.refresh_place()
        turn_minutes = clk.minutes_of(plan.duration)
        if moved or plan.wait != clk.NO_WAIT:
            turn_minutes = min(turn_minutes, 5)
        saved, eng.minutes_per_turn = eng.minutes_per_turn, turn_minutes
        try:
            wt.result = eng.turn(text, **turn_kw)
        finally:
            eng.minutes_per_turn = saved
        wt.news = self.register_news(wt.result.fact_ids)
        stop = self.tick(eng.scene.time, interruptible=True)
        wt.interrupted_by = wt.interrupted_by or stop
        self.refresh_place()
        return wt

    # -- the debug view ("світ") ----------------------------------------------------------------
    def mood(self, col_id: str) -> list[dict[str, Any]]:
        out = []
        for a in self.eng.attitudes.of(col_id):
            f = self.eng.facts.get(a.fact_id)
            out.append({"stance": a.stance, "magnitude": a.magnitude,
                        "about": f.content if f else ""})
        return out

    def report(self, since: int = 0) -> dict[str, Any]:
        """What happened beyond the scene since log id `since`: news with every version (who
        holds it, the operator, the source, when), who heard it, authorities' reactions,
        off-screen updates, canon events, and the moods of the collectives."""
        log = self.eng.log
        sel = lambda *ts: [e for e in log.active(ts) if e.id > since]  # noqa: E731
        names = self._name
        versions = [e for e in log.active([nw.NEWS_VERSION])]
        heard = [e for e in log.active([nw.NEWS_HEARD])]
        news_out = []
        for ne in self.news_events():
            vs = [v for v in versions if v.payload["news"] == ne.id]
            hs = [h for h in heard if h.payload["news"] == ne.id]
            news_out.append({
                "id": ne.id, "new": ne.id > since, "text": ne.payload["text"],
                "notability": ne.payload["notability"],
                "origin": self.map.name(ne.payload["origin"]), "at": ne.game_time,
                "versions": [{
                    "new": v.id > since, "holder": names(v.payload["holder"]),
                    "place": self.map.name(v.payload["place"]), "text": v.payload["text"],
                    "operator": v.payload["operator"], "hops": v.payload["hops"],
                    "source": names(v.payload["source"]) if v.payload["source"] else None,
                    "at": v.payload["at"], "verified": v.payload["verified"],
                    "stance": next((a["stance"] for a in self.mood(v.payload["holder"])
                                    if a["about"] == v.payload["text"]), None)} for v in vs],
                "heard_by": [{"new": h.id > since, "person": names(h.payload["person"]),
                              "via": names(h.payload["via"]), "at": h.game_time} for h in hs],
            })
        return {
            "clock": {"now": self.now, "place": self.eng.scene.location},
            "news": news_out,
            "reactions": [{"authority": names(e.payload["authority"]), "kind": e.payload["kind"],
                           "text": e.payload["text"], "at": e.game_time, "eta": e.payload["eta"]}
                          for e in sel(nw.WORLD_REACTION)],
            "offscreen": [{"character": names(e.payload["character"]),
                           "what": e.payload["phrase"], "kind": e.payload["kind"],
                           "place": self.map.name(e.payload["place"]), "at": e.game_time,
                           "arrives": e.payload["arrives"]} for e in sel(nw.OFFSCREEN_UPDATE)],
            "summaries": [{"character": names(e.payload["character"]), "text": e.payload["text"]}
                          for e in sel(nw.PERIOD_SUMMARY)],
            "threads": self.open_threads(),
            "arrivals": [{"text": e.payload["text"], "at": e.game_time}
                         for e in sel(nw.WORLD_ARRIVAL)],
            "canon": [{"id": e.payload["canon_id"], "outcome": e.payload["outcome"],
                       "summary": e.payload["summary"], "at": e.game_time}
                      for e in sel(nw.CANON_EXECUTED)],
            "moves": [e.payload for e in sel(nw.WORLD_MOVE)],
            "mood": {cid: self.mood(cid) for cid in self.collectives},
        }
