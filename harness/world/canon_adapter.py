"""The one place where the world touches `harness.canon` (task 19 wires it to the real task 16 API).

`CanonSource` is what the world needs: scheduled canon events after a time (campaign minutes),
what a person knows from their own life on a topic, and, when the player may have changed an
event's preconditions, a proportional-pull verdict with a reason (task 16's `judge_event`).

`PlayCanon` is the real source: it wraps a `harness.canon.play.CanonPlay` (a campaign that starts
inside the canon) and converts between canon entity ids / story minutes and engine character ids /
campaign minutes. `NullCanon` has nothing; `ListCanon` is for tests and scripted pilots.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class ScheduledEvent:
    """A canon event the world executes when its time comes. `t` is in campaign minutes; `place`
    a world place id or name; `participants`/`knowers` engine character (or collective) ids."""
    id: str
    t: int
    place: str
    participants: tuple[str, ...]
    summary: str
    knowers: tuple[str, ...] = ()
    notability: float = 0.5
    raw: Any = field(default=None, compare=False, repr=False)  # the canon-side event, if any


@dataclass(frozen=True)
class Verdict:
    outcome: str      # "as_written" | "differently" | "not_happen"
    reason: str = ""
    new_summary: str | None = None


class CanonSource(Protocol):
    def scheduled(self, after_t: int, up_to_t: int) -> Sequence[ScheduledEvent]: ...
    def background(self, character: str, topic: str) -> str | None: ...


class NullCanon:
    def scheduled(self, after_t: int, up_to_t: int) -> Sequence[ScheduledEvent]:
        return ()

    def background(self, character: str, topic: str) -> str | None:
        return None


@dataclass
class ListCanon:
    """A fixed list of events and a dict of background answers (tests, scripted pilots)."""
    events: list[ScheduledEvent] = field(default_factory=list)
    knowledge: dict[tuple[str, str], str] = field(default_factory=dict)

    def scheduled(self, after_t: int, up_to_t: int) -> Sequence[ScheduledEvent]:
        return [e for e in self.events if after_t < e.t <= up_to_t]

    def background(self, character: str, topic: str) -> str | None:
        return self.knowledge.get((character, topic))


class PlayCanon:
    """The real canon (task 16) for the world. `groups`: canon collective id -> world collective id
    (or engine id); `places`: canon place entity -> world place id (an unmapped place keeps its
    display name, which the world adds to its map). `text_call` is a cheap-model call for the
    proportional-pull verdict (prompt -> text); `judge` the typed judge for background."""

    def __init__(self, play: Any, judge: Any, *, groups: Mapping[str, str] | None = None,
                 places: Mapping[str, str] | None = None,
                 text_call: Callable[[str], str] | None = None,
                 phrase: Callable[[str], str] | None = None) -> None:
        self.play, self.judge = play, judge
        self.groups, self.places = dict(groups or {}), dict(places or {})
        self.text_call, self.phrase = text_call, phrase
        self.eng: Any = None
        self._by_id: dict[str, Any] = {}

    def bind(self, eng: Any) -> None:
        """The world gives the engine once; background answers are stored through it."""
        self.eng = eng

    # -- ids ---------------------------------------------------------------------------------
    def cid(self, entity: str) -> str:
        from ..canon.play import cid_of
        return self.groups.get(entity) or self.play.made.get(entity) or cid_of(entity)

    def entity(self, cid: str) -> str | None:
        for ent, c in self.play.made.items():
            if c == cid:
                return ent
        for ent, c in self.groups.items():
            if c == cid:
                return ent
        return None

    def place_of(self, entity: str | None, name: str | None) -> str:
        if entity and entity in self.places:
            return self.places[entity]
        return name or entity or "?"

    # -- the world's three needs -----------------------------------------------------------------
    def scheduled(self, after_t: int, up_to_t: int) -> Sequence[ScheduledEvent]:
        """Events in (after_t, up_to_t] campaign minutes."""
        out = []
        after_t = max(after_t, self.play.start.to_campaign_t(self.play.start.start_t))  # never the past
        for e in self.play.upcoming(after_t, up_to_t):
            self._by_id[str(e.id)] = e
            out.append(ScheduledEvent(
                id=str(e.id), t=self.play.start.to_campaign_t(e.t),
                place=self.place_of(e.place, e.place_name),
                participants=tuple(self.cid(p) for p in e.participants),
                summary=e.summary,
                knowers=tuple(dict.fromkeys(self.cid(k.entity) for k in e.knowers)),
                notability=e.notability, raw=e))
        return out

    def background(self, character: str, topic: str) -> str | None:
        ent = self.entity(character)
        if ent is None or self.eng is None:
            return None  # not a canon person: no life to read
        got = self.play.know_from_life(self.eng, ent, topic, self.judge, phrase=self.phrase)
        return got.text if got else None

    def verdict(self, ev: ScheduledEvent, changes: Sequence[str]) -> Verdict:
        """Proportional canon pull with a reason (task 16 `judge_event`)."""
        from ..canon import api
        raw = ev.raw or self._by_id.get(ev.id)
        if raw is None or self.text_call is None:
            return Verdict("as_written", "no judge available: the event stands as written")
        v = api.judge_event(self.play.canon, raw, list(changes), judge=self.text_call,
                            at_t=ev.t)
        outcome = {"happens": "as_written", "differently": "differently",
                   "does_not_happen": "not_happen"}.get(v.outcome, "as_written")
        return Verdict(outcome, v.reason, v.new_summary)


def default_source() -> CanonSource:
    return NullCanon()
