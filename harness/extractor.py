"""Extractor diff: parsing and validation in code. LLM output is never trusted.

The extractor proposes only fact text, the segment it came from, and notability — plus optional
live-state changes. Who knew a fact is computed in code (perception.py); a diff that tries to
assign knowers is rejected.
"""
from __future__ import annotations

import copy
import json
import math
import re
from dataclasses import dataclass, field, replace
from typing import Any, Collection

from .metaphor import literal_reading
from . import items
from .state import State, StateChange, StateError, apply, check_change


class DiffValidationError(ValueError):
    """The extractor produced a malformed or unauthorized diff."""


@dataclass(frozen=True)
class FactDraft:
    content: str
    source: str  # segment key: "narration", "player", "action1".., or a character id
    notability: float
    location: str | None


@dataclass(frozen=True)
class Diff:
    facts: list[FactDraft]
    changes: list[StateChange]
    dropped: list[dict[str, Any]] = field(default_factory=list)  # invalid changes, with reasons


_TOP_KEYS = {"new_facts", "state_changes"}
_FACT_KEYS = {"content", "source", "notability", "location"}
_CHANGE_KEYS = {"character", "category", "op", "item", "observable", "source", "id", "location"}
_REFERS = ("remove", "move", "reveal", "hide")  # ops that must name an existing item
MAX_CONTENT = 500
MAX_FACTS = 20
MAX_CHANGES = 20
DEFAULT_NOTABILITY = 0.3


def parse_diff(raw: str) -> Any:
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        raise DiffValidationError(f"not valid JSON: {e}") from e


def _notability(f: dict[str, Any], where: str) -> float:
    nb = f.get("notability", DEFAULT_NOTABILITY)
    if (
        isinstance(nb, bool)
        or not isinstance(nb, (int, float))
        or math.isnan(nb)
        or not 0.0 <= nb <= 1.0
    ):
        raise DiffValidationError(f"{where}: notability must be a number in [0, 1]")
    return float(nb)


def validate_diff(
    data: Any,
    *,
    present: Collection[str],
    sources: Collection[str],
    state: State | None = None,
    characters: Collection[str] | None = None,
    texts: dict[str, str] | None = None,
    fuzzy: bool = False,
) -> Diff:
    """Accept only `new_facts` and `state_changes`.

    Unknown keys are rejected (so the model cannot invent operations such as editing canon),
    and `knowers` is rejected explicitly: perception is computed in code. State changes are
    checked one by one against the state as it would be after the previous ones, so a diff
    cannot remove what is not there. A change that is invalid in itself or against the state is
    dropped one by one (`Diff.dropped`); it does not reject the diff. `characters` (default: `present`) are who a change may
    be about.
    """
    if not isinstance(data, dict):
        raise DiffValidationError("diff must be a JSON object")
    extra = set(data) - _TOP_KEYS
    if extra:
        raise DiffValidationError(f"unauthorized keys: {sorted(extra)}")
    facts = data.get("new_facts", [])
    changes = data.get("state_changes", [])
    if not isinstance(facts, list) or not isinstance(changes, list):
        raise DiffValidationError("new_facts and state_changes must be lists")
    if len(facts) > MAX_FACTS or len(changes) > MAX_CHANGES:
        raise DiffValidationError("too many entries")

    drafts: list[FactDraft] = []
    for i, f in enumerate(facts):
        where = f"new_facts[{i}]"
        if not isinstance(f, dict):
            raise DiffValidationError(f"{where} must be an object")
        if "knowers" in f:
            raise DiffValidationError(f"{where}: knowers are computed in code, not proposed")
        extra = set(f) - _FACT_KEYS
        if extra:
            raise DiffValidationError(f"{where}: unauthorized keys {sorted(extra)}")
        content = f.get("content")
        if not isinstance(content, str) or not content.strip():
            raise DiffValidationError(f"{where}: content must be non-empty text")
        if len(content) > MAX_CONTENT:
            raise DiffValidationError(f"{where}: content too long")
        source = f.get("source")
        if not isinstance(source, str) or source not in sources:
            raise DiffValidationError(f"{where}: unknown source {source!r}")
        loc = f.get("location")
        if loc is not None and not isinstance(loc, str):
            raise DiffValidationError(f"{where}: location must be text")
        drafts.append(FactDraft(content.strip(), source, _notability(f, where), loc))

    who = set(characters if characters is not None else present)
    sim = copy.deepcopy(state or {})
    out_changes: list[StateChange] = []
    dropped: list[dict[str, Any]] = []
    handled = _containers_handled(changes, who, sources, sim, fuzzy)
    said = " ".join((texts or {}).values())
    for i, c in enumerate(changes):
        where = f"state_changes[{i}]"
        try:
            change = _parse_change(c, where, who, sources)
            change = _bind_item(c, change, where, sim, fuzzy)
            change = _taken_out(change, where, sim, handled, said)
            for opened in _implicit_opens(change, sim):
                check_change(sim, opened)
                apply(sim, opened)
                out_changes.append(opened)
            check_change(sim, change)
            why = literal_reading(change.category, change.op, change.item,
                                  (texts or {}).get(change.source, ""))
            if why:  # "took his hand" must not add a hand to the inventory (task 19)
                raise DiffValidationError(f"{where}: metaphor read literally: {why}")
        except (DiffValidationError, StateError) as e:
            # one bad change (revealing an item that is in another category, removing what is not
            # there, an unknown character) is dropped and reported; the rest of the turn stands
            dropped.append({"change": c, "reason": str(e)})
            continue
        apply(sim, change)
        out_changes.append(change)
    return Diff(drafts, out_changes, dropped)


