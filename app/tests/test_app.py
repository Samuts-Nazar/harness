"""Server and session tests with the fake engine (no network).  Run: pytest app/tests"""
from __future__ import annotations

import json
import tempfile
import time

import pytest
from starlette.testclient import TestClient

from app.campaigns import open_campaign
from app.game import Game
from app.server import create_app
from app.stacks import FakeUk, fake_stack


import pytest as _pytest
import app.campaigns as _campaigns


@_pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    """App tests never read the local, uncommitted character file (data/Ragnar.md)."""
    monkeypatch.setattr(_campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(pace: float = 0.0, stack=None, root=None) -> Game:
    stack = stack or fake_stack()
    root = root or tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: open_campaign(stack, root=root, new=new), pace=pace)


def sse(client: TestClient, after: int = 0) -> list[dict]:
    out = []
    with client.stream("GET", f"/api/events?after={after}&until_idle=1") as r:
        assert r.headers["content-type"].startswith("text/event-stream")
        for line in r.iter_lines():
            if line.startswith("data:"):
                out.append(json.loads(line[5:]))
    return out


def test_turn_streams_narration_then_labelled_npc_lines(monkeypatch):
    monkeypatch.setattr(_campaigns, "DIALOGUE", "classic")  # the classic director (A/B)
    g = make()
    c = TestClient(create_app(g))
    assert c.post("/api/turn", json={"text": "Я киваю Горсту."}).status_code == 202
    evs = sse(c)
    types = [e["type"] for e in evs]
    assert types[0] == "turn_start" and types[-2:] == ["turn_done", "settled"]
    assert types.index("narr_start") < types.index("narr_end") < types.index("speaker")
    speaker = next(e for e in evs if e["type"] == "speaker")
    assert speaker["tok"] == g.camp.tok("horst") and speaker["label"] == "Горст"
    assert "who" not in speaker and "name" not in speaker
    words = [e["w"] for e in evs if e["type"] == "word"]
    assert len(words) > 20
    st = c.get("/api/state").json()
    kinds = [t["kind"] for t in st["transcript"]]
    assert kinds == ["intro", "player", "narr", "npc"]
    assert st["transcript"][3]["tok"] == g.camp.tok("horst") and not st["running"]


def test_sse_resumes_after_seq():
    g = make()
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Привіт."})
    g.wait_idle()
    all_ev = sse(c)
    mid = all_ev[5]["seq"]
    rest = sse(c, after=mid)
    assert [e["seq"] for e in rest] == [e["seq"] for e in all_ev if e["seq"] > mid]


def test_empty_rejected_and_typing_during_a_turn_interrupts_then_runs():
    g = make(pace=0.02)
    c = TestClient(create_app(g))
    assert c.post("/api/turn", json={"text": "  "}).status_code == 400
    assert c.post("/api/turn", json={"text": "Один."}).status_code == 202
    assert c.post("/api/turn", json={"text": "Два."}).status_code == 202  # cuts in, then runs
    g.wait_idle()
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Один.", "Два."]
    assert c.post("/api/turn", json={"text": "Три."}).status_code == 202
    g.wait_idle()


def test_interrupt_during_speech_cuts_and_keeps_private_intent():
    g = make(pace=0.02)
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Що сталося на млині?"})
    deadline = time.time() + 10
    while g.phase != "speaking" and time.time() < deadline:
        time.sleep(0.01)
    assert g.phase == "speaking"
    time.sleep(0.1)
    assert c.post("/api/interrupt").json() == {"interrupted": "speech"}
    g.wait_idle()
    evs = g.events_after(0)
    done = next(e for e in evs if e["type"] == "turn_done")
    assert done["interrupted"] is True
    spoken = [e["w"] for e in evs if e["type"] == "word"]
    full = len(g.eng.intents.pending("horst")[0].payload["text"].split()) + len(spoken)
    assert 0 < len(spoken) < full           # the cut remainder is the NPC's private intent
    last = g.transcript[-1]
    assert last["cut"] is True and last["text"] == " ".join(spoken)


