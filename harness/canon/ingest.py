"""Canon ingestion of one arc: chunk, extract (entities, then events per window), validate, load.

    python -m harness.canon.ingest --model deepseek/deepseek-v4.1-flash-1017 --out campaigns/canon/pilot_deepseek.db

Nothing here writes world state through an LLM: the model proposes JSON, code validates it (closed
vocabularies, known entity ids, quote present in the source, line numbers inside the window) and
stores what passes. What fails is counted in the returned report and kept in `dropped`.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from ..policy import Spend
from ..providers import OpenRouterProvider, Provider
from . import chunk, extract
from .store import add_record, create_store
from .vocab import ATTITUDES, CHANNELS, EKINDS, PARTS, REACTIONS

INGEST_VERSION = "pilot-1"
BOOK_FIRST, BOOK_LAST = 7, 694
CHAPTERS = [(7, "Голос розуму-1"), (19, "Відьмак")]
TYPE_OF_PREFIX = {"char": "person", "coll": "collective", "place": "place", "item": "item",
                  "creature": "creature"}
ROLES = {"actor", "target", "victim", "speaker", "listener", "witness", "bystander", "subject"}
PRESENT_ROLES = {"actor", "target", "victim", "speaker", "listener", "witness"}


class TokenSpend(Spend):
    """Spend that also counts tokens and keeps a per-call log."""

    def __init__(self, cap: float | None = None) -> None:
        super().__init__(cap)
        self.tokens_in = 0
        self.tokens_out = 0
        self._tlock = threading.Lock()

    def add(self, usage: dict | None) -> None:  # type: ignore[type-arg]
        super().add(usage)
        with self._tlock:
            self.tokens_in += int((usage or {}).get("prompt_tokens") or 0)
            self.tokens_out += int((usage or {}).get("completion_tokens") or 0)


def story_minutes(t: dict[str, Any] | None, last: int) -> tuple[int, str, int | None, str | None]:
    """Event time object -> (t_from minutes, precision, day, part). Day 1, 00:00 = 0; the past is
    negative (years_before); 'unknown' carries the last known time forward."""
    if not isinstance(t, dict):
        return last, "unknown", None, None
    kind = t.get("kind")
    part = t.get("part") if t.get("part") in PARTS else None
    if kind == "day" and isinstance(t.get("day"), int) and t["day"] >= 1:
        hour = PARTS.get(part or "", 12)
        return (t["day"] - 1) * 1440 + hour * 60, ("hour" if part else "day"), t["day"], part
    if kind == "before":
        y = t.get("years_before")
        if isinstance(y, (int, float)) and y >= 0:
            return -int(y * 525600), "season", None, None
        return -525600, "unknown", None, None
    return last, "unknown", None, None


def _slug_ok(eid: Any) -> bool:
    return isinstance(eid, str) and ":" in eid and eid.split(":", 1)[0] in TYPE_OF_PREFIX


class Ingestor:
    def __init__(self, provider: Provider, model: str, source: str | Path, out_db: str | Path,
                 *, raw_dir: str | Path | None = None, spend: TokenSpend | None = None,
                 first: int = BOOK_FIRST, last: int = BOOK_LAST,
                 chapters: list[tuple[int, str]] | None = None, log=print) -> None:
        self.provider, self.model, self.source = provider, model, Path(source)
        self.out_db, self.raw_dir = out_db, Path(raw_dir) if raw_dir else None
        self.spend = spend or TokenSpend()
        self.first, self.last, self.chapters = first, last, chapters or CHAPTERS
        self.log = log
        self.stats: dict[str, Any] = {"format_failures": 0, "dropped": [], "calls": 0, "window_failures": 0}
        self.entities: dict[str, dict[str, Any]] = {}

    # ---- raw log -------------------------------------------------------------------------
    def _save_raw(self, name: str, obj: Any) -> None:
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1))

    def _drop(self, what: str, why: str, **kw: Any) -> None:
        self.stats["dropped"].append({"what": what, "why": why, **kw})

    # ---- entities -------------------------------------------------------------------------
    def _take_entity(self, e: Any, where: str) -> None:
        if not isinstance(e, dict) or not _slug_ok(e.get("id")) or not e.get("name"):
            self._drop("entity", "bad id or name", where=where, raw=str(e)[:120])
            return
        eid = e["id"]
        typ = TYPE_OF_PREFIX[eid.split(":", 1)[0]]
        if e.get("type") in TYPE_OF_PREFIX.values() and e["type"] != typ:
            typ = e["type"] if e["type"] in ("person", "collective", "place", "item", "creature") else typ
        if eid in self.entities:
            # same id seen again: only merge aliases
            old = self.entities[eid]
            old["aliases"] = sorted(set(old.get("aliases") or []) | set(e.get("aliases") or []))
            return
        self.entities[eid] = {**e, "type": typ, "aliases": list(e.get("aliases") or [])}

    def entity_pass(self, paras: list[chunk.Para]) -> None:
        text = "\n".join(f"[L{p.line}] {p.text}" for p in paras)
        msgs = extract.entity_prompt(text)
        obj, fails = extract.ask_json(self.provider, self.model, msgs)
        self.stats["format_failures"] += fails
        self._save_raw("entities", obj)
        for e in obj.get("entities") or []:
            self._take_entity(e, "entity_pass")

    # ---- events ---------------------------------------------------------------------------
    def event_pass(self, windows: list[list[chunk.Passage]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        prior: list[str] = []
        for wi, win in enumerate(windows):
            text = chunk.tagged(win)
            lines = {p.line for ps in win for p in ps.paras}
            msgs = extract.event_prompt(text, list(self.entities.values()), prior[-14:])
            t0 = time.time()
            try:
                obj, fails = extract.ask_json(self.provider, self.model, msgs)
            except extract.JsonFailure as e:
                self.stats["window_failures"] += 1
                self._drop("window", "no valid json", window=wi, err=str(e)[:160])
                continue
            self.stats["format_failures"] += fails
            self._save_raw(f"window_{wi:02d}", obj)
            for e in obj.get("new_entities") or []:
                self._take_entity(e, f"window {wi}")
            n_new = 0
            for ev in obj.get("events") or []:
                if not isinstance(ev, dict) or not isinstance(ev.get("what"), str) or not ev["what"].strip():
                    self._drop("event", "no text", window=wi)
                    continue
                ev["_window"] = wi
                ev["_lines_ok"] = sorted(int(x) for x in (ev.get("lines") or [])
                                         if isinstance(x, int) and x in lines)
                ev["_win_lines"] = (min(lines), max(lines))
                out.append(ev)
                n_new += 1
                tag = f"e{len(out)} [L{(ev['_lines_ok'] or [min(lines)])[0]}]"
                prior.append(f"{tag} {ev['what'][:140]}")
            self.log(f"  window {wi + 1}/{len(windows)}: {n_new} events, {time.time() - t0:.0f}s, "
                     f"${self.spend.total:.4f}")
        return out

    # ---- load -----------------------------------------------------------------------------
    def load(self, paras: list[chunk.Para], passages: list[chunk.Passage], events: list[dict[str, Any]],
             sha: str) -> sqlite3.Connection:
        con = create_store(self.out_db)
        con.execute("INSERT INTO canon_meta VALUES (?,?,?,?,?)",
                    ("witcher", INGEST_VERSION, sha, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     json.dumps([self.model])))
        con.execute("INSERT INTO canon_source VALUES (?,?,?,?)",
                    ("last-wish-arc", "Останнє бажання: Голос розуму-1, Відьмак", "uk", sha))
        pid_by_line: dict[int, int] = {}
        arc_text = "\n".join(p.text for p in paras)
        for ps in passages:
            rid = add_record(con, "canon_passage", ps.text, t_from=0, t_prec="unknown", writer_ref="chunker")
            con.execute("INSERT INTO canon_passage VALUES (?,?,?,?,?,?,?,?)",
                        (rid, "last-wish-arc", ps.chapter, ps.ord, ps.char_from, ps.char_to,
                         ps.line_from, ps.line_to))
            con.execute("INSERT INTO canon_passage_fts(rowid, text) VALUES (?,?)", (rid, ps.text))
            for p in ps.paras:
                pid_by_line[p.line] = rid
        # entities
        for eid, e in self.entities.items():
            con.execute("INSERT INTO entity(id, type, name) VALUES (?,?,?)", (eid, e["type"], str(e["name"])))
            for a in dict.fromkeys([str(e["name"]), *[str(x) for x in e.get("aliases") or []]]):
                con.execute("INSERT OR IGNORE INTO canon_alias VALUES (?,?)", (eid, a))
            if e["type"] in ("person", "creature", "collective"):
                knows = [k for k in (e.get("knows") or []) if isinstance(k, dict) and k.get("fact")]
                fl = e.get("first_line") if isinstance(e.get("first_line"), int) else None
                con.execute("INSERT INTO canon_character VALUES (?,?,?,?,?,?,?)",
                            (eid, e.get("who"), e.get("role"), e.get("standing"),
                             json.dumps(knows, ensure_ascii=False), fl, 1 if e.get("unnamed") else 0))
        for eid, e in self.entities.items():
            for g in e.get("member_of") or []:
                if g in self.entities and g != eid:
                    rid = add_record(con, "canon_relation", f"{eid} member_of {g}", t_from=0, writer_ref=self.model)
                    con.execute("INSERT INTO canon_relation VALUES (?,?,?,?,?,?)",
                                (rid, eid, g, "member_of", None, None))
        # events
        last_t = 0
        seen_quotes: set[str] = set()
        norm_arc = chunk.norm(arc_text)
        order = 0
        for ev in events:
            flags: list[str] = []
            kind = ev.get("ekind") if ev.get("ekind") in EKINDS else "other"
            if ev.get("ekind") not in EKINDS:
                flags.append("bad_ekind")
            try:
                loud = min(1.0, max(0.0, float(ev.get("loudness", 0.3))))
            except (TypeError, ValueError):
                loud = 0.3
                flags.append("bad_loudness")
            try:
                conf = min(1.0, max(0.0, float(ev.get("confidence", 0.5))))
            except (TypeError, ValueError):
                conf = 0.5
            quote = ev.get("quote") if isinstance(ev.get("quote"), str) else ""
            nq = chunk.norm(quote)
            if not nq:
                flags.append("no_quote")
            elif nq not in norm_arc:
                flags.append("quote_not_in_text")
            if nq and nq in seen_quotes:
                flags.append("dup_quote")
            seen_quotes.add(nq)
            if not ev["_lines_ok"]:
                flags.append("no_valid_lines")
            t_from, prec, day, part = story_minutes(ev.get("time"), last_t)
            if prec != "unknown" and ev["time"].get("kind") == "day":
                last_t = t_from
            place = ev.get("place") if ev.get("place") in self.entities and \
                self.entities[ev["place"]]["type"] == "place" else None
            if ev.get("place") and place is None:
                flags.append("unknown_place")
            rid = add_record(con, "canon_event", ev["what"].strip(), t_from=t_from, t_prec=prec, place=place,
                             notability=loud, meta={"flags": flags}, writer_ref=self.model)
            order += 1
            con.execute("INSERT INTO canon_event VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (rid, kind, loud, order, prec, conf, "unreviewed", day, part, quote,
                         json.dumps(ev["_lines_ok"]), f"w{ev['_window']}"))
            con.execute("INSERT INTO canon_event_fts(rowid, text) VALUES (?,?)", (rid, ev["what"] + " " + quote))
            for ln in ev["_lines_ok"]:
                con.execute("INSERT OR IGNORE INTO canon_evidence VALUES (?,?,?,?)", (rid, pid_by_line[ln], None, None))
            ev["_id"] = rid
            parts_seen: set[tuple[str, str]] = set()
            for p in ev.get("participants") or []:
                if not isinstance(p, dict) or p.get("entity") not in self.entities:
                    self._drop("participant", "unknown entity", event=rid, raw=str(p)[:100])
                    continue
                role = p.get("role") if p.get("role") in ROLES else "subject"
                if (p["entity"], role) in parts_seen:
                    continue
                parts_seen.add((p["entity"], role))
                con.execute("INSERT INTO canon_participant VALUES (?,?,?)", (rid, p["entity"], role))
            known: set[str] = set()
            for k in ev.get("knowers") or []:
                if not isinstance(k, dict) or k.get("entity") not in self.entities:
                    self._drop("knower", "unknown entity", event=rid, raw=str(k)[:100])
                    continue
                if k["entity"] in known:
                    continue
                if k.get("channel") not in CHANNELS:
                    self._drop("knower", "bad channel", event=rid, raw=str(k)[:100])
                    continue
                src = k.get("source") if k.get("source") in self.entities else None
                lt, lp, _, _ = story_minutes(k.get("when"), t_from) if k.get("when") else (t_from, prec, None, None)
                ll = k.get("line") if isinstance(k.get("line"), int) else None
                known.add(k["entity"])
                con.execute("INSERT INTO canon_knower VALUES (?,?,?,?,?,?,?,?)",
                            (rid, k["entity"], k["channel"], src, max(0, lt - t_from) if lt >= t_from else 0,
                             lt, lp, ll))
            for r in ev.get("reactions") or []:
                if not isinstance(r, dict) or r.get("party") not in self.entities:
                    self._drop("reaction", "unknown party", event=rid, raw=str(r)[:100])
                    continue
                if r.get("reaction") not in REACTIONS:
                    self._drop("reaction", "not in closed vocabulary", event=rid, raw=str(r)[:100])
                    continue
                att = r.get("attitude") if r.get("attitude") in ATTITUDES else None
                rr = add_record(con, "canon_reaction", str(r.get("text") or r["reaction"]), t_from=t_from,
                                t_prec=prec, writer_ref=self.model)
                con.execute("INSERT INTO canon_reaction VALUES (?,?,?,?,?,?)",
                            (rr, rid, r["party"], r["reaction"], att, None))
        con.commit()
        return con

    # ---- run ------------------------------------------------------------------------------
    def run(self) -> dict[str, Any]:
        t0 = time.time()
        paras = chunk.read_arc(self.source, self.first, self.last, self.chapters)
        passages = chunk.make_passages(paras)
        windows = chunk.make_windows(passages)
        self.log(f"{self.model}: {len(paras)} paragraphs, {len(passages)} passages, {len(windows)} windows")
        self.entity_pass(paras)
        self.log(f"  entities: {len(self.entities)}, ${self.spend.total:.4f}")
        events = self.event_pass(windows)
        con = self.load(paras, passages, events, chunk.file_sha256(self.source))
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "entity", "canon_passage", "canon_event", "canon_participant", "canon_knower", "canon_reaction")}
        con.close()
        rep = {"model": self.model, "seconds": round(time.time() - t0), "cost_usd": round(self.spend.total, 5),
               "calls": self.spend.calls, "tokens_in": self.spend.tokens_in, "tokens_out": self.spend.tokens_out,
               "counts": counts, "format_failures": self.stats["format_failures"],
               "window_failures": self.stats["window_failures"], "dropped": self.stats["dropped"]}
        self._save_raw("report", rep)
        return rep


def main() -> None:
    from dotenv import load_dotenv
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--source", default="data/witcher_books.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw")
    ap.add_argument("--cap", type=float, default=0.2, help="spend cap in USD for this run")
    a = ap.parse_args()
    load_dotenv(os.environ.get("HARNESS_ENV", ".env"))
    spend = TokenSpend(cap=a.cap)
    prov = OpenRouterProvider(spend=spend, timeout=300)
    rep = Ingestor(prov, a.model, a.source, a.out, raw_dir=a.raw, spend=spend).run()
    rep.pop("dropped")
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
