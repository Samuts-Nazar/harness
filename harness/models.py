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
ACTION = "action"  # an observable action from narration
SCENE_ENTRY = "scene_entry"
STATE_CHANGE = "state_change"
SCRIPTED = "scripted"  # code-side marker event (setup, scripted changes)
NOTICED = "noticed"  # salience verdict of one observer on one observation
NOTICE_SHOWN = "notice_shown"  # a noteworthy observation was surfaced in the NPC's context
ATTITUDE = "attitude"

# Live-state categories and operations
INJURY, CLOTHING, INVENTORY, EQUIPMENT, INTERNAL = (
    "injury", "clothing", "inventory", "equipment", "internal")
STATE_CATEGORIES = (INJURY, CLOTHING, INVENTORY, EQUIPMENT, INTERNAL)
OPS = ("add", "remove", "reveal", "hide")

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
    source: str | None = None  # None: perceived directly; else the character who said/told it
    event_id: int | None = None  # the event this knowledge came from


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
    manner: str = ""  # how this person talks (task 15); generated once, stored with the profile


@dataclass
class Scene:
    location: str
    present: tuple[str, ...]  # in the room: see and hear everything (includes PLAYER)
    time: int = 0
    outside: tuple[str, ...] = ()  # nearby but not in the room: hear loud things only


def format_time(t: int) -> str:
    day, rem = divmod(t, 24 * 60)
    return f"day {day + 1}, {rem // 60:02d}:{rem % 60:02d}"
