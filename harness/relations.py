"""The NPC -> other relationship state, kept in the event log.

A relationship is a rung of the ladder (harness/portrait.py RUNGS) plus warmth and trust. Every
change is a RELATION event caused by the event that moved it, so rolling the cause back reverts
the relationship to the previous state; the latest active event per pair wins.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .eventlog import EventLog
from .models import PLAYER, RELATION, Event, Scene
from .portrait import LADDER, RUNGS, Switch

# warmth / trust a seeded rung starts with (a stranger is slightly cold and unsure)
SEED_VALUES = {"stranger": (-0.2, 0.2), "client": (0.0, 0.4), "ally": (0.5, 0.6),
               "close": (0.7, 0.7), "lover": (0.9, 0.85)}


# climbing to a rung: (warmth, trust) both needed (a stranger becomes a client on trust alone)
CLIMB = {"client": (-1.0, 0.3), "ally": (0.3, 0.45), "close": (0.6, 0.65), "lover": (0.85, 0.8)}
# a rung drops one rung when warmth falls below its entry warmth - DROP_MARGIN (a stranger never
# drops, except to enemy)
ENTRY_WARMTH = {"stranger": -1.0, "client": 0.0, "ally": 0.3, "close": 0.6, "lover": 0.85}
DROP_MARGIN = 0.3
ENEMY_AT = -0.7  # warmth at or below: enemy, from any rung
# an enemy becomes a stranger again once warmth is back to ENEMY_AT + DROP_MARGIN (hysteresis)
ENEMY_LEFT_AT = ENEMY_AT + DROP_MARGIN


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
    """NPC -> other relationships. Only NPC -> player is stored and changes; NPC -> NPC rungs stay
    the portrait's static `relations` in this version (ContextBuilder.rung_of)."""

    def __init__(self, log: EventLog, seeds: dict[str, str] | None = None) -> None:
        # `seeds`: npc -> rung toward the player stored in the campaign settings (campaigns made
        # before the store have no RELATION event); the dict is shared, not copied
        self.log = log
        self.seeds = seeds if seeds is not None else {}

    def get(self, npc: str, other: str) -> Relationship:
        """The latest active relationship; with no event, the seeded rung (else stranger) at its
        SEED_VALUES, event_id None. The one source of truth for the numbers."""
        for e in reversed(self.log.active([RELATION])):
            p = e.payload
            if p["npc"] == npc and p["other"] == other:
                return Relationship(npc, other, p["rung"], p["warmth"], p["trust"],
                                    p.get("reason", ""), e.id)
        rung = self.seeds.get(npc, "stranger") if other == PLAYER else "stranger"
        w, t = SEED_VALUES.get(rung, SEED_VALUES["stranger"])
        return Relationship(npc, other, rung, w, t, "", None)

    def set(self, npc: str, other: str, rung: str, warmth: float, trust: float, reason: str,
            scene: Scene, cause_id: int | None = None, lines: Sequence[int] = ()) -> Event:
        """`lines`: the world's events (NPC lines, gestures) the change was judged on; a model
        error or challenge that replaces one of them reverts the change (Engine)."""
        if rung not in RUNGS:
            raise ValueError(f"unknown rung {rung!r}")
        return self.log.append(
            RELATION, game_time=scene.time, location=scene.location, participants=[npc],
            witnesses=[], notability=0.1, cause_id=cause_id,
            payload={"npc": npc, "other": other, "rung": rung,
                     "warmth": max(-1.0, min(1.0, warmth)), "trust": max(0.0, min(1.0, trust)),
                     "reason": reason, **({"lines": list(lines)} if lines else {})})

    def seed(self, npc: str, other: str, rung: str, scene: Scene) -> Event:
        """The starting state from a package or a portrait (no cause: it is never rolled back)."""
        if rung not in SEED_VALUES:
            raise ValueError(f"cannot seed rung {rung!r}")
        w, t = SEED_VALUES[rung]
        return self.set(npc, other, rung, w, t, "seed", scene, None)


def _next_rung(rung: str, warmth: float, trust: float) -> str:
    if warmth <= ENEMY_AT:
        return "enemy"
    if rung == "enemy":
        return "stranger" if warmth >= round(ENEMY_LEFT_AT, 4) else "enemy"
    if rung not in LADDER:  # rival, subordinate: only the enemy threshold moves them
        return rung
    i = LADDER.index(rung)
    if i + 1 < len(LADDER):
        up = LADDER[i + 1]
        need_w, need_t = CLIMB[up]
        if warmth >= need_w and trust >= need_t:
            return up
    if i > 0 and warmth < round(ENTRY_WARMTH[rung] - DROP_MARGIN, 4):
        return LADDER[i - 1]
    return rung


def apply(rel: Relationship, hits: Sequence[Switch]) -> Relationship:
    """The relationship after this turn's switches: deltas summed, warmth clamped to [-1, 1] and
    trust to [0, 1], at most one rung up or down (or to enemy). `reason` lists the switch ids;
    `event_id` is None until the caller stores it."""
    w = round(max(-1.0, min(1.0, rel.warmth + sum(s.warmth for s in hits))), 4)
    t = round(max(0.0, min(1.0, rel.trust + sum(s.trust for s in hits))), 4)
    return replace(rel, rung=_next_rung(rel.rung, w, t), warmth=w, trust=t,
                   reason=",".join(s.id for s in hits), event_id=None)
