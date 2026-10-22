"""The NPC -> other relationship state, kept in the event log.

A relationship is a rung of the ladder (harness/portrait.py RUNGS) plus warmth and trust. Every
change is a RELATION event caused by the event that moved it, so rolling the cause back reverts
the relationship to the previous state; the latest active event per pair wins.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Sequence

from .eventlog import EventLog
from .models import PLAYER, RELATION, SCENE_ENTRY, Event, Scene
from .portrait import LADDER, RUNGS, Switch

# warmth / trust a seeded rung starts with (a stranger is slightly cold and unsure)
SEED_VALUES = {"stranger": (-0.2, 0.2), "client": (0.0, 0.4), "ally": (0.5, 0.6),
               "close": (0.7, 0.7), "lover": (0.9, 0.85)}


# climbing to a rung: (warmth, trust) both needed (a stranger becomes a client on trust alone)
CLIMB = {"client": (-1.0, 0.3), "ally": (0.3, 0.45), "close": (0.6, 0.65), "lover": (0.85, 0.8)}
# a rung drops one rung when a cooling turn leaves warmth below its entry warmth - DROP_MARGIN
# (a stranger never drops, except to enemy)
ENTRY_WARMTH = {"stranger": -1.0, "client": 0.0, "ally": 0.3, "close": 0.6, "lover": 0.85}
DROP_MARGIN = 0.3
ENEMY_AT = -0.7  # warmth at or below: enemy, from any rung
# an enemy becomes a stranger again at warmth >= -0.4, and only after a scene change since
ENEMY_LEFT_AT = ENEMY_AT + DROP_MARGIN

# pacing: per turn only the largest positive switch counts (capped), every negative counts
POS_CAP = 0.3  # the most a turn adds to warmth, and to trust
RUNG_MULT = {"stranger": 1.0, "client": 0.75, "ally": 0.5, "close": 0.35, "lover": 0.35}
REPEAT_FACTOR = 0.5  # a positive switch hit in the scene before counts half
DECAY = 0.05  # a new scene after one with no positive hit: warmth drifts toward the rung's rest
# where warmth rests on each rung: its entry warmth; a stranger rests at its seed (-1, the
# "never drops" entry, would make every stranger colder each scene), an enemy at the threshold
DECAY_TARGET = {**ENTRY_WARMTH, "stranger": -0.2, "enemy": ENEMY_AT}
CLOSE_HELD = 1  # close needs ally held across this many scene changes
LOVER_HELD, LOVER_DISTINCT = 2, 3  # lover: close held across 2, and 3 distinct positive ids
ENEMY_HELD = 1
# a scene ends with the game day, or after this many game minutes with the NPC not judged
SCENE_GAP = 120
DAY = 24 * 60


@dataclass(frozen=True)
class Relationship:
    npc: str
    other: str
    rung: str
    warmth: float  # -1..1
    trust: float  # 0..1
    reason: str
    event_id: int | None
    scene: str = ""  # the scene key it was judged in (Relations.scene_key)
    counted: tuple[str, ...] = ()  # the positive switch that counted this turn


@dataclass(frozen=True)
class Pace:
    """What pacing needs to know of the pair's history (Relations.pace)."""
    scene: str = ""  # this turn's scene key
    changed: bool = False  # a new scene since the pair's last judged turn
    this_scene: frozenset[str] = frozenset()  # positive ids already counted in this scene
    prev_scene: frozenset[str] = frozenset()  # positive ids counted in the scene before
    prev_had_positive: bool = True  # (changed) the scene just left had a positive hit
    held: int = 0  # scene changes since the current rung was reached (this turn's included)
    distinct: frozenset[str] = frozenset()  # every positive id counted so far


def is_positive(sw: Switch) -> bool:
    return sw.warmth + sw.trust > 0


