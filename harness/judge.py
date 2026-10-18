"""Slot for typed judgments (Jev later): yes/no, choice, score. No text generation."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, Sequence


@dataclass(frozen=True)
class Judgment:
    answer: bool | str | float
    probabilities: dict[str, float] = field(default_factory=dict)


class Judge(Protocol):
    def yes_no(self, question: str, context: str = "") -> Judgment: ...
    def choice(self, question: str, options: Sequence[str], context: str = "") -> Judgment: ...
    def score(
        self, question: str, context: str = "", lo: float = 0.0, hi: float = 1.0
    ) -> Judgment: ...


class StubJudge:
    """Deterministic placeholder. Answers yes / first option / midpoint."""

    def __init__(self, yes: bool = True) -> None:
        self.yes = yes

    def yes_no(self, question: str, context: str = "") -> Judgment:
        return Judgment(self.yes, {"yes": float(self.yes), "no": float(not self.yes)})

    def choice(self, question: str, options: Sequence[str], context: str = "") -> Judgment:
        probs = {o: float(i == 0) for i, o in enumerate(options)}
        return Judgment(options[0], probs)

    def score(
        self, question: str, context: str = "", lo: float = 0.0, hi: float = 1.0
    ) -> Judgment:
        return Judgment((lo + hi) / 2)
