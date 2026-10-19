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
from dataclasses import dataclass, field
from typing import Any, Collection

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
_CHANGE_KEYS = {"character", "category", "op", "item", "observable", "source"}
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
    for i, c in enumerate(changes):
        where = f"state_changes[{i}]"
        try:
            change = _parse_change(c, where, who, sources)
            check_change(sim, change)
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
    return StateChange(ch, cat, op, item.strip(), obs, src)
