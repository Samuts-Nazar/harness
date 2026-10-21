"""Living dialogue in the app: a quick exchange is just the speakers' lines, no narration; each
line is its own block, gesture-only steps show as the NPC's action; typing cuts in; a tap skips
the pace."""
from __future__ import annotations

import tempfile
import time

import pytest
from starlette.testclient import TestClient

from app import campaigns
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack
from harness.director import NEXT_TAG, SHAPE_TAG


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(pace=0.0, narration=False, floors=None, shapes=None) -> Game:
    stack = fake_stack()
    stack.judge.rules["director_narration"] = narration
    if floors:
        stack.judge.rules[NEXT_TAG] = list(floors)
    if shapes:
        stack.judge.rules[SHAPE_TAG] = list(shapes)
    root = tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: campaigns.open_campaign(stack, root=root, new=new), pace=pace)


def wait_phase(g, phase, timeout=10):
    end = time.time() + timeout
    while g.phase != phase and time.time() < end:
        time.sleep(0.005)
    assert g.phase == phase


def after(g, text):
    """Transcript entries after the player's `text`."""
    i = next(i for i, t in enumerate(g.transcript) if t.get("text") == text)
    return g.transcript[i + 1:]


def test_app_defaults_to_living_dialogue():
    assert campaigns.DIALOGUE == "living"
    assert make().eng.dialogue == "living"


def test_app_turn_without_narration():
    g = make()
    g.start_turn("Добрий вечір.")
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "speaker" in types and "word" in types and "turn_done" in types
    assert "narr_start" not in types and "narr_word" not in types
    assert not any(t["kind"] == "narr" for t in g.transcript)


def test_empty_exchange_turn_renders():
    """Nobody answers: the turn still ends cleanly (the engine narrates the silence), and no
    empty bubble or NPC block appears."""
    g = make(floors=["nobody"])
    g.start_turn("Мовчу.")
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "turn_done" in types and "error" not in types and "speaker" not in types
    assert not any(t["kind"] == "npc" for t in g.transcript)
    assert all(t["text"].strip() for t in g.transcript)
    assert g.phase == "idle"


def test_empty_narration_is_never_shown():
    g = make()
    spoken: list[str] = []
    g._stream_narration("   ", spoken, lambda: None)
    assert spoken == []
    assert not [e for e in g.events_after(0) if e["type"] in ("narr_start", "narr_word")]
    assert g.phase == "idle"


def test_each_line_of_an_exchange_is_its_own_block():
    g = make(floors=["horst", "elza", "horst", "player"])
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    evs = g.events_after(0)
    assert [e["who"] for e in evs if e["type"] == "speaker"] == ["horst", "elza", "horst"]
    npc = [t for t in g.transcript if t["kind"] == "npc"]
    assert [t["who"] for t in npc] == ["horst", "elza", "horst"]
    assert all(t["text"] for t in npc) and all(t["event"] for t in npc)
    done = next(e for e in evs if e["type"] == "turn_done")
    assert done["lines"] == [t["event"] for t in npc]


def test_gesture_step_is_shown_as_the_npcs_action_between_lines():
    g = make(floors=["horst", "elza", "horst", "player"], shapes=["normal", "gesture", "normal"])
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    kinds = [(t["kind"], t["who"]) for t in g.transcript if t["kind"] in ("npc", "npc_act")]
    assert kinds == [("npc", "horst"), ("npc_act", "elza"), ("npc", "horst")]
    act = next(t for t in g.transcript if t["kind"] == "npc_act")
    assert act["text"] and act["name"]
    order = [e["type"] for e in g.events_after(0) if e["type"] in ("speaker", "npc_act")]
    assert order == ["speaker", "npc_act", "speaker"]  # horst twice: two blocks


def test_send_during_exchange_interrupts_then_runs():
    g = make(pace=0.02, floors=["horst", "elza", "horst", "player"])
    g.start_turn("Перша.")
    wait_phase(g, "speaking")
    time.sleep(0.08)
    g.start_turn("Друга.")  # cuts in, waits for the first turn, runs the second
    g.wait_idle(30)
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша.", "Друга."]
    first = [t for t in g.transcript[:g.transcript.index(
        next(t for t in g.transcript if t.get("text") == "Друга."))] if t["kind"] == "npc"]
    assert first and first[-1].get("cut") is True
    first_line = [u for u in g.eng.log.active(["utterance"]) if u.payload["speaker"] != "player"][0]
    assert first_line.payload.get("interrupted") is True
    assert any(t["kind"] == "npc" for t in after(g, "Друга."))  # the second turn ran


def test_send_during_exchange_via_http_does_not_return_409():
    g = make(pace=0.02)
    c = TestClient(create_app(g))
    assert c.post("/api/turn", json={"text": "Перша."}).status_code == 202
    assert c.post("/api/turn", json={"text": "Друга."}).status_code == 202
    g.wait_idle(30)
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша.", "Друга."]


def test_skip_delivers_rest_without_interrupt():
    g = make(pace=0.3, floors=["horst", "elza", "player"])
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Що кажете?"})
    wait_phase(g, "speaking")
    t0 = time.time()
    assert c.post("/api/skip").status_code == 200
    g.wait_idle(30)
    assert time.time() - t0 < 3, "the rest must come at once, not at 0.3 s a word"
    evs = g.events_after(0)
    assert next(e for e in evs if e["type"] == "turn_done")["interrupted"] is False
    assert not any(t.get("cut") for t in g.transcript)
    npc = [t for t in g.transcript if t["kind"] == "npc"]
    assert [t["who"] for t in npc] == ["horst", "elza"]
    assert " ".join(e["w"] for e in evs if e["type"] == "word") == " ".join(t["text"] for t in npc)
    assert g.pace == 0
    g.start_turn("Ще.")  # the next turn is paced again
    assert g.pace == 0.3
    g.skip()
    g.wait_idle(30)


def test_skip_when_idle_is_harmless():
    g = make(pace=0.1)
    assert TestClient(create_app(g)).post("/api/skip").status_code == 200
    assert g.pace == 0.1
