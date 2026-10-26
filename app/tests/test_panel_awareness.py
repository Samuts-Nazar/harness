"""The panel is the character's own view: what the character is not aware of is not a chip."""
from starlette.testclient import TestClient

from app.server import create_app
from harness.models import PLAYER, INTERNAL
from harness.state import StateChange
from test_app import make


def test_panel_chips_exclude_unaware():
    g = make()
    eng = g.eng
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "add", "тавро на спині", False, aware=False))
    c = TestClient(create_app(g))
    texts = [x["text"] for x in c.get("/api/panel").json()["chips"]]
    g._panel = g._compute_panel()
    texts = [x["text"] for x in c.get("/api/panel").json()["chips"]]
    assert "сталевий меч" in texts and not any("тавро" in t for t in texts)
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "realize", "тавро на спині", False))
    g._panel = g._compute_panel()
    assert any("тавро" in x["text"] for x in c.get("/api/panel").json()["chips"])
