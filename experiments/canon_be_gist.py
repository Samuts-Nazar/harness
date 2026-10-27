"""Write the Ukrainian gist (canon_event.gist_uk) into the «Кров ельфів» canon store, then rebuild its FTS.

    python experiments/canon_be_gist.py [campaigns/canon/be.db] [--gists campaigns/canon/raw_be/gists.json]

gists.json is {event_id: one Ukrainian sentence}, translated by hand from the stored English `what`
(no model call, no network). Idempotent: running it again writes the same strings and rebuilds the same
search rows. The store is rewritten through a temporary copy, as in canon_be_finish.py.
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


def apply(db: str | Path, gists: str | Path) -> dict:
    db = Path(db)
    data = {int(k): v.strip() for k, v in json.loads(Path(gists).read_text(encoding="utf8")).items()}
    fd, tmp = tempfile.mkstemp(suffix=".db", dir=db.parent)
    os.close(fd)
    raw = Path(tempfile.mkdtemp(prefix="refine_raw_"))
    ref = Refiner(None, "none", db, tmp, [], [], raw_dir=raw, log=lambda *_: None)  # type: ignore[arg-type]
    ids = {r[0] for r in ref.con.execute("SELECT id FROM canon_event")}
    if set(data) != ids:
        raise SystemExit(f"gists.json does not match the events: missing {sorted(ids - set(data))[:5]}, "
                         f"extra {sorted(set(data) - ids)[:5]}")
    changed = 0
    for i, g in data.items():
        old = ref.con.execute("SELECT gist_uk FROM canon_event WHERE id=?", (i,)).fetchone()[0]
        if old != g:
            ref.con.execute("UPDATE canon_event SET gist_uk=? WHERE id=?", (g, i))
            changed += 1
    ref.con.commit()
    ref.rebuild_fts()
    out = {"events": len(ids), "changed": changed,
           "fts_rows": ref.con.execute("SELECT COUNT(*) FROM canon_event_fts").fetchone()[0],
           "model_calls": ref.stats["calls"]}
    ref.con.close()
    os.replace(tmp, db)
    raw.rmdir()
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("db", nargs="?", default=str(MAIN / "be.db"))
    ap.add_argument("--gists", default=str(MAIN / "raw_be" / "gists.json"))
    a = ap.parse_args()
    print(json.dumps(apply(a.db, a.gists), indent=1))


if __name__ == "__main__":
    main()
