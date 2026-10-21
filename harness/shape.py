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

import math
import random
import re
from enum import Enum
from typing import TYPE_CHECKING, Iterable, Mapping, Sequence

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


def shape_prior(profile: "WorldProfile | None") -> str:
    """A prior line for the director's shape question, from the world's numbers ("" without a
    profile)."""
    if profile is None or not profile.length_bins:
        return ""
    pct = round(100 * (profile.length_bins.get("1", 0.0) + profile.length_bins.get("2-3", 0.0)))
    return f"In this world about {pct}% of replies are 1-3 words."


# -- the session's shapes follow the world profile (Task 12) ----------------------------------
# The decider says which shape fits the moment, as probabilities; code samples the shape from
# them blended with the world's length bins, and leans against the gap between the lines said so
# far in the session and the profile (the model's own drift, e.g. never writing long, is
# corrected by asking for more of what is missing). Note kind `shape_sampled`.
SHAPE_BINS: dict[Shape, tuple[str, ...]] = {
    Shape.WORD: ("1", "2-3"), Shape.SHORT: ("4-7",), Shape.NORMAL: ("8-15",),
    Shape.LONG: ("16-30", "31+")}
SPEECH_SHAPES = tuple(SHAPE_BINS)
MIX = 0.5     # weight of the profile against the decider in the base distribution
CONF_K = 6.0  # lines after which the session gap counts half
GAIN = 1.5    # how hard a gap pulls (exponent per relative gap)
_CLIP = (0.25, 4.0)


def shape_targets(profile: "WorldProfile") -> dict[Shape, float]:
    """The world's share of spoken lines per speech shape."""
    raw = {s: sum(profile.length_bins.get(b, 0.0) for b in bins) for s, bins in SHAPE_BINS.items()}
    tot = sum(raw.values()) or 1.0
    return {s: v / tot for s, v in raw.items()}


def decider_dist(probs: Mapping[str, float], answer: str, p_answer: float) -> dict[Shape, float]:
    """The decider's answer as a distribution over all shapes. Options it gave no probability
    share what is left evenly (a decider that reports only its answer's probability)."""
    known = {s: float(probs[s.value]) for s in Shape if s.value in probs}
    try:
        ans = Shape(answer)
    except ValueError:
        ans = Shape.NORMAL
    if ans not in known:
        known[ans] = max(0.0, min(1.0, p_answer))
    left = [s for s in Shape if s not in known]
    rest = max(0.0, 1.0 - sum(known.values()))
    dist = {s: known.get(s, rest / len(left) if left else 0.0) for s in Shape}
    tot = sum(dist.values())
    return {s: v / tot for s, v in dist.items()} if tot > 0 else {s: float(s is ans) for s in Shape}


def _session(lines: Sequence[str], names: Sequence[str]) -> tuple[dict[Shape, float], int]:
    from .profile import profile_of_lines
    try:
        p = profile_of_lines(lines, names)
    except ValueError:
        return {s: 0.0 for s in SPEECH_SHAPES}, 0
    return shape_targets(p), p.n_lines


def shape_weights(decider: Mapping[Shape, float], profile: "WorldProfile",
                  lines: Sequence[str], names: Sequence[str] = ()) -> dict[Shape, float]:
    """Probabilities to sample this step's shape from. Gesture and silence keep the decider's
    mass; the speech mass is shared by base = (1-MIX)*decider + MIX*profile, times
    exp(GAIN * conf * (target - session) / target) clipped to [0.25, 4], conf = n / (n + 6) over
    the n spoken lines of the session so far (`names`: as `profile_of_lines` takes them)."""
    speech = sum(decider.get(s, 0.0) for s in SPEECH_SHAPES)
    out = {s: float(decider.get(s, 0.0)) for s in Shape if s not in SHAPE_BINS}
    if speech <= 0:
        return {**out, **{s: 0.0 for s in SPEECH_SHAPES}}
    target = shape_targets(profile)
    have, n = _session(lines, names)
    conf = n / (n + CONF_K)
    q: dict[Shape, float] = {}
    for s in SPEECH_SHAPES:
        base = (1 - MIX) * decider.get(s, 0.0) / speech + MIX * target[s]
        rel = (target[s] - have[s]) / max(target[s], 0.05)
        q[s] = base * min(_CLIP[1], max(_CLIP[0], math.exp(GAIN * conf * rel)))
    tot = sum(q.values())
    return {**out, **{s: speech * v / tot for s, v in q.items()}}


