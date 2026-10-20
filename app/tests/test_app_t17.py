"""Task 17 in the app: a campaign with a world runs turns through `World.play` and the debug view
carries a "world" section. Fake stack, no network."""
from __future__ import annotations

import tempfile

import pytest

import app.campaigns as campaigns
from app.campaigns import TITLE, open_campaign
from app.game import Game
from app.stacks import fake_stack
from harness.world.places import Place, WorldMap
from harness.world.world import World


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def test_debug_has_a_world_section_and_the_turn_goes_through_the_world():
    stack = fake_stack()
    root = tempfile.mkdtemp(prefix="harness-app-t17-")

    def opener(new: bool):
        camp = open_campaign(stack, root=root, new=new)
        wmap = WorldMap()
        wmap.add_place(Place("inn", TITLE))
        camp.world = World(camp.engine, wmap, collectives=[], cast={})
        return camp

    g = Game(opener, pace=0.0)
    g.start_turn("Я киваю Горсту.")
    g.wait_idle(20)
    assert "world" in g.debug
    w = g.debug["world"]
    assert w["clock"]["place"] == TITLE and "news" in w and "offscreen" in w
    kinds = [t["kind"] for t in g.transcript]
    assert kinds[:3] == ["intro", "player", "narr"]
