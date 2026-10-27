"""The Ellander start (outsider campaign D7): glossary entries for the temple arc, the start point
`ellander_road` on the general canon builder (its own places, its own canon store, a campaign clock
that starts at day 1 while canon runs on its own story clock), and the Vizima start points kept as
they were. Fake stack, no network.

The canon store of «Кров ельфів» (campaigns/canon/be.db) is local and git-ignored: the tests that
build on it skip when it is absent."""
from __future__ import annotations

import hashlib
import json
import pathlib

import pytest

from app import newgame
from app.game import Game
from app.newgame import parse
from app.stacks import fake_stack
from harness.glossary import Glossary
from harness.models import PLAYER
from harness.world import pilot
from harness.world.places import vizima

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "app" / "tests" / "fixtures" / "outsider_ellander.yaml"
_CANDIDATES = [ROOT / "campaigns/canon/be.db",
               pathlib.Path("/home/cock/projects/harness/campaigns/canon/be.db")]
BE = next((p for p in _CANDIDATES if p.is_file()), None)
needs_be = pytest.mark.skipif(BE is None, reason="local canon store be.db is absent")
VIZIMA_IDS = ["vidmak_A_tavern", "vidmak_B_gate", "vidmak_C_tavern_morning", "vidmak_D_market",
              "vidmak_E_velerad_office", "vidmak_F_palace_dusk", "vidmak_G_night_watch"]
VIZIMA_DIGEST = "120989ea30a0c7854c837f8db983ebba537bf6b112c47a1539b4e5a69d01139d"
SOURCE = "у ньому дрімає Джерело"
ARRIVAL_T = -105120   # the store's stamp of Yennefer's arrival at the temple (`before` 0.2 years)


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)
    monkeypatch.delenv("HARNESS_CANON_DB_BE", raising=False)


def build(tmp_path, canon_db):
    stack = fake_stack()
    pkg = parse(FIX.read_text(encoding="utf-8"))
    return Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=canon_db),
                pace=0.0), stack


# -- glossary ---------------------------------------------------------------------------------

def test_glossary_fixes_wrong_forms():
    g = Glossary.for_world("witcher")
    text, found = g.fix("Ненеке вийшла до воріт храму Мелителе; Нененке кликала. "
                        "Шлях з Еландеру. Nenneke, Melitele, Ellander.")
    assert text == ("Неннеке вийшла до воріт храму Мелітеле; Неннеке кликала. "
                    "Шлях з Елландеру. Неннеке, Мелітеле, Елландер.")
    assert len(found) == 7
    right = "Неннеке, Мелітеле, Елландер, в Елландері, до Елландеру, Цірі, Йеннефер."
    assert g.fix(right) == (right, [])
    by = {e.canonical: e for e in g.entries}
    assert by["Неннеке"].kind == "person" and by["Неннеке"].id == "char:nenneke"
    assert by["Елландер"].kind == "place" and by["Елландер"].cases == ("Елландері", "Елландеру")
    # the existing entries stay as they were
    assert (by["Цірі"].latin, by["Цірі"].wrong) == (("Ciri", "Cirilla"), ("Цирі",))
    assert by["Йеннефер"].wrong == ("Єнніфер", "Йенефер", "Єнефер", "Єніфер")


# -- the start point --------------------------------------------------------------------------

def test_start_point_loads_and_binds_portraits():
    cs = newgame.canon_start("ellander_road")
    assert cs.builder == "canon" and cs.canon_db == "be.db"
    assert cs.here == ("char:yennefer",) and cs.extras == ()
    assert dict(cs.portraits) == {"char:yennefer": "yennefer_temple", "char:nenneke": "nenneke",
                                  "char:ciri": "ciri_temple"}
    assert set(dict(cs.portraits).values()) <= set(newgame.world_portraits()[0])
    assert {e for e, _h, _g in cs.people} == {"char:yennefer", "char:nenneke", "char:ciri"}
    # the places of this start: the road, the temple and its grounds, linked
    wmap = cs.world_map()
    assert {"road", "temple", "grounds"} <= set(wmap.places)
    assert cs.place_id == "road" and cs.location == "дорога до Елландера"
    assert wmap.resolve("храм Мелітеле").id == "temple"
    assert 0 < wmap.minutes("road", "temple") < wmap.minutes("road", "grounds")
    assert dict(cs.canon_places)["place:temple-refectory"] == "temple"
    # the clock: the campaign starts at day 1 in the morning; canon runs on the story clock, the
    # arrival at the temple a little later than the start, so it is still ahead
    camp = cs.campaign()
    assert 0 <= cs.t < 1440 and 6 * 60 <= cs.t <= 10 * 60
    assert camp.start_t == cs.story_t < ARRIVAL_T and ARRIVAL_T - camp.start_t <= 4 * 60
    assert camp.to_campaign_t(ARRIVAL_T) > cs.t and camp.to_story_t(cs.t) == camp.start_t
    # the intro names nobody the newcomer has not met
    assert cs.intro and "Йеннефер" not in cs.intro and "Неннеке" not in cs.intro
    pkg = parse(FIX.read_text(encoding="utf-8"))
    assert pkg.data["start"] == {"canon": "ellander_road"} and pkg.warnings == []
    assert newgame.summary(pkg)["title"] == newgame.start_points()["ellander_road"]["title"]


