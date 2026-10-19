-- Campaign store (campaign.sqlite). Executable; design/tools/build.py loads it and
-- builds the scenario tables in schema.md from real rows. Sections are marked `-- @@name`
-- and are quoted in schema.md.
-- Times are integer in-world minutes since the campaign epoch (day 1, 00:00 = 0).

-- @@core
CREATE TABLE entity (               -- identities only; everything descriptive is a record
  id        TEXT PRIMARY KEY,       -- 'ragnar', 'marta', 'town:vergen', 'place:heron-taproom'
  type      TEXT NOT NULL CHECK (type IN ('person','collective','place','item','creature')),
  name      TEXT NOT NULL,
  canon_id  TEXT,                   -- id in canon.sqlite if this entity exists in the books
  origin    INTEGER                 -- record that introduced it (entity is dead if that is rolled back)
);

CREATE TABLE record (               -- the envelope: EVERY record in the campaign log
  id            INTEGER PRIMARY KEY AUTOINCREMENT,   -- also the log position
  kind          TEXT NOT NULL,      -- open vocabulary; see the catalogue
  slot          TEXT,               -- "register" key: current value = latest alive record of (kind, slot)
  body          TEXT NOT NULL,      -- the content, free text
  tags          TEXT NOT NULL DEFAULT '[]',   -- JSON array, open vocabulary (panel groups, 'covert', ...)
  meta          TEXT NOT NULL DEFAULT '{}',   -- JSON object, open metadata
  place         TEXT REFERENCES entity(id),
  t_from        INTEGER NOT NULL,   -- IN-WORLD time: when it happened / became true / was learned
  t_to          INTEGER,            -- in-world end (NULL: instant or open-ended)
  t_prec        TEXT NOT NULL DEFAULT 'exact' CHECK (t_prec IN ('exact','hour','day','season','unknown')),
  notability    REAL CHECK (notability BETWEEN 0 AND 1),
  logged_world  INTEGER NOT NULL,   -- LOG time, world clock when written (>= t_from unless scheduled)
  logged_wall   TEXT NOT NULL,      -- LOG time, wall clock (UTC), for the dev view and cost audit
  turn          INTEGER,            -- turn counter at writing
  writer        TEXT NOT NULL CHECK (writer IN ('code','extractor','judgment','player','ingest')),
  writer_ref    TEXT,               -- 'j:<judgment id>' | model id | 'turn:<n>'
  CHECK (t_to IS NULL OR t_to >= t_from)
);
CREATE INDEX idx_record_slot ON record(kind, slot, t_from, id);
CREATE INDEX idx_record_kind ON record(kind, t_from);

CREATE TABLE record_link (          -- derivation and reference edges (child -> parent)
  child        INTEGER NOT NULL REFERENCES record(id),
  parent_store TEXT NOT NULL DEFAULT 'campaign' CHECK (parent_store IN ('campaign','canon')),
  parent       INTEGER NOT NULL,
  role         TEXT NOT NULL CHECK (role IN ('requires','supports','about','replaces')),
  span_from    INTEGER,             -- word range inside the parent's text (1-based, inclusive);
  span_to      INTEGER,             -- only for links to text units
  PRIMARY KEY (child, parent_store, parent, role)
);
CREATE INDEX idx_link_parent ON record_link(parent_store, parent, role);

CREATE TABLE rollback (             -- append-only tombstones; a record is dead iff it has a row here
  record_id  INTEGER PRIMARY KEY REFERENCES record(id),
  root_id    INTEGER NOT NULL,      -- the record whose removal started this cascade
  by_record  INTEGER REFERENCES record(id),   -- the interruption / correction that caused it (NULL: debug)
  reason     TEXT NOT NULL CHECK (reason IN ('interruption','model_error','turn_failed','debug')),
  at_seq     INTEGER NOT NULL       -- max(record.id) when the rollback ran
);

