"""Finish a canon store loaded from subagent JSON with the Refiner passes that need no model.

    python experiments/canon_be_finish.py campaigns/canon/be.db [--source data/witcher_books.txt]

No provider is built and no network call is made. What it runs, and why only this (task 8b):

- pass_time with no scenes: there is no scene timeline for this store (timeline.build needs a model), so
  the pass only fills src_from/src_to (where the event sits in the arc text). The event times already
  come from the subagents' time objects; pass_time with scenes would overwrite them, and without scenes it
  does not touch them.
- the "people present are knowers" half of code_knower_rules: a present participant (actor, target,
  victim, speaker, listener, witness) without a knower row gets a `witnessed` row at the event's time.
  The other half is NOT run: it treats every event with t_from < 0 as a retold past event and demotes
  `witnessed` to `heard` for speakers and listeners. Here chapter 1 is a real scene stored as
  `before` 0.9-1.0 years, so that rule would demote correct rows (128 on the first load). Its retiming
  step needs scenes and would do nothing.
- rebuild_fts: the search table from quote and record text (no gist exists).
- no embeddings: the game opens `Canon(path)` without an embedder, so recall is FTS-only and ignores
  `canon_embedding`; HashEmbedder vectors would only matter to a caller that passes a HashEmbedder, and
  SEM_MIN is calibrated for a real multilingual model, not trigram hashing.

Not run: pass_places (falls back to place:vizim), pass_knowers and pass_gist (model calls),
pass_reactions (deletes the reactions loaded from JSON).

The store is rewritten in place through a temporary copy (Refiner always copies src to out).
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.canon import chunk
from harness.canon.refine import PRESENT, Refiner


def arc_paras(con: sqlite3.Connection, source: str | Path) -> list[chunk.Para]:
    """Rebuild the paragraphs the store was loaded from and check they give the stored passage offsets."""
    first, last = con.execute("SELECT MIN(line_from), MAX(line_to) FROM canon_passage").fetchone()
    chapters = [(r[1], r[0]) for r in con.execute(
        "SELECT chapter, MIN(line_from) FROM canon_passage GROUP BY chapter ORDER BY 2")]
    chapters[0] = (first, chapters[0][1])
    paras = chunk.read_arc(source, first, last, chapters)
    by_line = {p.line: p for p in paras}
    for line_from, char_from in con.execute("SELECT line_from, char_from FROM canon_passage"):
        p = by_line.get(line_from)
        if p is None or p.char_from != char_from:
            raise SystemExit(f"source does not match the store at line {line_from}: wrong --source?")
    return paras


def add_present_knowers(ref: Refiner) -> int:
    n = 0
    for ev in ref.events():
        have = {k["entity"] for k in ev["know"]}
        for p in ev["parts"]:
            ent = ref.ents.get(p["entity"])
            if p["role"] not in PRESENT or p["entity"] in have or ent is None or \
                    ent["type"] not in ("person", "collective", "creature"):
                continue
            ref._upsert_knower(ev, p["entity"], "witnessed", None, None)
            have.add(p["entity"])
            n += 1
    ref.con.commit()
    return n


def finish(db: str | Path, source: str | Path) -> dict:
    db = Path(db)
    with sqlite3.connect(db) as con:
        paras = arc_paras(con, source)
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=db.parent)
    os.close(fd)
    raw = Path(tempfile.mkdtemp(prefix="refine_raw_"))
    ref = Refiner(None, "subagent-json", db, tmp, paras, [], raw_dir=raw, log=lambda s: None)  # type: ignore[arg-type]
    ref.pass_time()
    added = add_present_knowers(ref)
    ref.rebuild_fts()
    q = lambda s: ref.con.execute(s).fetchone()[0]  # noqa: E731
    out = {"events": q("SELECT COUNT(*) FROM canon_event"),
           "src_offsets": q("SELECT COUNT(*) FROM canon_event WHERE src_from IS NOT NULL"),
           "present_knowers_added": added,
           "knowers": q("SELECT COUNT(*) FROM canon_knower"),
           "reactions": q("SELECT COUNT(*) FROM canon_reaction"),
           "fts_rows": q("SELECT COUNT(*) FROM canon_event_fts"),
           "embeddings": q("SELECT COUNT(*) FROM canon_embedding"),
           "model_calls": ref.stats["calls"]}
    ref.con.close()
    os.replace(tmp, db)
    raw.rmdir()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db")
    ap.add_argument("--source", default="data/witcher_books.txt")
    a = ap.parse_args()
    print(json.dumps(finish(a.db, a.source), indent=1))


if __name__ == "__main__":
    main()