@needs_be
def test_ellander_start_scene_has_yennefer_and_player(tmp_path):
    g, _ = build(tmp_path, BE)
    eng, world = g.eng, g.camp.world
    assert eng.scene.time == newgame.canon_start("ellander_road").t
    assert eng.scene.location == "дорога до Елландера"
    assert set(eng.scene.present) == {PLAYER, "yennefer"}
    assert eng.profiles["yennefer"].name == "Йеннефер"
    assert eng.profiles["yennefer"].portrait == "yennefer_temple"
    assert eng.profiles["nenneke"].portrait == "nenneke"
    assert eng.profiles["ciri"].portrait == "ciri_temple"
    assert world.cast["nenneke"] == "temple" and world.cast["ciri"] == "temple"
    # the temple meeting is ahead of the clock: Nenneke does not know it yet, and it is scheduled
    def known(c):
        return eng.facts.visible_to(c, eng.scene.time + 10 ** 6, store="canon")
    assert known("yennefer") and all(f.game_time < eng.scene.time for f in known("yennefer"))
    assert all(f.game_time < eng.scene.time for f in known("nenneke") + known("ciri"))
    ahead = world.canon.scheduled(eng.scene.time, eng.scene.time + 6 * 60)
    assert ahead and all(e.t > eng.scene.time for e in ahead)
    assert any(e.place == "temple" and "yennefer" in e.participants for e in ahead)
    assert min(e.t for e in ahead) == eng.scene.time + 120   # the arrival, two hours on
    # Yennefer perceives the latent Source by her magic sense; the player's own panel does not
    assert "magic" in eng.senses_of("yennefer")
    assert any(SOURCE in f.content for f in eng.facts.visible_to("yennefer", eng.scene.time))
    assert SOURCE not in " ".join(e.item for e in eng.live.of(PLAYER, viewer=PLAYER))
    # one turn plays
    g.start_turn("Підводжуся з дороги й дивлюся на жінку.")
    g.wait_idle(20)
    kinds = [t["kind"] for t in g.transcript]
    assert kinds[0] == "intro" and "narr" in kinds
    # the newcomer has not learned the names of the canon people (the goddess's name is public)
    seen = " ".join([g.camp.title, g.camp.intro, json.dumps(g.cast(), ensure_ascii=False)])
    for secret in ("Йеннефер", "Неннеке", "Цірі"):
        assert secret not in seen, secret
    # and the campaign reopens on the same store
    name, t = g.camp.name, eng.scene.time
    eng.close()
    camp = newgame.reopen(fake_stack(), name, root=tmp_path, canon_db=BE)
    assert camp.engine.scene.time == t and camp.world.cast["nenneke"] == "temple"
    assert camp.world.canon.scheduled(t, t + 6 * 60)


def test_ellander_start_without_its_store_keeps_yennefer(tmp_path):
    """No canon store (like the Vizima starts without theirs): the people of the start are
    stand-ins made from their portraits, so the scene stays whole; no canon events."""
    g, _ = build(tmp_path, False)
    eng = g.eng
    assert set(eng.scene.present) == {PLAYER, "yennefer"}
    assert eng.profiles["yennefer"].name == "Йеннефер"
    assert eng.profiles["yennefer"].portrait == "yennefer_temple"
    assert eng.profiles["nenneke"].portrait == "nenneke" and g.camp.world.cast["nenneke"] == "temple"
    assert any(SOURCE in f.content for f in eng.facts.visible_to("yennefer", eng.scene.time))
    assert eng.canon_guard is None