CREATE TABLE stale (                -- alive, but one of several `supports` parents died
  record_id  INTEGER PRIMARY KEY REFERENCES record(id),
  lost_parent INTEGER NOT NULL,
  at_seq     INTEGER NOT NULL
);

CREATE TABLE judgment (             -- provenance of every typed judgment (not world state)
  id        INTEGER PRIMARY KEY AUTOINCREMENT,
  batch     INTEGER NOT NULL,       -- questions about one state share a batch (one Jev call)
  tag       TEXT NOT NULL,          -- 'salience', 'unknown_claim', 'reach', 'symptom', ...
  kind      TEXT NOT NULL CHECK (kind IN ('yes_no','choice','score')),
  question  TEXT NOT NULL,
  options   TEXT,                   -- JSON, for choices
  answer    TEXT NOT NULL,
  p         REAL,                   -- probability of the answer
  backend   TEXT NOT NULL,          -- 'jev-1.13' | 'jev-1.14' | an allowed cheap LLM
  escalated INTEGER NOT NULL DEFAULT 0,   -- 1: Jev p < 0.8, the LLM answer was used
  inputs    TEXT NOT NULL DEFAULT '[]',   -- JSON: record ids the question was built from
  logged_wall TEXT NOT NULL,
  cost_usd  REAL
);

-- @@views
CREATE VIEW v_alive AS
  SELECT r.* FROM record r
  WHERE NOT EXISTS (SELECT 1 FROM rollback b WHERE b.record_id = r.id);

-- current value of every register ("now"; the as-of form takes :T and :L, see schema.md)
CREATE VIEW v_current AS
  SELECT r.* FROM v_alive r
  WHERE r.slot IS NOT NULL
    AND r.id = (SELECT x.id FROM v_alive x WHERE x.kind = r.kind AND x.slot = r.slot
                ORDER BY x.t_from DESC, x.id DESC LIMIT 1);