def sample_shape(weights: Mapping[Shape, float], rng: random.Random) -> Shape:
    """One draw (the order of `Shape` is fixed, so a seeded rng gives the same shape)."""
    x, acc = rng.random() * sum(weights.values()), 0.0
    last = Shape.NORMAL
    for s in Shape:
        w = weights.get(s, 0.0)
        if w <= 0:
            continue
        acc += w
        last = s
        if x < acc:
            return s
    return last


def beat_wanted(profile: "WorldProfile | None", lines: Sequence[str],
                rng: random.Random, names: Sequence[str] = ()) -> bool | None:
    """Does this line carry a beat (the speaker's own small action)? Drawn from the profile's
    `no_beat_share`, leaning against the session's own share the same way; None without a
    profile (left to the model)."""
    if profile is None or not profile.no_beat_share:
        return None
    from .profile import profile_of_lines
    t = profile.no_beat_share
    try:
        p = profile_of_lines(lines, names)
        have, n = p.no_beat_share, p.n_lines
    except ValueError:
        have, n = t, 0
    conf = n / (n + CONF_K)
    p_none = min(0.95, max(0.05, t + conf * (t - have)))
    return rng.random() >= p_none


_INSTR = {
    Shape.SILENCE: "{name} says nothing this turn and does nothing worth noting.",
    Shape.GESTURE: "{name} does not speak this turn: write only one small action, no words.",
    Shape.WORD: "Reply with a word or two ({lo}-{hi} words), nothing more.",
    Shape.SHORT: "Keep it short: {lo}-{hi} words of speech.",
    Shape.NORMAL: "Speak in one or two full sentences, {lo}-{hi} words.",
    Shape.LONG: ("This turn runs longer: several sentences, at least {lo} and up to about {hi} "
                 "words (an explanation, a story, an argument), but not a speech."),
}


def shape_instruction(shape: Shape, language: str | None = None, *,
                      bounds: tuple[int, int] | None = None, name: str | None = None) -> str:
    """An English instruction line for the shape. `bounds`: the same (min, max) words the caller
    gives `fit_to_shape` (default: the no-profile bounds), so the prompt and the fit agree.
    `name`: the character (default "The character"). `language`: appends "Write in <language>."
    for a caller that has no language line of its own (`Style.npc_instruction` has one)."""
    lo, hi = bounds if bounds is not None else _DEFAULT[shape]
    line = _INSTR[shape].format(name=name or "The character", lo=lo, hi=hi)
    return line + (f" Write in {language}." if language and shape is not Shape.SILENCE else "")


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
                 allow_trim: bool = False, names: Iterable[str] = ()) -> tuple[str, str]:
    """Fit an NPC line to its shape; returns (text, how), how in {"ok", "trimmed", "regenerate"}.
    Only the spoken part is counted. SILENCE -> empty; GESTURE -> beats only, as plain text with
    no dash (a reply with no dash at all is taken whole as the action; a dash reply without
    beats is speech: ask again, or silence once `allow_trim`). Speech over 1.5x the upper bound -> "regenerate"; the
    caller asks once more and then calls with `allow_trim=True`, which cuts the speech at a
    sentence boundary (beats kept, as "— speech — beat."). `names`: known character names for
    `split_npc_output` (a piece naming one is a beat)."""
    if shape is Shape.SILENCE:
        return "", "ok"
    out = split_npc_output(text, names)
    if shape is Shape.GESTURE:
        if out.beats:
            return " ".join(_ensure_end(b) for b in out.beats), "ok"
        if not out.has_dash and out.speech:  # no dash at all: the answer is the action itself
            return _ensure_end(out.speech), "ok"
        return ("", "ok") if allow_trim else (text, "regenerate")
    hi = bounds[1]
    n = _n(out.speech)
    if n > hi * _OVER and not allow_trim:
        return text, "regenerate"
    if n <= hi or not allow_trim:
        return text, "ok"
    speech = _trim_speech(out.speech, hi)
    if not out.has_dash:  # plain speech (no book-style dashes): stays plain
        return speech, "trimmed"
    parts = ["— " + speech] + [_ensure_end(b) for b in out.beats]
    return " — ".join(parts), "trimmed"
