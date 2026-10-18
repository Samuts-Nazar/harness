"""Live character state, derived from STATE_CHANGE events (so rollback just works).

Per character: injuries, clothing, inventory, equipment, internal changes. Each element is
observable or hidden, and persists until an event changes it. The extractor only *proposes*
changes; `check_change` validates them against the state as it is now.
"""
from __future__ import annotations

from dataclasses import dataclass

from .eventlog import EventLog
from .models import OPS, STATE_CATEGORIES, STATE_CHANGE


class StateError(ValueError):
    """A proposed state change is not valid against the current state."""


@dataclass(frozen=True)
class StateChange:
    character: str
    category: str
    op: str  # add | remove | reveal | hide
    item: str
    observable: bool = True  # only meaningful for `add`
    source: str | None = None  # extractor segment key the change came from


@dataclass(frozen=True)
class Element:
    category: str
    item: str
    observable: bool


State = dict[str, dict[tuple[str, str], bool]]  # character -> {(category, item): observable}


def apply(state: State, ch: StateChange) -> None:
    """Apply a change in place. Assumes it has been checked."""
    elems = state.setdefault(ch.character, {})
    key = (ch.category, ch.item)
    if ch.op == "add":
        elems[key] = ch.observable
    elif ch.op == "remove":
        del elems[key]
    elif ch.op == "reveal":
        elems[key] = True
    elif ch.op == "hide":
        elems[key] = False


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
    if ch.op == "reveal" and elems[key]:
        raise StateError(f"{ch.item!r} is already observable")
    if ch.op == "hide" and not elems[key]:
        raise StateError(f"{ch.item!r} is already hidden")


def payload(ch: StateChange) -> dict:  # type: ignore[type-arg]
    return {
        "character": ch.character,
        "category": ch.category,
        "op": ch.op,
        "item": ch.item,
        "observable": ch.observable,
    }


class LiveState:
    def __init__(self, log: EventLog) -> None:
        self.log = log

    def snapshot(self) -> State:
        """Current state of everyone: replay of active STATE_CHANGE events in order."""
        state: State = {}
        for e in self.log.active([STATE_CHANGE]):
            p = e.payload
            apply(state, StateChange(p["character"], p["category"], p["op"], p["item"],
                                     p["observable"]))
        return state

    def of(self, character: str) -> list[Element]:
        elems = self.snapshot().get(character, {})
        return [Element(c, i, o) for (c, i), o in elems.items()]

    def observable(self, character: str) -> list[Element]:
        return [e for e in self.of(character) if e.observable]
