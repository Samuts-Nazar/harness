"""The NPC -> other relationship state, kept in the event log.

A relationship is a rung of the ladder (harness/portrait.py RUNGS) plus warmth and trust. Every
change is a RELATION event caused by the event that moved it, so rolling the cause back reverts
the relationship to the previous state; the latest active event per pair wins.
"""
from __future__ import annotations

from dataclasses import dataclass

from .eventlog import EventLog
from .models import RELATION, Event, Scene
from .portrait import RUNGS

# warmth / trust a seeded rung starts with (a stranger is slightly cold and unsure)
SEED_VALUES = {"stranger": (-0.2, 0.2), "client": (0.0, 0.4), "ally": (0.5, 0.6)}


@dataclass(frozen=True)
class Relationship:
    npc: str
    other: str
    rung: str
    warmth: float  # -1..1
    trust: float  # 0..1
    reason: str
    event_id: int | None


class Relations:
    def __init__(self, log: EventLog) -> None:
        self.log = log

    def get(self, npc: str, other: str) -> Relationship:
        for e in reversed(self.log.active([RELATION])):
            p = e.payload
            if p["npc"] == npc and p["other"] == other:
                return Relationship(npc, other, p["rung"], p["warmth"], p["trust"],
                                    p.get("reason", ""), e.id)
        return Relationship(npc, other, "stranger", 0.0, 0.2, "", None)

    def set(self, npc: str, other: str, rung: str, warmth: float, trust: float, reason: str,
            scene: Scene, cause_id: int | None = None) -> Event:
        if rung not in RUNGS:
            raise ValueError(f"unknown rung {rung!r}")
        return self.log.append(
            RELATION, game_time=scene.time, location=scene.location, participants=[npc],
            witnesses=[], notability=0.1, cause_id=cause_id,
            payload={"npc": npc, "other": other, "rung": rung,
                     "warmth": max(-1.0, min(1.0, warmth)), "trust": max(0.0, min(1.0, trust)),
                     "reason": reason})

    def seed(self, npc: str, other: str, rung: str, scene: Scene) -> Event:
        """The starting state from a package or a portrait (no cause: it is never rolled back)."""
        w, t = SEED_VALUES.get(rung, (0.0, 0.3))
        return self.set(npc, other, rung, w, t, "seed", scene, None)
