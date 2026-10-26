"""Character portraits: schema, loader and the per-call slice (docs/superpowers/specs).

A portrait is one YAML file per NPC (`worlds/<world>/portraits/*.yaml`). The whole portrait never
goes into a prompt: `select_stance` picks a stance in code, `slice_text` renders at most 260 words.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import yaml

WORLDS = Path(__file__).resolve().parents[1] / "worlds"
RUNGS = ("stranger", "client", "ally", "close", "lover", "rival", "enemy", "subordinate")
LADDER = ("stranger", "client", "ally", "close", "lover")
WHEN_KEYS = ("power", "audience", "stakes")
MAX_WORDS = 260
MAX_EXAMPLES = 2


class PortraitError(ValueError):
    def __init__(self, path, field, problem):
        self.path, self.field, self.problem = path, field, problem
        super().__init__(f"{path}: {field}: {problem}")


@dataclass(frozen=True)
class Situation:
    power: str  # "self" | "other" | "even"
    audience: bool
    stakes: str  # "low" | "high" | "mortal"


@dataclass(frozen=True)
class Stance:
    id: str
    rung: tuple[str, ...]
    when: dict
    does: str
    sounds: str
    tail: str = ""
    examples: tuple[str, ...] = ()


@dataclass(frozen=True)
class Switch:
    id: str
    trigger: str  # an English yes/no question about what the player just did
    warmth: float
    trust: float
    note: str = ""


@dataclass(frozen=True)
class Portrait:
    id: str
    character: str  # profile id
    name: str
    phase: str
    core: str
    stances: tuple[Stance, ...]
    switches: tuple[Switch, ...]
    hidden: str
    leaks: tuple[str, ...]
    voice: str
    never: str
    relations: dict[str, str]  # other character id -> rung (static NPC->NPC)
    senses: tuple[str, ...] = ("sight",)  # `senses: [magic]` adds the magic sense to whoever plays it


def _req(path, d, key, types, where=""):
    name = f"{where}{key}"
    if not isinstance(d, dict) or key not in d or d[key] is None:
        raise PortraitError(path, name, "missing")
    v = d[key]
    if isinstance(v, bool) and bool not in (types if isinstance(types, tuple) else (types,)):
        raise PortraitError(path, name, "wrong type")
    if not isinstance(v, types):
        raise PortraitError(path, name, "wrong type")
    return v


def _str_list(path, v, name):
    if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
        raise PortraitError(path, name, "must be a list of strings")
    return tuple(v)


def _rung(path, r, name):
    if r not in RUNGS:
        raise PortraitError(path, name, f"unknown rung {r!r}")
    return r


def _stance(path, d, i):
    w = f"stances[{i}]."
    rung = _str_list(path, _req(path, d, "rung", list, w), w + "rung")
    if not rung:
        raise PortraitError(path, w + "rung", "empty")
    for r in rung:
        _rung(path, r, w + "rung")
    when = d.get("when") or {}
    if not isinstance(when, dict) or set(when) - set(WHEN_KEYS):
        raise PortraitError(path, w + "when", f"keys must be among {WHEN_KEYS}")
    tail = d.get("tail") or ""
    if not isinstance(tail, str):
        raise PortraitError(path, w + "tail", "wrong type")
    ex = _str_list(path, d.get("examples") or [], w + "examples")
    return Stance(_req(path, d, "id", str, w), rung, dict(when), _req(path, d, "does", str, w),
                  _req(path, d, "sounds", str, w), tail, ex)


def _switch(path, d, i):
    w = f"switches[{i}]."
    nums = (int, float)
    note = d.get("note") or ""
    return Switch(_req(path, d, "id", str, w), _req(path, d, "trigger", str, w),
                  float(_req(path, d, "warmth", nums, w)), float(_req(path, d, "trust", nums, w)),
                  str(note))


def load_portrait(path: Path) -> Portrait:
    path = Path(path)
    try:
        d = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        raise PortraitError(path, "<file>", f"invalid YAML: {e}") from e
    return parse_portrait(d, path)


def parse_portrait(d: object, path: Path | str = "<portrait>") -> Portrait:
    """A Portrait from its mapping (a loaded YAML file, or a cached generated portrait)."""
    if not isinstance(d, dict):
        raise PortraitError(path, "<file>", "top level must be a mapping")
    sts = _req(path, d, "stances", list)
    if not sts:
        raise PortraitError(path, "stances", "empty")
    sws = d.get("switches") or []
    if not isinstance(sws, list):
        raise PortraitError(path, "switches", "must be a list")
    rel = d.get("relations") or {}
    if not isinstance(rel, dict):
        raise PortraitError(path, "relations", "must be a mapping")
    for k, r in rel.items():
        _rung(path, r, f"relations.{k}")
    senses = ("sight",)
    if d.get("senses") is not None:
        got = _str_list(path, d["senses"], "senses")
        bad = [x for x in got if x not in ("sight", "magic")]
        if bad:
            raise PortraitError(path, "senses", f"unknown sense {bad[0]!r}")
        senses = tuple(dict.fromkeys(("sight", *got)))
    return Portrait(
        id=_req(path, d, "id", str), character=_req(path, d, "character", str),
        name=_req(path, d, "name", str), phase=_req(path, d, "phase", str),
        core=_req(path, d, "core", str),
        stances=tuple(_stance(path, s, i) for i, s in enumerate(sts)),
        switches=tuple(_switch(path, s, i) for i, s in enumerate(sws)),
        hidden=_req(path, d, "hidden", str),
        leaks=_str_list(path, _req(path, d, "leaks", list), "leaks"),
        voice=_req(path, d, "voice", str), never=_req(path, d, "never", str),
        relations=dict(rel), senses=senses,
    )


def load_world_portraits(world: str) -> dict[str, Portrait]:
    out: dict[str, Portrait] = {}
    for f in sorted((WORLDS / world / "portraits").glob("*.yaml")):
        p = load_portrait(f)
        if p.id in out:
            raise PortraitError(f, "id", f"duplicate portrait id {p.id!r}")
        out[p.id] = p
    return out


def _matches(when: dict, sit: Situation) -> bool:
    return all(getattr(sit, k) == v for k, v in when.items())


def _fallback_order(rung: str) -> list[str]:
    if rung not in LADDER:
        return ["stranger"]
    i = LADDER.index(rung)
    # down the ladder first (nearest lower rung), then up if nothing lower exists
    return list(LADDER[:i][::-1]) + list(LADDER[i + 1:])


def select_stance(p: Portrait, rung: str, sit: Situation) -> Stance:
    order = [rung] + [r for r in _fallback_order(rung) if r != rung]
    for r in order:
        cands = [s for s in p.stances if r in s.rung]
        for s in cands:
            if s.when and _matches(s.when, sit):
                return s
        for s in cands:
            if not s.when:
                return s
    return p.stances[0]


def slice_text(p: Portrait, stance: Stance, leak: str | None, budget: int = MAX_WORDS) -> str:
    """At most `budget` words (default MAX_WORDS): trims the leak (it is rationed anyway), then the
    examples, then the tail, then cuts words from the core, `does`, `sounds` and `voice`, in that
    order, so `never` is kept longest. A caller that adds a header passes the budget left after it."""
    def build(parts):
        core, does, sounds, tail, examples, voice, never, leak_line = parts
        return "\n".join(x for x in (core, does, sounds, tail, *examples, voice, never, leak_line)
                          if x)

    parts = [p.core, stance.does, stance.sounds, stance.tail, list(stance.examples[:MAX_EXAMPLES]),
             p.voice, p.never, leak or ""]
    for trim in (7, 4, 3):   # the leak, the examples, the tail
        out = build(parts)
        if len(out.split()) <= budget:
            return out
        parts[trim] = [] if trim == 4 else ""
    out = build(parts)
    over = len(out.split()) - budget
    for i in (0, 1, 2, 5, 6):   # core, does, sounds, voice, never
        if over <= 0:
            break
        words = parts[i].split()
        cut = min(over, len(words))
        parts[i] = " ".join(words[:len(words) - cut])
        over -= cut
    return build(parts)


_WORD = re.compile(r"[\w'’]+")


def _grams(text: str, n: int) -> set[tuple[str, ...]]:
    w = _WORD.findall(text.lower())
    return {tuple(w[i:i + n]) for i in range(len(w) - n + 1)}


def copy_overlap(line: str, examples: Iterable[str], n: int = 6) -> bool:
    """True when `line` repeats `n` consecutive words of any example line (case-insensitive,
    punctuation ignored): the example leaked into play instead of only showing the voice."""
    got = _grams(line, n)
    return bool(got) and any(got & _grams(ex, n) for ex in examples)
