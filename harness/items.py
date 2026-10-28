"""Item ids, locations and containers (derived over the live state, nothing stored here).

An element may carry a stable `id` (`item:<slug>`) and a `location`: `worn`, `in_hand`,
`on:<place>` or `in:<container id>`. Whether it can be perceived is derived at read time:
the stored observable flag, and for something inside a container, that the container (and
whatever it sits in) is open and itself observable. The owner is not an observer, so this
is the view of everyone else. A container's open state is `Element.open`, set by op `open`.
Elements without ids behave exactly as before.
"""
from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from .state import Element, State, StateChange, StateError

if TYPE_CHECKING:
    from .pipeline import Engine

IN = "in:"
_ARTICLES = {"a", "an", "the"}


def _slug(text: str) -> str:
    words = re.findall(r"\w+", text.casefold())
    return "-".join(words)[:40].strip("-") or "item"


def mint_id(name: str, taken: set[str]) -> str:
    base = f"item:{_slug(name)}"
    cand, n = base, 2
    while cand in taken:
        cand, n = f"{base}-{n}", n + 1
    return cand


def all_ids(state: State) -> set[str]:
    return {e.id for elems in state.values() for e in elems.values()
            if isinstance(e, Element) and e.id}


def _index(state: State) -> dict[str, Element]:
    return {e.id: e for elems in state.values() for e in elems.values()
            if isinstance(e, Element) and e.id}


def _norm(text: str) -> str:
    return " ".join(w for w in re.findall(r"\w+", text.casefold()) if w not in _ARTICLES)


def resolve(text: str, character: str, state: State) -> str | None:
    """Id of the character's item that best matches `text` (normalised), else None."""
    want = _norm(text)
    if not want:
        return None
    cands = [(e, _norm(e.item)) for e in state.get(character, {}).values()
             if isinstance(e, Element) and e.id]
    exact = [e for e, n in cands if n == want]
    if len(exact) == 1:
        return exact[0].id
    if exact:
        return None
    part = [(abs(len(n) - len(want)), e) for e, n in cands
            if n and (want in n or n in want)]
    if not part:
        return None
    part.sort(key=lambda t: t[0])
    if len(part) > 1 and part[0][0] == part[1][0]:
        return None  # ambiguous
    return part[0][1].id


def _stored(v: Any) -> bool:
    return v.observable if isinstance(v, Element) else bool(v)


def is_observable(el: Element, state: State) -> bool:
    if not isinstance(el, Element):
        return bool(el)
    idx = _index(state)
    seen: set[str] = set()
    cur = el
    while True:
        if not cur.observable:
            return False
        loc = cur.location
        if not (loc and loc.startswith(IN)):
            return True  # worn, in_hand, on:<place>, free text, or none
        cid = loc[len(IN):]
        parent = idx.get(cid)
        if parent is None or not parent.open or cid in seen:
            return False
        seen.add(cid)
        cur = parent


def check_location(state: State, item_id: str | None, location: str) -> None:
    if not location.startswith(IN):
        return
    idx = _index(state)
    cid = location[len(IN):]
    if cid not in idx:
        raise StateError(f"no container {cid!r}")
    seen: set[str] = set()
    while cid:
        if cid == item_id or cid in seen:
            raise StateError(f"container cycle: {item_id!r} cannot be inside itself")
        seen.add(cid)
        loc = idx[cid].location
        cid = loc[len(IN):] if loc and loc.startswith(IN) and loc[len(IN):] in idx else ""


def newly_observable(before: State, after: State, character: str) -> list[Element]:
    """The character's elements that are observable in `after` but were not in `before`."""
    out = []
    for key, el in after.get(character, {}).items():
        was = before.get(character, {}).get(key)
        if is_observable(el, after) and not (was is not None and is_observable(was, before)):
            out.append(el)
    return out


def open_container(engine: "Engine", character: str, container_id: str) -> list[str]:
    """Open a container: whatever becomes observable is perceived once (by `_apply_change`).
    Opening an empty or already open container does nothing. Returns the new items' ids."""
    snap = engine.live.snapshot()
    box = next((e for e in snap.get(character, {}).values()
                if isinstance(e, Element) and e.id == container_id), None)
    if box is None:
        raise StateError(f"{character} has no container {container_id!r}")
    if box.open:
        return []
    inside = [e for e in snap[character].values() if e.location == IN + container_id]
    if not inside:
        return []
    engine.apply_state_change(StateChange(character, box.category, "open", box.item))
    after = engine.live.snapshot()
    return [e.id or e.item for e in newly_observable(snap, after, character)]
