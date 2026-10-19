-- Canon store (canon.sqlite): one file per world, built once by ingestion, opened read-only
-- (sqlite URI mode=ro), shared by every campaign of that world. No rollback table exists here.
-- Uses the same `entity` and `record` envelope as the campaign store (see schema.sql), with
-- writer = 'ingest' and kinds below. Dates the books do not give are NULL / 'unknown'.

-- @@canon
CREATE TABLE canon_meta (           -- one row; campaigns pin `content_hash`
  world TEXT NOT NULL, ingest_version TEXT NOT NULL, content_hash TEXT NOT NULL,
  built_wall TEXT NOT NULL, extractor_models TEXT NOT NULL    -- JSON list of models used
);
CREATE TABLE canon_source (
  id TEXT PRIMARY KEY, title TEXT NOT NULL, lang TEXT NOT NULL, file_sha256 TEXT NOT NULL
);
CREATE TABLE canon_passage (        -- kind 'canon_passage': raw text chunk, the retrieval unit
  id        INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body = the passage text, original language
  source_id TEXT NOT NULL REFERENCES canon_source(id),
  chapter   TEXT, ord INTEGER NOT NULL,                  -- reading order inside the source
  char_from INTEGER NOT NULL, char_to INTEGER NOT NULL
);
CREATE VIRTUAL TABLE canon_passage_fts USING fts5(text, content='', tokenize='unicode61');
CREATE TABLE canon_embedding (passage_id INTEGER PRIMARY KEY, model TEXT NOT NULL, vec BLOB NOT NULL);

CREATE TABLE canon_event (          -- kind 'canon_event': who / what / how others reacted
  id         INTEGER PRIMARY KEY REFERENCES record(id),  -- record.body = WHAT happened, one or two sentences
  ekind      TEXT NOT NULL,         -- violence|magic|death|crime|miracle|scandal|politics|... (open)
  loudness   REAL NOT NULL CHECK (loudness BETWEEN 0 AND 1),
  order_key  INTEGER NOT NULL,      -- story order; always present
  when_prec  TEXT NOT NULL,         -- exact|day|season|year|unknown (record.t_from may be NULL-ish: see t_prec)
  confidence REAL NOT NULL,         -- extractor's own, 0..1
  review     TEXT NOT NULL DEFAULT 'unreviewed' CHECK (review IN ('unreviewed','ok','fixed','dropped'))
);
CREATE TABLE canon_participant (    -- WHO
  event_id INTEGER NOT NULL REFERENCES canon_event(id),
  entity   TEXT NOT NULL REFERENCES entity(id),
  role     TEXT NOT NULL,           -- actor|target|witness|bystander|beneficiary|victim (open)
  PRIMARY KEY (event_id, entity, role)
);
CREATE TABLE canon_knower (         -- who learned of it and how (seed for campaign knowledge)
  event_id INTEGER NOT NULL REFERENCES canon_event(id),
  entity   TEXT NOT NULL REFERENCES entity(id),   -- person or collective
  channel  TEXT NOT NULL,           -- same vocabulary as knowledge.channel
  source   TEXT, delay_minutes INTEGER,
  PRIMARY KEY (event_id, entity)
);
CREATE TABLE canon_reaction (       -- kind 'canon_reaction': HOW OTHERS REACTED
  id          INTEGER PRIMARY KEY REFERENCES record(id), -- record.body = the reaction, free text
  event_id    INTEGER NOT NULL REFERENCES canon_event(id),
  party       TEXT NOT NULL REFERENCES entity(id),       -- person or collective
  reaction    TEXT NOT NULL REFERENCES canon_vocab(reaction),   -- closed list: Jev can choose, not write
  attitude    TEXT,                 -- stance word from the attitude vocabulary
  delay_minutes INTEGER
);
CREATE TABLE canon_vocab (          -- closed reaction vocabulary per party kind
  party_kind TEXT NOT NULL, reaction TEXT PRIMARY KEY, description TEXT NOT NULL
);
CREATE TABLE canon_evidence (       -- every canon_* record -> the passages it was read from
  record_id INTEGER NOT NULL REFERENCES record(id),
  passage_id INTEGER NOT NULL REFERENCES canon_passage(id),
  quote_from INTEGER, quote_to INTEGER,
  PRIMARY KEY (record_id, passage_id)
);
CREATE TABLE canon_relation (       -- kind 'canon_relation': A to B over story order
  id INTEGER PRIMARY KEY REFERENCES record(id),
  a TEXT NOT NULL, b TEXT NOT NULL, rtype TEXT NOT NULL, from_order INTEGER, to_order INTEGER
);
CREATE TABLE canon_pivot (          -- kind 'canon_pivot': a canon event that is scheduled to happen
  id INTEGER PRIMARY KEY REFERENCES record(id),  -- record.body = the pivot
  event_id INTEGER REFERENCES canon_event(id),
  preconditions TEXT NOT NULL,      -- free text, evaluated by judgment against the divergence ledger
  precondition_entities TEXT NOT NULL DEFAULT '[]'
);
-- kinds without an extension table (envelope only): 'canon_rule' (world rules, magic, law, customs)
