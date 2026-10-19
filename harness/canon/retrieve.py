"""Knowledge-filtered canon retrieval (pilot).

Epistemic isolation at retrieval, in code: `recall(holder, query, as_of)` returns only canon events the
holder (or a collective the holder belongs to) has a knower row for, learned at or before `as_of`
(in-world minutes, day 1 00:00 = 0). Raw passages never go to a character; `passages()` is for the
narrator and for judgments (unfiltered) and says so in its name.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

_WORD = re.compile(r"[^\W\d_]{3,}", re.U)
STOP = {"що", "як", "чи", "це", "від", "про", "для", "його", "вона", "вони", "але", "так", "там", "тут", "коли",
        "який", "яка", "які", "чому", "ким", "хто", "кого", "мав", "має", "був", "була", "було", "були", "the",
        "and", "who", "what", "how", "did", "does"}


def fts_query(q: str) -> str:
    """OR of prefix terms; Ukrainian is inflected, so long words are cut by two letters."""
    out = []
    for w in _WORD.findall(q.lower()):
        if w in STOP:
            continue
        stem = w[:-2] if len(w) > 6 else w[:-1] if len(w) > 4 else w
        out.append(f'"{stem}"*')
    return " OR ".join(dict.fromkeys(out))


class Canon:
    def __init__(self, path: str | Path | sqlite3.Connection) -> None:
        if isinstance(path, sqlite3.Connection):
            self.con = path
        else:
            self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            self.con.row_factory = sqlite3.Row

    # ---- helpers -------------------------------------------------------------------------
    def holders(self, holder: str) -> list[str]:
        rows = self.con.execute("SELECT b FROM canon_relation WHERE a=? AND rtype='member_of'", (holder,))
        return [holder, *[r["b"] for r in rows]]

    def name(self, eid: str) -> str:
        r = self.con.execute("SELECT name FROM entity WHERE id=?", (eid,)).fetchone()
        return r["name"] if r else eid

    def profile(self, eid: str) -> dict[str, Any] | None:
        r = self.con.execute("SELECT * FROM canon_character WHERE entity=?", (eid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["knows"] = json.loads(d["knows"])
        d["name"] = self.name(eid)
        return d

    def _fts_ids(self, table: str, q: str, limit: int = 60) -> list[int]:
        fq = fts_query(q)
        if not fq:
            return []
        try:
            return [r[0] for r in self.con.execute(
                f"SELECT rowid FROM {table} WHERE {table} MATCH ? ORDER BY bm25({table}) LIMIT ?", (fq, limit))]
        except sqlite3.OperationalError:
            return []

    def _mentioned(self, q: str) -> list[str]:
        """Entities whose name or alias appears in the question (prefix match on the stem)."""
        ql = q.lower()
        out = []
        for r in self.con.execute("SELECT entity, alias FROM canon_alias"):
            a = r["alias"].lower()
            stem = a[:-2] if len(a) > 5 else a
            if len(stem) >= 4 and stem in ql and r["entity"] not in out:
                out.append(r["entity"])
        return out

    # ---- filtered recall -----------------------------------------------------------------
    def recall(self, holder: str, query: str, as_of: int, k: int = 6) -> dict[str, Any]:
        hs = self.holders(holder)
        ph = ",".join("?" * len(hs))
        known = {r["event_id"]: dict(r) for r in self.con.execute(
            f"SELECT event_id, entity, channel, source, learned_t FROM canon_knower "
            f"WHERE entity IN ({ph}) AND COALESCE(learned_t, -999999999) <= ?", (*hs, as_of))}
        rank: dict[int, float] = {}
        for i, eid in enumerate(self._fts_ids("canon_event_fts", query)):
            if eid in known:
                rank[eid] = rank.get(eid, 0) + 1.0 / (1 + i)
        for i, pid in enumerate(self._fts_ids("canon_passage_fts", query)):
            for r in self.con.execute("SELECT record_id FROM canon_evidence WHERE passage_id=?", (pid,)):
                if r["record_id"] in known:
                    rank[r["record_id"]] = rank.get(r["record_id"], 0) + 0.7 / (1 + i)
        for ent in self._mentioned(query):
            for r in self.con.execute("SELECT event_id FROM canon_participant WHERE entity=?", (ent,)):
                if r["event_id"] in known:
                    rank[r["event_id"]] = rank.get(r["event_id"], 0) + 0.25
        top = sorted(rank, key=lambda e: -rank[e])[:k]
        events = []
        for eid in top:
            e = self.con.execute(
                "SELECT r.body, r.place, r.t_from, c.quote, c.lines, c.ekind FROM record r "
                "JOIN canon_event c ON c.id=r.id WHERE r.id=?", (eid,)).fetchone()
            kn = known[eid]
            own = [dict(x) for x in self.con.execute(
                "SELECT reaction, attitude FROM canon_reaction WHERE event_id=? AND party IN (%s)" % ph, (eid, *hs))]
            events.append({"id": eid, "what": e["body"], "place": self.name(e["place"]) if e["place"] else None,
                           "t": e["t_from"], "how_known": kn["channel"],
                           "source": self.name(kn["source"]) if kn["source"] else None,
                           "learned_t": kn["learned_t"], "quote": e["quote"], "kind": e["ekind"],
                           "own_reaction": own})
        return {"holder": holder, "as_of": as_of, "events": events, "profile": self.profile(holder),
                "n_known": len(known)}

    # ---- unfiltered (narrator / judgments only) ------------------------------------------
    def passages_unfiltered(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        out = []
        for pid in self._fts_ids("canon_passage_fts", query)[:k]:
            r = self.con.execute("SELECT p.line_from, p.line_to, r.body FROM canon_passage p "
                                 "JOIN record r ON r.id=p.id WHERE p.id=?", (pid,)).fetchone()
            out.append({"id": pid, "lines": (r["line_from"], r["line_to"]), "text": r["body"]})
        return out