def _parse_change(c: Any, where: str, who: set[str], sources: Collection[str]) -> StateChange:
    if not isinstance(c, dict):
        raise DiffValidationError(f"{where} must be an object")
    extra = set(c) - _CHANGE_KEYS
    if extra:
        raise DiffValidationError(f"{where}: unauthorized keys {sorted(extra)}")
    ch, cat, op, item = (c.get(k) for k in ("character", "category", "op", "item"))
    if not all(isinstance(x, str) for x in (ch, cat, op, item)):
        raise DiffValidationError(f"{where}: character, category, op, item must be text")
    if ch not in who:
        raise DiffValidationError(f"{where}: unknown character {ch!r}")
    src = c.get("source")
    if not isinstance(src, str) or src not in sources:
        raise DiffValidationError(f"{where}: unknown source {src!r}")
    obs = c.get("observable", True)
    if not isinstance(obs, bool):
        raise DiffValidationError(f"{where}: observable must be true or false")
    loc = c.get("location")
    if loc is not None and not isinstance(loc, str):
        raise DiffValidationError(f"{where}: location must be text")
    return StateChange(ch, cat, op, item.strip(), obs, src, location=loc.strip() if loc else None)


def _bind_item(c: dict[str, Any], change: StateChange, where: str, sim: State,
                fuzzy: bool) -> StateChange:
    """Tie the change to an item. `add` of new text mints an id in code (a model-proposed id is
    ignored). remove/move/reveal/hide/realize/open refer to an item by `id`, else by its text;
    an id that matches nothing, or text that only matches an id-less item exactly, is left for
    check_change, which drops what it cannot find."""
    elems = sim.get(change.character, {})
    if change.op == "add":
        return replace(change, id=items.mint_id(change.item, items.all_ids(sim)))
    mid = c.get("id")
    if mid is not None:
        if not isinstance(mid, str):
            raise DiffValidationError(f"{where}: id must be text")
        el = next((e for e in elems.values() if e.id == mid), None)
        if el is None:
            raise DiffValidationError(f"{where}: unknown item id {mid!r}")
        return replace(change, category=el.category, item=el.item)
    if fuzzy and (change.category, change.item) not in elems:  # only with item_ids on
        rid = items.resolve(change.item, change.character, sim)
        if rid is not None:
            el = next(e for e in elems.values() if e.id == rid)
            return replace(change, category=el.category, item=el.item)
    return change


# -- containers (outsider live check, problem 3) ----------------------------------------------------
# "Знімаю рюкзак, розстібаю його, дістаю ноутбук" once came out as `move рюкзак -> on:ground` plus
# `remove ноутбук` with no `open`: the laptop was lost. The prompt says how to write it; these are
# the safety net in code.
_TAKE_OUT = re.compile(
    r"(?<!\w)(?:діста\w*|дістав\w*|дістан\w*|вийма\w*|вийня\w*|вийму|витяг\w*|витягу\w*|"
    r"takes? out|took out|taking out|pull(?:s|ed|ing)? out|gets? out|got out)(?!\w)", re.IGNORECASE)


def _element(sim: State, ch: StateChange) -> Any:
    return sim.get(ch.character, {}).get((ch.category, ch.item))


def _box_of(sim: State, character: str, el: Any) -> Any:
    loc = getattr(el, "location", None) or ""
    if not loc.startswith(items.IN):
        return None
    bid = loc[len(items.IN):]
    return next((e for e in sim.get(character, {}).values()
                 if getattr(e, "id", None) == bid), None)


def _containers_handled(changes: list[Any], who: set[str], sources: Collection[str], sim: State,
                        fuzzy: bool) -> set[str]:
    """Ids of the containers this diff opens or moves (resolved against the state before it)."""
    out: set[str] = set()
    for i, c in enumerate(changes):
        if not isinstance(c, dict) or c.get("op") not in ("open", "move"):
            continue
        try:
            ch = _bind_item(c, _parse_change(c, f"state_changes[{i}]", who, sources), "", sim, fuzzy)
        except (DiffValidationError, StateError):
            continue
        el = _element(sim, ch)
        if getattr(el, "id", None):
            out.add(el.id)
    return out


def _taken_out(change: StateChange, where: str, sim: State, handled: set[str],
               said: str) -> StateChange:
    """A `remove` of an item that sits in a container this same diff opens or moves is an item
    taken out, not one that is gone: when the text says it is taken out it becomes a `move` to the
    hand (which opens the container, below); otherwise the remove is dropped."""
    if change.op != "remove":
        return change
    el = _element(sim, change)
    box = _box_of(sim, change.character, el)
    if box is None or box.id not in handled:
        return change
    if _TAKE_OUT.search(said):
        return replace(change, op="move", location="in_hand")
    raise DiffValidationError(f"{where}: remove of {change.item!r}, which is inside {box.item!r} "
                              "that this diff opens or moves: taken out is a move, not a remove")


def _implicit_opens(change: StateChange, sim: State) -> list[StateChange]:
    """A `move` of an item out of a closed container opens it first (each closed container on the
    way out, outermost first), so whatever is inside is observed once."""
    if change.op != "move" or not change.location:
        return []
    el = _element(sim, change)
    opens: list[StateChange] = []
    seen: set[str] = set()
    box = _box_of(sim, change.character, el)
    while box is not None and box.id not in seen:
        seen.add(box.id)
        if change.location == items.IN + box.id:
            break  # moved within the same container: nothing comes out
        if not box.open:
            opens.append(StateChange(change.character, box.category, "open", box.item,
                                     source=change.source))
        box = _box_of(sim, change.character, box)
    return opens[::-1]
