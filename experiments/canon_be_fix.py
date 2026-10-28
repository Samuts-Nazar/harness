"""Fix the problems found in reports/canon_be/VERIFY.md (task 8b follow-up), idempotent.

    python experiments/canon_be_fix.py [campaigns/canon/be.db]

1. Event 672 happens in the poultry yard, not the temple park. There is no such place in the cast, so a
   minimal entity `place:temple-poultry-yard` is added and the event is moved there; the record meta gets
   the flag `place_unverified`, and "in the temple park" in the stored `what` becomes "in the temple
   poultry yard" (the only text change).
2. Learned time of flashback knowers. A told/heard/read/inferred row whose event is a `before` event
   (t_from < 0) got the ingest's time_at_line, which is day 21 afternoon (29700) for flashback lines. These
   rows (699, 707, 729, 751) now learn at the event's own time, delay 0. Rows with an early learned time
   (letters, 474, 624, 645, 646) are correct and are not touched: the rule only matches learned_t 29700.
3. Bystanders without knower rows are by design not knowers: nothing is changed (see VERIFY.md).
4. The misspelt alias «Йеннфер» of `char:yennefer` (outsider live check, problem 2: it became her
   appearance label, a name form the player never learned) is removed from `canon_alias`, and from
   `raw_be/entities.json` next to the store when that file exists.

The FTS table is rebuilt at the end. No model call, no network.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from harness.canon.refine import Refiner

MAIN = Path("/home/cock/projects/harness/campaigns/canon")
PLACE = "place:temple-poultry-yard"
DAY21_PM = 29700
BAD_ALIASES = [("char:yennefer", "Йеннфер")]


def fix_raw_entities(path: Path) -> int:
    """Drop the bad aliases from an ingest's entities.json (idempotent). Returns how many."""
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for ent in data.get("entities", []):
        for eid, alias in BAD_ALIASES:
            if ent.get("id") == eid and alias in ent.get("aliases", []):
                ent["aliases"] = [a for a in ent["aliases"] if a != alias]
                n += 1
    if n:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return n


def fix(db: str | Path) -> dict:
    db = Path(db)
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=db.parent)
    os.close(fd)
    raw = Path(tempfile.mkdtemp(prefix="refine_raw_"))
    ref = Refiner(None, "none", db, tmp, [], [], raw_dir=raw, log=lambda *_: None)  # type: ignore[arg-type]
    con = ref.con
    n_place = 0
    if not con.execute("SELECT 1 FROM entity WHERE id=?", (PLACE,)).fetchone():
        con.execute("INSERT INTO entity (id, type, name) VALUES (?, 'place', ?)", (PLACE, "птахівник храму"))
    rec = con.execute("SELECT body, place, meta FROM record WHERE id=672").fetchone()
    if rec["place"] != PLACE:
        meta = json.loads(rec["meta"] or "{}")
        flags = meta.setdefault("flags", [])
        if "place_unverified" not in flags:
            flags.append("place_unverified")
        body = rec["body"].replace("in the temple park", "in the temple poultry yard")
        con.execute("UPDATE record SET place=?, body=?, meta=? WHERE id=672",
                    (PLACE, body, json.dumps(meta, ensure_ascii=False)))
        n_place = 1
    cur = con.execute(
        "UPDATE canon_knower SET learned_t=(SELECT t_from FROM record WHERE id=canon_knower.event_id), "
        "delay_minutes=0 WHERE learned_t=? AND channel IN ('told','heard','read','inferred') "
        "AND event_id IN (SELECT id FROM record WHERE t_from < 0)", (DAY21_PM,))
    n_learned = cur.rowcount
    n_alias = 0
    for eid, alias in BAD_ALIASES:
        n_alias += con.execute("DELETE FROM canon_alias WHERE entity=? AND alias=?",
                               (eid, alias)).rowcount
    con.commit()
    ref.rebuild_fts()
    out = {"place_fixed": n_place, "learned_fixed": n_learned, "alias_removed": n_alias,
           "raw_alias_removed": fix_raw_entities(db.parent / "raw_be" / "entities.json")}
    con.close()
    os.replace(tmp, db)
    raw.rmdir()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db", nargs="?", default=str(MAIN / "be.db"))
    print(json.dumps(fix(ap.parse_args().db), indent=1))


if __name__ == "__main__":
    main()
