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
5. Geralt's letter to Yennefer (468) and her reply (469, with Geralt's reaction 470) were stamped after
   her arrival at the temple (`before` 0.2, -105120) though the letter is what sends her there. They
   are moved before it: the letter `before` 0.25 (-131400), read by Yennefer at `before` 0.24 (-126144); the
   reply and her departure `before` 0.23 (-120888). Geralt still reads the reply on day 1 (540). The
   "about a month earlier" of 468 (relative to Geralt's day 1) no longer holds and is dropped from its
   `what` and `gist_uk`. The same times go into raw_be/window_19009-19408.json and raw_be/gists.json.
6. Start-phase roles. The store's `role` of Yennefer ("Ciri's teacher and guardian"), of Ciri
   ("studying with Nenneke and Yennefer") and Nenneke's `standing` ("defends Ciri against Yennefer's
   harshness") describe the end of the temple stay; the only start on this
   store (`ellander_road`) is the day Yennefer arrives, before any teaching. They now read as of that
   day, in `canon_character` and in raw_be/entities.json.

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
LETTER_T, LETTER_READ_T, REPLY_T, GERALT_READS_T = -131400, -126144, -120888, 540
LETTER_WHAT = ("Before Йеннефер came to the temple, Ґеральт wrote to her, asking for her help with the "
               "problem he had received from Fate (Цірі) and showing concern for her health.")
LETTER_GIST = ("Ще до приїзду Йеннефер до храму Ґеральт написав їй, просячи допомоги з проблемою, яку "
               "дала йому Доля (Цірі), і турбуючись про її здоров'я.")
ROLES = {  # (entity, profile field) -> its text as of the day Yennefer arrives
    ("char:yennefer", "role"): "sorceress, asked by Geralt to examine Ciri; riding to the temple of "
                               "Melitele, she has not met Ciri yet",
    ("char:ciri", "role"): "girl at the temple of Melitele, an adept under Nenneke",
    ("char:nenneke", "standing"): "Respected head of the temple; keeps Ciri safe and her identity secret",
}


def fix_raw_letter(raw: Path) -> int:
    """The letter and reply times (and the letter's text) in the ingest's window and gists files,
    as text replacements that keep each file's own layout (idempotent). Returns how many changed."""
    n = 0
    old_what = ("About a month earlier Ґеральт wrote to Йеннефер, asking for her help with the problem "
                "he had received from Fate (Цірі) and showing concern for her health.")
    win = raw / "window_19009-19408.json"
    if win.is_file():
        t = win.read_text(encoding="utf-8")
        t0 = t
        e5 = t.find('{"id": "e5", "what": ')
        e6 = t.find('{"id": "e6", "what": ')
        e7 = t.find('{"id": "e7", "what": ')
        if 0 <= e5 < e6 < e7:
            five, six = t[e5:e6], t[e6:e7]
            five = five.replace(old_what, LETTER_WHAT).replace(
                '"time": {"kind": "before", "years_before": 0.08}',
                '"time": {"kind": "before", "years_before": 0.25}').replace(
                '"char:yennefer", "channel": "read", "source": "char:geralt", "line": 19097, "when": null}',
                '"char:yennefer", "channel": "read", "source": "char:geralt", "line": 19097, '
                '"when": {"kind": "before", "years_before": 0.24}}')
            six = six.replace('"time": {"kind": "before", "years_before": 0.03}',
                              '"time": {"kind": "before", "years_before": 0.23}')
            t = t[:e5] + five + six + t[e7:]
        if t != t0:
            json.loads(t)  # still valid
            win.write_text(t, encoding="utf-8")
            n += 1
    gists = raw / "gists.json"
    if gists.is_file():
        t = gists.read_text(encoding="utf-8")
        g = json.loads(t)
        if g.get("468") not in (None, LETTER_GIST):
            t = t.replace(json.dumps(g["468"], ensure_ascii=False), json.dumps(LETTER_GIST, ensure_ascii=False))
            assert json.loads(t)["468"] == LETTER_GIST
            gists.write_text(t, encoding="utf-8")
            n += 1
    return n


def fix_raw_roles(path: Path) -> int:
    """The start-phase roles in an ingest's entities.json (idempotent). Returns how many."""
    if not path.is_file():
        return 0
    data = json.loads(path.read_text(encoding="utf-8"))
    n = 0
    for ent in data.get("entities", []):
        for (eid, key), text in ROLES.items():
            if ent.get("id") == eid and ent.get(key) != text:
                ent[key] = text
                n += 1
    if n:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    return n


def fix_letter(con) -> int:
    """Step 5 in the store (idempotent). Returns how many rows changed."""
    n = 0
    for rid, t in ((468, LETTER_T), (469, REPLY_T), (470, REPLY_T)):
        n += con.execute("UPDATE record SET t_from=? WHERE id=? AND t_from<>?", (t, rid, t)).rowcount
    n += con.execute("UPDATE record SET body=? WHERE id=468 AND body<>?", (LETTER_WHAT, LETTER_WHAT)).rowcount
    n += con.execute("UPDATE canon_event SET gist_uk=? WHERE id=468 AND gist_uk<>?",
                     (LETTER_GIST, LETTER_GIST)).rowcount
    rows = (  # (event, knower, learned_t)
        (468, "char:geralt", LETTER_T), (468, "char:yennefer", LETTER_READ_T),
        (469, "char:yennefer", REPLY_T), (469, "char:geralt", GERALT_READS_T))
    for eid, ent, lt in rows:
        ev_t = LETTER_T if eid == 468 else REPLY_T
        n += con.execute("UPDATE canon_knower SET learned_t=?, delay_minutes=? WHERE event_id=? AND entity=? "
                         "AND (learned_t<>? OR delay_minutes<>?)",
                         (lt, lt - ev_t, eid, ent, lt, lt - ev_t)).rowcount
    return n


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
    n_letter = fix_letter(con)
    n_roles = 0
    for (ent, key), text in ROLES.items():  # key: a fixed column name of canon_character
        n_roles += con.execute(f"UPDATE canon_character SET {key}=? WHERE entity=? AND {key}<>?",
                               (text, ent, text)).rowcount
    con.commit()
    ref.rebuild_fts()
    out = {"place_fixed": n_place, "learned_fixed": n_learned, "alias_removed": n_alias,
           "raw_alias_removed": fix_raw_entities(db.parent / "raw_be" / "entities.json"),
           "letter_fixed": n_letter, "raw_letter_fixed": fix_raw_letter(db.parent / "raw_be"),
           "roles_fixed": n_roles, "raw_roles_fixed": fix_raw_roles(db.parent / "raw_be" / "entities.json")}
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