-- @@text
CREATE TABLE text_unit (            -- kinds: player_input, narration, action, hidden, utterance
  id        INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body = text delivered when written
  actor     TEXT REFERENCES entity(id),    -- speaker / acting character
  shown     INTEGER NOT NULL DEFAULT 1,    -- 0: never displayed (narrator's covert channel)
  audience  TEXT NOT NULL DEFAULT '[]',    -- JSON: who perceived it directly; computed by code once, at writing
  generated TEXT NOT NULL                  -- what the model produced (superset of body)
);
CREATE TABLE interruption (         -- kind 'interruption'
  id           INTEGER PRIMARY KEY REFERENCES record(id),
  utterance_id INTEGER NOT NULL REFERENCES text_unit(id),
  after_word   INTEGER NOT NULL CHECK (after_word >= 1),
  mode         TEXT NOT NULL CHECK (mode IN ('live','retro'))
);
CREATE VIEW v_delivered AS          -- how many words of each utterance were really said
  SELECT t.id, t.actor,
         MIN(COALESCE((SELECT MIN(i.after_word) FROM interruption i
                       JOIN v_alive ia ON ia.id = i.id WHERE i.utterance_id = t.id), 1000000),
             LENGTH(TRIM(r.body)) - LENGTH(REPLACE(TRIM(r.body), ' ', '')) + 1) AS delivered_words
  FROM text_unit t JOIN v_alive r ON r.id = t.id WHERE r.kind = 'utterance';

-- @@presence
CREATE TABLE presence (             -- kind 'presence', slot 'presence|<entity>'
  id      INTEGER PRIMARY KEY REFERENCES record(id),
  entity  TEXT NOT NULL REFERENCES entity(id),
  place   TEXT NOT NULL REFERENCES entity(id),
  zone    TEXT NOT NULL CHECK (zone IN ('room','nearby','away'))
);

-- @@fact
CREATE TABLE fact (                 -- kind 'fact': world truth, or a character's assertion about it
  id          INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body = the fact as free text
  status      TEXT NOT NULL CHECK (status IN ('established','asserted')),
  asserted_by TEXT REFERENCES entity(id),
  CHECK ((status = 'asserted') = (asserted_by IS NOT NULL))
);

-- @@knowledge
CREATE TABLE knowledge (            -- kind 'knowledge': one holder's version of something
  id          INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body = the holder's VERSION (may be distorted)
                                                           -- record.t_from = when the holder learned it
  holder      TEXT NOT NULL REFERENCES entity(id),         -- a person OR a collective
  about       INTEGER,            -- the truth record (fact / state / canon) this is a version of; NULL = rumour with no truth record
  about_store TEXT NOT NULL DEFAULT 'campaign' CHECK (about_store IN ('campaign','canon')),
  channel     TEXT NOT NULL CHECK (channel IN
              ('witnessed','heard','overheard','told','hearsay','read','inferred','sensed','innate')),
  source      TEXT REFERENCES entity(id),                  -- who said / told it; may be a collective; NULL = diffuse or direct
  source_knowledge INTEGER REFERENCES knowledge(id),       -- the source's own record: the chain
  hops        INTEGER NOT NULL DEFAULT 0,
  operators   TEXT NOT NULL DEFAULT '[]',  -- distortion operators applied vs. the truth, JSON list
  stance      TEXT NOT NULL DEFAULT 'unjudged',            -- unjudged|firsthand|believes|suspects|doubts|rejects
  confidence  REAL,
  sincerity   TEXT NOT NULL DEFAULT 'unknown' CHECK (sincerity IN ('unknown','sincere','lie','mistaken')),
                                                           -- source's sincerity: narrator/judgment-only, never in a holder's context
  salience    TEXT NOT NULL DEFAULT 'unjudged' CHECK (salience IN ('unjudged','noteworthy','ignored'))
);
CREATE INDEX idx_knowledge_holder ON knowledge(holder);
CREATE INDEX idx_knowledge_about ON knowledge(about_store, about);
CREATE TABLE belief_update (        -- kind 'belief_update', slot 'bel|<knowledge id>'
  id           INTEGER PRIMARY KEY REFERENCES record(id),
  knowledge_id INTEGER NOT NULL REFERENCES knowledge(id),
  stance       TEXT NOT NULL,
  confidence   REAL
);
CREATE TABLE membership (           -- kind 'membership', slot 'mem|<member>|<collective>'
  id         INTEGER PRIMARY KEY REFERENCES record(id),
  member     TEXT NOT NULL REFERENCES entity(id),
  collective TEXT NOT NULL REFERENCES entity(id),
  present    INTEGER NOT NULL DEFAULT 1
);

-- @@attitude
CREATE TABLE attitude (             -- kind 'attitude', slot 'att|<holder>|<knowledge id>'
  id           INTEGER PRIMARY KEY REFERENCES record(id),  -- record.body: short reason, optional
  holder       TEXT NOT NULL REFERENCES entity(id),
  knowledge_id INTEGER NOT NULL REFERENCES knowledge(id),  -- the version the attitude reacts to
  about        INTEGER,           -- the fact/state it is about (= knowledge.about), NULL for pure rumour
  stance       TEXT NOT NULL,     -- from the world's closed attitude vocabulary
  magnitude    REAL NOT NULL CHECK (magnitude BETWEEN 0 AND 1)
);

-- @@state
CREATE TABLE state_elem (           -- kind 'state', slot '<subject>|<elem>'
  id          INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body: the element in this state, free text
  subject     TEXT NOT NULL REFERENCES entity(id),         -- person, companion, item
  elem        TEXT NOT NULL,      -- identity of the element: 'sword:steel', 'poison:foxglove', 'wound:left-forearm'
  category    TEXT NOT NULL,      -- default panel tag: body|effect|appearance|gear|possession|companion|standing|posture|inner
  present     INTEGER NOT NULL DEFAULT 1,   -- 0: the element has ended (sheathed, healed, removed)
  observable  INTEGER NOT NULL,             -- 1: others in the scene can perceive it
  perceptibility TEXT,            -- optional JSON {"sight":0.9,"examination":0.8}: refines `observable`
  self_aware  TEXT NOT NULL DEFAULT 'known' CHECK (self_aware IN ('known','suspected','unaware')),
  expires_at  INTEGER             -- timed effects: lapses at this in-world time without a new record
);

-- @@intent
CREATE TABLE intent (               -- kind 'intent'
  id            INTEGER PRIMARY KEY REFERENCES record(id),  -- record.body: what the holder meant to say / do
  holder        TEXT NOT NULL REFERENCES entity(id),
  type          TEXT NOT NULL CHECK (type IN ('unsaid','tellable','plan')),
  audience      TEXT REFERENCES entity(id),
  utterance_id  INTEGER REFERENCES text_unit(id),           -- 'unsaid': the cut utterance
  from_word     INTEGER,                                    -- 'unsaid': first undelivered word
  secrecy       REAL,
  player_salience REAL
);
CREATE TABLE intent_resolution (    -- kind 'intent_resolved'
  id        INTEGER PRIMARY KEY REFERENCES record(id),
  intent_id INTEGER NOT NULL REFERENCES intent(id),
  outcome   TEXT NOT NULL CHECK (outcome IN ('said','done','dropped','expired'))
);

-- @@spread
CREATE TABLE reach (                -- kind 'reach': memoised "did news of X reach place P"
  id        INTEGER PRIMARY KEY REFERENCES record(id),    -- record.t_from = judged arrival time
  place     TEXT NOT NULL REFERENCES entity(id),
  about     INTEGER NOT NULL REFERENCES record(id),       -- the truth record that travelled
  reached   INTEGER NOT NULL,
  earliest  INTEGER               -- physical lower bound computed by code from the map graph
);

-- @@correction
CREATE TABLE correction (           -- kind 'correction': a model-error explanation
  id         INTEGER PRIMARY KEY REFERENCES record(id),   -- record.body: the player's words, verbatim
  target     INTEGER NOT NULL REFERENCES record(id),      -- the world output that was wrong (its narration record)
  applies_to TEXT NOT NULL DEFAULT '["narrator","npc","extractor"]'
);

-- @@divergence
CREATE TABLE divergence (           -- kind 'divergence', slot 'div|<key>': the campaign-vs-canon ledger
  id        INTEGER PRIMARY KEY REFERENCES record(id),    -- record.body: what differs, one sentence
  status    TEXT NOT NULL CHECK (status IN ('open','absorbed','reconverged')),
  threads   TEXT NOT NULL DEFAULT '[]',                   -- canon pivots / threads it touches
  magnitude REAL
);
CREATE TABLE drift_ruling (         -- kind 'drift_ruling': narration deviated from canon and was JUSTIFIED
  id           INTEGER PRIMARY KEY REFERENCES record(id),
  output       INTEGER NOT NULL REFERENCES record(id),    -- the narration record
  explained_by INTEGER NOT NULL REFERENCES record(id)     -- the campaign record that justifies it
);

-- @@immutable
-- generated by build.py for every table above (record, record_link, rollback, stale, judgment,
-- text_unit, ..., drift_ruling):
--   CREATE TRIGGER <t>_no_update BEFORE UPDATE ON <t> BEGIN SELECT RAISE(ABORT,'append-only'); END;
--   CREATE TRIGGER <t>_no_delete BEFORE DELETE ON <t> BEGIN SELECT RAISE(ABORT,'append-only'); END;
CREATE TRIGGER link_requires_alive BEFORE INSERT ON record_link
WHEN NEW.role = 'requires' AND NEW.parent_store = 'campaign'
 AND EXISTS (SELECT 1 FROM rollback WHERE record_id = NEW.parent)
BEGIN SELECT RAISE(ABORT, 'a record cannot be derived from a rolled-back record'); END;
