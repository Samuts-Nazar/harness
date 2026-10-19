"""A cheap code metric of repetition across the last N player-facing outputs (task 12).

Measured, not acted on: nothing is regenerated because of it yet. Three signals, each 0..1, for
one new output against the outputs before it:
- ngram:   share of the output's word trigrams that already occurred in the previous outputs;
- opening: share of its sentences that start with the same two words as an earlier sentence (in the
           previous outputs or earlier in the same output);
- shape:   share of the previous outputs of the same kind that have the same paragraph shape
           (paragraph count, sentence count, average sentence length bucket).
`score` is their mean. `examples` quotes up to three of the repeated pieces.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Sequence

WINDOW = 8  # previous outputs compared against
_WORDS = re.compile(r"\w+(?:['ʼ’]\w+)*", re.UNICODE)
_SENT = re.compile(r"(?<=[.!?…»\"])\s+")


def words(text: str) -> list[str]:
    return [w.lower() for w in _WORDS.findall(text)]


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text.strip()) if words(s)]


def trigrams(ws: Sequence[str]) -> list[tuple[str, str, str]]:
    return [tuple(ws[i:i + 3]) for i in range(len(ws) - 2)]  # type: ignore[misc]


def shape(text: str) -> tuple[int, int, int]:
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    sents = sentences(text)
    n_w = sum(len(words(s)) for s in sents)
    avg = n_w / len(sents) if sents else 0
    return (len(paras), min(len(sents), 8), int(avg // 5))


@dataclass
class Repetition:
    ngram: float = 0.0
    opening: float = 0.0
    shape: float = 0.0
    score: float = 0.0
    kind: str = ""
    examples: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:  # type: ignore[type-arg]
        d = asdict(self)
        for k in ("ngram", "opening", "shape", "score"):
            d[k] = round(d[k], 3)
        return d


def measure(latest: str, prior: Sequence[tuple[str, str]], kind: str = "",
            window: int = WINDOW) -> Repetition:
    """`prior`: (kind, text) of the earlier outputs, oldest first; only the last `window` count."""
    prior = list(prior)[-window:]
    out = Repetition(kind=kind)
    if not prior or not words(latest):
        return out
    seen3: set[tuple[str, str, str]] = set()
    openings: set[tuple[str, ...]] = set()
    for _, t in prior:
        seen3.update(trigrams(words(t)))
        openings.update(tuple(words(s)[:2]) for s in sentences(t))
    mine = trigrams(words(latest))
    rep3 = [g for g in mine if g in seen3]
    out.ngram = len(rep3) / len(mine) if mine else 0.0
    sents = sentences(latest)
    reps: list[str] = []
    n_rep = 0
    for s in sents:
        op = tuple(words(s)[:2])
        if len(op) == 2 and op in openings:
            n_rep += 1
            reps.append(" ".join(op) + " ...")
        openings.add(op)
    out.opening = n_rep / len(sents) if sents else 0.0
    same = [t for k, t in prior if k == kind] if kind else [t for _, t in prior]
    mine_shape = shape(latest)
    out.shape = sum(shape(t) == mine_shape for t in same) / len(same) if same else 0.0
    out.score = (out.ngram + out.opening + out.shape) / 3
    ex = [" ".join(g) for g in rep3[:3]]
    out.examples = ex + [r for r in reps if r not in ex][: 3 - len(ex)] if ex else reps[:3]
    return out


def measure_turn(outputs: Sequence[tuple[str, str]], prior: Sequence[tuple[str, str]],
                 window: int = WINDOW) -> dict:  # type: ignore[type-arg]
    """One turn's outputs ((kind, text): "narration" or "npc") against `prior`. Outputs of the same
    turn do not count as prior for each other (an NPC may quote the narration's scene)."""
    per = [measure(t, prior, k, window) for k, t in outputs]
    return {"outputs": [p.as_dict() for p in per],
            "score": round(sum(p.score for p in per) / len(per), 3) if per else 0.0,
            "ngram": round(max((p.ngram for p in per), default=0.0), 3),
            "opening": round(max((p.opening for p in per), default=0.0), 3),
            "shape": round(max((p.shape for p in per), default=0.0), 3)}