def test_store_resolution(tmp_path, monkeypatch):
    from app import vizima as viz
    cs = newgame.canon_start("ellander_road")
    got = tmp_path / "be.db"
    got.write_bytes(b"")
    pilot_db = tmp_path / "pilot_v3.db"
    pilot_db.write_bytes(b"")
    assert viz.canon_path(False, store=cs.canon_db) is None
    assert viz.canon_path(pilot_db, store=cs.canon_db) == got        # next to the pilot store
    monkeypatch.setenv("HARNESS_CANON_DB", str(pilot_db))
    assert viz.canon_path(None, store=cs.canon_db) == got
    other = tmp_path / "x" / "be.db"
    other.parent.mkdir()
    other.write_bytes(b"")
    monkeypatch.setenv("HARNESS_CANON_DB_BE", str(other))
    assert viz.canon_path(None, store=cs.canon_db) == other
    assert viz.canon_path(None) == pilot_db                          # the Vizima path as before


# -- the Vizima starts ------------------------------------------------------------------------

def test_vizima_start_points_unchanged():
    points = newgame.start_points()
    viz_points = {k: v for k, v in points.items() if v.get("builder", "vizima") == "vizima"}
    assert sorted(viz_points) == VIZIMA_IDS
    digest = hashlib.sha256(json.dumps(viz_points, ensure_ascii=False, sort_keys=True)
                            .encode()).hexdigest()
    assert digest == VIZIMA_DIGEST
    for cid in VIZIMA_IDS:
        cs = newgame.canon_start(cid)
        assert cs.builder == "vizima" and cs.story_t is None and cs.canon_db == ""
        camp = cs.campaign()
        assert (camp.start_t, camp.offset, camp.place) == (cs.t, 0, cs.canon_place)
        assert set(cs.world_map().places) == set(vizima(*cs.map_extra).places)
        assert dict(cs.place_map()) == pilot.CANON_PLACES
    assert pilot.SITUATION_A.builder == "vizima"


@needs_be
def test_temple_events_wait_while_yennefer_is_on_the_road(tmp_path):
    """Review fix: the arrival scenes at the temple (11:00) cannot happen to Yennefer while she
    stands on the road with the player; they happen once she is at the temple (or its park, the
    same site), in story order, six per step."""
    from harness.world import news as nw
    from harness.world.world import CANON_LATE_PER_STEP
    g, _ = build(tmp_path, BE)
    eng, world = g.eng, g.camp.world
    start = eng.scene.time
    world.tick(start + 3 * 60)                       # 12:00, past the arrival stamp, still on the road
    temple = world.map.name("temple")
    assert not [f for f in eng.facts.visible_to("yennefer", eng.scene.time)
                if f.location == temple]
    held = [e.payload["canon_id"] for e in eng.log.active([nw.CANON_DEFERRED])]
    assert len(held) >= CANON_LATE_PER_STEP + 1
    eng.scene.location = temple                      # scripted: she (with the player) is there
    world.tick(eng.scene.time + 60)
    late = [e for e in eng.log.active([nw.CANON_EXECUTED]) if "deferred_from" in e.payload]
    assert 0 < len(late) <= CANON_LATE_PER_STEP
    ids = [e.payload["canon_id"] for e in late]
    assert ids == held[:len(ids)]                      # in story order
    # a three-day wait at the temple: the park is part of its site, so the whole conversation
    # happens in story order (the park scenes before the guest-room scenes)
    world.tick(eng.scene.time + 3 * 1440)
    ex = [e for e in eng.log.active([nw.CANON_EXECUTED]) if e.payload["canon_id"] in held]
    order = [e.payload["canon_id"] for e in ex]
    assert sorted(order) == sorted(held) and order == held
    # found by their canon places: the park talk, then the talk in Yennefer's guest room
    raw = world.canon._by_id
    park = [i for i in order if raw[i].place == "place:temple-park"]
    room = [i for i in order if raw[i].place == "place:yennefer-room"]
    assert park and room and order.index(park[-1]) < order.index(room[0])
    stamps = [e.game_time for e in ex]
    assert stamps == sorted(stamps)
    per_step: dict[int, int] = {}
    for e in ex:
        per_step[e.game_time] = per_step.get(e.game_time, 0) + 1
    assert max(per_step.values()) <= CANON_LATE_PER_STEP
    assert any(f.location == temple for f in eng.facts.visible_to("yennefer", eng.scene.time))