class Relations:
    """NPC -> other relationships. Only NPC -> player is stored and changes; NPC -> NPC rungs stay
    the portrait's static `relations` in this version (ContextBuilder.rung_of)."""

    def __init__(self, log: EventLog, seeds: dict[str, str] | None = None) -> None:
        # `seeds`: npc -> rung toward the player stored in the campaign settings (campaigns made
        # before the store have no RELATION event); the dict is shared, not copied
        self.log = log
        self.seeds = seeds if seeds is not None else {}

    def _events(self, npc: str, other: str) -> list[Event]:
        return [e for e in self.log.active([RELATION])
                if e.payload["npc"] == npc and e.payload["other"] == other]

    def get(self, npc: str, other: str) -> Relationship:
        """The latest active relationship; with no event, the seeded rung (else stranger) at its
        SEED_VALUES, event_id None. The one source of truth for the numbers."""
        evs = self._events(npc, other)
        if evs:
            e, p = evs[-1], evs[-1].payload
            return Relationship(npc, other, p["rung"], p["warmth"], p["trust"],
                                p.get("reason", ""), e.id, p.get("scene", ""),
                                tuple(p.get("counted", ())))
        rung = self.seeds.get(npc, "stranger") if other == PLAYER else "stranger"
        w, t = SEED_VALUES.get(rung, SEED_VALUES["stranger"])
        return Relationship(npc, other, rung, w, t, "", None)

    def scene_key(self, npc: str, scene: Scene) -> str:
        """One scene for `npc` toward the player: the location, the NPC's latest entry (0: there
        from the start) and the game minute the scene began. A new scene begins on another
        location or entry, on a new day, or after a gap of SCENE_GAP minutes or more since the
        NPC was last judged (its latest RELATION event); otherwise the latest event's key goes
        on."""
        entries = [e.id for e in self.log.active([SCENE_ENTRY])
                   if e.payload.get("character") == npc]
        base = f"{scene.location}#{entries[-1] if entries else 0}"
        evs = self._events(npc, PLAYER)
        if evs:
            last, key = evs[-1], evs[-1].payload.get("scene") or ""
            if (key.split("@")[0] == base and last.game_time // DAY == scene.time // DAY
                    and scene.time - last.game_time < SCENE_GAP):
                return key
        return f"{base}@{scene.time}"

    def pace(self, npc: str, other: str, key: str) -> Pace:
        """The pacing history of the pair as of a turn in scene `key`. Scenes are runs of events
        with the same scene key (an event without one belongs to the run before it)."""
        evs = [e.payload for e in self._events(npc, other)]
        if not evs:
            return Pace(scene=key)
        eff: list[str] = []
        for p in evs:
            k = p.get("scene") or ""
            eff.append(k or (eff[-1] if eff else ""))
        if not eff[0]:  # unknown leading keys take the first known one
            first = next((k for k in eff if k), "")
            eff = [k or first for k in eff]
        segs: list[tuple[str, set[str]]] = []
        for k, p in zip(eff, evs):
            if not segs or k != segs[-1][0]:
                segs.append((k, set()))
            segs[-1][1].update(p.get("counted", ()))
        changed = bool(key) and bool(eff[-1]) and key != eff[-1]
        start = len(evs) - 1  # where the current rung was reached
        while start > 0 and evs[start - 1]["rung"] == evs[-1]["rung"]:
            start -= 1
        held = sum(1 for i in range(start + 1, len(evs)) if eff[i] != eff[i - 1]) + changed
        distinct = frozenset().union(*(c for _, c in segs))
        if changed:
            return Pace(key, True, frozenset(), frozenset(segs[-1][1]), bool(segs[-1][1]),
                        held, distinct)
        prev = frozenset(segs[-2][1]) if len(segs) > 1 else frozenset()
        return Pace(key, False, frozenset(segs[-1][1]), prev, True, held, distinct)

    def set(self, npc: str, other: str, rung: str, warmth: float, trust: float, reason: str,
            scene: Scene, cause_id: int | None = None, lines: Sequence[int] = (), *,
            key: str = "", counted: Sequence[str] = ()) -> Event:
        """`lines`: this NPC's own lines and gestures the change was judged on; a model error,
        challenge or cut that replaces one of them judges the turn again (Engine). `key`: the
        scene key; `counted`: the positive switch that counted (pacing)."""
        if rung not in RUNGS:
            raise ValueError(f"unknown rung {rung!r}")
        extra: dict[str, object] = {}
        if lines:
            extra["lines"] = list(lines)
        if key:
            extra["scene"] = key
        if counted:
            extra["counted"] = list(counted)
        return self.log.append(
            RELATION, game_time=scene.time, location=scene.location, participants=[npc],
            witnesses=[], notability=0.1, cause_id=cause_id,
            payload={"npc": npc, "other": other, "rung": rung,
                     "warmth": max(-1.0, min(1.0, warmth)), "trust": max(0.0, min(1.0, trust)),
                     "reason": reason, **extra})

    def seed(self, npc: str, other: str, rung: str, scene: Scene) -> Event:
        """The starting state from a package or a portrait (no cause: it is never rolled back)."""
        if rung not in SEED_VALUES:
            raise ValueError(f"cannot seed rung {rung!r}")
        w, t = SEED_VALUES[rung]
        return self.set(npc, other, rung, w, t, "seed", scene, None,
                        key=self.scene_key(npc, scene))


