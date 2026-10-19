"""Attitudes and salience notices, both derived from the event log.

An attitude is a character's stance toward a fact. It is stored apart from the fact and points
to it by id (different characters hold different attitudes toward the same fact).
A notice is the salience verdict of one observer on one observation (a fact about someone's
observable state); noteworthy notices are surfaced once in that NPC's next context.
"""
from __future__ import annotations

from dataclasses import dataclass

from .eventlog import EventLog
from .facts import FactStore
from .models import ATTITUDE, NOTICE_SHOWN, NOTICED, Event, Scene


@dataclass(frozen=True)
class Attitude:
    character: str
    fact_id: int
    stance: str  # e.g. positive | neutral | negative
    magnitude: float
    event_id: int


class Attitudes:
    def __init__(self, log: EventLog, facts: FactStore) -> None:
        self.log, self.facts = log, facts

    def set(self, character: str, fact_id: int, stance: str, magnitude: float, scene: Scene,
            cause_id: int) -> Event:
        # cause_id = the fact's source event, so rolling that back drops the attitude too
        return self.log.append(
            ATTITUDE,
            game_time=scene.time,
            location=scene.location,
            participants=[character],
            witnesses=[],
            payload={"character": character, "fact_id": fact_id, "stance": stance,
                     "magnitude": magnitude},
            cause_id=cause_id,
        )

    def of(self, character: str) -> list[Attitude]:
        """Latest attitude per fact, only for facts that are still active."""
        latest: dict[int, Attitude] = {}
        for e in self.log.active([ATTITUDE]):
            p = e.payload
            if p["character"] == character:
                latest[p["fact_id"]] = Attitude(character, p["fact_id"], p["stance"],
                                                p["magnitude"], e.id)
        return [a for a in latest.values() if self.facts.get(a.fact_id) is not None]


class Notices:
    def __init__(self, log: EventLog, facts: FactStore) -> None:
        self.log, self.facts = log, facts

    def add(self, observer: str, fact_id: int, noteworthy: bool, scene: Scene,
            cause_id: int) -> Event:
        return self.log.append(
            NOTICED,
            game_time=scene.time,
            location=scene.location,
            participants=[observer],
            witnesses=[],
            payload={"observer": observer, "fact_id": fact_id, "noteworthy": noteworthy},
            cause_id=cause_id,
        )

    def pending(self, observer: str) -> list[tuple[Event, int]]:
        """Noteworthy observations not yet surfaced in the observer's context."""
        shown = {e.payload["notice_event"] for e in self.log.active([NOTICE_SHOWN])}
        return [
            (e, e.payload["fact_id"])
            for e in self.log.active([NOTICED])
            if e.payload["observer"] == observer
            and e.payload["noteworthy"]
            and e.id not in shown
            and self.facts.get(e.payload["fact_id"]) is not None
        ]

    def mark_shown(self, notice: Event, scene: Scene) -> Event:
        return self.log.append(
            NOTICE_SHOWN,
            game_time=scene.time,
            location=scene.location,
            witnesses=[],
            payload={"notice_event": notice.id},
        )
