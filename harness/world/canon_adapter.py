"""The one place where the world touches `harness.canon.api` (task 16).

The agreed shape (brief of task 17): `ScheduledEvent(id, t, place, participants, summary, knowers,
notability)` and `background(character, topic) -> knowledge or None`. If `harness.canon.api` is
there it is used; otherwise the same dataclass is defined here and the source is empty. Nothing
else in `harness.world` imports from canon.

`CanonSource` is what the world needs: events after a time, background knowledge on a topic. The
default `NullCanon` has nothing; tests pass a `ListCanon`.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, Sequence

try:  # task 16 defines the real thing
    from ..canon import api as _api  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001 - not merged yet, or the canon package needs data we lack
    _api = None


@dataclass(frozen=True)
class ScheduledEvent:
    """A canon event the world executes when its time comes. `t` is in-world minutes on the
    campaign clock; `place` a place id or name; `knowers` characters who learn it."""
    id: str
    t: int
    place: str
    participants: tuple[str, ...]
    summary: str
    knowers: tuple[str, ...] = ()
    notability: float = 0.5


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


def _convert(ev: Any) -> ScheduledEvent:
    """Any object with the agreed attributes becomes our dataclass."""
    return ScheduledEvent(
        id=str(ev.id), t=int(ev.t), place=str(ev.place),
        participants=tuple(getattr(ev, "participants", ()) or ()), summary=str(ev.summary),
        knowers=tuple(getattr(ev, "knowers", ()) or ()),
        notability=float(getattr(ev, "notability", 0.5)))


class ApiCanon:
    """Wraps the functions of `harness.canon.api`. The names it looks for: `scheduled_events`
    (or `events_between`) and `background`; a missing one means "nothing"."""

    def __init__(self, api: Any = _api, to_minutes: Callable[[Any], int] | None = None) -> None:
        self.api, self.to_minutes = api, to_minutes

    def scheduled(self, after_t: int, up_to_t: int) -> Sequence[ScheduledEvent]:
        fn = (getattr(self.api, "scheduled_events", None)
              or getattr(self.api, "events_between", None))
        if fn is None:
            return ()
        try:
            got = fn(after_t, up_to_t)
        except TypeError:
            got = [e for e in fn() if after_t < e.t <= up_to_t]
        return [_convert(e) for e in got]

    def background(self, character: str, topic: str) -> str | None:
        fn = getattr(self.api, "background", None)
        if fn is None:
            return None
        got = fn(character, topic)
        return None if got is None else str(getattr(got, "text", got))


def default_source() -> CanonSource:
    return ApiCanon() if _api is not None else NullCanon()
