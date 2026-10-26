"""Canon ingestion of one arc: chunk, extract (entities, then events per window), validate, load.

    python -m harness.canon.ingest --model deepseek/deepseek-v4.1-flash-1017 --out campaigns/canon/pilot_deepseek.db
    python -m harness.canon.ingest --source data/witcher_books.txt --lines A-B --chapters "L:Title,L:Title" \
        --from-json DIR --out X.db

With `--from-json DIR` no provider is created and nothing goes over the network: each model call is
replaced by reading a JSON file that a Claude Code subagent wrote (see reports/canon_be/EXTRACTION.md):
    entities.json and/or entities_<A>-<B>.json   entity pass, {"entities": [...]} (all such files merged)
    timeline.json                                scene timeline, only with --v2
    window_<A>-<B>.json                          event pass for the arc lines A..B, {"new_entities", "events"}
Window files are taken in order of A. Missing or unparsable files are counted in the report, not raised.

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
from . import chunk, extract, extract2
from ..glossary import Glossary
from .store import add_record, create_store
from .vocab import ATTITUDES, CHANNELS, EKINDS, PARTS, REACTIONS

INGEST_VERSION = "pilot-1"
BOOK_FIRST, BOOK_LAST = 7, 694
CHAPTERS = [(7, "Голос розуму-1"), (19, "Відьмак")]
SOURCE_ID, SOURCE_TITLE = "last-wish-arc", "Останнє бажання: Голос розуму-1, Відьмак"
WINDOW_FILE = re.compile(r"^window_(\d+)-(\d+)\.json$")
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
                 chapters: list[tuple[int, str]] | None = None, log=print, replay: bool = False,
                 v2: bool = False, glossary: bool = False, json_dir: str | Path | None = None,
                 source_id: str = SOURCE_ID, source_title: str = SOURCE_TITLE) -> None:
        self.provider, self.model, self.source = provider, model, Path(source)
        self.out_db, self.raw_dir = out_db, Path(raw_dir) if raw_dir else None
        self.spend = spend or TokenSpend()
        self.first, self.last, self.chapters = first, last, chapters or CHAPTERS
        self.log = log
        self.glossary = Glossary.for_world("witcher") if glossary else None  # canonical names applied to event text
        self.v2 = v2          # scene-timeline pass supplies time and place (extract2)
        self.scenes: list[dict[str, Any]] = []
        self.replay = replay  # re-use the saved raw replies in raw_dir instead of calling the model
        # read the subagent-written JSON files instead of calling the model (no provider needed)
        self.json_dir = Path(json_dir) if json_dir else None
        self.source_id, self.source_title = source_id, source_title
        self.json_files: dict[str, Any] = {"read": 0, "missing": [], "invalid": [], "ignored": [],
                                           "uncovered_lines": []}
        self.stats: dict[str, Any] = {"format_failures": 0, "dropped": [], "calls": 0, "window_failures": 0}
        self.entities: dict[str, dict[str, Any]] = {}

    # ---- raw log -------------------------------------------------------------------------
    def _save_raw(self, name: str, obj: Any) -> None:
        if self.raw_dir:
            self.raw_dir.mkdir(parents=True, exist_ok=True)
            (self.raw_dir / f"{name}.json").write_text(json.dumps(obj, ensure_ascii=False, indent=1))

    def _load_raw(self, name: str) -> Any | None:
        if self.replay and self.raw_dir and (self.raw_dir / f"{name}.json").exists():
            return json.loads((self.raw_dir / f"{name}.json").read_text())
        return None

    def _read_json(self, name: str, lists: tuple[str, ...]) -> dict[str, Any] | None:
        """A subagent-written file in json_dir; None (and counted) when it is unreadable, not an object, or
        one of its top-level `lists` fields is present but not a list (null counts as absent)."""
        assert self.json_dir is not None
        try:
            obj = extract.parse_json((self.json_dir / name).read_text(encoding="utf-8"))
            bad = [k for k in lists if obj.get(k) is not None and not isinstance(obj[k], list)]
            if bad:
                raise ValueError(f"field(s) {', '.join(bad)} must be lists")
        except (OSError, ValueError) as e:  # JSONDecodeError is a ValueError
            self.json_files["invalid"].append(name)
            self._drop("file", "invalid json", file=name, err=str(e)[:160])
            return None
        self.json_files["read"] += 1
        return obj

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
        if self.json_dir:
            names = sorted(f.name for f in self.json_dir.glob("entities*.json"))
            if not names:
                self.json_files["missing"].append("entities*.json")
            for n in names:
                for e in (self._read_json(n, ("entities",)) or {}).get("entities") or []:
                    self._take_entity(e, n)
            return
        text = "\n".join(f"[L{p.line}] {p.text}" for p in paras)
        obj = self._load_raw("entities")
        if obj is None:
            obj, fails = extract.ask_json(self.provider, self.model, extract.entity_prompt(text))
            self.stats["format_failures"] += fails
            self._save_raw("entities", obj)
        for e in obj.get("entities") or []:
            self._take_entity(e, "entity_pass")

    def timeline_pass(self, paras: list[chunk.Para]) -> None:
        text = "\n".join(f"[L{p.line}] {p.text}" for p in paras)
        if self.json_dir:
            obj = {}
            if (self.json_dir / "timeline.json").exists():
                obj = self._read_json("timeline.json", ("scenes",)) or {}
            else:
                self.json_files["missing"].append("timeline.json")
        else:
            obj = self._load_raw("timeline")
        if obj is None:
            obj, fails = extract.ask_json(self.provider, self.model, extract2.timeline_prompt(text))
            self.stats["format_failures"] += fails
            self._save_raw("timeline", obj)
        self.scenes = [s for s in obj.get("scenes") or [] if isinstance(s, dict)
                       and isinstance(s.get("from_line"), int) and isinstance(s.get("to_line"), int)]

    def _scene_at(self, line: int) -> dict[str, Any] | None:
        for s in self.scenes:
            if s["from_line"] <= line <= s["to_line"]:
                return s
        return None

    def _place_id(self, name: Any) -> str | None:
        if not isinstance(name, str) or not name.strip():
            return None
        n = name.strip().lower()
        for eid, e in self.entities.items():
            if e["type"] == "place" and n in [str(e["name"]).lower(), *[str(a).lower() for a in e.get("aliases") or []]]:
                return eid
        return None

    def _apply_scene(self, ev: dict[str, Any], lines: set[int]) -> None:
        first = (ev["_lines_ok"] or [min(lines)])[0]
        sc = self._scene_at(first)
        past = ev.get("past")
        if isinstance(past, (int, float)) and past >= 0:
            ev["time"] = {"kind": "before", "years_before": past}
        elif sc and isinstance(sc.get("day"), int):
            ev["time"] = {"kind": "day", "day": sc["day"], "part": sc.get("part")}
        else:
            ev["time"] = {"kind": "unknown"}
        ev["place"] = self._place_id(sc.get("place")) if sc else None

    # ---- events ---------------------------------------------------------------------------
    def event_pass(self, windows: list[list[chunk.Passage]]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        prior: list[str] = []
        for wi, win in enumerate(windows):
            t0 = time.time()
            pieces = self._fetch(f"window_{wi:02d}", win, prior)
            for obj, lines in pieces:
                for e in obj.get("new_entities") or []:
                    self._take_entity(e, f"window {wi}")
            n_new = 0
            for obj, lines in pieces:
                n_new += self._take_events(obj, lines, wi, out, prior)
            self.log(f"  window {wi + 1}/{len(windows)}: {n_new} events, {time.time() - t0:.0f}s, "
                     f"${self.spend.total:.4f}")
        return out

    def json_event_pass(self, paras: list[chunk.Para]) -> list[dict[str, Any]]:
        """Event pass from window_<A>-<B>.json files: the window is the arc lines A..B."""
        assert self.json_dir is not None
        arc_lines = [p.line for p in paras]
        files: list[tuple[int, int, str]] = []
        for f in self.json_dir.glob("*.json"):
            m = WINDOW_FILE.match(f.name)
            if m and int(m[1]) <= int(m[2]):
                files.append((int(m[1]), int(m[2]), f.name))
            elif not (f.name.startswith("entities") or f.name in ("timeline.json",) or f.name.startswith("report")):
                self.json_files["ignored"].append(f.name)
        files.sort()
        if not files:
            self.json_files["missing"].append("window_<A>-<B>.json")
        covered: set[int] = set()
        out: list[dict[str, Any]] = []
        prior: list[str] = []
        for wi, (a, b, name) in enumerate(files):
            obj = self._read_json(name, ("new_entities", "events"))
            if obj is None:
                self.stats["window_failures"] += 1
                continue
            lines = {ln for ln in arc_lines if a <= ln <= b}
            if not lines:
                self._drop("file", "window outside the arc", file=name)
                continue
            covered |= lines
            for e in obj.get("new_entities") or []:
                self._take_entity(e, name)
            n_new = self._take_events(obj, lines, wi, out, prior)
            self.log(f"  {name}: {n_new} events")
        # arc paragraphs no window file covers, as "A-B" runs of consecutive paragraphs
        runs: list[list[int]] = []
        prev_in = True
        for ln in arc_lines:
            if ln in covered:
                prev_in = True
                continue
            if prev_in:
                runs.append([ln, ln])
            runs[-1][1] = ln
            prev_in = False
        self.json_files["uncovered_lines"] = [f"{x}-{y}" for x, y in runs]
        return out

    def _fetch(self, name: str, win: list[chunk.Passage], prior: list[str]) -> list[tuple[dict[str, Any], set[int]]]:
        """The model reply for a window; if its JSON cannot be parsed (often a reply cut off at the output
        limit) the window is split in two and each half is asked on its own."""
        text = chunk.tagged(win)
        lines = {p.line for ps in win for p in ps.paras}
        obj = self._load_raw(name)
        if obj is None:
            if self.v2:
                sc_txt = "\n".join(f"L{x['from_line']}-L{x['to_line']}: day {x.get('day')}, {x.get('part')}, "
                                   f"place {x.get('place')}" for x in self.scenes
                                   if x["to_line"] >= min(lines) and x["from_line"] <= max(lines))
                msgs = extract2.event_prompt2(text, list(self.entities.values()), prior[-14:], sc_txt)
            else:
                msgs = extract.event_prompt(text, list(self.entities.values()), prior[-14:])
            try:
                obj, fails = extract.ask_json(self.provider, self.model, msgs)
            except extract.JsonFailure as e:
                self.stats["window_failures"] += 1
                self._drop("window", "no valid json", window=name, err=str(e)[:160])
                if len(win) > 1:
                    mid = len(win) // 2
                    return self._fetch(name + "a", win[:mid], prior) + self._fetch(name + "b", win[mid:], prior)
                return []
            self.stats["format_failures"] += fails
            self._save_raw(name, obj)
        return [(obj, lines)]

    def _take_events(self, obj: dict[str, Any], lines: set[int], wi: int, out: list[dict[str, Any]],
                     prior: list[str]) -> int:
        n_new = 0
        for ev in obj.get("events") or []:
            if not isinstance(ev, dict) or not isinstance(ev.get("what"), str) or not ev["what"].strip():
                self._drop("event", "no text", window=wi)
                continue
            ev["_window"] = wi
            ev["_lines_ok"] = sorted(int(x) for x in (ev.get("lines") or [])
                                     if isinstance(x, int) and x in lines)
            ev["_win_lines"] = (min(lines), max(lines))
            if self.v2:
                self._apply_scene(ev, lines)
            out.append(ev)
            n_new += 1
            tag = f"e{len(out)} [L{(ev['_lines_ok'] or [min(lines)])[0]}]"
            prior.append(f"{tag} {ev['what'][:140]}")
        return n_new

    # ---- load -----------------------------------------------------------------------------
    def load(self, paras: list[chunk.Para], passages: list[chunk.Passage], events: list[dict[str, Any]],
             sha: str) -> sqlite3.Connection:
        con = create_store(self.out_db)
        con.execute("INSERT INTO canon_meta VALUES (?,?,?,?,?)",
                    ("witcher", INGEST_VERSION, sha, time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                     json.dumps([self.model])))
        con.execute("INSERT INTO canon_source VALUES (?,?,?,?)",
                    (self.source_id, self.source_title, "uk", sha))
        pid_by_line: dict[int, int] = {}
        arc_text = "\n".join(p.text for p in paras)
        for ps in passages:
            rid = add_record(con, "canon_passage", ps.text, t_from=0, t_prec="unknown", writer_ref="chunker")
            con.execute("INSERT INTO canon_passage VALUES (?,?,?,?,?,?,?,?)",
                        (rid, self.source_id, ps.chapter, ps.ord, ps.char_from, ps.char_to,
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
        # story time at a text line, from events that carry a story day: a person told about a past
        # event learns it when the telling happens, not when the event happened
        day_marks = sorted((min(e["_lines_ok"]), story_minutes(e.get("time"), 0)[0]) for e in events
                           if e["_lines_ok"] and isinstance(e.get("time"), dict) and e["time"].get("kind") == "day"
                           and story_minutes(e.get("time"), 0)[1] != "unknown")

        def time_at_line(ln: int | None, default: int) -> int:
            if ln is None:
                return default
            t = default
            for lmin, tm in day_marks:
                if lmin <= ln:
                    t = tm
                else:
                    break
            return t

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
            if self.glossary:
                ev["what"] = self.glossary.apply(ev["what"])
            rid = add_record(con, "canon_event", ev["what"].strip(), t_from=t_from, t_prec=prec, place=place,
                             notability=loud, meta={"flags": flags}, writer_ref=self.model)
            order += 1
            con.execute("INSERT INTO canon_event(id, ekind, loudness, order_key, when_prec, confidence, review, day, part, quote, lines, local_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
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
                ll = k.get("line") if isinstance(k.get("line"), int) else None
                if k.get("when"):
                    lt, lp, _, _ = story_minutes(k.get("when"), t_from)
                elif k["channel"] in ("told", "heard", "hearsay", "read", "inferred") and ev["_lines_ok"]:
                    lt = max(t_from, time_at_line(ll or ev["_lines_ok"][0], t_from))
                    lp = "day"
                else:
                    lt, lp = t_from, prec
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
        self.log(f"{self.model}: {len(paras)} paragraphs, {len(passages)} passages, "
                 + (f"JSON from {self.json_dir}" if self.json_dir else f"{len(windows)} windows"))
        self.entity_pass(paras)
        self.log(f"  entities: {len(self.entities)}, ${self.spend.total:.4f}")
        if self.v2:
            self.timeline_pass(paras)
            self.log(f"  scenes: {len(self.scenes)}, ${self.spend.total:.4f}")
        events = self.json_event_pass(paras) if self.json_dir else self.event_pass(windows)
        con = self.load(paras, passages, events, chunk.file_sha256(self.source))
        counts = {t: con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "entity", "canon_passage", "canon_event", "canon_participant", "canon_knower", "canon_reaction")}
        flagged: dict[str, int] = {}
        for (meta,) in con.execute("SELECT meta FROM record WHERE kind='canon_event'"):
            for f in json.loads(meta or "{}").get("flags") or []:
                flagged[f] = flagged.get(f, 0) + 1
        con.close()
        by_reason: dict[str, int] = {}
        for d in self.stats["dropped"]:
            k = f"{d['what']}: {d['why']}"
            by_reason[k] = by_reason.get(k, 0) + 1
        rep = {"model": self.model, "seconds": round(time.time() - t0), "cost_usd": round(self.spend.total, 5),
               "calls": self.spend.calls, "tokens_in": self.spend.tokens_in, "tokens_out": self.spend.tokens_out,
               "counts": counts, "format_failures": self.stats["format_failures"],
               "window_failures": self.stats["window_failures"], "flagged": flagged,
               "dropped_by_reason": by_reason, "dropped": self.stats["dropped"]}
        if self.json_dir:
            rep["json_files"] = self.json_files
        self._save_raw("report_replay" if self.replay else "report", rep)
        return rep


def parse_lines(s: str) -> tuple[int, int]:
    """"A-B" -> (A, B), 1-based inclusive file lines."""
    m = re.fullmatch(r"\s*(\d+)\s*-\s*(\d+)\s*", s)
    if not m or not 1 <= int(m[1]) <= int(m[2]):
        raise ValueError(f"--lines wants A-B with 1 <= A <= B, got {s!r}")
    return int(m[1]), int(m[2])


def parse_chapters(s: str) -> list[tuple[int, str]]:
    """"L:Title,L:Title" -> [(L, Title)] sorted by line (a title may not contain a comma)."""
    out = []
    for item in s.split(","):
        ln, sep, title = item.strip().partition(":")
        if not sep or not ln.strip().isdigit() or not title.strip():
            raise ValueError(f"--chapters wants L:Title items separated by commas, got {item!r}")
        out.append((int(ln), title.strip()))
    return sorted(out)


def main() -> None:
    from dotenv import load_dotenv
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", help="extractor model (required unless --from-json; then only a label)")
    ap.add_argument("--source", default="data/witcher_books.txt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--raw")
    ap.add_argument("--v2", action="store_true", help="scene-timeline pass supplies time and place")
    ap.add_argument("--glossary", action="store_true", help="apply the canonical-name glossary to event text")
    ap.add_argument("--replay", action="store_true", help="reload from the saved raw replies, no API calls")
    ap.add_argument("--cap", type=float, default=0.2, help="spend cap in USD for this run")
    ap.add_argument("--lines", help=f"arc as file lines A-B (default {BOOK_FIRST}-{BOOK_LAST}, the pilot arc)")
    ap.add_argument("--chapters", help='"L:Title,L:Title" chapter starts (default: the pilot chapters; with --lines '
                                       'only, one chapter named after the range)')
    ap.add_argument("--from-json", metavar="DIR", help="read subagent-written JSON files instead of calling a model")
    ap.add_argument("--source-id", default=SOURCE_ID)
    ap.add_argument("--source-title", default=SOURCE_TITLE)
    a = ap.parse_args()
    try:
        first, last = parse_lines(a.lines) if a.lines else (BOOK_FIRST, BOOK_LAST)
        chapters = parse_chapters(a.chapters) if a.chapters else (
            [(first, f"lines {first}-{last}")] if a.lines else CHAPTERS)
    except ValueError as e:
        ap.error(str(e))
    if chapters[0][0] > first:
        ap.error(f"the first chapter starts at line {chapters[0][0]}, after the arc start {first}")
    kw = dict(raw_dir=a.raw, first=first, last=last, chapters=chapters, v2=a.v2, glossary=a.glossary,
              source_id=a.source_id, source_title=a.source_title)
    if a.from_json:
        if not Path(a.from_json).is_dir():
            ap.error(f"--from-json: {a.from_json} is not a directory")
        ing = Ingestor(None, a.model or "subagent-json", a.source, a.out, json_dir=a.from_json, **kw)  # type: ignore[arg-type]
    else:
        if not a.model:
            ap.error("--model is required unless --from-json is given")
        load_dotenv(os.environ.get("HARNESS_ENV", ".env"))
        spend = TokenSpend(cap=a.cap)
        prov = OpenRouterProvider(spend=spend, timeout=300)
        ing = Ingestor(prov, a.model, a.source, a.out, spend=spend, replay=a.replay, **kw)  # type: ignore[arg-type]
    rep = ing.run()
    rep.pop("dropped")
    print(json.dumps(rep, ensure_ascii=False))


if __name__ == "__main__":
    main()
