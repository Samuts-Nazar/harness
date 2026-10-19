"""Slot for "how much does C believe this". The belief model is not decided yet, so the default
is neutral. Swap `Engine(belief=...)` for a real function later; nothing else needs to change."""
from __future__ import annotations

from typing import Callable

from .models import Fact, Knower

BeliefFn = Callable[[str, Fact, Knower], float]  # (character, fact, how they know it) -> 0..1

NEUTRAL = 0.5


def neutral_belief(character: str, fact: Fact, knower: Knower) -> float:
    return NEUTRAL
