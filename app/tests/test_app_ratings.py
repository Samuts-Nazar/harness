"""👍/👎 on world lines: stored app-side in the campaign folder, never in the world."""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
from starlette.testclient import TestClient

import app.campaigns as campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.ratings import RatingBook
from app.server import create_app
from app.stacks import fake_stack
from app.tests.test_app import sse

HERE = Path(__file__).resolve().parent
NODE = shutil.which("node")


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def played():
    root = tempfile.mkdtemp(prefix="harness-ratings-")
    stack = fake_stack()
    g = Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0, suggestions=False)
    c = TestClient(create_app(g))
    assert c.post("/api/turn", json={"text": "Я киваю Горсту."}).status_code == 202
    sse(c)
    g.wait_idle()
    return g, c


def world(g, kind):
    return [t for t in g.transcript if t["kind"] == kind and "event" in t]


def lines(g):
    path = Path(g.camp.engine.campaign_dir) / "ratings.jsonl"
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def test_rate_stores_a_record_with_what_produced_the_line():
    g, c = played()
    npc = world(g, "npc")[0]
    r = c.post("/api/rate", json={"event": npc["event"], "kind": "npc", "rating": "down",
                                  "note": "надто сухо"})
    assert r.status_code == 200 and r.json() == {"ok": True}
    (rec,) = lines(g)
    assert rec["event"] == npc["event"] and rec["kind"] == "npc" and rec["rating"] == "down"
    assert rec["note"] == "надто сухо" and rec["text"] == npc["text"]
    assert rec["role"] == "npc" and rec["model"] == "npc"  # the fake stack's configured npc model
    assert rec["speaker"] == g.camp.tok("horst") and rec["label"] == npc["label"]
    assert rec["turn"] == npc["turn"] and rec["campaign"] and rec["time"]
    assert rec["dialogue"] in ("living", "classic") and "temperature" in rec and "prompt" in rec
    assert "horst" not in json.dumps(rec), "no real id in the record"


def test_narration_role_and_memory_book():
    g, c = played()
    narr = world(g, "narr")[0]
    assert c.post("/api/rate", json={"event": narr["event"], "kind": "narr",
                                     "rating": "up"}).status_code == 200
    (rec,) = lines(g)
    assert rec["role"] == "narrator" and rec["model"] == "narrator" and rec["speaker"] == ""
    assert rec["note"] == ""
    book = RatingBook(None)
    book.put({"event": 1, "rating": "up"})
    assert book.marks() == {"1": "up"}


def test_rating_again_replaces_and_marks_are_listed():
    g, c = played()
    npc = world(g, "npc")[0]
    narr = world(g, "narr")[0]

    def post(ev, kind, rating, note=""):
        return c.post("/api/rate", json={"event": ev, "kind": kind, "rating": rating,
                                         "note": note})
    assert post(npc["event"], "npc", "up").status_code == 200
    assert post(npc["event"], "npc", "down", "ні").status_code == 200
    assert post(narr["event"], "narr", "up").status_code == 200
    recs = lines(g)
    assert len(recs) == 2
    assert [r["rating"] for r in recs if r["event"] == npc["event"]] == ["down"]
    assert c.get("/api/ratings").json() == {str(npc["event"]): "down", str(narr["event"]): "up"}
    assert g.ratings() == c.get("/api/ratings").json()


def test_bad_requests_get_ukrainian_400_and_store_nothing():
    g, c = played()
    npc = world(g, "npc")[0]
    bad = [
        {"event": 99999, "kind": "npc", "rating": "up"},                      # unknown event
        {"event": npc["event"], "kind": "narr", "rating": "up"},              # wrong kind
        {"event": npc["event"], "kind": "npc", "rating": "meh"},              # bad rating
        {"event": "x", "kind": "npc", "rating": "up"},
        {"kind": "npc", "rating": "up"},
        {"event": npc["event"], "kind": "npc", "rating": "up", "note": "я" * 5000},
    ]
    for body in bad:
        r = c.post("/api/rate", json=body)
        assert r.status_code == 400 and r.json()["error"], body
    assert any(ord(ch) > 127 for ch in c.post("/api/rate", json=bad[0]).json()["error"])
    assert not (Path(g.camp.engine.campaign_dir) / "ratings.jsonl").exists()
    assert c.post("/api/rate", content=b"not json").status_code == 400
    # the player's own line is not rateable
    assert c.post("/api/rate", json={"event": 1, "kind": "player",
                                     "rating": "up"}).status_code == 400


