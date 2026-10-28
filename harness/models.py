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
NAME_LEARNED = "name_learned"  # a character learned another's name (through a channel)
RELATION = "relation"  # an NPC's rung, warmth and trust toward someone (harness/relations.py)
CORRECTION = "correction"  # the player's note on a model error, kept per campaign
PORTRAIT_LEAK = "portrait_leak"  # a hidden-layer leak a portrait NPC's line carried (one per scene)

# Live-state categories and operations
INJURY, CLOTHING, INVENTORY, EQUIPMENT, INTERNAL, APPEARANCE = (
    "injury", "clothing", "inventory", "equipment", "internal", "appearance")
STATE_CATEGORIES = (INJURY, CLOTHING, INVENTORY, EQUIPMENT, INTERNAL, APPEARANCE)
OPS = ("add", "remove", "reveal", "hide", "move", "realize", "open")

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
    appearance: str = ""  # what an observer sees of them (short, in the output language). A
    # character with an appearance is referred to by it until the viewer has learned the name;
    # one without is known by name to everyone.
    core: str = ""  # task 19: immutable core (voice, drives, values), set once and shown verbatim
    sex: str = ""  # "m"/"f" of a generated NPC (from its text or one decider call); "" unknown
    portrait: str = ""  # id of the world portrait (worlds/<world>/portraits) this NPC plays; ""
    # none: the flat profile (core, manner) is used
    senses: tuple[str, ...] = ("sight",)  # how this character perceives ("magic" too: a sorceress)


@dataclass
class Scene:
    location: str
    present: tuple[str, ...]  # in the room: see and hear everything (includes PLAYER)
    time: int = 0
    outside: tuple[str, ...] = ()  # nearby but not in the room: hear loud things only


def format_time(t: int) -> str:
    day, rem = divmod(t, 24 * 60)
    return f"day {day + 1}, {rem // 60:02d}:{rem % 60:02d}"
