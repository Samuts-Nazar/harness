"""A tiny made-up canon store for the task 16 tests (no book text). Story days: the campaign starts on day 3
evening; e1-e3 are the world's past, e4-e5 are scheduled canon events."""
from __future__ import annotations

import json

from harness.canon.store import add_record, create_store

D = 1440
START = 2 * D + 19 * 60   # day 3, 19:00


def make_store(path=":memory:"):
    con = create_store(path)
    ents = [("char:bart", "person", "Барт"), ("char:mirko", "person", "Мірко"), ("char:yarosh", "person", "Ярош"),
            ("char:captain", "person", "капітан"), ("coll:guards", "collective", "стражники"),
            ("place:town", "place", "Вишня"), ("place:owl", "place", "корчма «Під Совою»"),
            ("place:hall", "place", "ратуша"), ("place:wood", "place", "старий ліс")]
    for i, t, n in ents:
        con.execute("INSERT INTO entity(id,type,name) VALUES (?,?,?)", (i, t, n))
        con.execute("INSERT INTO canon_alias VALUES (?,?)", (i, n))
    con.execute("INSERT INTO canon_alias VALUES ('char:yarosh','староста')")
    con.execute("INSERT INTO canon_alias VALUES ('char:bart','корчмар')")
    for who, role, standing, unnamed, knows in [
            ("char:bart", "tavern keeper", "respected local", 0, [{"fact": "keeps the tavern for twenty years", "basis": "text"}]),
            ("char:yarosh", "village elder", "rules the town", 0, []), ("char:mirko", "traveller", "stranger", 0, []),
            ("char:captain", "captain of the guard", "feared", 1, [])]:
        con.execute("INSERT INTO canon_character VALUES (?,?,?,?,?,?,?)", (who, f"{role} of Вишня", role, standing, json.dumps(knows), 1, unnamed))
    ev = [
        # id-key, text_en, gist_uk, t, place, day, part, loud, participants, knowers
        ("e1", "Мірко arrives at the tavern and Барт serves him ale.", "Мірко прийшов до корчми, і Барт налив йому елю.", D + 19 * 60,
         "place:owl", 1, "evening", 0.2, [("char:mirko", "actor"), ("char:bart", "speaker")],
         [("char:mirko", "witnessed", None), ("char:bart", "witnessed", None)]),
        ("e2", "A miller was found dead in the forest; the guards tell Барт.", "Мірошника знайшли мертвим у лісі, стражники розповіли Барту.", D + 23 * 60,
         "place:wood", 1, "night", 0.5, [("char:bart", "listener"), ("coll:guards", "speaker")],
         [("char:bart", "heard", "coll:guards"), ("coll:guards", "witnessed", None)]),
        ("e3", "Ярош bribes the captain of the guard to hide a debt.", "Ярош підкупив капітана, щоб приховати борг.", 2 * D + 600,
         "place:hall", 2, "morning", 0.1, [("char:yarosh", "actor"), ("char:captain", "target")],
         [("char:yarosh", "witnessed", None), ("char:captain", "witnessed", None)]),
        ("e4", "Ярош announces a curfew at the town hall.", "Ярош оголосив у ратуші комендантську годину.", 4 * D + 12 * 60,
         "place:hall", 4, "noon", 0.7, [("char:yarosh", "speaker"), ("coll:guards", "listener")],
         [("char:yarosh", "witnessed", None), ("coll:guards", "heard", "char:yarosh")]),
        ("e5", "The guards hunt the beast in the old wood at night.", "Стражники вночі полюють на звіра в старому лісі.", 6 * D + 23 * 60,
         "place:wood", 6, "night", 0.6, [("coll:guards", "actor"), ("char:captain", "speaker")],
         [("coll:guards", "witnessed", None), ("char:captain", "witnessed", None)]),
    ]
    ids = {}
    for key, en, uk, t, place, day, part, loud, parts, knowers in ev:
        rid = add_record(con, "canon_event", en, t_from=t, t_prec="hour", place=place, notability=loud)
        ids[key] = rid
        con.execute("INSERT INTO canon_event(id, ekind, loudness, order_key, when_prec, confidence, review, day, part, quote, lines, local_id, "
                    "day_to, gist_uk, kw_uk, time_conf, time_basis) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (rid, "other", loud, rid, "hour", 0.9, "ok", day, part, "", "[1]", key, day, uk, "", 0.9, "test"))
        con.execute("INSERT INTO canon_event_fts(rowid, text) VALUES (?,?)", (rid, uk + " " + en))
        for ent, role in parts:
            con.execute("INSERT INTO canon_participant VALUES (?,?,?)", (rid, ent, role))
        for ent, ch, src in knowers:
            lt = t
            con.execute("INSERT INTO canon_knower VALUES (?,?,?,?,?,?,?,?)", (rid, ent, ch, src, 0, lt, "hour", None))
    rid = add_record(con, "canon_relation", "char:captain member_of coll:guards", t_from=0)
    con.execute("INSERT INTO canon_relation VALUES (?,?,?,?,?,?)", (rid, "char:captain", "coll:guards", "member_of", None, None))
    con.commit()
    return con, ids