def test_rating_changes_nothing_in_the_world():
    g, c = played()
    eng = g.eng
    before = ([e.id for e in eng.log.active()], list(g.transcript), g.panel())
    npc = world(g, "npc")[0]
    c.post("/api/rate", json={"event": npc["event"], "kind": "npc", "rating": "down", "note": "x"})
    after = ([e.id for e in eng.log.active()], list(g.transcript), g.panel())
    assert before == after
    assert "rating" not in json.dumps(g.state()["transcript"])


def test_fallback_model_is_recorded_when_the_engine_used_it():
    g, c = played()
    npc = world(g, "npc")[0]
    assert g._produced[npc["event"]]["model"] == "npc"
    g._produced[npc["event"]] = {"role": "npc", "model": "other/model"}
    c.post("/api/rate", json={"event": npc["event"], "kind": "npc", "rating": "up"})
    assert lines(g)[0]["model"] == "other/model"


def run(job):
    out = subprocess.run([NODE, str(HERE / "client_harness.js"),
                          str(HERE.parent / "static" / "app.js"), json.dumps(job)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_menu_offers_rating_on_world_lines_only():
    base = {"tok": "t", "event": True, "cut": False, "lastWorld": False, "lastLine": False,
            "busy": False}
    cases = [("say", ["rate_up", "rate_down"]), ("act", ["rate_up", "rate_down"]),
             ("narr", ["rate_up", "rate_down"]), ("me", []), ("intro", [])]
    expr = "[" + ",".join(
        f"sheetItems({json.dumps({**base, 'kind': k})}, []).filter(a => a.startsWith('rate'))"
        for k, _ in cases) + "]"
    assert run({"events": [], "eval": expr})["value"] == [w for _, w in cases]
    # a line the server has no id for yet cannot be rated
    got = run({"events": [], "eval": "sheetItems(%s, [])" % json.dumps(
        {**base, "kind": "say", "event": False})})
    assert "rate_up" not in got["value"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_marks_follow_the_ratings_after_a_render():
    st = {"title": "t", "live": False, "clock": "x",
          "panel": {"name": "R", "chips": [], "prose": []},
          "transcript": [{"kind": "narr", "text": "Двері рипнули.", "event": 3},
                         {"kind": "npc", "tok": "a1b2c3d4", "label": "чоловік", "text": "Ну?",
                          "event": 4}]}
    got = run({"state": st, "eval": "(applyRatings({'3': 'up', '4': 'down'}), "
                                    "[...feed.children].map(n => n.dataset.rating || ''))"})
    assert got["value"] == ["up", "down"]


def test_report_counts_per_model_and_role_and_shows_notes(tmp_path, capsys):
    from app import ratings_report

    def rec(model, role, rating, note="", label=""):
        return {"model": model, "role": role, "rating": rating, "note": note, "label": label,
                "speaker": "tok", "event": 1}
    for name, recs in {"a": [rec("m1", "npc", "up"), rec("m1", "npc", "down", "сухо", "чоловік"),
                             rec("m1", "narrator", "up")],
                       "b": [rec("m2", "npc", "down"), rec("m1", "npc", "down")]}.items():
        (tmp_path / name).mkdir()
        (tmp_path / name / "ratings.jsonl").write_text(
            "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs), encoding="utf-8")
    ratings_report.main([str(tmp_path)])
    out = capsys.readouterr().out
    row = {tuple(line.split()[:2]): line.split()[2:] for line in out.splitlines()[1:4]}
    assert row[("m1", "npc")] == ["1", "2", "67%"]
    assert row[("m1", "narrator")] == ["1", "0", "0%"]
    assert row[("m2", "npc")] == ["0", "1", "100%"]
    assert "сухо" in out and "[чоловік]" in out and "horst" not in out
    ratings_report.main([str(tmp_path / "none")])
    assert "немає" in capsys.readouterr().out
