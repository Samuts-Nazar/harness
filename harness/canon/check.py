"""Mechanical checks and a readable dump of a canon store, for the review of every record.

    python -m harness.canon.check <db> [--dump]
"""
from __future__ import annotations

import argparse
import difflib
import json
import sqlite3
from typing import Any


def _con(path: str) -> sqlite3.Connection:
    c = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


def events(con: sqlite3.Connection) -> list[dict[str, Any]]:
    out = []
    for r in con.execute("SELECT r.id, r.body, r.t_from, r.t_prec, r.place, r.meta, c.* FROM record r "
                         "JOIN canon_event c ON c.id=r.id ORDER BY c.order_key"):
        e = dict(r)
        e["flags"] = json.loads(e.pop("meta")).get("flags", [])
        e["lines"] = json.loads(e["lines"])
        e["parts"] = [(p["entity"], p["role"]) for p in con.execute(
            "SELECT entity, role FROM canon_participant WHERE event_id=?", (e["id"],))]
        e["knowers"] = [dict(k) for k in con.execute("SELECT * FROM canon_knower WHERE event_id=?", (e["id"],))]
        e["reactions"] = [(x["party"], x["reaction"], x["attitude"], x["body"]) for x in con.execute(
            "SELECT r.party, r.reaction, r.attitude, rec.body FROM canon_reaction r JOIN record rec ON rec.id=r.id "
            "WHERE r.event_id=?", (e["id"],))]
        out.append(e)
    return out


def checks(path: str) -> dict[str, Any]:
    con = _con(path)
    evs = events(con)
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM entity")}
    res: dict[str, Any] = {"events": len(evs)}
    flag_counts: dict[str, int] = {}
    for e in evs:
        for f in e["flags"]:
            flag_counts[f] = flag_counts.get(f, 0) + 1
    res["flags"] = flag_counts
    res["no_knowers"] = sum(1 for e in evs if not e["knowers"])
    res["no_participants"] = sum(1 for e in evs if not e["parts"])
    # a participant in a present-role who is not a knower
    pn = 0
    for e in evs:
        ks = {k["entity"] for k in e["knowers"]}
        pn += sum(1 for ent, role in e["parts"] if role in ("actor", "target", "victim", "speaker", "listener", "witness")
                  and ent not in ks and ent.split(":")[0] in ("char",))
    res["participant_not_knower"] = pn
    # "witnessed" by someone who is not a participant
    wn = 0
    for e in evs:
        ps = {p[0] for p in e["parts"]}
        wn += sum(1 for k in e["knowers"] if k["channel"] == "witnessed" and k["entity"] not in ps)
    res["witnessed_not_participant"] = wn
    # told without a source
    res["told_no_source"] = sum(1 for e in evs for k in e["knowers"] if k["channel"] == "told" and not k["source"])
    # story time going backwards among 'day' events (backstory events are negative and skipped)
    back = 0
    last = None
    for e in evs:
        if e["day"] is None:
            continue
        if last is not None and e["t_from"] < last:
            back += 1
        last = e["t_from"]
    res["day_time_goes_back"] = back
    # near-duplicate events
    dup = 0
    for i, a in enumerate(evs):
        for b in evs[i + 1:i + 8]:
            if difflib.SequenceMatcher(None, a["body"].lower(), b["body"].lower()).ratio() > 0.75:
                dup += 1
    res["near_duplicates"] = dup
    # duplicate entity names
    seen: dict[str, list[str]] = {}
    for eid, n in names.items():
        seen.setdefault(n.lower(), []).append(eid)
    res["same_name_entities"] = {n: ids for n, ids in seen.items() if len(ids) > 1}
    res["reactions"] = con.execute("SELECT COUNT(*) FROM canon_reaction").fetchone()[0]
    res["knower_rows"] = con.execute("SELECT COUNT(*) FROM canon_knower").fetchone()[0]
    return res


def dump(path: str) -> str:
    con = _con(path)
    names = {r["id"]: r["name"] for r in con.execute("SELECT id, name FROM entity")}
    n = lambda i: names.get(i, i or "-")  # noqa: E731
    lines = []
    for e in events(con):
        t = f"d{e['day']}{('/' + e['part']) if e['part'] else ''}" if e["day"] else \
            (f"{e['t_from'] / 525600:.0f}y" if e["t_from"] < 0 else "?")
        lines.append(f"#{e['order_key']} L{e['lines']} {t} {e['ekind']} loud={e['loudness']} @{n(e['place'])} "
                     f"{'FLAGS=' + ','.join(e['flags']) if e['flags'] else ''}")
        lines.append(f"   {e['body']}")
        lines.append("   who: " + ", ".join(f"{n(a)}:{b}" for a, b in e["parts"]))
        lines.append("   knows: " + ", ".join(
            f"{n(k['entity'])}({k['channel']}{'<' + n(k['source']) if k['source'] else ''}"
            f"{'@' + str(k['learned_t']) if k['learned_t'] != e['t_from'] else ''})" for k in e["knowers"]))
        for p, r, a, t_ in e["reactions"]:
            lines.append(f"   react: {n(p)} -> {r}/{a}: {t_[:80]}")
        lines.append(f"   q: {e['quote']}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("db")
    ap.add_argument("--dump", action="store_true")
    a = ap.parse_args()
    print(json.dumps(checks(a.db), ensure_ascii=False, indent=1))
    if a.dump:
        print(dump(a.db))


if __name__ == "__main__":
    main()
