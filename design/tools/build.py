"""Builds design/schema.md from design/schema.template.md.

Loads schema.sql and canon.sql into SQLite, plays the five scenarios with the rollback algorithm
described in the design, asserts the properties the document claims, and renders the resulting
rows as Markdown tables. Run:  nix develop --command python design/tools/build.py
No network, no API calls.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMA = (ROOT / "schema.sql").read_text()
CANON = (ROOT / "canon.sql").read_text()
HOLDER = (ROOT / "holder_views.sql").read_text()
HOLDER_VIEWS = ("v_knows", "v_own_state", "v_attitudes", "v_intents", "v_heard_text", "v_scene")

IMMUTABLE = ["entity", "record", "record_link", "rollback", "stale", "judgment", "text_unit",
             "interruption", "presence", "fact", "knowledge", "belief_update", "membership",
             "attitude", "state_elem", "intent", "intent_resolution", "reach", "correction",
             "divergence", "drift_ruling"]


def T(d: int, h: int = 0, m: int = 0) -> int:
    return (d - 1) * 1440 + h * 60 + m


def fmt(t):
    if t is None:
        return None
    d, r = divmod(t, 1440)
    return f"d{d + 1} {r // 60:02d}:{r % 60:02d}"


def section(sql: str, name: str) -> str:
    m = re.search(rf"-- @@{name}\n(.*?)(?=\n-- @@|\Z)", sql, re.S)
    return m.group(1).strip() if m else ""


def new_db() -> sqlite3.Connection:
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.create_function("T", 1, fmt)
    c.executescript(SCHEMA)
    for t in IMMUTABLE:
        c.execute(f"CREATE TRIGGER {t}_no_update BEFORE UPDATE ON {t} "
                  f"BEGIN SELECT RAISE(ABORT,'append-only'); END")
        c.execute(f"CREATE TRIGGER {t}_no_delete BEFORE DELETE ON {t} "
                  f"BEGIN SELECT RAISE(ABORT,'append-only'); END")
    c.execute("PRAGMA foreign_keys = ON")
    return c


def cell(v) -> str:
    if v is None:
        return "—"
    return str(v).replace("|", "\\|").replace("\n", " ")


def tbl(conn, sql: str, params=()) -> str:
    cur = conn.execute(sql, params)
    cols = [d[0] for d in cur.description]
    rows = cur.fetchall()
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def rows_md(cols, rows) -> str:
    out = ["| " + " | ".join(cols) + " |", "|" + "|".join("---" for _ in cols) + "|"]
    out += ["| " + " | ".join(cell(v) for v in r) + " |" for r in rows]
    return "\n".join(out)


def as_of(kind: str) -> str:
    """Current value of every register of `kind` at in-world time :T (the canonical as-of query)."""
    return (f"(SELECT r.* FROM v_alive r WHERE r.kind='{kind}' AND r.t_from <= :T AND r.id = "
            f"(SELECT x.id FROM v_alive x WHERE x.kind = r.kind AND x.slot = r.slot "
            f"AND x.t_from <= :T ORDER BY x.t_from DESC, x.id DESC LIMIT 1))")


class W:
    """One campaign database plus bookkeeping."""

    def __init__(self) -> None:
        self.c = new_db()
        self.ids: dict[str, int] = {}
        self.wall = dt.datetime(2026, 10, 19, 10, 0, 0)
        self.turn = 0
        self.batch = 0
        self.world_now = 0

    def ent(self, id_: str, type_: str, name: str) -> None:
        self.c.execute("INSERT INTO entity (id,type,name) VALUES (?,?,?)", (id_, type_, name))

    def _wall(self) -> str:
        self.wall += dt.timedelta(seconds=7)
        return self.wall.strftime("%Y-%m-%dT%H:%M:%SZ")

    def rec(self, kind, body, t, *, t_to=None, slot=None, place=None, notab=None, logged=None,
            writer="code", ref=None, tags=(), meta=None, req=(), sup=(), about=(), repl=(),
            ext=None, name=None, prec="exact") -> int:
        logged = t if logged is None else logged
        self.world_now = max(self.world_now, logged)
        cur = self.c.execute(
            "INSERT INTO record (kind,slot,body,tags,meta,place,t_from,t_to,t_prec,notability,"
            "logged_world,logged_wall,turn,writer,writer_ref) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (kind, slot, body, json.dumps(list(tags)), json.dumps(meta or {}), place, t, t_to, prec,
             notab, logged, self._wall(), self.turn, writer, ref))
        rid = int(cur.lastrowid)
        if ext:
            tab, vals = ext
            vals = {"id": rid, **vals}
            self.c.execute(f"INSERT INTO {tab} ({','.join(vals)}) VALUES ({','.join('?' * len(vals))})",
                           list(vals.values()))
        for role, items in (("requires", req), ("supports", sup), ("about", about), ("replaces", repl)):
            for it in items:
                pid, sf, st = (it, None, None) if isinstance(it, int) else it
                self.c.execute("INSERT INTO record_link (child,parent,role,span_from,span_to) "
                               "VALUES (?,?,?,?,?)", (rid, pid, role, sf, st))
        if name:
            self.ids[name] = rid
        return rid

    # -- typed shortcuts --------------------------------------------------------------
    def text(self, kind, body, t, actor=None, *, shown=1, generated=None, aud=(), **kw) -> int:
        return self.rec(kind, body, t, ext=("text_unit", {
            "actor": actor, "shown": shown, "audience": json.dumps(list(aud)),
            "generated": generated or body}), **kw)

    def presence(self, who, place, zone, t, **kw) -> int:
        return self.rec("presence", f"{who} is {'in' if zone == 'room' else 'near'} {place}", t,
                        slot=f"presence|{who}", place=place,
                        ext=("presence", {"entity": who, "place": place, "zone": zone}), **kw)

    def fact(self, body, t, *, status="established", by=None, **kw) -> int:
        return self.rec("fact", body, t, ext=("fact", {"status": status, "asserted_by": by}), **kw)

    def state(self, subject, elem, body, t, *, category, observable, present=1, aware="known",
              percept=None, expires=None, tags=(), **kw) -> int:
        return self.rec("state", body, t, slot=f"{subject}|{elem}", tags=tags, ext=("state_elem", {
            "subject": subject, "elem": elem, "category": category, "present": present,
            "observable": observable, "perceptibility": json.dumps(percept) if percept else None,
            "self_aware": aware, "expires_at": expires}), **kw)

    def know(self, holder, body, t, *, about=None, channel, source=None, sk=None, hops=0,
             ops=(), stance="unjudged", conf=None, sal="unjudged", sincerity="unknown",
             req=(), **kw) -> int:
        req = list(req)
        if about is not None and about not in req:
            req.append(about)
        if sk is not None and sk not in req:
            req.append(sk)
        return self.rec("knowledge", body, t, req=req, ext=("knowledge", {
            "holder": holder, "about": about, "channel": channel, "source": source,
            "source_knowledge": sk, "hops": hops, "operators": json.dumps(list(ops)),
            "stance": stance, "confidence": conf, "sincerity": sincerity, "salience": sal}), **kw)

    def attitude(self, holder, kid, stance, mag, t, *, reason="", **kw) -> int:
        about = self.c.execute("SELECT about FROM knowledge WHERE id=?", (kid,)).fetchone()[0]
        return self.rec("attitude", reason, t, slot=f"att|{holder}|{kid}", req=[kid],
                        ext=("attitude", {"holder": holder, "knowledge_id": kid, "about": about,
                                          "stance": stance, "magnitude": mag}), **kw)

    def intent(self, holder, body, t, *, type_, audience=None, utt=None, from_word=None, **kw) -> int:
        return self.rec("intent", body, t, ext=("intent", {
            "holder": holder, "type": type_, "audience": audience, "utterance_id": utt,
            "from_word": from_word, "secrecy": None, "player_salience": None}), **kw)

    def judge(self, tag, kind, question, answer, p, *, backend="jev-1.13", options=None,
              escalated=0, inputs=(), batch=None, cost=0.0003) -> int:
        if batch is None:
            self.batch += 1
            batch = self.batch
        cur = self.c.execute(
            "INSERT INTO judgment (batch,tag,kind,question,options,answer,p,backend,escalated,inputs,"
            "logged_wall,cost_usd) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
            (batch, tag, kind, question, json.dumps(options) if options else None, str(answer), p,
             backend, escalated, json.dumps(list(inputs)), self._wall(), cost))
        return int(cur.lastrowid)

    # -- reading ----------------------------------------------------------------------
    def q(self, sql, params=()):
        return self.c.execute(sql, params).fetchall()

    def t(self, sql, params=()) -> str:
        return tbl(self.c, sql, params)

    def alive(self, rid: int) -> bool:
        return self.c.execute("SELECT 1 FROM rollback WHERE record_id=?", (rid,)).fetchone() is None

    # -- rollback: the algorithm of the design -----------------------------------------
    def _descend(self, seeds) -> set[int]:
        rows = self.c.execute(
            "WITH RECURSIVE d(id) AS (SELECT value FROM json_each(?) UNION "
            "SELECT l.child FROM record_link l JOIN d ON l.parent = d.id "
            "WHERE l.role='requires' AND l.parent_store='campaign') SELECT id FROM d",
            (json.dumps(sorted(seeds)),)).fetchall()
        return {r[0] for r in rows}

    def plan_rollback(self, seeds) -> tuple[list[int], list[int]]:
        """(records that die, records that become stale). Does not write."""
        already = {r[0] for r in self.c.execute("SELECT record_id FROM rollback")}
        dead = self._descend(seeds) - already
        sup = self.c.execute("SELECT child, parent FROM record_link WHERE role='supports'"
                             " AND parent_store='campaign'").fetchall()
        groups: dict[int, list[int]] = {}
        for ch, pa in sup:
            groups.setdefault(ch, []).append(pa)
        while True:
            gone = dead | already
            new = {ch for ch, ps in groups.items() if ch not in gone and all(p in gone for p in ps)}
            if not new:
                break
            dead |= self._descend(new) - already
        gone = dead | already
        stale = sorted(ch for ch, ps in groups.items()
                       if ch not in gone and any(p in gone for p in ps))
        return sorted(dead), stale

    def rollback(self, seeds, reason, by=None) -> tuple[list[int], list[int]]:
        dead, stale = self.plan_rollback(seeds)
        seq = self.c.execute("SELECT MAX(id) FROM record").fetchone()[0]
        root = min(seeds) if seeds else None
        for i in dead:
            self.c.execute("INSERT INTO rollback (record_id,root_id,by_record,reason,at_seq) "
                           "VALUES (?,?,?,?,?)", (i, root, by, reason, seq))
        sup_of = {i: [r[0] for r in self.c.execute(
            "SELECT parent FROM record_link WHERE child=? AND role='supports'", (i,))] for i in stale}
        for i in stale:
            lost = [p for p in sup_of[i] if not self.alive(p)][0]
            if self.c.execute("SELECT 1 FROM stale WHERE record_id=?", (i,)).fetchone() is None:
                self.c.execute("INSERT INTO stale (record_id,lost_parent,at_seq) VALUES (?,?,?)",
                               (i, lost, seq))
        return dead, stale

    def cut_seeds(self, utt: int, after_word: int, exclude=()) -> list[int]:
        """Records derived from words after the cut (no span = derived from the whole text)."""
        rows = self.c.execute(
            "SELECT child FROM record_link WHERE parent=? AND parent_store='campaign' AND "
            "role='requires' AND (span_to IS NULL OR span_to > ?)", (utt, after_word)).fetchall()
        return [r[0] for r in rows if r[0] not in exclude]

    def fork(self) -> "W":
        other = W()
        self.c.commit()
        other.c.close()
        other.c = sqlite3.connect(":memory:")
        other.c.row_factory = sqlite3.Row
        self.c.backup(other.c)
        other.c.create_function("T", 1, fmt)
        other.wall, other.turn, other.batch, other.world_now = (
            self.wall, self.turn, self.batch, self.world_now)
        other.ids = dict(self.ids)
        return other


def snapshot(w: "W", who: str, t: int) -> sqlite3.Connection:
    """The ONLY thing an NPC / assistant prompt builder receives: a throwaway in-memory database
    holding the holder-scoped views for (who, t) and nothing else (schema.md 6.2)."""
    c = w.c
    if not getattr(w, "_holder_ready", False):
        c.executescript(HOLDER)
        w._holder_ready = True
    c.execute("DELETE FROM ctx")
    c.execute("INSERT INTO ctx (who,t) VALUES (?,?)", (who, t))
    snap = sqlite3.connect(":memory:")
    snap.row_factory = sqlite3.Row
    for v in sorted(HOLDER_VIEWS):
        cur = c.execute(f"SELECT * FROM {v}")
        cols = [d[0] for d in cur.description]
        name = v[2:]
        snap.execute(f"CREATE TABLE {name} ({', '.join(cols)})")
        snap.executemany(f"INSERT INTO {name} VALUES ({','.join('?' * len(cols))})",
                         [tuple(r) for r in cur.fetchall()])
    return snap


def run_as(w: "W", who: str, t: int, sql: str) -> str:
    return tbl(snapshot(w, who, t), sql)


def denied(w: "W", sql: str) -> str:
    snap = snapshot(w, "marta", 0)
    try:
        snap.execute(sql).fetchall()
        return "NOT DENIED"
    except sqlite3.DatabaseError as e:
        return str(e)


OUT: dict[str, str] = {}   # table name -> markdown
IDS: dict[str, int] = {}   # 's1.F1' -> record id

KROW = ("SELECT k.id, k.holder, k.about, k.channel, k.source AS src, k.source_knowledge AS src_k, "
        "k.hops, k.salience AS sal, T(r.t_from) AS learned, T(r.logged_world) AS logged, "
        "CASE WHEN EXISTS(SELECT 1 FROM rollback b WHERE b.record_id=k.id) THEN 'DEAD' ELSE '' END AS dead, "
        "r.body AS version FROM knowledge k JOIN record r ON r.id=k.id")


def ids_of(w: W, prefix: str) -> None:
    for k, v in w.ids.items():
        IDS[f"{prefix}.{k}"] = v


def perceivers(w: W, t: int, kind: str, notab: float, actor: str, speaker=None):
    """The code-side perception rule used in the scenarios (mirrors harness/perception.py,
    extended with observer state and presence-as-of). Returns [(entity, channel, source, why)]."""
    pres = w.q(f"SELECT p.entity, p.zone FROM {as_of('presence')} r JOIN presence p ON p.id=r.id "
               "ORDER BY p.entity", {"T": t})
    states = w.q(f"SELECT s.subject, r.tags FROM {as_of('state')} r JOIN state_elem s ON s.id=r.id "
                 "WHERE s.present=1", {"T": t})
    blocked = {s["subject"]: json.loads(s["tags"]) for s in states}
    out = []
    for p in pres:
        who, zone = p["entity"], p["zone"]
        tags = blocked.get(who, [])
        if who == actor and kind == "action":
            out.append((who, "witnessed", None, "own act"))
        elif zone == "room":
            if kind == "action":
                if "blocks:sight" in tags:
                    out.append((who, None, None, "asleep: cannot see"))
                else:
                    out.append((who, "witnessed", None, "in the room, can see"))
            elif kind == "speech":
                if who == speaker:
                    continue
                out.append((who, "told", speaker, "in the room"))
        elif zone == "nearby":
            if notab >= 0.7:
                out.append((who, "heard", speaker, f"nearby, notability {notab} >= 0.7"))
            else:
                out.append((who, None, None, f"nearby, notability {notab} < 0.7"))
    return out


def perc_table(rows) -> str:
    return rows_md(["observer", "result", "why"],
                   [(r[0], r[1] or "does not perceive", r[3]) for r in rows])


# ======================================================================================
# Scenario 1: a bloody sword in an inn
# ======================================================================================
def scenario1() -> W:
    w = W()
    for e in [("ragnar", "person", "Ragnar (player)"), ("marta", "person", "Marta, innkeeper"),
              ("hubert", "person", "Hubert, drover"), ("joss", "person", "Joss, drover"),
              ("brandt", "person", "Captain Brandt"), ("tilda", "person", "Tilda, peddler"),
              ("place:taproom", "place", "Heron taproom"), ("place:upstairs", "place", "Heron upper floor")]:
        w.ent(*e)
    # setup (turn 0, materialised before the scene)
    w.turn = 0
    for who, place, zone, t in [("marta", "place:taproom", "room", T(3, 18)),
                                ("hubert", "place:taproom", "room", T(3, 18)),
                                ("joss", "place:taproom", "room", T(3, 18)),
                                ("brandt", "place:upstairs", "nearby", T(3, 18)),
                                ("ragnar", "place:taproom", "room", T(3, 19, 30))]:
        w.presence(who, place, zone, t, name=f"pres_{who}", writer="code", ref="setup")
    w.state("joss", "posture:asleep", "Joss sleeps with his head on the table", T(3, 19, 10),
            category="posture", observable=1, percept={"sight": 0.95}, name="asleep",
            tags=["posture", "blocks:sight", "dulls:hearing"])
    # --- turn 12, 19:40
    w.turn = 12
    t0 = T(3, 19, 40)
    p = w.text("player_input", "I step up to the fire and draw my sword to check the edge.", t0,
               "ragnar", writer="player", name="p")
    n = w.text("narration", "Ragnar draws his steel sword at the fire. Dark, wet blood runs down the "
               "fuller; the taproom goes quiet.", t0, None, req=[p], name="n")
    a = w.text("action", "Ragnar draws his steel sword; the blade is smeared with fresh blood.", t0,
               "ragnar", req=[n], name="a", aud=["hubert", "marta", "ragnar"])
    f1 = w.fact("Ragnar drew a steel sword with fresh blood on the blade in the Heron taproom.", t0,
                place="place:taproom", notab=0.62, req=[a], writer="extractor", ref="ext:turn12",
                tags=["sword", "blood"], name="F1")
    s1 = w.state("ragnar", "sword:steel", "steel sword drawn, in his hand", t0, category="gear",
                 observable=1, req=[a], writer="extractor", ref="ext:turn12", name="S1")
    s2 = w.state("ragnar", "blood:blade", "fresh blood smeared along the blade of his sword", t0,
                 category="appearance", observable=1, percept={"sight": 0.9}, req=[a],
                 writer="extractor", ref="ext:turn12", name="S2")
    pr = perceivers(w, t0, "action", 0.62, "ragnar")
    OUT["s1_perceivers"] = perc_table(pr)
    jb = w.judge("salience", "yes_no", "Would Marta notice this and find it worth reacting to?", "yes", 0.95,
                 options=None, inputs=[f1, s1, s2])
    w.judge("salience", "yes_no", "Would Hubert notice this and find it worth reacting to?", "yes", 0.91,
            batch=w.batch, inputs=[f1])
    sal = {("marta", "F1"): "noteworthy", ("hubert", "F1"): "noteworthy",
           ("marta", "S1"): "noteworthy", ("hubert", "S1"): "ignored",
           ("marta", "S2"): "noteworthy", ("hubert", "S2"): "noteworthy"}
    texts = {"F1": "The stranger drew a steel sword by the fire, and there was fresh blood on it.",
             "S1": "The stranger's sword is out, in his hand.",
             "S2": "There is fresh blood smeared on the stranger's blade."}
    kids = {}
    for who in ("ragnar", "marta", "hubert"):
        kids[(who, "F1")] = w.know(
            who, texts["F1"] if who != "ragnar" else "I drew my sword by the fire; there is fresh blood on it.",
            t0, about=f1, channel="witnessed", stance="firsthand", sal=sal.get((who, "F1"), "unjudged"),
            ref=f"j:{jb}", name=f"K_{who}_F1")
    for who in ("marta", "hubert"):
        for tag, rid in (("S1", s1), ("S2", s2)):
            kids[(who, tag)] = w.know(who, texts[tag], t0, about=rid, channel="witnessed",
                                      stance="firsthand", sal=sal[(who, tag)], ref=f"j:{jb}",
                                      name=f"K_{who}_{tag}")
    ja = w.judge("attitude_direction", "choice", "How does Marta feel about this?", "negative", 0.93,
                 options=["positive", "neutral", "negative"], inputs=[f1])
    jm = w.judge("relationship_magnitude", "score", "How strongly does Marta feel about this?", 0.7, 0.8,
                 backend="deepseek/deepseek-v4-flash", inputs=[f1], cost=0.0002)
    w.judge("attitude_direction", "choice", "How does Hubert feel about this?", "neutral", 0.88,
            options=["positive", "neutral", "negative"], inputs=[f1], batch=ja)
    att = w.attitude("marta", kids[("marta", "F1")], "negative", 0.7, t0, reason="afraid for her taproom",
                     writer="judgment", ref=f"j:{ja},{jm}", name="A_marta")
    # Marta's context, read through the restricted connection (the only way a prompt builder may read)
    OUT["s1_marta_ctx"] = run_as(w, "marta", T(3, 19, 41),
        "SELECT body AS 'What you know', channel, source_name AS 'from', salience, surfaced FROM knows "
        "ORDER BY learned, id")
    OUT["iso_denied_fact"] = denied(w, "SELECT * FROM fact")
    OUT["iso_denied_state"] = denied(w, "SELECT * FROM state_elem")
    OUT["iso_denied_record"] = denied(w, "SELECT body FROM record")
    OUT["iso_denied_sincerity"] = denied(w, "SELECT sincerity FROM knows")
    OUT["iso_joss_ctx"] = run_as(w, "joss", T(3, 19, 41), "SELECT COUNT(*) AS rows_joss_may_read FROM knows")
    # Marta's line: first candidate rejected by the output check (no channel), second accepted
    w.judge("unknown_claim", "yes_no", "Does the line assert something this character had no channel to learn? "
            "Line: 'You killed Brandt's rider, didn't you?'", "yes", 0.96, inputs=[kids[("marta", "F1")]])
    w.judge("unknown_claim", "yes_no", "… Line: 'Blood on steel in my taproom? Put it away, stranger, or take "
            "it outside.'", "no", 0.97, inputs=[kids[("marta", "F1")]])
    u1 = w.text("utterance", "Blood on steel in my taproom? Put it away, stranger, or take it outside.",
                T(3, 19, 41), "marta", req=[n], name="U1", notab=0.4, aud=["hubert", "ragnar"])
    for kk in ("K_marta_F1", "K_marta_S1", "K_marta_S2"):   # the noteworthy observations were put in her prompt
        w.rec("surfaced", "", T(3, 19, 41), about=[w.ids[kk]], req=[u1], writer="code")
    # --- turn 14, 20:07: Joss wakes, Hubert tells him
    w.turn = 14
    t1 = T(3, 20, 7)
    n2 = w.text("narration", "Joss stirs, lifts his head from the table and squints at the room.", t1,
                req=[p], name="n2")
    w.state("joss", "posture:asleep", "Joss is awake", t1, category="posture", observable=1, present=0,
            req=[n2, w.ids["asleep"]], writer="extractor", ref="ext:turn14", name="awake",
            tags=["posture"])
    u2 = w.text("utterance", "Wake up, Joss. That stranger pulled a bloody sword by the fire.", t1, "hubert",
                req=[n2], name="U2", notab=0.4, aud=["joss", "marta", "ragnar"])
    jmatch = w.judge("match_fact", "choice", "Which existing fact does Hubert's line report?",
                     f"F{f1}", 0.94, options=[f"F{f1}", "none"], inputs=[u2, f1])
    w.know("joss", "A stranger pulled a bloody sword by the fire.", t1, about=f1, channel="told",
           source="hubert", sk=w.ids["K_hubert_F1"], hops=1, req=[(u2, 1, 12)], writer="code",
           ref=f"j:{jmatch}", name="K_joss_F1")
    # --- turn 15, 20:20: Marta shouts upstairs (loud)
    w.turn = 15
    t2 = T(3, 20, 20)
    n3 = w.text("narration", "Marta's patience snaps; she turns to the stairs and shouts.", t2, req=[p],
                name="n3")
    u3 = w.text("utterance", "Captain Brandt! There's a man down here with a bloody sword!", t2, "marta",
                req=[n3], notab=0.75, name="U3",
                aud=["brandt", "hubert", "joss", "ragnar"])
    OUT["s1_perceivers_u3"] = perc_table(perceivers(w, t2, "speech", 0.75, "marta", speaker="marta"))
    w.know("brandt", "Marta says a man with a bloody sword is in the taproom.", t2, about=f1,
           channel="heard", source="marta", sk=w.ids["K_marta_F1"], hops=1, req=[(u3, 1, 11)],
           ref="j:match", name="K_brandt_F1")
    # --- 20:40 Tilda walks in: the persisting state is perceived on entry
    w.turn = 17
    t3 = T(3, 20, 40)
    n4 = w.text("narration", "The door opens; Tilda, a peddler with a pack, shuffles in out of the cold.",
                t3, req=[p], name="n4")
    pt = w.presence("tilda", "place:taproom", "room", t3, req=[n4], writer="extractor", name="pres_tilda")
    ents = w.q(f"SELECT r.id, r.body FROM {as_of('state')} r JOIN state_elem s ON s.id=r.id "
               "WHERE s.subject='ragnar' AND s.present=1 AND s.observable=1", {"T": t3})
    for e in ents:
        sid = e["id"]
        sal3 = "noteworthy" if sid == s2 else "ignored"
        w.know("tilda", texts["S1" if sid == s1 else "S2"], t3, about=sid, channel="witnessed",
               stance="firsthand", sal=sal3, req=[pt], name=f"K_tilda_{'S1' if sid == s1 else 'S2'}")
    ids_of(w, "s1")
    # -- tables
    OUT["s1_records"] = w.t(
        "SELECT r.id, r.kind, T(r.t_from) AS in_world, T(r.logged_world) AS logged, r.writer, "
        "substr(r.body,1,58) AS body FROM record r WHERE r.turn=12 ORDER BY r.id")
    OUT["s1_links"] = w.t(
        "SELECT child, role, parent FROM record_link WHERE child IN "
        "(SELECT id FROM record WHERE turn=12) ORDER BY child, parent")
    OUT["s1_knowledge"] = w.t(KROW + f" WHERE k.about = {f1} ORDER BY r.t_from, k.id")
    OUT["s1_knowledge_state"] = w.t(KROW + f" WHERE k.about IN ({s1},{s2}) ORDER BY r.t_from, k.id")
    OUT["s1_ragnar_state"] = w.t(
        f"SELECT T(r.t_from) AS since, s.category, s.elem, r.body, s.observable AS obs FROM {as_of('state')} r "
        "JOIN state_elem s ON s.id=r.id WHERE s.subject='ragnar' AND s.present=1 ORDER BY r.id",
        {"T": T(3, 20, 41)})
    OUT["s1_who_knew_at_1950"] = w.t(
        "SELECT k.holder, k.channel FROM knowledge k JOIN v_alive r ON r.id=k.id "
        "WHERE k.about=:f AND r.t_from <= :T ORDER BY k.holder", {"f": f1, "T": T(3, 19, 50)})
    OUT["s1_attitude"] = w.t(
        "SELECT a.id, a.holder, a.knowledge_id, a.about, a.stance, a.magnitude FROM attitude a")
    OUT["s1_judgments"] = w.t(
        "SELECT id, batch, tag, kind, answer, p, backend, escalated AS esc FROM judgment ORDER BY id")
    # rollback preview: what would die if the narration of turn 12 were removed (dry run)
    dead, stale = w.plan_rollback([n])
    OUT["s1_dry"] = ", ".join(map(str, dead))
    return w


# ======================================================================================
# Scenario 2: a rumour reaches another town in two distorted versions
# ======================================================================================
def scenario2() -> W:
    w = W()
    for e in [("ragnar", "person", "Ragnar (player)"), ("osk", "person", "Osk, ford-keeper"),
              ("ostrik", "person", "Ostrik, cloth merchant"), ("hanza", "person", "Hanza, innkeeper of Vergen"),
              ("town:vergen", "collective", "Vergen (the town)"),
              ("place:ford", "place", "Alder ford"), ("place:vergen", "place", "Vergen"),
              ("place:vergen-inn", "place", "Vergen, the Bell inn")]:
        w.ent(*e)
    w.turn = 31
    t0 = T(9, 14, 20)
    p = w.text("player_input", "I wade the ford; when the riders come out of the reeds I draw and fight.",
               t0, "ragnar", writer="player", name="p")
    n = w.text("narration", "Two riders burst from the reeds. Ragnar kills both; the third wheels his "
               "horse and flees. The ford-keeper watches from his hut.", t0, req=[p], name="n")
    f = w.fact("At Alder ford two river-bandits attacked Ragnar; he killed both, took nothing, and let "
               "a third flee.", t0, place="place:ford", notab=0.85, req=[n], writer="extractor",
               ref="ext:turn31", tags=["kind:violence"], name="F")
    w.know("ragnar", "I killed two bandits who attacked me at the ford and let the third go.", t0,
           about=f, channel="witnessed", stance="firsthand", req=[n], name="K_ragnar")
    w.know("osk", "The stranger killed two riders at my ford after they jumped him; a third ran.", t0,
           about=f, channel="witnessed", stance="firsthand", req=[n], name="K_osk")
    # travel: no spread computed (lazy)
    w.turn = 32
    tp = w.rec("time_passes", "Ragnar travels away from the ford, then on toward Vergen.", T(9, 14, 30),
               t_to=T(15, 9), req=[n], meta={"mode": "skip"}, name="tp")
    # d15 09:00 arrival: pre-scene materialisation
    w.turn = 40
    now = T(15, 9)
    w.world_now = now
    earliest = T(11, 20, 20)
    j1 = w.judge("reach", "choice", "Has news of the ford fight reached Vergen by d15 09:00, "
                 "given its scale and what has happened since?", "yes_several_versions", 0.84,
                 options=["no", "yes_one_version", "yes_several_versions"], inputs=[f])
    j2 = w.judge("reach_eta", "choice", "When did it reach Vergen?", "+1d after the earliest", 0.82,
                 options=["at_earliest", "+1d after the earliest", "+2d after the earliest"], inputs=[f],
                 batch=j1)
    reach = w.rec("reach", "News of the ford fight reached Vergen.", T(12, 18), logged=now, place="place:vergen",
                  req=[f], writer="judgment", ref=f"j:{j1},{j2}", prec="hour",
                  ext=("reach", {"place": "place:vergen", "about": f, "reached": 1, "earliest": earliest}),
                  name="reach")
    ko = w.know("ostrik", "A stranger killed two men at the ford; the keeper says the third ran.",
                T(10, 8), logged=now, about=f, channel="told", source="osk", sk=w.ids["K_osk"], hops=1,
                ops=["lose_mitigating_detail"], req=[reach], writer="judgment", ref="j:ver1", name="K_ostrik")
    j3 = w.judge("version_derivable", "yes_no", "Is version A derivable from the fact by exaggerate_magnitude "
                 "+ add_motive and consistent with world rules?", "yes", 0.91, inputs=[f, ko])
    j4 = w.judge("version_derivable", "yes_no", "Is version B derivable from the fact by swap_actor + "
                 "lose_mitigating_detail and consistent with world rules?", "yes", 0.87, inputs=[f], batch=j3)
    va = w.know("town:vergen", "A grey-cloaked butcher cut down a whole band at Alder ford and took their "
                "purses.", T(12, 18), logged=now, about=f, channel="hearsay", source="ostrik", sk=ko, hops=2,
                ops=["exaggerate_magnitude", "add_motive"], req=[reach], writer="judgment",
                ref=f"j:ver1,{j3}", name="V_A", prec="hour")
    vb = w.know("town:vergen", "The ford gang fell out and killed each other; some stranger only watched.",
                T(13, 8), logged=now, about=f, channel="hearsay", source=None, hops=3,
                ops=["swap_actor", "lose_mitigating_detail"], req=[reach], writer="judgment",
                ref=f"j:ver2,{j4}", name="V_B", prec="hour")
    j5 = w.judge("version_heard", "choice", "Which Vergen version has Hanza heard?", "V_A", 0.86,
                 options=["V_A", "V_B", "both", "neither"], inputs=[va, vb])
    w.rec("membership", "Hanza lives in Vergen", T(1), slot="mem|hanza|town:vergen",
          ext=("membership", {"member": "hanza", "collective": "town:vergen", "present": 1}), name="mem")
    kh = w.know("hanza", "They say a grey butcher cut down a whole band at Alder ford and robbed them.",
                T(13, 12), logged=now, about=f, channel="hearsay", source="town:vergen", sk=va, hops=3,
                ops=["exaggerate_magnitude", "add_motive"], stance="believes", conf=0.7,
                req=[va], writer="judgment", ref=f"j:{j5}", name="K_hanza")
    ja = w.judge("attitude_direction", "choice", "How does Hanza feel about this?", "negative", 0.9,
                 options=["positive", "neutral", "negative"], inputs=[kh])
    w.attitude("hanza", kh, "negative", 0.7, T(13, 12), logged=now, reason="fears the butcher",
               writer="judgment", ref=f"j:{ja}", name="A_hanza")
    w.attitude("town:vergen", va, "negative", 0.6, T(12, 18), logged=now, reason="the town fears the butcher",
               writer="judgment", ref=f"j:{ja}", name="A_town_A")
    w.rec("summary", "In Vergen Ragnar is spoken of as a butcher, though some say the ford gang killed itself.",
          T(13, 12), logged=now, slot="rep|ragnar|town:vergen", sup=[va, vb], req=[reach], writer="judgment",
          tags=["reputation"], name="rep")
    # Hanza speaks (scene at d15 09:02)
    u = w.text("utterance", "They say a grey butcher cut down a whole band at the ford. Mind your tongue here.",
               T(15, 9, 2), "hanza", req=[n], name="U_hanza")
    ids_of(w, "s2")
    OUT["s2_versions"] = w.t(
        "SELECT k.id, k.holder, k.source AS src, k.source_knowledge AS src_k, k.hops, k.operators, "
        "T(r.t_from) AS learned, T(r.logged_world) AS logged, r.body AS version "
        f"FROM knowledge k JOIN record r ON r.id=k.id WHERE k.about={f} ORDER BY r.t_from, k.id")
    OUT["s2_truth"] = w.t(
        f"SELECT r.id, r.kind, f.status, T(r.t_from) AS in_world, r.notability AS notab, r.body FROM fact f JOIN record r ON r.id=f.id WHERE f.id={f}")
    OUT["s2_reach"] = w.t(
        "SELECT r.id, x.place, x.about, x.reached, T(x.earliest) AS earliest, T(r.t_from) AS arrival, "
        "T(r.logged_world) AS logged, r.writer FROM reach x JOIN record r ON r.id=x.id")
    OUT["s2_links"] = w.t(
        "SELECT child, role, parent FROM record_link WHERE child IN "
        f"({reach},{ko},{va},{vb},{kh},{w.ids['A_hanza']},{w.ids['A_town_A']},{w.ids['rep']}) ORDER BY child, role, parent")
    OUT["s2_hanza_ctx"] = w.t(
        "SELECT r.body AS 'What you know', k.channel, k.source AS from_ FROM knowledge k "
        "JOIN v_alive r ON r.id=k.id WHERE k.holder='hanza' AND r.t_from <= :T", {"T": T(15, 9, 2)})
    dead, stale = w.plan_rollback([n])
    OUT["s2_dry_n"] = str(len(dead))
    dead_f, _ = w.plan_rollback([f])
    OUT["s2_dry_f"] = ", ".join(map(str, dead_f))
    assert va in dead and vb in dead and kh in dead and w.ids["rep"] in dead
    return w


# ======================================================================================
# Scenario 3: retroactive interruption
# ======================================================================================
MARTA = ("The margrave's tax collector was strangled in the barn behind the mill last night. "
         "Everyone in Lower Alder says the dwarves from Mahakam did it, but I saw a woman leave.")


def scenario3() -> W:
    w = W()
    words = MARTA.split()
    assert len(words) == 31 and words[13] == "night." and words[14] == "Everyone"
    for e in [("ragnar", "person", "Ragnar (player)"), ("marta", "person", "Marta, innkeeper"),
              ("hubert", "person", "Hubert, drover"), ("town:lower-alder", "collective", "Lower Alder"),
              ("place:taproom", "place", "Heron taproom"), ("stableboy", "person", "Pavel, stable boy")]:
        w.ent(*e)
    w.turn = 0
    for who in ("ragnar", "marta", "hubert"):
        w.presence(who, "place:taproom", "room", T(8, 18), writer="code", ref="setup")
    # Marta's own knowledge, materialised before the scene (backdated)
    w.turn = 39
    lw = T(8, 20, 30)
    km0 = w.know("marta", "The tax collector was found strangled in the barn behind the mill.", T(8, 7),
                 logged=lw, channel="told", source="stableboy", writer="judgment", ref="j:materialise",
                 stance="believes", name="K_m_found")
    km1 = w.know("marta", "The villagers say the dwarves from Mahakam killed the collector.", T(8, 12),
                 logged=lw, channel="hearsay", source="town:lower-alder", writer="judgment",
                 ref="j:materialise", stance="believes", name="K_m_dwarves")
    w.know("marta", "I saw a woman leave the barn that night.", T(7, 23, 30), logged=lw,
           channel="witnessed", stance="firsthand", writer="judgment", ref="j:materialise", name="K_m_woman")
    # an earlier asserted fact about the same gossip, from another day: a survivor of the cut
    w.turn = 36
    early = w.fact("The stable boy says dwarves were seen near the mill on day 7.", T(8, 8),
                   status="asserted", by="stableboy", notab=0.4, writer="extractor", ref="ext:turn36",
                   req=[], name="F_early")
    # turn 40
    w.turn = 40
    t0 = T(8, 20, 50)
    p = w.text("player_input", "I ask Marta what happened to the tax collector.", t0, "ragnar",
               writer="player", name="p")
    n = w.text("narration", "Marta lowers her voice and glances at the door.", t0, req=[p], name="n")
    u = w.text("utterance", MARTA, t0 + 1, "marta", req=[n], notab=0.6, name="U",
               aud=["hubert", "ragnar"])
    f1 = w.fact("The margrave's tax collector was strangled in the barn behind the mill on the night of day 7.",
                t0 + 1, status="asserted", by="marta", notab=0.6, req=[(u, 1, 14)], writer="extractor",
                ref="ext:turn40", name="FA1", place="place:taproom")
    f2 = w.fact("The villagers of Lower Alder blame the dwarves from Mahakam for the killing.", t0 + 1,
                status="asserted", by="marta", notab=0.6, req=[(u, 15, 25)], writer="extractor",
                ref="ext:turn40", name="FA2")
    f3 = w.fact("Marta saw a woman leave the barn that night.", t0 + 1, status="asserted", by="marta",
                notab=0.5, req=[(u, 26, 31)], writer="extractor", ref="ext:turn40", name="FA3")
    OUT["s3_perceivers"] = perc_table(perceivers(w, t0 + 1, "speech", 0.6, "marta", speaker="marta"))
    for who in ("ragnar", "hubert"):
        for tag, fid, txt, hop in (("FA1", f1, "Marta says the collector was strangled in the barn.", (u, 1, 14)),
                                   ("FA2", f2, "Marta says the village blames the Mahakam dwarves.", (u, 15, 25)),
                                   ("FA3", f3, "Marta says she saw a woman leave the barn.", (u, 26, 31))):
            w.know(who, txt, t0 + 1, about=fid, channel="told", source="marta",
                   sk={"ragnar": None, "hubert": None}[who], hops=1,
                   writer="code", ref="turn:40", name=f"K_{who}_{tag}")
    ja = w.judge("attitude_direction", "choice", "How does Hubert feel about this?", "negative", 0.91,
                 options=["positive", "neutral", "negative"], inputs=[f2])
    jm = w.judge("relationship_magnitude", "score", "How strongly does Hubert feel about this?", 0.7, 0.8,
                 backend="deepseek/deepseek-v4-flash", inputs=[f2], cost=0.0002)
    w.attitude("hubert", w.ids["K_hubert_FA2"], "negative", 0.7, t0 + 1, logged=t0 + 5,
               reason="alarmed: he drives freight for dwarves", writer="judgment", ref=f"j:{ja},{jm}",
               name="A_hubert")
    # prefetch, written at the end of the turn: Hubert's lazily derived reaction (back-dated)
    now = T(8, 20, 55)
    jr = w.judge("reaction", "choice", "What does Hubert do about this?", "warn_dwarves", 0.88,
                 options=["ignore", "warn_dwarves", "confront_marta", "leave"], inputs=[f2])
    plan = w.intent("hubert", "Slip out to the stable yard and warn Brokvar's dwarf teamsters that the village "
                    "blames them.", T(8, 20, 53), type_="plan", audience=None, logged=now,
                    req=[w.ids["K_hubert_FA2"], w.ids["A_hubert"]], writer="judgment", ref=f"j:{jr}",
                    name="plan_hubert")
    gos = w.rec("summary", "Talk in Lower Alder is turning against the Mahakam dwarves.", T(8, 20, 54), logged=now,
                slot="gossip|town:lower-alder|dwarves", sup=[km1, f2], writer="judgment",
                tags=["gossip"], name="gossip")
    # snapshot BEFORE the cut (for the tables)
    OUT["s3_before"] = w.t(
        "SELECT r.id, r.kind, substr(r.body,1,52) AS body, T(r.t_from) AS in_world, T(r.logged_world) AS logged "
        "FROM v_alive r WHERE r.turn >= 39 AND r.kind IN ('fact','knowledge','attitude','intent','summary') "
        "ORDER BY r.id")
    OUT["s3_links_before"] = w.t(
        "SELECT l.child, r.kind, l.role, l.parent, l.span_from AS 'from', l.span_to AS 'to' FROM record_link l "
        "JOIN record r ON r.id=l.child WHERE l.child IN (%s) ORDER BY l.child, l.parent" %
        ",".join(map(str, [f1, f2, f3, plan, gos, w.ids['A_hubert']])))
    # the player cuts retroactively after word 14 (in-world: while she was speaking)
    w.turn = 40
    cut = 14
    t_cut = t0 + 1 + 1
    e = w.rec("interruption", "Ragnar interrupted Marta after \"…last night.\"", t_cut, logged=T(8, 20, 57),
              notab=0.5, req=[(u, 1, cut)], writer="code", ref="turn:40",
              ext=("interruption", {"utterance_id": u, "after_word": cut, "mode": "retro"}), name="E")
    fe = w.fact("Ragnar cut Marta off in the middle of her account of the killing.", t_cut,
                logged=T(8, 20, 57), notab=0.5, req=[e], writer="code", name="FE", place="place:taproom")
    for who in ("ragnar", "marta", "hubert"):
        w.know(who, "Ragnar cut Marta off in the middle of her account.", t_cut, logged=T(8, 20, 57),
               about=fe, channel="witnessed", stance="firsthand", name=f"K_{who}_FE")
    un = w.intent("marta", " ".join(words[cut:]), t_cut, logged=T(8, 20, 57), type_="unsaid",
                  audience="ragnar", utt=u, from_word=cut + 1, req=[e], name="unsaid")
    OUT["s3_links_cut"] = w.t(
        "SELECT l.child, r.kind, l.role, l.parent, l.span_from AS 'from', l.span_to AS 'to' FROM record_link l "
        "JOIN record r ON r.id=l.child WHERE l.child IN (%s) ORDER BY l.child, l.parent" %
        ",".join(map(str, [e, fe, un])))
    seeds = w.cut_seeds(u, cut)
    OUT["s3_seeds"] = ", ".join(map(str, seeds))
    dead, stale = w.rollback(seeds, "interruption", by=e)
    OUT["s3_rollback"] = w.t(
        "SELECT b.record_id, r.kind, substr(r.body,1,48) AS body, b.root_id, b.by_record, b.reason "
        "FROM rollback b JOIN record r ON r.id=b.record_id ORDER BY b.record_id")
    OUT["s3_stale"] = w.t("SELECT s.record_id, r.kind, s.lost_parent, substr(r.body,1,50) AS body "
                          "FROM stale s JOIN record r ON r.id=s.record_id")
    OUT["s3_after"] = w.t(
        "SELECT r.id, r.kind, substr(r.body,1,52) AS body FROM v_alive r WHERE r.turn >= 40 AND "
        "r.kind IN ('fact','knowledge','attitude','intent','summary','interruption') ORDER BY r.id")
    OUT["s3_delivered"] = w.t("SELECT id, actor, delivered_words FROM v_delivered")
    OUT["s3_ragnar_knows"] = w.t(
        "SELECT r.id, r.body, k.channel, k.source FROM knowledge k JOIN v_alive r ON r.id=k.id "
        "WHERE k.holder='ragnar' ORDER BY r.id")
    OUT["s3_marta_ctx"] = w.t(
        "SELECT 'knows' AS section, r.body FROM knowledge k JOIN v_alive r ON r.id=k.id WHERE k.holder='marta' "
        "AND r.kind='knowledge' UNION ALL SELECT 'unsaid', r.body FROM intent i JOIN v_alive r ON r.id=i.id "
        "WHERE i.holder='marta' AND i.type='unsaid' AND NOT EXISTS (SELECT 1 FROM intent_resolution x "
        "JOIN v_alive xr ON xr.id=x.id WHERE x.intent_id=i.id)")
    # properties claimed in the document
    assert set(dead) == {f2, f3, w.ids["K_ragnar_FA2"], w.ids["K_hubert_FA2"], w.ids["K_ragnar_FA3"],
                         w.ids["K_hubert_FA3"], w.ids["A_hubert"], plan}
    assert stale == [gos]
    assert w.alive(f1) and w.alive(un) and w.alive(e) and w.alive(early)
    ids_of(w, "s3")
    OUT["s3_dead_n"] = str(len(dead))
    return w


# ======================================================================================
# Scenario 4: poisoned without knowing; the panel shows symptoms
# ======================================================================================
def scenario4() -> W:
    w = W()
    for e in [("ragnar", "person", "Ragnar (player)"), ("orlik", "person", "Orlik, cook"),
              ("zoltan", "person", "Zoltan, healer"), ("place:inn", "place", "Heron kitchen yard"),
              ("place:gate", "place", "Vergen gate")]:
        w.ent(*e)
    w.turn = 0
    w.state("ragnar", "sword:steel", "steel sword at his belt, sheathed", T(5, 8), category="gear",
            observable=1, name="sword")
    w.state("ragnar", "purse", "14 crowns in a belt purse", T(5, 8), category="possession", observable=0,
            name="purse")
    w.presence("ragnar", "place:inn", "room", T(5, 12, 50))
    w.presence("orlik", "place:inn", "room", T(5, 12, 50))
    w.turn = 50
    t0 = T(5, 13)
    p = w.text("player_input", "I take the mug Orlik offers and drink while I wait for the cart.", t0,
               "ragnar", writer="player", name="p50")
    n = w.text("narration", "Orlik sets a mug of ale in front of Ragnar. It is warm and a little flat.", t0,
               req=[p], name="n50")
    h = w.text("hidden", "Orlik had stirred a few drops of foxglove tincture into the ale.", t0, "orlik",
               shown=0, req=[n], name="h50")
    fp = w.fact("Orlik laced Ragnar's ale with foxglove tincture.", t0, notab=0.5, req=[h],
                writer="extractor", ref="ext:turn50", tags=["covert", "poison"], name="F_poison")
    sp = w.state("ragnar", "poison:foxglove", "foxglove tincture in the blood, working slowly", t0,
                 category="body", observable=0, aware="unaware", percept={"examination": 0.8}, req=[h],
                 writer="extractor", ref="ext:turn50", tags=["poison"], name="S_poison")
    OUT["s4_perceivers"] = rows_md(["observer", "result", "why"], [
        ("orlik", "witnessed", "kind 'covert': only the actor perceives"),
        ("ragnar", "does not perceive", "kind 'covert': not the actor; hidden segment is never displayed")])
    w.know("orlik", "I put foxglove in the stranger's ale.", t0, about=fp, channel="witnessed",
           stance="firsthand", req=[h], name="K_orlik_F")
    w.know("orlik", "The stranger has foxglove in him.", t0, about=sp, channel="witnessed",
           stance="firsthand", req=[h], name="K_orlik_S")
    # turn 51: time passes, symptoms emitted
    w.turn = 51
    p51 = w.text("player_input", "We ride the cart to Vergen.", T(5, 13, 5), "ragnar", writer="player",
                 name="p51")
    n51 = w.text("narration", "The cart rolls through the afternoon. By the time the gate comes into view "
                 "the sun is low.", T(5, 13, 5), req=[p51], name="n51")
    jd = w.judge("duration", "choice", "How long does the ride take?", "hours", 0.92,
                 options=["minutes", "hours", "half_day", "day"], inputs=[n51])
    tp = w.rec("time_passes", "Ride to Vergen.", T(5, 13, 5), t_to=T(5, 19), req=[n51],
               meta={"mode": "turn"}, writer="judgment", ref=f"j:{jd}", name="tp")
    js = w.judge("symptom", "choice", "After about six hours with foxglove, what does the character notice?",
                 "mild_nausea", 0.88, options=["nothing", "mild_nausea", "sharp_pain", "collapse"],
                 inputs=[sp, tp])
    s1 = w.state("ragnar", "symptom:nausea", "queasy, a sour taste at the back of the throat", T(5, 16, 10),
                 logged=T(5, 19), category="body", observable=0, aware="known", req=[sp, tp],
                 writer="judgment", ref=f"j:{js}", name="S_nausea", tags=["symptom"])
    js2 = w.judge("symptom", "choice", "At the gate, what shows now?", "cold_sweat", 0.81,
                  options=["nothing", "cold_sweat", "shaking", "collapse"], inputs=[sp, tp], batch=js)
    s2 = w.state("ragnar", "symptom:sweat", "cold sweat, face gone pale", T(5, 18, 40), logged=T(5, 19),
                 category="body", observable=1, aware="known", req=[sp, tp], writer="judgment",
                 ref=f"j:{js2}", name="S_sweat", tags=["symptom"])
    # the panel at 19:05
    panel_sql = (f"SELECT s.category, s.elem, r.body FROM {as_of('state')} r JOIN state_elem s ON s.id=r.id "
                 "WHERE s.subject='ragnar' AND s.present=1 AND (s.expires_at IS NULL OR s.expires_at > :T) "
                 "AND s.self_aware != 'unaware' ORDER BY r.id")
    OUT["s4_panel_before"] = w.t(panel_sql, {"T": T(5, 19, 5)})
    # the holder view (what Ragnar's own context / the assistant get) must equal the panel query
    snap = snapshot(w, "ragnar", T(5, 19, 5))
    mine = [tuple(r) for r in snap.execute("SELECT category, elem, body FROM own_state ORDER BY id")]
    panel = [tuple(r) for r in w.q(panel_sql, {"T": T(5, 19, 5)})]
    assert mine == panel, (mine, panel)
    OUT["s4_narrator_view"] = w.t(
        f"SELECT s.elem, r.body, s.observable AS obs, s.self_aware AS aware FROM {as_of('state')} r "
        "JOIN state_elem s ON s.id=r.id WHERE s.subject='ragnar' AND s.present=1 ORDER BY r.id",
        {"T": T(5, 19, 5)})
    # Zoltan at the gate
    w.turn = 52
    t1 = T(5, 19, 20)
    p52 = w.text("player_input", "I let the healer look me over; I feel strange.", t1, "ragnar",
                 writer="player", name="p52")
    n52 = w.text("narration", "Zoltan checks his pulse, lifts an eyelid, and smells his breath.", t1, req=[p52],
                 name="n52")
    a52 = w.text("action", "Zoltan examines Ragnar: pulse, eyes, breath.", t1, "zoltan", req=[n52], name="a52")
    w.presence("zoltan", "place:gate", "room", T(5, 19, 15))
    w.presence("ragnar", "place:gate", "room", T(5, 19, 15))
    jz = w.judge("salience", "yes_no", "Would Zoltan notice Ragnar's pallor and sweat and find it worth "
                 "reacting to?", "yes", 0.97, inputs=[s2])
    w.know("zoltan", "The stranger is pale and sweating cold.", t1, about=s2, channel="witnessed",
           stance="firsthand", sal="noteworthy", req=[a52], ref=f"j:{jz}", name="K_zoltan_sweat")
    jx = w.judge("examination", "yes_no", "Can Zoltan, a healer, identify the cause of Ragnar's state by this "
                 "examination (perceptibility examination 0.8)?", "yes", 0.85, inputs=[sp, a52])
    kz = w.know("zoltan", "The stranger has foxglove in his blood.", t1, about=sp, channel="sensed",
                stance="believes", req=[a52], writer="judgment", ref=f"j:{jx}", name="K_zoltan_poison")
    UZ = "That is foxglove. Someone dosed your ale, and you are lucky it was not more."
    uz = w.text("utterance", UZ, t1 + 1, "zoltan", req=[n52], name="U_zoltan")
    kr = w.know("ragnar", "Zoltan says there is foxglove in my blood.", t1 + 1, about=sp, channel="told",
                source="zoltan", sk=kz, hops=1, req=[(uz, 1, 3)], stance="unjudged", name="K_ragnar_poison")
    sk = w.state("ragnar", "poison:foxglove", "foxglove tincture in the blood, working slowly "
                 "(identified by Zoltan)", t1 + 1, category="body", observable=0, aware="known",
                 percept={"examination": 0.8}, req=[sp, (uz, 1, 3)], writer="code", ref="reveal",
                 tags=["poison"], name="S_poison_known")
    OUT["s4_panel_after"] = w.t(panel_sql, {"T": T(5, 19, 25)})
    OUT["s4_slot"] = w.t(
        "SELECT r.id, T(r.t_from) AS since, s.self_aware AS aware, s.observable AS obs, r.body FROM record r "
        "JOIN state_elem s ON s.id=r.id WHERE r.slot='ragnar|poison:foxglove' ORDER BY r.id")
    OUT["s4_records"] = w.t(
        "SELECT r.id, r.kind, r.writer, T(r.t_from) AS in_world, T(r.logged_world) AS logged, substr(r.body,1,56) AS body "
        "FROM record r WHERE r.turn IN (50,51) AND r.kind != 'presence' ORDER BY r.id")
    OUT["s4_links"] = w.t(
        "SELECT child, role, parent, span_from AS 'from', span_to AS 'to' FROM record_link WHERE child IN "
        f"({fp},{sp},{s1},{s2},{kz},{kr},{sk}) ORDER BY child, parent")
    OUT["s4_knowledge"] = w.t(KROW + f" WHERE k.about IN ({sp},{s2},{fp}) ORDER BY r.t_from, k.id")
    # what-if: retro-interrupt Zoltan after word 2 ("That is"): the revelation goes
    fk = w.fork()
    seeds = fk.cut_seeds(uz, 2)
    dead, stale = fk.plan_rollback(seeds)
    OUT["s4_whatif_dead"] = ", ".join(map(str, dead))
    assert sk in dead and kr in dead and kz not in dead
    # panel in the fork once the cut is applied
    fk.rollback(seeds, "interruption")
    OUT["s4_panel_whatif"] = fk.t(panel_sql, {"T": T(5, 19, 25)})
    ids_of(w, "s4")
    return w


# ======================================================================================
# Scenario 5: model-error report and regeneration
# ======================================================================================
def scenario5() -> W:
    w = W()
    for e in [("ragnar", "person", "Ragnar (player)"), ("marta", "person", "Marta, innkeeper"),
              ("place:taproom", "place", "Heron taproom")]:
        w.ent(*e)
    w.turn = 0
    for who in ("ragnar", "marta"):
        w.presence(who, "place:taproom", "room", T(7, 20))
    w.turn = 20
    p20 = w.text("player_input", "I sit by the fire and warm my hands.", T(7, 20, 30), "ragnar",
                 writer="player", name="p20")
    n20 = w.text("narration", "The fire pops. Marta wipes a mug and watches the door.", T(7, 20, 30),
                 req=[p20], name="n20")
    # the bad turn
    w.turn = 21
    t0 = T(7, 20, 40)
    p = w.text("player_input", "I ask Marta for a room for the night.", t0, "ragnar", writer="player", name="p21")
    fq = w.fact("Ragnar asked Marta for a room for the night.", t0, status="asserted", by="ragnar",
                notab=0.3, req=[(p, 1, 8)], writer="extractor", ref="ext:turn21", name="FA_room")
    n = w.text("narration", "Ragnar's hands shake with fear as he asks Marta for a room; Marta frowns.", t0,
               req=[p], name="n21")
    a = w.text("action", "Ragnar's hands shake as he asks Marta for a room.", t0, "ragnar", req=[n], name="a21")
    s = w.state("ragnar", "inner:afraid", "afraid; his hands shake", t0, category="inner", observable=1,
                req=[a], writer="extractor", ref="ext:turn21", name="S_afraid")
    w.know("marta", "The stranger is afraid; his hands are shaking.", t0, about=s, channel="witnessed",
           stance="firsthand", sal="noteworthy", req=[a], name="K_marta_afraid")
    w.know("marta", "The stranger asks me for a room for the night.", t0, about=fq, channel="told",
           source="ragnar", hops=1, name="K_marta_room")
    u = w.text("utterance", "You look frightened, stranger. I have no rooms.", t0 + 1, "marta", req=[n],
               name="U21")
    tp = w.rec("time_passes", "A short exchange.", t0, t_to=t0 + 5, req=[n], meta={"mode": "turn"},
               name="tp21")
    OUT["s5_before"] = w.t(
        "SELECT r.id, r.kind, r.writer, substr(r.body,1,60) AS body FROM v_alive r WHERE r.turn=21 ORDER BY r.id")
    # the player presses "model error" and explains
    expl = "You wrote that Ragnar is afraid. I never said that. How my character feels is mine to decide."
    c = w.rec("correction", expl, t0 + 5, logged=t0 + 5, writer="player", about=[n], tags=["player-sovereignty"],
              ext=("correction", {"target": n, "applies_to": json.dumps(["narrator", "npc", "extractor"])}),
              name="C")
    dead, stale = w.rollback([n], "model_error", by=c)
    OUT["s5_rollback"] = w.t(
        "SELECT b.record_id, r.kind, substr(r.body,1,52) AS body, b.root_id, b.by_record, b.reason FROM rollback b "
        "JOIN record r ON r.id=b.record_id ORDER BY b.record_id")
    OUT["s5_survivors"] = w.t(
        "SELECT r.id, r.kind, substr(r.body,1,60) AS body FROM v_alive r WHERE r.turn=21 ORDER BY r.id")
    # regeneration with the explanation in the prompt
    n2 = w.text("narration", "Ragnar asks Marta for a room for the night. Marta looks him up and down.", t0 + 6,
                req=[p], repl=[n], name="n21b")
    w.rec("time_passes", "A short exchange.", t0 + 6, t_to=t0 + 11, req=[n2], meta={"mode": "turn"})
    u2 = w.text("utterance", "One room left, at the back. Two crowns, paid now.", t0 + 7, "marta", req=[n2],
                repl=[u], name="U21b")
    OUT["s5_regen"] = w.t(
        "SELECT r.id, r.kind, T(r.t_from) AS in_world, substr(r.body,1,66) AS body, "
        "(SELECT group_concat(l.parent) FROM record_link l WHERE l.child=r.id AND l.role='replaces') AS replaces "
        "FROM v_alive r WHERE r.turn=21 AND r.id > %d ORDER BY r.id" % c)
    # later turn: corrections retrieved for the next narrator call
    w.turn = 23
    OUT["s5_prompt_corrections"] = w.t(
        "SELECT r.id, c.target, r.body AS 'Corrections for this campaign' FROM correction c JOIN v_alive r ON r.id=c.id "
        "WHERE c.applies_to LIKE '%narrator%' ORDER BY r.id DESC LIMIT 8")
    OUT["s5_c_alive"] = "alive" if w.alive(c) else "dead"
    OUT["s5_target_alive"] = "alive" if w.alive(n) else "dead"
    assert w.alive(p) and w.alive(fq) and w.alive(w.ids["K_marta_room"]) and w.alive(c)
    assert not w.alive(n) and not w.alive(s) and not w.alive(u) and not w.alive(tp)
    ids_of(w, "s5")
    OUT["s5_dead_n"] = str(len(dead))
    return w


def render(template: str) -> str:
    def sub(m):
        kind, key = m.group(1), m.group(2)
        if kind == "t":
            return OUT[key]
        if kind == "id":
            return str(IDS[key])
        if kind == "v":
            return OUT[key]
        if kind == "sql":
            return "```sql\n" + section(SCHEMA, key) + "\n```"
        if kind == "hsql":
            return "```sql\n" + section(HOLDER, key) + "\n```"
        if kind == "csql":
            return "```sql\n" + section(CANON, key) + "\n```"
        raise KeyError(kind)
    return re.sub(r"\{\{(t|id|v|sql|csql|hsql):([A-Za-z0-9_.]+)\}\}", sub, template)


def main() -> None:
    # the DDL must load, and canon.sql must too (it needs the envelope)
    c = new_db()
    cc = sqlite3.connect(":memory:")
    cc.executescript("CREATE TABLE entity (id TEXT PRIMARY KEY); CREATE TABLE record (id INTEGER PRIMARY KEY);\n" + CANON)
    for fn in (scenario1, scenario2, scenario3, scenario4, scenario5):
        fn()
    tpl = (ROOT / "schema.template.md").read_text()
    out = render(tpl)
    (ROOT / "schema.md").write_text(out)
    print(f"wrote {ROOT / 'schema.md'}: {len(out.splitlines())} lines")


if __name__ == "__main__":
    main()
