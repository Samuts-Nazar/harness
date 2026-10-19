"""Canon store file: a subset of design/canon.sql plus the entity/record envelope.

Deviations (docs/assumptions.md T13-*): canon_knower carries learned_t/learned_line (when and where in
the text the holder learned it), canon_event carries day/part, its source lines and a verbatim quote,
and characters have a profile table. The FTS tables are regular (not contentless) so the pilot can show
text; a finished store may go back to contentless.
"""
from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path

from .vocab import REACTIONS

DDL = """
CREATE TABLE canon_meta (world TEXT NOT NULL, ingest_version TEXT NOT NULL, content_hash TEXT NOT NULL,
  built_wall TEXT NOT NULL, extractor_models TEXT NOT NULL);
CREATE TABLE canon_source (id TEXT PRIMARY KEY, title TEXT NOT NULL, lang TEXT NOT NULL, file_sha256 TEXT NOT NULL);
CREATE TABLE entity (id TEXT PRIMARY KEY,
  type TEXT NOT NULL CHECK (type IN ('person','collective','place','item','creature')),
  name TEXT NOT NULL, canon_id TEXT, origin INTEGER);
CREATE TABLE record (id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, slot TEXT, body TEXT NOT NULL,
  tags TEXT NOT NULL DEFAULT '[]', meta TEXT NOT NULL DEFAULT '{}', place TEXT REFERENCES entity(id),
  t_from INTEGER NOT NULL, t_to INTEGER,
  t_prec TEXT NOT NULL DEFAULT 'exact' CHECK (t_prec IN ('exact','hour','day','season','unknown')),
  notability REAL, logged_world INTEGER NOT NULL, logged_wall TEXT NOT NULL, turn INTEGER,
  writer TEXT NOT NULL, writer_ref TEXT);
CREATE TABLE canon_alias (entity TEXT NOT NULL REFERENCES entity(id), alias TEXT NOT NULL, PRIMARY KEY (entity, alias));
CREATE TABLE canon_character (entity TEXT PRIMARY KEY REFERENCES entity(id),
  who TEXT, role TEXT, standing TEXT, knows TEXT NOT NULL DEFAULT '[]', first_line INTEGER, unnamed INTEGER DEFAULT 0);
CREATE TABLE canon_passage (id INTEGER PRIMARY KEY REFERENCES record(id), source_id TEXT NOT NULL REFERENCES canon_source(id),
  chapter TEXT, ord INTEGER NOT NULL, char_from INTEGER NOT NULL, char_to INTEGER NOT NULL,
  line_from INTEGER NOT NULL, line_to INTEGER NOT NULL);
CREATE VIRTUAL TABLE canon_passage_fts USING fts5(text, tokenize='unicode61 remove_diacritics 0');
CREATE TABLE canon_event (id INTEGER PRIMARY KEY REFERENCES record(id), ekind TEXT NOT NULL,
  loudness REAL NOT NULL CHECK (loudness BETWEEN 0 AND 1), order_key INTEGER NOT NULL,
  when_prec TEXT NOT NULL, confidence REAL NOT NULL,
  review TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review IN ('unreviewed','ok','fixed','dropped')),
  day INTEGER, part TEXT, quote TEXT, lines TEXT NOT NULL DEFAULT '[]', local_id TEXT,
  day_to INTEGER, gist_uk TEXT, kw_uk TEXT, scene INTEGER, time_conf REAL, time_basis TEXT, src_from INTEGER, src_to INTEGER);
CREATE VIRTUAL TABLE canon_event_fts USING fts5(text, tokenize='unicode61 remove_diacritics 0');
CREATE TABLE canon_participant (event_id INTEGER NOT NULL REFERENCES canon_event(id),
  entity TEXT NOT NULL REFERENCES entity(id), role TEXT NOT NULL, PRIMARY KEY (event_id, entity, role));
CREATE TABLE canon_knower (event_id INTEGER NOT NULL REFERENCES canon_event(id),
  entity TEXT NOT NULL REFERENCES entity(id), channel TEXT NOT NULL, source TEXT, delay_minutes INTEGER,
  learned_t INTEGER, learned_prec TEXT, learned_line INTEGER, PRIMARY KEY (event_id, entity));
CREATE TABLE canon_vocab (party_kind TEXT NOT NULL, reaction TEXT PRIMARY KEY, description TEXT NOT NULL);
CREATE TABLE canon_reaction (id INTEGER PRIMARY KEY REFERENCES record(id), event_id INTEGER NOT NULL REFERENCES canon_event(id),
  party TEXT NOT NULL REFERENCES entity(id), reaction TEXT NOT NULL REFERENCES canon_vocab(reaction),
  attitude TEXT, delay_minutes INTEGER);
CREATE TABLE canon_evidence (record_id INTEGER NOT NULL REFERENCES record(id),
  passage_id INTEGER NOT NULL REFERENCES canon_passage(id), quote_from INTEGER, quote_to INTEGER,
  PRIMARY KEY (record_id, passage_id));
CREATE TABLE canon_relation (id INTEGER PRIMARY KEY REFERENCES record(id), a TEXT NOT NULL, b TEXT NOT NULL,
  rtype TEXT NOT NULL, from_order INTEGER, to_order INTEGER);
CREATE TABLE canon_embedding (event_id INTEGER NOT NULL REFERENCES canon_event(id), model TEXT NOT NULL,
  dim INTEGER NOT NULL, vec BLOB NOT NULL, PRIMARY KEY (event_id, model));
CREATE INDEX idx_knower_entity ON canon_knower(entity);
CREATE INDEX idx_part_entity ON canon_participant(entity);
"""


def open_store(path: str | Path) -> sqlite3.Connection:
    con = sqlite3.connect(str(path))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def create_store(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    if str(path) != ":memory:":
        p.parent.mkdir(parents=True, exist_ok=True)
        if p.exists():
            p.unlink()
    con = open_store(path)
    con.executescript(DDL)
    for r, (kind, desc) in REACTIONS.items():
        con.execute("INSERT INTO canon_vocab VALUES (?,?,?)", (kind, r, desc))
    con.commit()
    return con


def add_record(con: sqlite3.Connection, kind: str, body: str, *, t_from: int, t_prec: str = "unknown",
               place: str | None = None, notability: float | None = None, meta: dict | None = None,
               writer_ref: str = "") -> int:
    cur = con.execute(
        "INSERT INTO record(kind, body, place, t_from, t_prec, notability, meta, logged_world, logged_wall, "
        "writer, writer_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (kind, body, place, t_from, t_prec, notability, json.dumps(meta or {}, ensure_ascii=False), 0,
         time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "ingest", writer_ref))
    return int(cur.lastrowid)  # type: ignore[arg-type]
