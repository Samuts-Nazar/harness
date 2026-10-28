"""Canon ingestion from JSON files written by Claude Code subagents (no model, no network).

Invented source text and invented JSON only: no book text in the repo."""
import json
import sys

import pytest

from harness.canon import extract, ingest
from harness.canon.retrieve import Canon

TEXT = """заголовок
пропуск
Частина перша
Олеся прийшла до млина на світанку. Мірошник Тарас відчинив їй двері.
Тарас сказав Олесі, що минулої зими вовки забрали трьох овець.

Частина друга
Олеся вирушила до міста Лугова з листом для старости.
Староста прочитав лист і наказав виставити варту.
кінець
"""
# lines 3..9 form the arc (6 is empty); chapters start at lines 3 and 7
LINES, CHAPTERS = "3-9", "3:Перша,7:Друга"

ENT = {"entities": [
    {"id": "char:olesia", "type": "person", "name": "Олеся", "aliases": [], "who": "A young woman", "role": "messenger",
     "standing": "", "knows": [], "member_of": [], "first_line": 4},
    {"id": "char:taras", "type": "person", "name": "Тарас", "aliases": ["мірошник"], "who": "The miller",
     "role": "host", "standing": "", "knows": [], "member_of": [], "first_line": 4},
    {"id": "place:mill", "type": "place", "name": "млин", "aliases": []},
    {"id": "olesia", "type": "person", "name": "no prefix"},                      # dropped: bad id
]}
# window 1: lines 3-5
W1 = {"new_entities": [], "events": [
    {"id": "e1", "what": "Олеся arrives at the mill and Тарас lets her in.", "ekind": "arrival", "loudness": 0.1,
     "place": "place:mill", "time": {"kind": "day", "day": 1, "part": "dawn"},
     "participants": [{"entity": "char:olesia", "role": "actor"}, {"entity": "char:taras", "role": "actor"}],
     "knowers": [{"entity": "char:olesia", "channel": "witnessed", "source": None, "line": 4},
                 {"entity": "char:taras", "channel": "saw_it", "source": None, "line": 4}],     # dropped: channel
     "reactions": [{"party": "char:taras", "reaction": "welcome", "attitude": "positive", "text": "x"}],  # dropped
     "lines": [4], "quote": "Олеся прийшла до млина на світанку", "confidence": 0.9},
    {"id": "e2", "what": "Wolves took three sheep last winter.", "ekind": "monster", "loudness": 0.3, "place": None,
     "time": {"kind": "before", "years_before": 0.5},
     "participants": [{"entity": "creature:wolves", "role": "actor"}],                         # dropped: unknown
     "knowers": [{"entity": "char:taras", "channel": "witnessed", "source": None, "line": 5},
                 {"entity": "char:olesia", "channel": "told", "source": "char:taras", "line": 5}],
     "reactions": [], "lines": [5], "quote": "вовки забрали дванадцять корів", "confidence": 0.6},  # flagged: quote
]}
# window 2: lines 6-9
W2 = {"new_entities": [{"id": "char:starosta", "type": "person", "name": "староста", "aliases": [], "unnamed": True},
                       {"id": "place:luhiv", "type": "place", "name": "Лугів", "aliases": ["Лугова"]}],
      "events": [
    {"id": "e1", "what": "Олеся travels to Лугів with a letter.", "ekind": "pilgrimage", "loudness": 0.1,  # flagged: ekind
     "place": "place:luhiv", "time": {"kind": "day", "day": 2, "part": "unknown"},
     "participants": [{"entity": "char:olesia", "role": "actor"}],
     "knowers": [{"entity": "char:olesia", "channel": "witnessed", "source": None, "line": 8}],
     "reactions": [], "lines": [77], "quote": "вирушила до міста Лугова", "confidence": 0.8},          # flagged: lines
    {"id": "e2", "what": "The elder reads the letter and orders a watch.", "ekind": "politics", "loudness": 0.4,
     "place": "place:luhiv", "time": {"kind": "day", "day": 2, "part": "unknown"},
     "participants": [{"entity": "char:starosta", "role": "actor"}],
     "knowers": [{"entity": "char:starosta", "channel": "witnessed", "source": None, "line": 9}],
     "reactions": [{"party": "char:olesia", "reaction": "comply", "attitude": "neutral", "text": "waits"}],
     "lines": [9], "quote": "наказав виставити варту", "confidence": 0.8},
]}


def _no_model(*a, **k):
    raise AssertionError("a model or provider was touched in --from-json mode")


