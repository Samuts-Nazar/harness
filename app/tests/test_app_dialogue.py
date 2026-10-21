"""Living dialogue in the app: a quick exchange is just the speakers' lines, no narration."""
from __future__ import annotations

import tempfile

from starlette.testclient import TestClient

from app import campaigns
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack


def test_app_turn_without_narration(monkeypatch):
    monkeypatch.setattr(campaigns, "DIALOGUE", "living")
    root = tempfile.mkdtemp(prefix="harness-app-")
    stack = fake_stack()
    stack.judge.rules["director_narration"] = False
    g = Game(lambda new: campaigns.open_campaign(stack, root=root, new=new), pace=0.0)
    client = TestClient(create_app(g))
    client.post("/api/turn", json={"text": "Добрий вечір."})
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "speaker" in types and "word" in types and "turn_done" in types
    assert "narr_start" not in types and "narr_word" not in types
    assert not any(t["kind"] == "narr" for t in g.transcript)
