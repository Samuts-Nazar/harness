"""Response shape (task 3): how much an NPC says this turn, and fitting a written line to it.

The books' rhythm is short: a shape is chosen for the turn (by a decider, a later task), the NPC
prompt names it (`shape_instruction`), and `fit_to_shape` checks what came back. It is a pure
function; the engine wiring and the notes it logs live in the turn loop. Note kinds, both in
`decisions.CODE_CHOICE_KINDS`:

- `shape_regenerated`: the line was far over the shape (`fit_to_shape` said "regenerate") and
  the NPC was asked once more;
- `shape_trimmed`: after that the line was still over and code cut it at a sentence boundary.
"""
from __future__ import annotations

import re
from enum import Enum
from typing import TYPE_CHECKING

from .style import split_npc_output

if TYPE_CHECKING:
    from .profile import WorldProfile


class Shape(str, Enum):
    SILENCE = "silence"   # says nothing at all
    GESTURE = "gesture"   # only a small action, no words
    WORD = "word"         # a word or two
    SHORT = "short"
    NORMAL = "normal"
    LONG = "long"


_DEFAULT = {Shape.SILENCE: (0, 0), Shape.GESTURE: (0, 0), Shape.WORD: (1, 2),
            Shape.SHORT: (3, 9), Shape.NORMAL: (10, 25), Shape.LONG: (26, 80)}
# with a world profile the bounds follow its length bins ("1", "2-3", "4-7", "8-15", "16-30")
_FROM_BINS = {Shape.WORD: (1, 3), Shape.SHORT: (4, 7), Shape.NORMAL: (8, 15), Shape.LONG: (16, 80)}
_OVER = 1.5  # speech beyond this multiple of the upper bound is regenerated
_SENT = re.compile(r"(?<=[.!?…])\s+")
_END = ".!?…"


def word_bounds(shape: Shape, profile: "WorldProfile | None") -> tuple[int, int]:
    """(min, max) spoken words for a shape: the book bins when the world has a profile."""
    if profile is not None and profile.length_bins and shape in _FROM_BINS:
        return _FROM_BINS[shape]
    return _DEFAULT[shape]


_INSTR = {
    Shape.SILENCE: "{name} says nothing this turn and does nothing worth noting.",
    Shape.GESTURE: "{name} does not speak this turn: write only one small action, no words.",
    Shape.WORD: "Reply with a word or two ({lo}-{hi} words), nothing more.",
    Shape.SHORT: "Keep it short: {lo}-{hi} words of speech.",
    Shape.NORMAL: "Speak in one or two sentences, about {lo}-{hi} words.",
    Shape.LONG: "This turn may run longer, up to about {hi} words, but not a speech.",
}


def shape_instruction(shape: Shape, language: str | None) -> str:
    """An English instruction line for the shape (bounds are the no-profile defaults)."""
    lo, hi = _DEFAULT[shape]
    line = _INSTR[shape].format(name="The character", lo=lo, hi=hi)
    return line + (f" Write in {language}." if language and shape not in (Shape.SILENCE,) else "")


def _n(text: str) -> int:
    return len(text.split())


def _ensure_end(s: str) -> str:
    s = s.rstrip(" ,;:—–-")
    return s if s and s[-1] in _END else s + "."


def _trim_speech(speech: str, hi: int) -> str:
    kept: list[str] = []
    for sent in _SENT.split(speech.strip()):
        if _n(" ".join(kept + [sent])) > hi:
            break
        kept.append(sent)
    if kept:
        return " ".join(kept)
    words = speech.split()[:max(hi, 1)]  # one sentence alone is too long: cut on a word
    return _ensure_end(" ".join(words))


def fit_to_shape(text: str, shape: Shape, bounds: tuple[int, int], *,
                 allow_trim: bool = False) -> tuple[str, str]:
    """Fit an NPC line to its shape; returns (text, how), how in {"ok", "trimmed", "regenerate"}.
    Only the spoken part is counted. SILENCE -> empty; GESTURE -> beats only (no beats: ask
    again, or silence once `allow_trim`). Speech over 1.5x the upper bound -> "regenerate"; the
    caller asks once more and then calls with `allow_trim=True`, which cuts the speech at a
    sentence boundary (beats kept, as "— speech — beat.")."""
    if shape is Shape.SILENCE:
        return "", "ok"
    out = split_npc_output(text)
    if shape is Shape.GESTURE:
        if out.beats:
            return " ".join(_ensure_end(b) for b in out.beats), "ok"
        return ("", "ok") if allow_trim else (text, "regenerate")
    hi = bounds[1]
    n = _n(out.speech)
    if n > hi * _OVER and not allow_trim:
        return text, "regenerate"
    if n <= hi or not allow_trim:
        return text, "ok"
    speech = _trim_speech(out.speech, hi)
    parts = ["— " + speech] + [_ensure_end(b) for b in out.beats]
    return " — ".join(parts), "trimmed"
