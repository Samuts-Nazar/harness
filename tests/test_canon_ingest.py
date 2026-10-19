"""Canon ingestion with a fake provider and a made-up two-chapter text (no book text in the repo)."""
import json

from harness.canon import chunk
from harness.canon.ingest import Ingestor, story_minutes
from harness.canon.retrieve import Canon
from harness.providers import FakeProvider

TEXT = """title
skip

Розділ перший

Мірко прийшов до корчми «Під Совою». Корчмар Барт мовчав.

Барт розповів Мірку, що вчора у лісі знайшли мертвого мірошника.

Розділ другий

Староста наказав зачинити браму.
"""
CHAPTERS = [(4, "one"), (10, "two")]

ENT = {"entities": [
    {"id": "char:mirko", "type": "person", "name": "Мірко", "aliases": [], "who": "A traveller", "role": "hero",
     "standing": "stranger", "knows": [], "member_of": [], "first_line": 6},
    {"id": "char:bart", "type": "person", "name": "Барт", "aliases": ["корчмар"], "who": "Innkeeper",
     "role": "innkeeper", "standing": "", "knows": [{"fact": "knows the town", "basis": "inferred"}],
     "member_of": ["coll:town"], "first_line": 6},
    {"id": "coll:town", "type": "collective", "name": "містяни", "aliases": []},
    {"id": "place:owl", "type": "place", "name": "Під Совою", "aliases": []},
    {"id": "bad", "type": "person", "name": "x"}]}

W1 = {"new_entities": [], "events": [
    {"id": "e1", "what": "Мірко arrives at the tavern.", "ekind": "arrival", "loudness": 0.1, "place": "place:owl",
     "time": {"kind": "day", "day": 1, "part": "evening"}, "participants": [
         {"entity": "char:mirko", "role": "actor"}, {"entity": "char:ghost", "role": "witness"}],
     "knowers": [{"entity": "char:bart", "channel": "witnessed", "source": None, "line": 6}],
     "reactions": [{"party": "char:bart", "reaction": "ignore", "attitude": "neutral", "text": "silent"},
                   {"party": "char:bart", "reaction": "dance", "attitude": "neutral", "text": "x"}],
     "lines": [6, 99], "quote": "Мірко прийшов до корчми", "confidence": 0.9},
    {"id": "e2", "what": "A miller was found dead in the forest.", "ekind": "death", "loudness": 0.4, "place": None,
     "time": {"kind": "before", "years_before": 2}, "participants": [],
     "knowers": [{"entity": "char:bart", "channel": "heard", "source": None, "line": 8},
                 {"entity": "char:mirko", "channel": "told", "source": "char:bart", "line": 8,
                  "when": {"kind": "day", "day": 1, "part": "evening"}}],
     "reactions": [], "lines": [8], "quote": "invented words not in the text", "confidence": 0.5}]}
W2 = {"events": [{"id": "e1", "what": "The elder orders the gate shut.", "ekind": "politics", "loudness": 0.5,
                  "time": {"kind": "unknown"}, "participants": [], "knowers": [], "reactions": [],
                  "lines": [12], "quote": "зачинити браму", "confidence": 0.7}]}


def run(tmp_path, replies):
    src = tmp_path / "book.txt"
    src.write_text(TEXT, encoding="utf-8")
    m = "fake/model"
    prov = FakeProvider({m: replies})
    ing = Ingestor(prov, m, src, tmp_path / "c.db", first=4, last=12, chapters=CHAPTERS, log=lambda *_: None)
    return ing, ing.run(), prov


def test_ingest_loads_and_validates(tmp_path):
    # window 1 comes back wrapped in a code fence plus prose, window 2 first as garbage then valid
    replies = [json.dumps(ENT), "```json\n" + json.dumps(W1) + "\n```", "oops", json.dumps(W2)]
    ing, rep, prov = run(tmp_path, replies)
    assert rep["counts"]["canon_event"] == 3
    assert rep["format_failures"] == 1
    assert rep["counts"]["entity"] == 4                      # the bad id was refused
    reasons = {d["why"] for d in rep["dropped"]}
    assert {"bad id or name", "unknown entity", "not in closed vocabulary"} <= reasons
    con = Canon(tmp_path / "c.db").con
    flags = {r["id"]: json.loads(r["meta"])["flags"] for r in con.execute("SELECT id, meta FROM record WHERE kind='canon_event'")}
    assert any("quote_not_in_text" in f for f in flags.values())
    assert any(f == [] for f in flags.values())
    # story time: day 1 evening = 19h; the past is negative; unknown carries the last time forward
    ts = [r["t_from"] for r in con.execute("SELECT t_from FROM record WHERE kind='canon_event' ORDER BY id")]
    assert ts[0] == 19 * 60 and ts[1] < 0 and ts[2] == ts[0]
    # knower rows: the told chain keeps its source
    row = con.execute("SELECT * FROM canon_knower WHERE entity='char:mirko'").fetchone()
    assert row["channel"] == "told" and row["source"] == "char:bart"


def test_story_minutes():
    assert story_minutes({"kind": "day", "day": 2, "part": "dawn"}, 0)[0] == 1440 + 300
    assert story_minutes({"kind": "before", "years_before": 14}, 0)[0] == -14 * 525600
    assert story_minutes(None, 77) == (77, "unknown", None, None)


def test_windows_and_quote_norm():
    paras = [chunk.Para(i, "x" * 800, i * 801, "c") for i in range(1, 9)]
    ps = chunk.make_passages(paras, target=1400)
    assert all(len(p.paras) <= 2 for p in ps) and ps[0].line_from == 1
    assert chunk.norm("«Привіт», — сказав він.") == chunk.norm('"привіт", - сказав він')


def test_retrieval_filters_by_knowledge(tmp_path):
    replies = [json.dumps(ENT), json.dumps(W1), json.dumps(W2)]
    run(tmp_path, replies)
    canon = Canon(tmp_path / "c.db")
    bart = canon.recall("char:bart", "мірошник", as_of=10 ** 6)
    assert any("miller" in h["what"] for h in bart["events"])
    mirko_before = canon.recall("char:mirko", "мірошник", as_of=600)
    assert mirko_before["events"] == []                      # nobody told him yet
    assert canon.recall("char:mirko", "мірошник", as_of=1200)["events"][0]["source"] == "Барт"
    stranger = canon.recall("char:nobody", "мірошник", as_of=10 ** 6)
    assert stranger["events"] == []
