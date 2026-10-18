"""Extractor diff: parsing and validation in code. LLM output is never trusted."""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any, Collection

from .models import HOW_VALUES


class DiffValidationError(ValueError):
    """The extractor produced a malformed or unauthorized diff."""


@dataclass(frozen=True)
class FactDraft:
    content: str
    source: str  # segment key: "narration", "player" or a character id
    knowers: tuple[tuple[str, str], ...]
    notability: float
    location: str | None


_TOP_KEYS = {"new_facts"}
_FACT_KEYS = {"content", "source", "knowers", "notability", "location"}
MAX_CONTENT = 500
MAX_FACTS = 20
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


def validate_diff(
    data: Any, *, present: Collection[str], sources: Collection[str]
) -> list[FactDraft]:
    """Accept only `new_facts` about the current scene.

    Authorization rules: unknown keys are rejected (so the model cannot invent
    operations such as editing canon or deleting facts); every knower must be
    present in the scene; every fact must name a known source segment.
    """
    if not isinstance(data, dict):
        raise DiffValidationError("diff must be a JSON object")
    extra = set(data) - _TOP_KEYS
    if extra:
        raise DiffValidationError(f"unauthorized keys: {sorted(extra)}")
    facts = data.get("new_facts", [])
    if not isinstance(facts, list):
        raise DiffValidationError("new_facts must be a list")
    if len(facts) > MAX_FACTS:
        raise DiffValidationError("too many facts")

    out: list[FactDraft] = []
    for i, f in enumerate(facts):
        where = f"new_facts[{i}]"
        if not isinstance(f, dict):
            raise DiffValidationError(f"{where} must be an object")
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
        nb = f.get("notability", DEFAULT_NOTABILITY)
        if (
            isinstance(nb, bool)
            or not isinstance(nb, (int, float))
            or math.isnan(nb)
            or not 0.0 <= nb <= 1.0
        ):
            raise DiffValidationError(f"{where}: notability must be a number in [0, 1]")
        loc = f.get("location")
        if loc is not None and not isinstance(loc, str):
            raise DiffValidationError(f"{where}: location must be text")
        ks = f.get("knowers")
        if not isinstance(ks, list) or not ks:
            raise DiffValidationError(f"{where}: knowers must be a non-empty list")
        seen: set[str] = set()
        knowers: list[tuple[str, str]] = []
        for k in ks:
            if not isinstance(k, dict) or set(k) != {"character", "how"}:
                raise DiffValidationError(f"{where}: bad knower entry {k!r}")
            ch, how = k["character"], k["how"]
            if not isinstance(ch, str) or ch not in present:
                raise DiffValidationError(f"{where}: {ch!r} is not present in the scene")
            if not isinstance(how, str) or how not in HOW_VALUES:
                raise DiffValidationError(f"{where}: bad knowledge mode {how!r}")
            if ch in seen:
                raise DiffValidationError(f"{where}: duplicate knower {ch!r}")
            seen.add(ch)
            knowers.append((ch, how))
        out.append(FactDraft(content.strip(), source, tuple(knowers), float(nb), loc))
    return out
