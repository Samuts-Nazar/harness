"""Append-only event log. State is derived from active (non-rolled-back) events."""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Callable, Iterable

from .models import ACTION, Event, NARRATION, PLAYER, UTTERANCE


def _row_to_event(r: sqlite3.Row) -> Event:
    return Event(
        id=r["id"],
        type=r["type"],
        game_time=r["game_time"],
        location=r["location"],
        participants=tuple(json.loads(r["participants"])),
        witnesses=tuple(json.loads(r["witnesses"])),
        notability=r["notability"],
        payload=json.loads(r["payload"]),
        cause_id=r["cause_id"],
    )


class EventLog:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn
        self.observers: list[Callable[[Event], None]] = []

    def subscribe(self, fn: Callable[[Event], None]) -> Callable[[], None]:
        """Call `fn(event)` after every append (the debug view collects a turn's events this
        way). Returns the function that removes the subscription."""
        self.observers.append(fn)
        return lambda: self.observers.remove(fn) if fn in self.observers else None

    def append(
        self,
        type: str,
        *,
        game_time: int,
        location: str,
        participants: Iterable[str] = (),
        witnesses: Iterable[str] = (),
        notability: float = 0.3,
        payload: dict[str, Any] | None = None,
        cause_id: int | None = None,
    ) -> Event:
        if not 0.0 <= notability <= 1.0:
            raise ValueError("notability must be in [0, 1]")
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO events (type, game_time, location, participants, witnesses,"
                " notability, payload, cause_id) VALUES (?,?,?,?,?,?,?,?)",
                (
                    type,
                    game_time,
                    location,
                    json.dumps(list(participants)),
                    json.dumps(list(witnesses)),
                    notability,
                    json.dumps(payload or {}),
                    cause_id,
                ),
            )
        ev = self.get(int(cur.lastrowid))  # type: ignore[arg-type]
        for fn in list(self.observers):
            fn(ev)
        return ev

    def get(self, event_id: int) -> Event:
        r = self.conn.execute("SELECT * FROM events WHERE id=?", (event_id,)).fetchone()
        if r is None:
            raise KeyError(f"no event {event_id}")
        return _row_to_event(r)

    def is_active(self, event_id: int) -> bool:
        r = self.conn.execute(
            "SELECT 1 FROM rollbacks WHERE event_id=?", (event_id,)
        ).fetchone()
        return r is None

    def active(
        self, types: Iterable[str] | None = None, up_to_time: int | None = None
    ) -> list[Event]:
        sql = "SELECT * FROM events WHERE id NOT IN (SELECT event_id FROM rollbacks)"
        args: list[Any] = []
        if types is not None:
            ts = list(types)
            sql += f" AND type IN ({','.join('?' * len(ts))})"
            args += ts
        if up_to_time is not None:
            sql += " AND game_time <= ?"
            args.append(up_to_time)
        sql += " ORDER BY id"
        return [_row_to_event(r) for r in self.conn.execute(sql, args)]

    def descendants(self, event_id: int) -> list[int]:
        out: list[int] = []
        frontier = [event_id]
        while frontier:
            marks = ",".join("?" * len(frontier))
            rows = self.conn.execute(
                f"SELECT id FROM events WHERE cause_id IN ({marks})", frontier
            ).fetchall()
            frontier = [r["id"] for r in rows]
            out += frontier
        return out

    def rollback(self, event_id: int, reason: str = "rollback") -> list[int]:
        """Mark the event and everything caused by it as rolled back.

        Facts and intents derived from these events vanish from derived state,
        because every query filters on active events. Returns newly rolled-back ids.
        """
        self.get(event_id)  # raises if unknown
        ids = [event_id, *self.descendants(event_id)]
        done: list[int] = []
        with self.conn:
            for i in ids:
                if self.is_active(i):
                    self.conn.execute(
                        "INSERT INTO rollbacks (event_id, reason) VALUES (?,?)", (i, reason)
                    )
                    done.append(i)
        return done

    def last_npc_utterance(self) -> Event | None:
        for e in reversed(self.active([UTTERANCE])):
            if e.payload.get("speaker") != PLAYER:
                return e
        return None

    def recent_dialogue(
        self, *, witnessed_by: str | None = None, limit: int = 10, include_narration: bool = False
    ) -> list[Event]:
        types = [UTTERANCE, ACTION] + ([NARRATION] if include_narration else [])
        evs = self.active(types)
        if witnessed_by is not None:
            evs = [e for e in evs if witnessed_by in e.witnesses]
        return evs[-limit:]
