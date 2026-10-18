"""SQLite schema. Events and facts are append-only (enforced by triggers)."""
from __future__ import annotations

import sqlite3

SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL,
    game_time INTEGER NOT NULL,
    location TEXT NOT NULL,
    participants TEXT NOT NULL,
    witnesses TEXT NOT NULL,
    notability REAL NOT NULL,
    payload TEXT NOT NULL,
    cause_id INTEGER REFERENCES events(id)
);
CREATE TABLE IF NOT EXISTS rollbacks (
    event_id INTEGER PRIMARY KEY REFERENCES events(id),
    reason TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS facts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    store TEXT NOT NULL CHECK (store IN ('canon', 'campaign')),
    content TEXT NOT NULL,
    source_event_id INTEGER REFERENCES events(id),
    game_time INTEGER NOT NULL,
    location TEXT NOT NULL,
    notability REAL NOT NULL,
    CHECK ((store = 'canon' AND source_event_id IS NULL)
        OR (store = 'campaign' AND source_event_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS fact_knowers (
    fact_id INTEGER NOT NULL REFERENCES facts(id),
    character TEXT NOT NULL,
    how TEXT NOT NULL CHECK (how IN ('witnessed', 'heard', 'told')),
    learned_at INTEGER NOT NULL,
    source TEXT,                                 -- NULL: perceived directly; else who told/said it
    event_id INTEGER REFERENCES events(id),      -- the event this knowledge came from
    PRIMARY KEY (fact_id, character)
);
CREATE INDEX IF NOT EXISTS idx_knowers_char ON fact_knowers(character);
CREATE INDEX IF NOT EXISTS idx_events_cause ON events(cause_id);

CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
BEGIN SELECT RAISE(ABORT, 'events are append-only'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_update BEFORE UPDATE ON facts
BEGIN SELECT RAISE(ABORT, 'facts are immutable'); END;
CREATE TRIGGER IF NOT EXISTS facts_no_delete BEFORE DELETE ON facts
BEGIN SELECT RAISE(ABORT, 'facts are immutable'); END;
"""


def connect(path: str = ":memory:") -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