def _r(x: float) -> float:
    return round(x, 4)


def _next_rung(rung: str, warmth: float, trust: float, dw: float, pace: Pace,
               distinct: frozenset[str]) -> str:
    if warmth <= ENEMY_AT:
        return "enemy"
    if rung == "enemy":
        return ("stranger" if warmth >= _r(ENEMY_LEFT_AT) and pace.held >= ENEMY_HELD
                else "enemy")
    if rung not in LADDER:  # rival, subordinate: only the enemy threshold moves them
        return rung
    i = LADDER.index(rung)
    if i + 1 < len(LADDER):
        up = LADDER[i + 1]
        need_w, need_t = CLIMB[up]
        gate = (up != "close" or pace.held >= CLOSE_HELD) and (
            up != "lover" or (pace.held >= LOVER_HELD and len(distinct) >= LOVER_DISTINCT))
        if warmth >= need_w and trust >= need_t and gate:
            return up
    if i > 0 and dw < 0 and warmth < _r(ENTRY_WARMTH[rung] - DROP_MARGIN):
        return LADDER[i - 1]
    return rung


def apply(rel: Relationship, hits: Sequence[Switch], pace: Pace | None = None) -> Relationship:
    """The relationship after this turn's switches, paced:

    - on a new scene after one with no positive hit, warmth first drifts DECAY toward the
      rung's rest (DECAY_TARGET);
    - only the largest positive switch counts: not one already counted in this scene, half if
      counted in the scene before, times the rung's RUNG_MULT, capped at +POS_CAP warmth and
      +POS_CAP trust; every negative switch counts in full;
    - warmth is clamped to [-1, 1], trust to [0, 1]; at most one rung up (close and lover gated
      by scene changes and distinct switches) or, on a cooling turn, one down; enemy at
      warmth <= ENEMY_AT.

    `reason` lists every switch hit; `counted` the positive one that counted; `event_id` is
    None until the caller stores it."""
    pace = pace or Pace()
    w, t = rel.warmth, rel.trust
    if pace.changed and not pace.prev_had_positive and rel.rung in DECAY_TARGET:
        w += max(-DECAY, min(DECAY, DECAY_TARGET[rel.rung] - w))
    mult = RUNG_MULT.get(rel.rung, 1.0)

    def gain(s: Switch) -> tuple[float, float]:
        f = mult * (REPEAT_FACTOR if s.id in pace.prev_scene else 1.0)
        return (min(POS_CAP, s.warmth * f) if s.warmth > 0 else s.warmth,
                min(POS_CAP, s.trust * f) if s.trust > 0 else s.trust)

    pos = [s for s in hits if is_positive(s) and s.id not in pace.this_scene]
    best = max(pos, key=lambda s: sum(gain(s)), default=None)
    pw, pt = gain(best) if best is not None else (0.0, 0.0)
    neg = [s for s in hits if not is_positive(s)]
    dw = pw + sum(s.warmth for s in neg)
    dt = pt + sum(s.trust for s in neg)
    w = _r(max(-1.0, min(1.0, w + dw)))
    t = _r(max(0.0, min(1.0, t + dt)))
    counted = (best.id,) if best is not None else ()
    rung = _next_rung(rel.rung, w, t, dw, pace, pace.distinct | frozenset(counted))
    return replace(rel, rung=rung, warmth=w, trust=t, reason=",".join(s.id for s in hits),
                   event_id=None, scene=pace.scene, counted=counted)
