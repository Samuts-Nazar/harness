"""Persistent agents, pending intents and the off-screen update hook (all derived from the log)."""
from __future__ import annotations

from typing import Protocol

from .eventlog import EventLog
from .models import AGENT_PROMOTED, INTENT_RESOLVED, INTENT_SET, Event, Scene


class AgentRegistry:
    def __init__(self, log: EventLog) -> None:
        self.log = log

    def agents(self) -> list[str]:
        seen: list[str] = []
        for e in self.log.active([AGENT_PROMOTED]):
            c = e.payload["character"]
            if c not in seen:
                seen.append(c)
        return seen

    def is_agent(self, character: str) -> bool:
        return character in self.agents()

    def promote(self, character: str, scene: Scene) -> bool:
        """Idempotent. Returns True if the character was newly promoted."""
        if self.is_agent(character):
            return False
        self.log.append(
            AGENT_PROMOTED,
            game_time=scene.time,
            location=scene.location,
            participants=[character],
            witnesses=[],
            payload={"character": character},
        )
        return True


class Intents:
    """Private intents: what a character meant to say or do and has not yet."""

    def __init__(self, log: EventLog) -> None:
        self.log = log

    def set(self, character: str, text: str, scene: Scene, cause_id: int | None = None) -> Event:
        return self.log.append(
            INTENT_SET,
            game_time=scene.time,
            location=scene.location,
            participants=[character],
            witnesses=[],  # private
            payload={"character": character, "text": text},
            cause_id=cause_id,
        )

    def pending(self, character: str) -> list[Event]:
        resolved = {e.payload["intent_event"] for e in self.log.active([INTENT_RESOLVED])}
        return [
            e
            for e in self.log.active([INTENT_SET])
            if e.payload["character"] == character and e.id not in resolved
        ]

    def resolve(self, intent_event_id: int, scene: Scene) -> None:
        self.log.append(
            INTENT_RESOLVED,
            game_time=scene.time,
            location=scene.location,
            payload={"intent_event": intent_event_id},
        )


class OffscreenUpdater(Protocol):
    def update(self, character: str, from_time: int, to_time: int) -> None: ...


class StubOffscreenUpdater:
    """Placeholder: records calls, changes nothing."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, int, int]] = []

    def update(self, character: str, from_time: int, to_time: int) -> None:
        self.calls.append((character, from_time, to_time))
