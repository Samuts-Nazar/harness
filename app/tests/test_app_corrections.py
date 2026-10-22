"""Task 4: «Помилка моделі» and the retroactive cut over HTTP. Fake stack, no network."""
from __future__ import annotations

import tempfile

import pytest
from starlette.testclient import TestClient

import app.campaigns as campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack
from harness.director import NEXT_TAG, SHAPE_TAG
from harness.models import CORRECTION, NARRATION, UTTERANCE


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(floors=("horst", "player"), narration=False, shapes=None):
    stack = fake_stack()
    stack.judge.rules["director_narration"] = narration
    if shapes:
        stack.judge.rules[SHAPE_TAG] = list(shapes)
    stack.judge.rules[NEXT_TAG] = list(floors)
    root = tempfile.mkdtemp(prefix="harness-app-corr-")
    g = Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0, suggestions=False)
    g.root = root
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    return g, TestClient(create_app(g)), stack


def last(g, kind):
    return dict([t for t in g.transcript if t["kind"] == kind][-1])  # a snapshot


def test_model_error_on_the_last_npc_line_rewrites_it_and_stores_the_note():
    g, c, stack = make()
    line = last(g, "npc")
    players = [t for t in g.transcript if t["kind"] == "player"]
    r = c.post("/api/model_error", json={"event": line["event"], "explanation": "він грубіянить"})
    assert r.status_code == 200, r.text
    new = last(g, "npc")
    assert new["event"] != line["event"]
    assert [t for t in g.transcript if t["kind"] == "player"] == players   # the turn stays
    notes = g.eng.log.active([CORRECTION])
    assert notes and notes[-1].payload["explanation"] == "він грубіянить"
    assert not g.eng.log.is_active(line["event"])
    assert any("він грубіянить" in x for x in g.eng.ctx.corrections("horst"))


def test_model_error_on_the_last_gesture_regenerates_it_and_survives_a_reload():
    g, c, stack = make(floors=("horst", "elza", "player"), shapes=("normal", "gesture"))
    act = last(g, "npc_act")
    assert last_kind(g) == "npc_act" and act["event"]
    players = [t for t in g.transcript if t["kind"] == "player"]
    r = c.post("/api/model_error", json={"event": act["event"], "explanation": "надто театрально"})
    assert r.status_code == 200, r.text
    new = last(g, "npc_act")
    assert new["event"] != act["event"] and new["text"] and new["tok"] == act["tok"]
    assert [t for t in g.transcript if t["kind"] == "player"] == players
    assert not g.eng.log.is_active(act["event"])
    ev = g.eng.log.get(new["event"])
    assert ev.payload["gesture"] and ev.payload["by"] == "elza" and ev.payload["regenerated"]
    assert g.eng.last_world_output().id == new["event"]
    assert g.eng.log.active([CORRECTION])[-1].payload["explanation"] == "надто театрально"
    assert any("надто театрально" in x for x in g.eng.ctx.corrections("elza"))
    assert g.state()["transcript"][-1]["event"] == new["event"]
    reloaded = campaigns.open_campaign(stack, root=g.root, new=False).transcript()
    assert [t for t in reloaded if t["kind"] == "npc_act"][-1]["text"] == new["text"]


def test_model_error_on_an_older_gesture_is_refused():
    g, c, _ = make(floors=("horst", "elza", "horst", "player"),
                   shapes=("normal", "gesture", "normal"))
    act = last(g, "npc_act")
    assert last_kind(g) == "npc"
    r = c.post("/api/model_error", json={"event": act["event"], "explanation": "не так"})
    assert r.status_code == 400 and g.eng.log.is_active(act["event"])