def test_interrupt_during_narration_cuts_narration_only():
    g = make(pace=0.02)
    g.start_turn("Дивлюсь навколо.")
    deadline = time.time() + 10
    while g.phase != "narrating" and time.time() < deadline:
        time.sleep(0.005)
    assert g.interrupt() == "narration"
    g.wait_idle()
    end = next(e for e in g.events_after(0) if e["type"] == "narr_end")
    assert end["cut"] is True
    assert g.transcript[-1]["kind"] == "npc"      # speech still follows


def test_interrupt_when_idle_is_noop():
    g = make()
    assert TestClient(create_app(g)).post("/api/interrupt").json() == {"interrupted": "none"}


def test_panel_is_the_characters_own_view():
    g = make()
    c = TestClient(create_app(g))
    p = c.get("/api/panel").json()
    chips = {x["text"]: x["observable"] for x in p["chips"]}
    assert chips == {"сталевий меч": True, "старий шрам під сорочкою": False}
    assert p["name"] == "Рагнар" and p["prose"]
    # Горст knows the hidden scar? No: only the character's own derived view is shown, and the
    # NPC-only canon fact never reaches the player's prose
    assert not any("Відьмаки полюють" in s for s in p["prose"])
    c.post("/api/turn", json={"text": "Кажу щось."})
    g.wait_idle()
    after = c.get("/api/panel").json()
    assert {x["text"] for x in after["chips"]} >= {"сталевий меч", "насторожений"}


def test_debug_view_has_events_judgments_calls_with_cost_and_latency():
    g = make()
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Привіт."})
    g.wait_idle()
    d = c.get("/api/debug").json()
    assert {x["role"].split(":")[0] for x in d["calls"]} >= {"narrator", "npc", "extractor"}
    assert all("seconds" in x and "cost" in x for x in d["calls"])
    assert {"first_word_s", "total_s"} <= set(d["timing"])
    assert [e["type"] for e in d["events"]][:2] == ["utterance", "narration"]
    assert d["judgments"], "output checks are judgments and must be logged"


class Failing(FakeUk):
    def __init__(self) -> None:
        super().__init__()
        self.fail = True

    def complete(self, model, messages):
        if self.fail and "narrator" in messages[0]["content"]:
            raise RuntimeError("provider down")
        return super().complete(model, messages)


def test_model_failure_reports_error_keeps_input_and_world_unchanged():
    stack = fake_stack()
    stack.provider = Failing()
    g = make(stack=stack)
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Мій хід."})
    g.wait_idle()
    err = next(e for e in g.events_after(0) if e["type"] == "error")
    assert err["text"] == "Мій хід." and "RuntimeError" in err["message"]
    assert g.transcript == [g.transcript[0]]                  # nothing was committed
    assert g.eng.log.active(["utterance"]) == []              # rolled back by the engine
    assert not c.get("/api/state").json()["running"]
    stack.provider.fail = False                               # the retry with the same text works
    c.post("/api/turn", json={"text": "Мій хід."})
    g.wait_idle()
    assert g.transcript[-1]["kind"] == "npc"


def test_world_pauses_while_app_is_in_background():
    g = make(pace=0.01)
    c = TestClient(create_app(g))
    c.post("/api/presence", json={"visible": False})
    g.start_turn("Чекаю.")
    time.sleep(0.4)
    assert not any(e["type"] in ("narr_word", "word") for e in g.events_after(0))
    c.post("/api/presence", json={"visible": True})
    g.wait_idle()
    assert any(e["type"] == "word" for e in g.events_after(0))


def test_new_campaign_resets_and_refuses_during_turn():
    g = make(pace=0.02)
    c = TestClient(create_app(g))
    g.start_turn("Раз.")
    assert c.post("/api/campaign/new").status_code == 409
    g.interrupt()
    g.wait_idle()
    st = c.post("/api/campaign/new").json()
    assert [t["kind"] for t in st["transcript"]] == ["intro"]


def test_index_and_static_served():
    c = TestClient(create_app(make()))
    assert "text/html" in c.get("/").headers["content-type"]
    assert c.get("/static/app.js").status_code == 200
