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
import threading
from pathlib import Path
from typing import Any

_WORD = re.compile(r"[^\W\d_]{3,}", re.U)
STOP = {"що", "як", "чи", "це", "від", "про", "для", "його", "вона", "вони", "але", "так", "там", "тут", "коли",
        "який", "яка", "які", "чому", "ким", "хто", "кого", "мав", "має", "був", "була", "було", "були", "the",
        "and", "who", "what", "how", "did", "does", "знає", "знав", "знаю", "знаєш", "відомо", "робив", "зробив",
        "зробила", "сказав", "казав", "можна", "треба", "ще", "вже", "тільки", "коли", "десь", "щодо", "чого",
        "цієї", "цього", "того", "тієї", "цей", "ця", "ці", "ніч", "дні", "відбувалося", "відбувалось", "відбулося",
        "сталося", "трапилося", "проти", "ночі", "вночі", "сьогодні", "вчора", "хто", "така", "такий", "яку", "якою"}


_SPLIT = re.compile(r"\s+(?:і|й|та|а також|або)\s+|[,;?!]\s*", re.I)


def split_question(q: str) -> list[str]:
    """The whole question first, then its clauses when it asks several things at once ("where from and who is")."""
    whole = q.strip()
    subs = [p.strip() for p in _SPLIT.split(whole) if len(stems(p)) >= 1]
    return [whole] + subs if len(subs) > 1 else [whole]


def _stem(w: str) -> str:
    if len(w) > 6:
        return w[:-2]
    if len(w) >= 4 and w[-1] in "аяіуеєюиоії":
        return w[:-1]
    return w


def stems(q: str) -> list[str]:
    out = []
    for w in _WORD.findall(q.lower()):
        if w in STOP:
            continue
        out.append(_stem(w))
    return list(dict.fromkeys(out))


def fts_query(q: str) -> str:
    """OR of prefix terms; Ukrainian is inflected, so long words are cut by two letters."""
    out = []
    for w in _WORD.findall(q.lower()):
        if w in STOP:
            continue
        out.append(f'"{_stem(w)}"*')
    return " OR ".join(dict.fromkeys(out))


SEM_MIN = 0.56      # cosine below this is noise for qwen/qwen3-embedding-8b on Ukrainian text (calibrated, docs/tools.md)
SEM_BAND = 0.15     # keep events within this distance of the best score
RARE = 0.25         # a query term is "rare" if it occurs in at most this share of the events


