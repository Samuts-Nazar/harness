"""Live character state, derived from STATE_CHANGE events (so rollback just works).

Per character: injuries, clothing, inventory, equipment, internal changes. Each element is
observable or hidden, and persists until an event changes it. The extractor only *proposes*
changes; `check_change` validates them against the state as it is now.
"""
from __future__ import annotations

from dataclasses import dataclass, replace

from .eventlog import EventLog
from .models import OPS, STATE_CATEGORIES, STATE_CHANGE


class StateError(ValueError):
    """A proposed state change is not valid against the current state."""


@dataclass(frozen=True)
class StateChange:
    character: str
    category: str
    op: str  # add | remove | reveal | hide | move | realize | open
    item: str
    observable: bool = True  # only meaningful for `add`
    source: str | None = None  # extractor segment key the change came from
    id: str | None = None  # stable attribute of the element (not its key); `add` only
    location: str | None = None  # where the element is; `add` and `move`
    aware: bool = True  # does the bearer know of it; `add` only (`realize` sets it)
    until: int | None = None  # game time it lasts until; `add` only
    channel: str = "sight"  # how an observer perceives it; `add` only


@dataclass(frozen=True)
class Element:
    category: str
    item: str
    observable: bool
    id: str | None = None
    location: str | None = None
    aware: bool = True
    until: int | None = None
    channel: str = "sight"
    open: bool = False  # a container: its contents (location "in:<id>") are visible once open

    def __bool__(self) -> bool:
        """Old callers treated a snapshot value as the observable flag."""
        # Only the *stored* flag: whether an item is really perceivable (inside a closed
        # container, say) is derived at read time by items.is_observable, never stored.
        return self.observable


State = dict[str, dict[tuple[str, str], Element]]  # character -> {(category, item): Element}


def _observable(v: "Element | bool") -> bool:
    return v.observable if isinstance(v, Element) else bool(v)


def _aware(v: "Element | bool") -> bool:
    return v.aware if isinstance(v, Element) else True


def apply(state: State, ch: StateChange) -> None:
    """Apply a change in place. Assumes it has been checked."""
    elems = state.setdefault(ch.character, {})
    key = (ch.category, ch.item)
    if ch.op == "add":
        elems[key] = Element(ch.category, ch.item, ch.observable, ch.id, ch.location, ch.aware,
                             ch.until, ch.channel)
        return
    if ch.op == "remove":
        del elems[key]
        return
    cur = elems[key]
    if not isinstance(cur, Element):  # a hand-built bool state
        cur = Element(ch.category, ch.item, bool(cur))
    if ch.op == "reveal":
        elems[key] = replace(cur, observable=True)
    elif ch.op == "hide":
        elems[key] = replace(cur, observable=False)
    elif ch.op == "move":
        elems[key] = replace(cur, location=ch.location)
    elif ch.op == "realize":
        elems[key] = replace(cur, aware=True)
    elif ch.op == "open":
        elems[key] = replace(cur, open=True)


def check_change(state: State, ch: StateChange) -> None:
    if ch.category not in STATE_CATEGORIES:
        raise StateError(f"unknown category {ch.category!r}")
    if ch.op not in OPS:
        raise StateError(f"unknown op {ch.op!r}")
    if not ch.item.strip():
        raise StateError("empty item")
    elems = state.get(ch.character, {})
    key = (ch.category, ch.item)
    if ch.op == "add" and key in elems:
        raise StateError(f"{ch.character} already has {ch.category} {ch.item!r}")
    if ch.op != "add" and key not in elems:
        raise StateError(f"cannot {ch.op} {ch.category} {ch.item!r}: {ch.character} does not have it")
    if ch.op == "reveal" and _observable(elems[key]):
        raise StateError(f"{ch.item!r} is already observable")
    if ch.op == "hide" and not _observable(elems[key]):
        raise StateError(f"{ch.item!r} is already hidden")
    if ch.op == "realize" and _aware(elems[key]):
        raise StateError(f"{ch.character} is already aware of {ch.item!r}")
    if ch.op == "open" and getattr(elems[key], "open", False):
        raise StateError(f"{ch.item!r} is already open")
    if ch.op == "move" and not ch.location:
        raise StateError(f"cannot move {ch.item!r}: no location given")
    if ch.op in ("add", "move") and ch.location:
        from . import items  # items imports this module
        cur = elems.get(key)
        items.check_location(state, ch.id if ch.op == "add" else getattr(cur, "id", None),
                             ch.location)


def payload(ch: StateChange) -> dict:  # type: ignore[type-arg]
    p: dict = {
        "character": ch.character,
        "category": ch.category,
        "op": ch.op,
        "item": ch.item,
        "observable": ch.observable,
    }
    if ch.id is not None:
        p["id"] = ch.id
    if ch.location is not None:
        p["location"] = ch.location
    if not ch.aware:
        p["aware"] = False
    if ch.until is not None:
        p["until"] = ch.until
    if ch.channel != "sight":
        p["channel"] = ch.channel
    return p


class LiveState:
    def __init__(self, log: EventLog) -> None:
        self.log = log

    def snapshot(self) -> State:
        """Current state of everyone: replay of active STATE_CHANGE events in order."""
        state: State = {}
        for e in self.log.active([STATE_CHANGE]):
            p = e.payload
            apply(state, StateChange(
                p["character"], p["category"], p["op"], p["item"], p["observable"],
                id=p.get("id"), location=p.get("location"), aware=p.get("aware", True),
                until=p.get("until"), channel=p.get("channel", "sight")))
        return state

    def of(self, character: str) -> list[Element]:
        elems = self.snapshot().get(character, {})
        return list(elems.values())

    def observable(self, character: str) -> list[Element]:
        from . import items
        snap = self.snapshot()
        return [e for e in snap.get(character, {}).values() if items.is_observable(e, snap)]