def test_model_error_on_narration_rewrites_it_and_feeds_the_narrator():
    g, c, stack = make(floors=("player",))        # a turn with narration only
    old = last(g, "narr")
    assert old.get("event") and last_kind(g) == "narr"
    r = c.post("/api/model_error", json={"event": None, "explanation": "дощу не було"})
    assert r.status_code == 200, r.text
    new = last(g, "narr")
    assert new["event"] != old["event"] and new["text"]
    assert not g.eng.log.is_active(old["event"])
    assert g.eng.log.get(new["event"]).type == NARRATION
    seen = [m for _, m in stack.provider.calls if "narrator" in m[0]["content"]][-1]
    assert "дощу не було" in seen[-1]["content"]
    g.start_turn("Дивлюсь далі.")
    g.wait_idle(20)
    seen = [m for _, m in stack.provider.calls if "narrator" in m[0]["content"]][-1]
    assert "дощу не було" in "\n".join(x["content"] for x in seen)
    assert not any("дощу не було" in x for x in g.eng.ctx.corrections("horst"))


def last_kind(g):
    return [t["kind"] for t in g.transcript if t["kind"] in ("narr", "npc", "npc_act")][-1]


def test_model_error_only_on_the_last_world_output(monkeypatch):
    monkeypatch.setattr(campaigns, "DIALOGUE", "classic")   # narration, then NPC lines
    g, c, _ = make()
    kinds = [t["kind"] for t in g.transcript]
    assert "narr" in kinds and last_kind(g) == "npc", kinds
    before = [dict(t) for t in g.transcript]
    narr = last(g, "narr")
    for ev in (None, narr["event"]):      # the narration is not the last output any more
        r = c.post("/api/model_error", json={"event": ev, "explanation": "не так"})
        assert r.status_code == 400
        assert ("event" if ev is None else "останньому") in r.json()["error"]
    assert g.transcript == before and not g.eng.log.active([CORRECTION])
    # an older NPC line too
    g.start_turn("Ще одне.")
    g.wait_idle(20)
    old_line = before[-1]
    r = c.post("/api/model_error", json={"event": old_line["event"], "explanation": "не так"})
    assert r.status_code == 400 and not g.eng.log.active([CORRECTION])


def test_model_error_needs_an_explanation_and_is_refused_while_a_turn_runs():
    g, c, _ = make()
    line = last(g, "npc")
    assert c.post("/api/model_error", json={"event": line["event"], "explanation": "  "}
                  ).status_code == 400
    assert c.post("/api/model_error", json={"event": 999999, "explanation": "x"}
                  ).status_code == 400
    g.challenging = True
    assert c.post("/api/model_error", json={"event": None, "explanation": "x"}
                  ).status_code == 409
    g.challenging = False


def test_cut_truncates_the_last_npc_line_and_keeps_the_rest_as_a_private_intent():
    g, c, _ = make()
    line = last(g, "npc")
    words = line["text"].split()
    assert len(words) > 4
    r = c.post("/api/cut", json={"event": line["event"], "after_words": 3})
    assert r.status_code == 200, r.text
    new = last(g, "npc")
    assert new["text"] == " ".join(words[:3]) and new["cut"] is True
    assert new["event"] != line["event"]
    assert not g.eng.log.is_active(line["event"])
    pend = g.eng.intents.pending("horst")
    assert pend and pend[-1].payload["text"].split()[:2] == words[3:5]
    # only once
    assert c.post("/api/cut", json={"event": new["event"], "after_words": 1}).status_code == 400


def test_cut_refuses_an_old_line_a_bad_index_and_missing_fields():
    g, c, _ = make()
    line = last(g, "npc")
    n = len(line["text"].split())
    assert c.post("/api/cut", json={"event": line["event"], "after_words": n}).status_code == 400
    assert c.post("/api/cut", json={"event": line["event"], "after_words": 0}).status_code == 400
    assert c.post("/api/cut", json={"event": line["event"]}).status_code == 400
    g.start_turn("Ще одне.")
    g.wait_idle(20)
    assert c.post("/api/cut", json={"event": line["event"], "after_words": 2}).status_code == 400
