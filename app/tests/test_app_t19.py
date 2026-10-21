"""Task 19 in the app: the Vizima campaign (situation A, the demon without limits), the slow lane
events, the death screen. Fake stack, no network."""
from __future__ import annotations

import pytest

from app.game import Ended, Game
from app.stacks import fake_stack
from app.vizima import TITLE, canon_path, open_vizima
from harness.models import PLAYER
from harness.outcome import CHARACTER_DEATH


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)


def make(tmp_path, canon_db=None):
    stack = fake_stack()
    return Game(lambda new: open_vizima(stack, root=tmp_path, new=new,
                                        canon_db=canon_db or tmp_path / "none.db"), pace=0.0)


def test_vizima_campaign_starts_at_situation_a_with_the_unbounded_demon(tmp_path):
    g = make(tmp_path)
    eng = g.eng
    assert g.camp.title == TITLE and g.camp.world is not None
    assert eng.scene.time == 2 * 1440 + 20 * 60                  # day 3, 20:00
    assert eng.scene.location == "корчма «Під Лисом»"
    assert eng.ctx.player_unlimited and eng.outcomes_on
    assert PLAYER in eng.scene.present and len(eng.scene.present) >= 3
    guard = eng.profiles["npc_guard"]
    assert guard.core and eng.vitals.people["npc_guard"].age(eng.scene.time) >= 16
    assert "vizima" in g.camp.name


def test_vizima_turn_streams_and_the_slow_lane_settles(tmp_path):
    g = make(tmp_path)
    g.start_turn("Сідаю біля стійки й замовляю пива.")
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "turn_done" in types and types[-1] == "settled"
    assert g.debug["timing"]["slow_s"] >= 0 and g.debug["lanes"]["fast_s"] >= 0
    assert "world" in g.debug
    dec = g.debug["decisions"]
    assert dec["turn"]["total"] > 0 and dec["session"]["total"] == dec["scene"]["total"]


def test_vizima_reopens_where_it_stopped(tmp_path):
    g = make(tmp_path)
    g.start_turn("Дивлюсь на корчмаря.")
    g.wait_idle(20)
    name, t = g.camp.name, g.eng.scene.time
    g.eng.close()
    g2 = make(tmp_path)
    assert g2.camp.name == name and g2.eng.scene.time == t
    assert g2.eng.profiles["npc_guard"].core                      # the core is saved with the setup
    assert g2.camp.world is not None


def test_death_makes_the_campaign_read_only_and_shows_the_chronicle(tmp_path):
    g = make(tmp_path)
    g.eng.log.append(CHARACTER_DEATH, game_time=g.eng.scene.time, location="x",
                     participants=[PLAYER], witnesses=[], notability=1.0,
                     payload={"text": "The player character dies: x", "reason": "body"})
    assert g.eng.ended
    with pytest.raises(Ended):
        g.start_turn("Ще раз.")
    st = g.state()
    assert st["ended"] is True and st["chronicle"][-1]["kind"] == "death"


@pytest.mark.skipif(canon_path() is None, reason="the local canon store is not in this checkout")
def test_vizima_on_the_real_canon_store(tmp_path):
    g = make(tmp_path, canon_db=canon_path())
    eng = g.eng
    assert "velerad" in eng.profiles and eng.profiles["velerad"].name == "Велерад"
    assert any(f for f in eng.facts.visible_to("velerad", eng.scene.time, store="canon"))
    assert set(g.camp.world.collectives) == {"vizim_townsfolk", "vizim_guards", "velerad", "foltest"}
