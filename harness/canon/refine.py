"""Second ingestion stage (task 16): turn a task-13 store into the pilot-2 store.

Input: a store from `ingest` (events, participants, knowers, reactions, entities) plus the book arc.
Passes, each cached by key in `raw_dir` so a rerun costs nothing and tests can use a fake provider:

1. time    : scene timeline (timeline.py) gives every event its story day range; learned_t of knower rows
             is recomputed from the scene at the line where the holder learns it.
2. places  : every scene gets a place entity (closed list + new places); every event gets a place.
3. knowers : code adds the people present, demotes "witnessed" for tellers, and one model call per batch
             adds "informed by" rows (an official states a fact he did not see) and drops impossible ones.
4. gist    : Ukrainian one-sentence gist and everyday keywords per event, so Ukrainian questions find
             English-written events.
5. reaction: separate pass; every candidate party answers with a reaction or "none".

Nothing here lets a model write state directly: ids are checked against the entity table, channels and
reactions against the closed vocabularies; what fails is counted and dropped.
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import time
from pathlib import Path
from typing import Any, Callable, Sequence

from ..glossary import Glossary
from ..providers import Provider
from . import extract, timeline
from .chunk import Para
from .store import open_store
from .vocab import ATTITUDES, CHANNELS, PARTS, REACTIONS

PRESENT = {"actor", "target", "victim", "speaker", "listener", "witness"}
BATCH = 10
SYSTEM = ("You work on a canon database for a role-playing game engine, from a Ukrainian translation of a novel. "
          "Use only the text you are given; do not use anything you remember about the books. "
          "Answer with one JSON object and nothing else.")

EXTRA_COLUMNS = (("canon_event", "day_to", "INTEGER"), ("canon_event", "gist_uk", "TEXT"),
                 ("canon_event", "kw_uk", "TEXT"), ("canon_event", "scene", "INTEGER"),
                 # time as an interval with a confidence and the basis (the cue in the text), and where in the
                 # source the event sits (character offsets in the arc), so a saga-wide timeline can be built later
                 ("canon_event", "time_conf", "REAL"), ("canon_event", "time_basis", "TEXT"),
                 ("canon_event", "src_from", "INTEGER"), ("canon_event", "src_to", "INTEGER"))


def _t(day: int, part: str | None) -> int:
    return (day - 1) * 1440 + PARTS.get(part or "", 12) * 60


def slug(s: str) -> str:
    t = "".join(c if c.isalnum() else "-" for c in s.lower()).strip("-")
    return re.sub("-+", "-", t)[:40] or "x"


class Refiner:
    def __init__(self, provider: Provider, model: str, src_db: str | Path, out_db: str | Path,
                 paras: Sequence[Para], scenes: list[timeline.Scene], *, raw_dir: str | Path,
                 glossary: Glossary | None = None, log: Callable[[str], None] = print) -> None:
        self.provider, self.model = provider, model
        Path(out_db).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src_db, out_db)
        self.con = open_store(out_db)
        self.paras = {p.line: p.text for p in paras}
        self.para_objs = list(paras)
        self.scenes = scenes
        self.raw = Path(raw_dir)
        self.raw.mkdir(parents=True, exist_ok=True)
        self.glossary, self.log = glossary, log
        self.stats: dict[str, Any] = {"dropped": [], "calls": 0}
        for tbl, col, typ in EXTRA_COLUMNS:
            if col not in {r[1] for r in self.con.execute(f"PRAGMA table_info({tbl})")}:
                self.con.execute(f"ALTER TABLE {tbl} ADD COLUMN {col} {typ}")
        self.ents = {r["id"]: dict(r) for r in self.con.execute("SELECT * FROM entity")}

    # ---- plumbing ------------------------------------------------------------------------
    def _ask(self, key: str, messages: list[dict[str, str]]) -> dict[str, Any]:
        f = self.raw / f"{key}.json"
        if f.exists():
            return json.loads(f.read_text())
        obj, _ = extract.ask_json(self.provider, self.model, messages)
        self.stats["calls"] += 1
        f.write_text(json.dumps(obj, ensure_ascii=False, indent=1))
        return obj

    def _drop(self, what: str, why: str, **kw: Any) -> None:
        self.stats["dropped"].append({"what": what, "why": why, **kw})

    def events(self) -> list[dict[str, Any]]:
        out = []
        for r in self.con.execute(
                "SELECT r.id, r.body, r.place, r.t_from, c.day, c.part, c.quote, c.lines, c.ekind, c.order_key "
                "FROM record r JOIN canon_event c ON c.id=r.id ORDER BY c.order_key"):
            d = dict(r)
            d["lines"] = json.loads(d["lines"])
            d["parts"] = [dict(x) for x in self.con.execute(
                "SELECT entity, role FROM canon_participant WHERE event_id=?", (d["id"],))]
            d["know"] = [dict(x) for x in self.con.execute(
                "SELECT * FROM canon_knower WHERE event_id=?", (d["id"],))]
            d["past"] = d["t_from"] < 0
            out.append(d)
        return out

    def source_text(self, ev: dict[str, Any], cap: int = 700) -> str:
        t = " ".join(self.paras.get(ln, "") for ln in ev["lines"][:4])
        return t if len(t) <= cap else t[:cap] + "..."

    def scene_for(self, ev: dict[str, Any]) -> tuple[int, timeline.Scene] | None:
        if not ev["lines"]:
            return None
        ln = min(ev["lines"])
        for i, s in enumerate(self.scenes):
            if s.from_line <= ln <= s.to_line:
                return i, s
        return None

    def time_at_line(self, ln: int | None) -> int | None:
        if ln is None:
            return None
        for s in self.scenes:
            if s.from_line <= ln <= s.to_line and s.day_lo is not None:
                return _t(s.day_lo, s.part if s.part in PARTS else None)
        return None

    # ---- 1. time -------------------------------------------------------------------------
    def scene_conf(self, s: timeline.Scene) -> float:
        """How far the day can be trusted: agreed by both readers and checked = high; arbitrated = medium;
        repaired by a code rule or a wide range = low."""
        span = (s.day_hi or s.day_lo or 0) - (s.day_lo or 0)
        c = 0.9
        if "arbitrated" in s.flags:
            c = 0.7
        if any(f.startswith("repaired") or f.startswith("clamped") for f in s.flags):
            c = 0.5
        return round(max(0.3, c - 0.1 * span), 2)

    def pass_time(self) -> None:
        by_line = {p.line: p for p in self.para_objs}
        for ev in self.events():
            sc = self.scene_for(ev)
            if ev["lines"] and ev["lines"][0] in by_line:
                lo = by_line[min(ev["lines"])]
                hi = by_line.get(max(ev["lines"]), lo)
                self.con.execute("UPDATE canon_event SET src_from=?, src_to=? WHERE id=?",
                                 (lo.char_from, hi.char_from + len(hi.text), ev["id"]))
            if sc is None:
                continue
            i, s = sc
            self.con.execute("UPDATE canon_event SET scene=? WHERE id=?", (i, ev["id"]))
            if ev["past"]:  # backstory keeps its "years before"; the model's reading of it is a guess
                self.con.execute("UPDATE canon_event SET time_conf=?, time_basis=? WHERE id=?",
                                 (0.5, "retold past event: years before as read by the extractor", ev["id"]))
                continue
            if s.day_lo is None:  # frame scene: no story day
                self.con.execute("UPDATE canon_event SET time_conf=?, time_basis=? WHERE id=?",
                                 (0.3, "frame scene outside the story days: " + s.cue[:160], ev["id"]))
                continue
            part = s.part if s.part in PARTS else None
            t = _t(s.day_lo, part)
            hi_day = s.day_hi or s.day_lo
            t_end = _t(hi_day, part) if hi_day != s.day_lo else t
            prec = "hour" if part and hi_day == s.day_lo else "day"
            self.con.execute("UPDATE record SET t_from=?, t_to=?, t_prec=? WHERE id=?", (t, t_end, prec, ev["id"]))
            self.con.execute(
                "UPDATE canon_event SET day=?, day_to=?, part=?, when_prec=?, time_conf=?, time_basis=? WHERE id=?",
                (s.day_lo, hi_day, part, prec, self.scene_conf(s), s.cue[:300], ev["id"]))
        self.con.commit()

    # ---- 2. places -----------------------------------------------------------------------
    def pass_places(self) -> None:
        """One place per event, in story order. The model sees the place of the previous event and keeps it
        unless the text shows a move; retold past events get their own place only if the text names one,
        otherwise the place of the telling (flagged)."""
        evs = self.events()
        current: str | None = None
        for bi in range(0, len(evs), BATCH):
            batch = evs[bi: bi + BATCH]
            places = {k: v for k, v in self.ents.items() if v["type"] == "place"}
            listing = "\n".join(
                f"{k} | {v['name']} | " + "; ".join(r[0] for r in self.con.execute(
                    "SELECT alias FROM canon_alias WHERE entity=?", (k,))) for k, v in places.items())
            blocks = [f"id {e['id']} ({'retold past event' if e['past'] else 'in the story'}): {e['body']}\n"
                      f"  text: {self.source_text(e, 600)}" for e in batch]
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
                "Places known so far (id | name | aliases):\n" + listing + "\n\nThe previous event took place at: "
                + (f"{current} ({places[current]['name']})" if current in places else "unknown") + "\n\nEvents (in order):\n"
                + "\n".join(blocks) + "\n\nFor every event give the most specific place where it happens, as the text shows. "
                "Keep the previous event's place when the text shows no move. A place can be a known id, or a new place with a short "
                "Ukrainian name as the text calls it (for example the burgomaster's office, the hall where the king receives, the courtyard "
                "of the old palace, the street) and the id of the larger known place it lies in. For a retold past event "
                "(someone tells about it) give the place the telling is about if the text names it, otherwise null.\n"
                'JSON: {"events": [{"id": 12, "place": "id or null", "new_place": "Ukrainian name or null", "inside": "id or null"}]}')}]
            obj = self._ask(f"places_{bi // BATCH:02d}", msgs)
            got = {r["id"]: r for r in obj.get("events") or [] if isinstance(r, dict) and isinstance(r.get("id"), int)}
            for e in batch:
                r = got.get(e["id"], {})
                pid = r.get("place") if r.get("place") in places else None
                if pid is None and isinstance(r.get("new_place"), str) and r["new_place"].strip():
                    pid = self._new_place(r["new_place"].strip(), r.get("inside") if r.get("inside") in places else "place:vizim")
                    places = {k: v for k, v in self.ents.items() if v["type"] == "place"}
                note = None
                if pid is None and e["past"]:
                    pid, note = current, "place_of_telling"
                elif pid is None:
                    pid = current or e["place"]
                if pid:
                    self.con.execute("UPDATE record SET place=? WHERE id=?", (pid, e["id"]))
                    if note:
                        self.con.execute("UPDATE record SET meta=json_set(meta,'$.place_note',?) WHERE id=?", (note, e["id"]))
                    if not e["past"] or note is None and False:
                        current = pid
                else:
                    self._drop("place", "no place for event", event=e["id"])
        self.con.commit()

    def _new_place(self, name: str, inside: str) -> str:
        for r in self.con.execute("SELECT entity FROM canon_alias WHERE lower(alias)=lower(?)", (name,)):
            if self.ents.get(r[0], {}).get("type") == "place":
                return r[0]
        eid = f"place:{slug(name)}"
        if eid not in self.ents:
            self.con.execute("INSERT INTO entity(id,type,name) VALUES (?,?,?)", (eid, "place", name))
            self.con.execute("INSERT OR IGNORE INTO canon_alias VALUES (?,?)", (eid, name))
            self.ents[eid] = {"id": eid, "type": "place", "name": name}
            from .store import add_record
            rid = add_record(self.con, "canon_relation", f"{eid} part_of {inside}", t_from=0, writer_ref=self.model)
            self.con.execute("INSERT INTO canon_relation VALUES (?,?,?,?,?,?)", (rid, eid, inside, "part_of", None, None))
        return eid

    def _place_in_text(self, text: str) -> str | None:
        low = text.lower()
        best = None
        for r in self.con.execute("SELECT e.id, a.alias FROM entity e JOIN canon_alias a ON a.entity=e.id WHERE e.type='place'"):
            a = r["alias"].lower().strip("«»\"' ")
            if len(a) >= 5 and a[: max(4, len(a) - 2)] in low and r["id"] not in (
                    "place:vizim", "place:temeria", "place:pontar", "place:mahakam", "place:rivia", "place:redania",
                    "place:novigrad"):
                best = r["id"]
        return best

    # ---- 3. knowers ----------------------------------------------------------------------
    def pass_knowers(self) -> None:
        evs = self.events()
        short = {e["id"]: e["body"][:110] for e in evs}
        for bi in range(0, len(evs), BATCH):
            batch = evs[bi: bi + BATCH]
            earlier = "\n".join(f"{i}: {t}" for i, t in short.items() if i < batch[0]["id"])
            blocks = []
            for e in batch:
                parts = ", ".join(f"{p['entity']}/{p['role']}" for p in e["parts"])
                kn = ", ".join(f"{k['entity']}:{k['channel']}" + (f"<{k['source']}" if k["source"] else "") for k in e["know"])
                sc = self.scene_for(e)
                blocks.append(f"id {e['id']} (scene {sc[0] if sc else '?'}, {'retold past event' if e['past'] else 'in the story'}): "
                              f"{e['body']}\n  participants: {parts}\n  knowers now: {kn}\n  text: {self.source_text(e)}")
            ents = "\n".join(f"{k} | {v['name']}" for k, v in self.ents.items() if v["type"] in ("person", "collective", "creature"))
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
                "Characters and groups (id | name):\n" + ents + "\n\nEarlier events (id: text):\n" + (earlier or "(none)") +
                "\n\nEvents to check:\n" + "\n".join(blocks) + "\n\n"
                "For each event decide who knows it. The people present are handled by code: do not add them. Tellers are "
                "not witnesses of what they only tell. Add a knower only when the text shows they learn it (a listener told it, "
                "someone overhears it, a group that is sent to act on it). Drop a listed knower only if the text shows they were not there or could not know. "
                "'presupposes': if in this event a person states or acts on a fact about an EARLIER event that this person did not see "
                "(an official quotes the number of dead, a king mentions what a stranger did), name that earlier event, the person, "
                "and who plausibly told them according to the text (null if the text does not show). Do not invent.\n"
                'JSON: {"events": [{"id": 12, "add": [{"entity": "id", "channel": one of ' + " | ".join(CHANNELS) +
                ', "source": "id or null", "line": number or null}], "drop": [{"entity": "id", "why": "English"}], '
                '"presupposes": [{"event": 7, "person": "id", "via": "id or null"}]}]}')}]
            obj = self._ask(f"knowers_{bi // BATCH:02d}", msgs)
            self._apply_knowers(batch, obj)
        self.con.commit()

    def _apply_knowers(self, batch: list[dict[str, Any]], obj: dict[str, Any]) -> None:
        by_id = {e["id"]: e for e in batch}
        for r in obj.get("events") or []:
            if not isinstance(r, dict) or r.get("id") not in by_id:
                continue
            eid = r["id"]
            ev = by_id[eid]
            for k in r.get("add") or []:
                if not isinstance(k, dict) or k.get("entity") not in self.ents or k.get("channel") not in CHANNELS:
                    self._drop("knower", "bad entity or channel", event=eid, raw=str(k)[:90])
                    continue
                src = k.get("source") if k.get("source") in self.ents else None
                self._upsert_knower(ev, k["entity"], k["channel"], src, k.get("line") if isinstance(k.get("line"), int) else None)
            for k in r.get("drop") or []:
                if isinstance(k, dict) and k.get("entity") in self.ents:
                    part = [p for p in ev["parts"] if p["entity"] == k["entity"] and p["role"] in PRESENT]
                    if part:
                        self._drop("knower_drop", "present participant kept", event=eid, entity=k["entity"])
                        continue
                    self.con.execute("DELETE FROM canon_knower WHERE event_id=? AND entity=?", (eid, k["entity"]))
            for p in r.get("presupposes") or []:
                if not isinstance(p, dict) or p.get("person") not in self.ents:
                    continue
                tgt = p.get("event")
                row = self.con.execute("SELECT r.t_from FROM record r JOIN canon_event c ON c.id=r.id WHERE r.id=?", (tgt,)).fetchone() \
                    if isinstance(tgt, int) else None
                if row is None or tgt >= eid:
                    self._drop("presupposes", "unknown or later event", event=eid, raw=str(p)[:90])
                    continue
                via = p.get("via") if p.get("via") in self.ents else None
                learned = max(self._event_t(eid), row["t_from"])
                self._upsert_knower(ev, p["person"], "heard", via, None, event_id=tgt, learned_t=learned, only_new=True)

    def _event_t(self, eid: int) -> int:
        return self.con.execute("SELECT t_from FROM record WHERE id=?", (eid,)).fetchone()[0]

    def _upsert_knower(self, ev: dict[str, Any], entity: str, channel: str, source: str | None, line: int | None,
                       *, event_id: int | None = None, learned_t: int | None = None, only_new: bool = False) -> None:
        eid = event_id or ev["id"]
        t = self._event_t(eid)
        if learned_t is None:
            learned_t = t
            if channel in ("told", "heard", "hearsay", "read", "inferred"):
                lt = self.time_at_line(line or (min(ev["lines"]) if ev["lines"] else None))
                learned_t = max(t, lt) if lt is not None else t
        old = self.con.execute("SELECT 1 FROM canon_knower WHERE event_id=? AND entity=?", (eid, entity)).fetchone()
        if old and only_new:
            return
        self.con.execute("INSERT OR REPLACE INTO canon_knower VALUES (?,?,?,?,?,?,?,?)",
                         (eid, entity, channel, source, max(0, learned_t - t), learned_t, "day", line))

    def code_knower_rules(self) -> dict[str, int]:
        """Deterministic part: present participants are knowers; tellers are not witnesses; learned_t from scenes."""
        n = {"added_present": 0, "demoted_teller": 0, "retimed": 0}
        for ev in self.events():
            have = {k["entity"]: k for k in ev["know"]}
            speakers = [p["entity"] for p in ev["parts"] if p["role"] == "speaker"]
            for p in ev["parts"]:
                if p["role"] not in PRESENT or p["entity"] in have:
                    continue
                ent = self.ents.get(p["entity"])
                if ent is None or ent["type"] not in ("person", "collective", "creature"):
                    continue
                if ev["past"]:  # a retold event: the listener is told by the speaker; others present were not at the event
                    if p["role"] == "listener" and speakers:
                        self._upsert_knower(ev, p["entity"], "told", speakers[0], min(ev["lines"]) if ev["lines"] else None)
                    elif p["role"] in ("actor", "victim", "target", "witness"):
                        self._upsert_knower(ev, p["entity"], "witnessed", None, None)
                else:
                    self._upsert_knower(ev, p["entity"], "witnessed", None, None)
                n["added_present"] += 1
            if ev["past"]:
                roles = {}
                for p in ev["parts"]:
                    roles.setdefault(p["entity"], set()).add(p["role"])
                for k in ev["know"]:
                    if k["channel"] == "witnessed" and not (roles.get(k["entity"], set()) & {"actor", "target", "victim", "witness"}):
                        self.con.execute("UPDATE canon_knower SET channel='heard' WHERE event_id=? AND entity=?", (ev["id"], k["entity"]))
                        n["demoted_teller"] += 1
        # learned_t from the scene at the line (or the event itself)
        for ev in self.events():
            for k in ev["know"]:
                if k["channel"] in ("told", "heard", "hearsay", "read", "inferred"):
                    lt = self.time_at_line(k["learned_line"] or (min(ev["lines"]) if ev["lines"] else None))
                    if lt is not None:
                        lt = max(lt, ev["t_from"])
                        self.con.execute("UPDATE canon_knower SET learned_t=?, delay_minutes=? WHERE event_id=? AND entity=?",
                                         (lt, max(0, lt - ev["t_from"]), ev["id"], k["entity"]))
                        n["retimed"] += 1
                elif ev["t_from"] != k["learned_t"] and not ev["past"]:
                    self.con.execute("UPDATE canon_knower SET learned_t=? WHERE event_id=? AND entity=?",
                                     (ev["t_from"], ev["id"], k["entity"]))
        self.con.commit()
        return n

    # ---- 4. Ukrainian gist ---------------------------------------------------------------
    def pass_gist(self) -> None:
        evs = self.events()
        for bi in range(0, len(evs), BATCH):
            batch = evs[bi: bi + BATCH]
            blocks = [f"id {e['id']}: {e['body']}\n  text: {self.source_text(e, 450)}" for e in batch]
            names = "; ".join(sorted({v['name'] for v in self.ents.values() if v["type"] in ("person", "collective", "place")}))
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
                "Write for each event a Ukrainian gist: ONE plain sentence (at most 30 words) saying who did or said what to whom, "
                "in everyday Ukrainian that a villager or a guard would use, with names in the form used in this list: " + names +
                ". Also give 6 to 10 keywords: everyday Ukrainian words (nominative or the form people say) that someone asking about this "
                "would use (for example: вбив, корчма, нагорода, король, відьмак). Use only what the event says.\n\n" + "\n".join(blocks) +
                '\n\nJSON: {"events": [{"id": 12, "gist": "...", "keywords": ["...", "..."]}]}')}]
            obj = self._ask(f"gist_{bi // BATCH:02d}", msgs)
            for r in obj.get("events") or []:
                if isinstance(r, dict) and isinstance(r.get("gist"), str) and r["gist"].strip() and \
                        r.get("id") in {e["id"] for e in batch}:
                    g = r["gist"].strip()
                    if self.glossary:
                        g = self.glossary.apply(g)
                    kw = " ".join(str(x) for x in (r.get("keywords") or []) if isinstance(x, str))
                    self.con.execute("UPDATE canon_event SET gist_uk=?, kw_uk=? WHERE id=?", (g, kw, r["id"]))
        self.con.commit()
        miss = [r[0] for r in self.con.execute("SELECT id FROM canon_event WHERE gist_uk IS NULL")]
        for i in miss:
            self._drop("gist", "missing", event=i)

    # ---- 5. reactions --------------------------------------------------------------------
    def pass_reactions(self) -> None:
        self.con.execute("DELETE FROM canon_reaction")
        self.con.execute("DELETE FROM record WHERE kind='canon_reaction'")
        evs = self.events()
        for bi in range(0, len(evs), BATCH):
            batch = evs[bi: bi + BATCH]
            blocks = []
            cands: dict[int, list[str]] = {}
            for e in batch:
                roles: dict[str, set[str]] = {}
                for p in e["parts"]:
                    roles.setdefault(p["entity"], set()).add(p["role"])
                # a party answers to what ANOTHER party did in the event: the sole actor or speaker is not a candidate
                c = [x for x in dict.fromkeys([k["entity"] for k in e["know"]] + [p["entity"] for p in e["parts"] if p["role"] in PRESENT])
                     if self.ents.get(x, {}).get("type") in ("person", "collective")
                     and not (roles.get(x, set()) and roles[x] <= {"actor", "speaker"})]
                cands[e["id"]] = c
                blocks.append(f"id {e['id']}: {e['body']}\n  text: {self.source_text(e, 600)}\n  parties: " +
                              ", ".join(f"{x} ({self.ents[x]['name']})" for x in c))
            msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": (
                "For each event and each listed party decide what the party DOES in response to the event, as the text shows it "
                "(a visible act or an explicit statement within the same scene). Choose one reaction word from: " + " | ".join(REACTIONS) +
                ' or "none". "none" is the right answer, and the usual one: most parties in most events show no response in the text. Use "none" when the text shows no '
                "response by that party, when the party only speaks as part of the event itself, or when the event is the party's own act. "
                "A reaction needs a visible act or an explicit statement in the text. Do not infer feelings the text does not show. Attitude: one of " +
                " | ".join(ATTITUDES) + " or null.\n\n" + "\n".join(blocks) +
                '\n\nJSON: {"events": [{"id": 12, "reactions": [{"party": "id", "reaction": "word or none", "attitude": "word or null"}]}]}')}]
            obj = self._ask(f"reactions_{bi // BATCH:02d}", msgs)
            for r in obj.get("events") or []:
                if not isinstance(r, dict) or r.get("id") not in cands:
                    continue
                ev = next(e for e in batch if e["id"] == r["id"])
                seen = set()
                for x in r.get("reactions") or []:
                    if isinstance(x, dict) and isinstance(x.get("party"), str) and x["party"].split():
                        x["party"] = x["party"].split()[0]
                    if not isinstance(x, dict) or x.get("party") not in cands[r["id"]]:
                        self._drop("reaction", "party not a candidate", event=r["id"], raw=str(x)[:80])
                        continue
                    if x.get("reaction") in (None, "none") or x["party"] in seen:
                        continue
                    if x["reaction"] not in REACTIONS:
                        self._drop("reaction", "not in vocabulary", event=r["id"], raw=str(x)[:80])
                        continue
                    seen.add(x["party"])
                    from .store import add_record
                    rid = add_record(self.con, "canon_reaction", x["reaction"], t_from=ev["t_from"], writer_ref=self.model)
                    att = x.get("attitude") if x.get("attitude") in ATTITUDES else None
                    self.con.execute("INSERT INTO canon_reaction VALUES (?,?,?,?,?,?)", (rid, r["id"], x["party"], x["reaction"], att, None))
        self.con.commit()

    # ---- 6. search tables ----------------------------------------------------------------
    def rebuild_fts(self) -> None:
        self.con.execute("DELETE FROM canon_event_fts")
        for r in self.con.execute("SELECT r.id, r.body, c.quote, c.gist_uk, c.kw_uk FROM record r JOIN canon_event c ON c.id=r.id"):
            txt = " ".join(x for x in (r["gist_uk"], r["kw_uk"], r["quote"], r["body"]) if x)
            self.con.execute("INSERT INTO canon_event_fts(rowid, text) VALUES (?,?)", (r["id"], txt))
        self.con.execute("UPDATE canon_meta SET ingest_version='pilot-2'")
        self.con.commit()

    def run(self) -> dict[str, Any]:
        t0 = time.time()
        self.pass_time()
        self.pass_places()
        self.code_knower_rules()
        self.pass_knowers()
        rules = self.code_knower_rules()
        self.pass_gist()
        self.pass_reactions()
        self.rebuild_fts()
        counts = {t: self.con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0] for t in (
            "entity", "canon_event", "canon_participant", "canon_knower", "canon_reaction")}
        return {"seconds": round(time.time() - t0), "model_calls": self.stats["calls"], "code_rules": rules,
                "counts": counts, "dropped": self.stats["dropped"]}