class Canon:
    def __init__(self, path: str | Path | sqlite3.Connection, embedder: Any = None) -> None:
        self.embedder = embedder
        self._lock = threading.RLock()   # one connection, shared by the engine's worker threads
        self._vecs: dict[int, list[float]] | None = None
        self._df: tuple[int, dict[str, int]] | None = None
        if isinstance(path, sqlite3.Connection):
            self.con = path
        else:
            self.con = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
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
        """Entities whose name or alias starts a word of the question. Persons are resolved before
        collectives and places: a collective is added only for words no person explained."""
        words = _WORD.findall(q.lower())
        found: dict[str, tuple[int, str]] = {}   # entity -> (rank by type, matched word)
        order = {"person": 0, "creature": 1, "collective": 2, "place": 3, "item": 4}
        for r in self.con.execute("SELECT a.entity, a.alias, e.type FROM canon_alias a JOIN entity e ON e.id=a.entity"):
            al = r["alias"].lower().strip("«»\"' ")
            if " " in al or len(al) < 4:
                continue
            stem = al[:-2] if len(al) > 5 else al
            for w in words:
                if w.startswith(stem) or (len(w) >= 4 and al.startswith(w[:-1] if len(w) > 5 else w) and len(w) >= len(stem) - 1):
                    found.setdefault(r["entity"], (order.get(r["type"], 5), w))
        explained = {w for (rk, w) in found.values() if rk == 0}
        out = [e for e, (rk, w) in sorted(found.items(), key=lambda kv: kv[1][0]) if rk == 0 or w not in explained]
        return out

    # ---- filtered recall -----------------------------------------------------------------
    def _event_text(self, eid: int) -> str:
        r = self.con.execute("SELECT text FROM canon_event_fts WHERE rowid=?", (eid,)).fetchone()
        return (r[0] if r else "").lower()

    def _load_vecs(self) -> dict[int, list[float]]:
        if self._vecs is None:
            from .embed import unpack
            self._vecs = {}
            if self.embedder is not None:
                try:
                    for r in self.con.execute("SELECT event_id, vec FROM canon_embedding WHERE model=?", (self.embedder.model,)):
                        self._vecs[r["event_id"]] = unpack(r["vec"])
                except sqlite3.OperationalError:
                    pass
        return self._vecs

    def _semantic(self, parts: list[str]) -> list[dict[int, float]]:
        """Cosine similarity of every event to each part of the question (empty without an embedder)."""
        vecs = self._load_vecs()
        if not vecs:
            return [{} for _ in parts]
        from .embed import cosine
        try:
            qs = self.embedder.embed(parts)
        except Exception:  # noqa: BLE001 - a failed embedding call must not stop play: lexical recall still works
            return [{} for _ in parts]
        return [{eid: cosine(q, v) for eid, v in vecs.items()} for q in qs]

    def _is_rare(self, term: str) -> bool:
        if self._df is None:
            texts = [r[0].lower() for r in self.con.execute("SELECT text FROM canon_event_fts")]
            self._df = (max(1, len(texts)), {})
            self._texts = texts
        n, cache = self._df
        if term not in cache:
            cache[term] = sum(1 for t in self._texts if term in t)
        return cache[term] / n <= RARE

    def rank(self, query: str, pool: set[int] | dict[int, Any], *, min_cover: float = 0.6) -> dict[int, float]:
        """Relevance of the events in `pool` to the query (see `recall`); only events that clear the bar."""
        with self._lock:
            parts = split_question(query)
            sems = self._semantic(parts)
            lex_ids = {e for e in self._fts_ids("canon_event_fts", query) if e in pool}
            for part in parts[1:]:
                lex_ids |= {e for e in self._fts_ids("canon_event_fts", part) if e in pool}
            cand = set(lex_ids) | {e for e in pool if any(sm.get(e, 0) >= SEM_MIN for sm in sems)}
            scored: dict[int, float] = {}
            for eid in cand:
                txt = self._event_text(eid)
                best = None
                for part, sm in zip(parts, sems):
                    terms = stems(part)
                    rare = [t for t in terms if self._is_rare(t)]
                    lex = (sum(1 for t in rare if t in txt) / len(rare)) if rare else 0.0
                    s_ = sm.get(eid, 0.0)
                    passes = s_ >= SEM_MIN or (rare and lex >= min_cover) or \
                        (not rare and not sm and terms and sum(1 for t in terms if t in txt) >= max(1, len(terms) // 2))
                    if passes:
                        v = s_ + 0.3 * lex
                        best = v if best is None else max(best, v)
                if best is not None:
                    scored[eid] = best
            # the book's own words: an event whose source passage holds most of the query's words
            for part in parts:
                allt = stems(part)
                terms = [t for t in allt if self._is_rare(t)] or allt
                if not terms:
                    continue
                for pid in self._fts_ids("canon_passage_fts", part, limit=6):
                    ptxt = (self.con.execute("SELECT body FROM record WHERE id=?", (pid,)).fetchone() or [""])[0].lower()
                    cover = sum(1 for t in terms if t in ptxt) / len(terms)
                    if cover < 0.75:
                        continue
                    for r in self.con.execute("SELECT record_id FROM canon_evidence WHERE passage_id=?", (pid,)):
                        if r["record_id"] in pool:
                            v = 0.45 + 0.3 * cover
                            scored[r["record_id"]] = max(scored.get(r["record_id"], 0.0), v)
            for ent in self._mentioned(query):
                for r in self.con.execute("SELECT event_id FROM canon_participant WHERE entity=?", (ent,)):
                    if r["event_id"] in scored:
                        scored[r["event_id"]] += 0.03
            if scored:
                top = max(scored.values())
                scored = {e: v for e, v in scored.items() if v >= top - SEM_BAND}
            return scored

    def recall(self, holder: str, query: str, as_of: int, k: int = 6, *, min_cover: float = 0.6,
               verify: Any = None) -> dict[str, Any]:
        """Events the holder knows (by as_of) that answer the query. Two signals: a multilingual embedding
        (when an embedder is given) and Ukrainian full-text over gist, keywords, quote and record. An event
        is returned only if it clears a relevance bar: semantic similarity >= SEM_MIN, or at least 60% of
        the query's RARE content words occur in it (names that occur everywhere do not count). An unrelated
        question gets nothing back rather than the nearest noise."""
        with self._lock:
            hs = self.holders(holder)
            ph = ",".join("?" * len(hs))
            known = {r["event_id"]: dict(r) for r in self.con.execute(
                f"SELECT event_id, entity, channel, source, learned_t FROM canon_knower "
                f"WHERE entity IN ({ph}) AND COALESCE(learned_t, -999999999) <= ?", (*hs, as_of))}
            scored = self.rank(query, known, min_cover=min_cover)
            top = sorted(scored, key=lambda e: -scored[e])[:k]
            if verify is not None and top:
                top = self._verified(verify, query, top)
            events = []
            for eid in top:
                e = self.con.execute(
                    "SELECT r.body, r.place, r.t_from, c.quote, c.lines, c.ekind, c.gist_uk, c.day, c.part FROM record r "
                    "JOIN canon_event c ON c.id=r.id WHERE r.id=?", (eid,)).fetchone()
                kn = known[eid]
                own = [dict(x) for x in self.con.execute(
                    "SELECT reaction, attitude FROM canon_reaction WHERE event_id=? AND party IN (%s)" % ph, (eid, *hs))]
                events.append({"id": eid, "what": e["gist_uk"] or e["body"], "what_en": e["body"],
                               "place": self.name(e["place"]) if e["place"] else None,
                               "t": e["t_from"], "day": e["day"], "how_known": kn["channel"],
                               "source": self.name(kn["source"]) if kn["source"] else None,
                               "learned_t": kn["learned_t"], "quote": e["quote"], "kind": e["ekind"],
                               "own_reaction": own, "score": round(scored[eid], 3)})
            return {"holder": holder, "as_of": as_of, "events": events, "profile": self.profile(holder),
                    "n_known": len(known)}

    def _verified(self, judge: Any, query: str, ids: list[int]) -> list[int]:
        """Second bar for the few events that cleared the first: one batched typed yes/no per event, "does this
        record help answer the question?". A verifier failure keeps the list as it is."""
        from ..judge import JudgeError, yes_no_q
        qs = {}
        for i in ids:
            r = self.con.execute("SELECT r.body, c.gist_uk FROM record r JOIN canon_event c ON c.id=r.id WHERE r.id=?", (i,)).fetchone()
            qs[str(i)] = yes_no_q("Question: " + query + "\nRecord: " + (r["gist_uk"] or r["body"]) +
                                  "\nDoes this record contain information that helps answer the question? "
                                  "Merely mentioning the same people is not enough.", tag="canon_relevance")
        try:
            got = judge.ask([], qs)
        except JudgeError:
            return ids
        return [i for i in ids if got[str(i)].answer]

    # ---- unfiltered: narrator, judgments and the drift check only -------------------------
    def search_unfiltered(self, query: str, k: int = 5) -> list[dict[str, Any]]:
        """Canon events relevant to a text, whoever knows them. For the narrator, the drift check and
        judgments: never for a character's context."""
        with self._lock:
            pool = {r[0] for r in self.con.execute("SELECT id FROM canon_event")}
            scored = self.rank(query, pool)
            out = []
            for eid in sorted(scored, key=lambda e: -scored[e])[:k]:
                e = self.con.execute(
                    "SELECT r.body, r.t_from, c.gist_uk, c.day, c.day_to, c.loudness FROM record r "
                    "JOIN canon_event c ON c.id=r.id WHERE r.id=?", (eid,)).fetchone()
                out.append({"id": eid, "what": e["gist_uk"] or e["body"], "what_en": e["body"], "t": e["t_from"],
                            "day": e["day"], "day_to": e["day_to"], "loudness": e["loudness"], "score": round(scored[eid], 3)})
            return out

    def secrets_about(self, holder: str, topic: str, as_of: int) -> list[dict[str, Any]]:
        """Canon events on the topic that the holder does not know and that stayed with few people
        (loudness below 0.4): the secrets background knowledge must never reveal."""
        with self._lock:
            hs = self.holders(holder)
            ph = ",".join("?" * len(hs))
            known = {r[0] for r in self.con.execute(
                f"SELECT event_id FROM canon_knower WHERE entity IN ({ph}) AND COALESCE(learned_t,-999999999) <= ?", (*hs, as_of))}
            pool = {r[0] for r in self.con.execute("SELECT id FROM canon_event WHERE loudness < 0.4")} - known
            scored = self.rank(topic, pool)
            return [{"id": e, "score": round(v, 3)} for e, v in sorted(scored.items(), key=lambda kv: -kv[1])]

    def passages_unfiltered(self, query: str, k: int = 3) -> list[dict[str, Any]]:
        out = []
        for pid in self._fts_ids("canon_passage_fts", query)[:k]:
            r = self.con.execute("SELECT p.line_from, p.line_to, r.body FROM canon_passage p "
                                 "JOIN record r ON r.id=p.id WHERE p.id=?", (pid,)).fetchone()
            out.append({"id": pid, "lines": (r["line_from"], r["line_to"]), "text": r["body"]})
        return out
