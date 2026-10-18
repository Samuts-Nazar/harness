"""Plain data types shared across the engine."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

PLAYER = "player"

# Event types
UTTERANCE = "utterance"
NARRATION = "narration"
INTERRUPTION = "interruption"
INTENT_SET = "intent_set"
INTENT_RESOLVED = "intent_resolved"
AGENT_PROMOTED = "agent_promoted"

# How a character came to know a fact
WITNESSED = "witnessed"
HEARD = "heard"
TOLD = "told"
HOW_VALUES = (WITNESSED, HEARD, TOLD)

CANON = "canon"
CAMPAIGN = "campaign"


@dataclass(frozen=True)
class Event:
    id: int
    type: str
    game_time: int  # in-game minutes since campaign epoch
    location: str
    participants: tuple[str, ...]
    witnesses: tuple[str, ...]
    notability: float
    payload: dict[str, Any] = field(default_factory=dict)
    cause_id: int | None = None


@dataclass(frozen=True)
class Knower:
    character: str
    how: str
    learned_at: int


@dataclass(frozen=True)
class Fact:
    id: int
    store: str
    content: str
    source_event_id: int | None
    game_time: int
    location: str
    notability: float
    knowers: tuple[Knower, ...] = ()


@dataclass(frozen=True)
class CharacterProfile:
    id: str
    name: str
    description: str = ""


@dataclass
class Scene:
    location: str
    present: tuple[str, ...]  # character ids, including PLAYER
    time: int = 0


def format_time(t: int) -> str:
    day, rem = divmod(t, 24 * 60)
    return f"day {day + 1}, {rem // 60:02d}:{rem % 60:02d}"