def test_from_json_loads_valid_and_counts_dropped(tmp_path, monkeypatch, capsys):
    src = tmp_path / "book.txt"
    src.write_text(TEXT, encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "entities.json").write_text(json.dumps(ENT, ensure_ascii=False), encoding="utf-8")
    (raw / "window_3-5.json").write_text(json.dumps(W1, ensure_ascii=False), encoding="utf-8")
    (raw / "window_6-9.json").write_text(json.dumps(W2, ensure_ascii=False), encoding="utf-8")
    (raw / "window_10-12.json").write_text("{not json", encoding="utf-8")       # invalid: counted, no crash
    monkeypatch.setattr(ingest, "OpenRouterProvider", _no_model)
    monkeypatch.setattr(extract, "ask_json", _no_model)
    out = tmp_path / "be.db"
    monkeypatch.setattr(sys, "argv", ["ingest", "--source", str(src), "--lines", LINES, "--chapters", CHAPTERS,
                                      "--from-json", str(raw), "--out", str(out)])
    ingest.main()
    rep = json.loads(capsys.readouterr().out.strip().splitlines()[-1])

    assert rep["cost_usd"] == 0 and rep["calls"] == 0
    assert rep["counts"]["canon_event"] == 4
    assert rep["counts"]["entity"] == 5                       # 3 valid + 2 new_entities; "olesia" refused
    assert rep["counts"]["canon_knower"] == 5                 # one bad channel refused
    assert rep["counts"]["canon_reaction"] == 1               # "welcome" is not in the closed list
    assert rep["counts"]["canon_participant"] == 4            # creature:wolves is unknown
    assert rep["dropped_by_reason"] == {"entity: bad id or name": 1, "knower: bad channel": 1,
                                        "reaction: not in closed vocabulary": 1,
                                        "participant: unknown entity": 1, "file: invalid json": 1}
    assert rep["flagged"] == {"quote_not_in_text": 1, "bad_ekind": 1, "no_valid_lines": 1}
    assert rep["json_files"]["read"] == 3 and rep["json_files"]["invalid"] == ["window_10-12.json"]
    assert rep["json_files"]["missing"] == []

    con = Canon(out).con
    src_row = con.execute("SELECT * FROM canon_passage").fetchone()
    assert src_row["line_from"] >= 3
    chapters = {r[0] for r in con.execute("SELECT chapter FROM canon_passage")}
    assert chapters == {"Перша", "Друга"}
    told = con.execute("SELECT * FROM canon_knower WHERE entity='char:olesia' AND channel='told'").fetchone()
    assert told["source"] == "char:taras"


def test_from_json_reports_missing_files(tmp_path, monkeypatch):
    src = tmp_path / "book.txt"
    src.write_text(TEXT, encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "window_3-5.json").write_text(json.dumps(W1, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(extract, "ask_json", _no_model)
    ing = ingest.Ingestor(None, "subagent-json", src, tmp_path / "x.db", first=3, last=9,
                          chapters=[(3, "Перша"), (7, "Друга")], json_dir=raw, log=lambda *_: None)
    rep = ing.run()
    assert rep["json_files"]["missing"] == ["entities*.json"]
    assert rep["json_files"]["uncovered_lines"] == ["7-9"]
    # without entities every participant and knower is unknown, but events still load
    assert rep["counts"]["canon_event"] == 2


def test_parse_lines_and_chapters():
    assert ingest.parse_lines("15505-22101") == (15505, 22101)
    assert ingest.parse_chapters("15505:Кров, 16000:Розділ 2") == [(15505, "Кров"), (16000, "Розділ 2")]
    with pytest.raises(ValueError):
        ingest.parse_lines("9-3")


def test_from_json_wrong_field_types_count_as_invalid(tmp_path, monkeypatch):
    src = tmp_path / "book.txt"
    src.write_text(TEXT, encoding="utf-8")
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "entities.json").write_text(json.dumps({"entities": 5}), encoding="utf-8")
    (raw / "entities_3-5.json").write_text(json.dumps(ENT, ensure_ascii=False), encoding="utf-8")
    (raw / "window_3-5.json").write_text(json.dumps({"new_entities": [], "events": {}}), encoding="utf-8")
    (raw / "window_6-9.json").write_text(json.dumps({"new_entities": "x", "events": []}), encoding="utf-8")
    (raw / "window_10-12.json").write_text(json.dumps([1, 2]), encoding="utf-8")   # not an object
    (raw / "timeline.json").write_text(json.dumps({"scenes": "nope"}), encoding="utf-8")
    monkeypatch.setattr(extract, "ask_json", _no_model)
    ing = ingest.Ingestor(None, "subagent-json", src, tmp_path / "x.db", first=3, last=9,
                          chapters=[(3, "Перша"), (7, "Друга")], json_dir=raw, v2=True, log=lambda *_: None)
    rep = ing.run()
    assert sorted(rep["json_files"]["invalid"]) == ["entities.json", "timeline.json", "window_10-12.json",
                                                    "window_3-5.json", "window_6-9.json"]
    assert rep["json_files"]["read"] == 1
    assert rep["dropped_by_reason"]["file: invalid json"] == 5
    assert rep["counts"]["entity"] == 3 and rep["counts"]["canon_event"] == 0
