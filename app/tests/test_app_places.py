"""Task 4 in the app: places for the drawer, the actions the server offers, turn ids on the
transcript. Fake stack, no network."""
from __future__ import annotations

import tempfile

import pytest
from starlette.testclient import TestClient

import app.campaigns as campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack
from app.vizima import open_vizima


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def test_places_from_vizima_world_and_empty_without_world():
    stack = fake_stack()
    root = tempfile.mkdtemp(prefix="harness-app-places-")
    g = Game(lambda new: open_vizima(stack, root=root, new=new, canon_db=False), pace=0.0)
    c = TestClient(create_app(g))
    places = c.get("/api/places").json()
    assert places and all(set(p) == {"name", "minutes"} for p in places)
    names = [p["name"] for p in places]
    assert "ринок" in names and "брама" in names
    assert g.eng.scene.location not in names          # where the player is now is not offered
    assert [p["minutes"] for p in places] == sorted(p["minutes"] for p in places)
    market = next(p for p in places if p["name"] == "ринок")
    assert market["minutes"] == 10 and all(isinstance(p["minutes"], int) for p in places)

    plain = Game(lambda new: open_campaign(fake_stack(), root=tempfile.mkdtemp(), new=new),
                 pace=0.0)
    assert TestClient(create_app(plain)).get("/api/places").json() == []


def test_state_offers_actions_only_when_idle_and_transcript_entries_carry_the_turn():
    g = Game(lambda new: open_campaign(fake_stack(), root=tempfile.mkdtemp(), new=new), pace=0.0)
    c = TestClient(create_app(g))
    assert c.get("/api/state").json()["actions"] == ["model_error", "cut"]
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    st = c.get("/api/state").json()
    assert st["actions"] == ["model_error", "cut"]
    mine = [t for t in st["transcript"] if t["kind"] != "intro"]
    assert mine and all(t["turn"] == g.turn_no for t in mine)
    g.start_turn("Ще.")
    g.wait_idle(20)
    turns = [t["turn"] for t in g.transcript if t["kind"] == "player"]
    assert turns == [1, 2]
