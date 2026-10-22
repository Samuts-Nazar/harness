"""The canon start points of the Vizima arc (worlds/witcher/start_points.yaml): each one builds
through the one shared path, the first scene matches where the canon puts Geralt and the canon
people, one turn plays, and nothing the newcomer has not learned is named. Fake stack, no network.

The canon store is local and git-ignored. The tests run on a tiny made-up store that mirrors the
real canon's times and places (`mini_canon`), and, where the real store is in the checkout (or
$HARNESS_CANON_DB), once more on it; those skip exactly as the other real-store tests do."""
from __future__ import annotations

import json
import pathlib

import pytest

from app import newgame
from app.game import Game
from app.newgame import parse, summary
from app.stacks import fake_stack
from app.vizima import canon_path
from harness.canon.api import CanonCampaign
from harness.canon.play import CanonCast, CanonPlay
from harness.canon.retrieve import Canon
from harness.canon.store import add_record, create_store
from harness.glossary import Glossary
from harness.models import PLAYER
from harness.scene_cast import HERE
from harness.world import pilot
from harness.world.places import VIZIMA_EXTRA, vizima

REAL = canon_path()  # resolved before any test clears the environment
POINTS = newgame.start_points()
IDS = list(POINTS)
D = 1440


def pkg_for(cid: str):
    return parse(f"version: 1\nworld: witcher\nplayer:\n  name: Збислав\n"
                 f"  description: Мандрівний лютняр, що співає за вечерю.\nstart:\n  canon: {cid}\n")


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)


@pytest.fixture(scope="module")
def mini_canon(tmp_path_factory) -> pathlib.Path:
    """A made-up canon store with the real arc's shape: who stands where on which story day.
    No book text; the gists are our own."""
    path = tmp_path_factory.mktemp("canon") / "mini.db"
    con = create_store(path)
    people = {"char:geralt": "Ґеральт", "char:innkeeper": "корчмар", "char:velerad": "Велерад",
              "char:foltest": "Фольтест"}
    colls = {"coll:vizim-guards": "стражники", "coll:vizim-townsfolk": "мешканці Визіма",
             "coll:vizim-officials": "міська влада Визіма"}
    places = {"place:lynvar-gate": "брама Линварів", "place:pid-lysom": "«Під Лисом»",
              "place:vizim": "Визім", "place:old-palace": "старий палац",
              "place:guardroom": "кімнатка над кордегардією",
              "place:кабінет-бургомістра": "кабінет бургомістра",
              "place:зал-де-король-приймає": "зал, де король приймає",
              "place:зруйнована-кімната-старого-палацу": "зруйнована кімната старого палацу",
              "place:подвір-я-старого-палацу": "подвір'я старого палацу"}
    for table, typ in ((people, "person"), (colls, "collective"), (places, "place")):
        for i, n in table.items():
            con.execute("INSERT INTO entity(id,type,name) VALUES (?,?,?)", (i, typ, n))
            con.execute("INSERT INTO canon_alias VALUES (?,?)", (i, n))
    for ent, role in (("char:geralt", "witcher"), ("char:innkeeper", "innkeeper"),
                      ("char:velerad", "burgomaster"), ("char:foltest", "king")):
        con.execute("INSERT INTO canon_character VALUES (?,?,?,?,?,?,?)",
                    (ent, f"{role} of Vizima", role, "known in town", "[]", 1,
                     1 if ent == "char:innkeeper" else 0))
    ev = [  # (story minute, canon place, day, participants, our gist)
        (900, "place:lynvar-gate", 1, ["char:geralt"], "Чужинець приходить пішки до брами."),
        (900, "place:pid-lysom", 1, ["char:geralt", "char:innkeeper"], "Чужинець у корчмі."),
        (1140, "place:кабінет-бургомістра", 1, ["char:geralt", "char:velerad"],
         "Бургомістр приймає чужинця."),
        (1140, "place:зал-де-король-приймає", 1, ["char:geralt", "char:foltest"],
         "Король наймає чужинця."),
        (D + 23 * 60, "place:guardroom", 2, ["char:geralt", "char:foltest"],
         "Король у кімнатці чужинця."),
        (6 * D + 19 * 60, "place:зруйнована-кімната-старого-палацу", 7, ["char:geralt"],
         "Чужинець готується в палаці."),
        (6 * D + 23 * 60, "place:подвір-я-старого-палацу", 7, ["char:geralt"],
         "Чужинець на подвір'ї палацу."),
    ]
    for i, (t, place, day, parts, gist) in enumerate(ev):
        rid = add_record(con, "canon_event", gist, t_from=t, t_prec="hour", place=place,
                         notability=0.3)
        con.execute(
            "INSERT INTO canon_event(id, ekind, loudness, order_key, when_prec, confidence, review,"
            " day, part, quote, lines, local_id, day_to, gist_uk, kw_uk, time_conf, time_basis) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (rid, "other", 0.3, rid, "hour", 0.9, "ok", day, "x", "", "[1]", f"e{i}", day, gist,
             "", 0.9, "test"))
        con.execute("INSERT INTO canon_event_fts(rowid, text) VALUES (?,?)", (rid, gist))
        for p in parts:
            con.execute("INSERT INTO canon_participant VALUES (?,?,?)", (rid, p, "actor"))
            con.execute("INSERT INTO canon_knower VALUES (?,?,?,?,?,?,?,?)",
                        (rid, p, "witnessed", None, 0, t, "hour", None))
    con.commit()
    con.close()
    return path


STORES = ["mini"] + (["real"] if REAL is not None else [])


@pytest.fixture(params=STORES)
def store(request, mini_canon) -> pathlib.Path:
    return mini_canon if request.param == "mini" else REAL  # type: ignore[return-value]


def build(tmp_path, cid: str, canon_db):
    stack = fake_stack()
    pkg = pkg_for(cid)
    return Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=canon_db),
                pace=0.0), stack


# -- the data ----------------------------------------------------------------------------------

def test_there_are_several_start_points_and_each_is_complete():
    assert len(IDS) >= 5 and "vidmak_A_tavern" in IDS
    wmap = vizima(*VIZIMA_EXTRA)
    for cid, d in POINTS.items():
        for key in ("title", "book", "place", "day", "time", "canon_place", "map_place", "extras",
                    "who", "geralt", "pitch", "summary"):
            assert d.get(key) not in (None, "", []), (cid, key)
        assert d["map_place"] in wmap.places, cid
        assert d["canon_place"].startswith("place:"), cid
        in_scene = [x for x in d["extras"] if x.get("home", d["map_place"]) == d["map_place"]]
        assert in_scene, f"{cid}: nobody seeded in the first scene"
        assert d["canon_place"] in pilot.CANON_PLACES or d["canon_place"] == "place:pid-lysom"
    assert len({d["title"] for d in POINTS.values()}) == len(POINTS)


def test_situation_a_is_the_default_start_of_the_generalised_builder():
    got = newgame.canon_start("vidmak_A_tavern")
    base = pilot.SITUATION_A
    assert (got.t, got.canon_place, got.place_id, got.here, got.extras, got.pairs) == (
        base.t, base.canon_place, base.place_id, base.here, base.extras, base.pairs)
    assert got.intro == newgame.viz.INTRO


def test_the_new_places_are_on_the_map():
    assert vizima().resolve("кабінет бургомістра") is None  # the base map (and its recordings) is unchanged
    wmap = vizima("office")
    assert wmap.resolve("кабінет бургомістра") is not None and wmap.minutes("office", "palace") <= 15


# -- every start point builds ------------------------------------------------------------------

@pytest.mark.parametrize("cid", IDS)
@pytest.mark.parametrize("canon", ["none", "store"])
def test_each_start_builds_with_the_right_time_place_and_cast(tmp_path, store, cid, canon):
    g, _ = build(tmp_path, cid, False if canon == "none" else store)
    eng, sp, cs = g.eng, POINTS[cid], newgame.canon_start(cid)
    assert eng.scene.time == cs.t == (sp["day"] - 1) * D + int(sp["time"][:2]) * 60 + int(
        sp["time"][3:])
    assert eng.scene.location == vizima(*VIZIMA_EXTRA).name(sp["map_place"])
    assert PLAYER in eng.scene.present
    here = {x["slot"] for x in sp["extras"] if x.get("home", sp["map_place"]) == sp["map_place"]}
    away = {x["slot"] for x in sp["extras"]} - here
    assert here and all(f"npc_{s}" in eng.scene.present for s in here)
    assert all(f"npc_{s}" not in eng.scene.present for s in away)
    assert g.camp.title == sp["title"] and g.camp.world is not None
    assert g.camp.intro.strip() == (sp.get("situation") or newgame.viz.INTRO).strip()
    world = g.camp.world
    assert all(world.cast[f"npc_{s}"] == sp["extras"][i].get("home", sp["map_place"])
               for i, s in enumerate(x["slot"] for x in sp["extras"]))
    assert eng.ctx.intent.count("opening situation") == (1 if sp.get("situation") else 0)
    if canon == "store":
        assert ("innkeeper" in eng.scene.present) == ("char:innkeeper" in sp["here"])
        assert "velerad" in eng.profiles and "geralt" not in eng.scene.present


@pytest.mark.parametrize("cid", IDS)
def test_geralt_is_present_only_where_the_canon_has_him(store, cid):
    sp, cs = POINTS[cid], newgame.canon_start(cid)
    canon = Canon(store)
    play = CanonPlay(canon, CanonCampaign(start_t=cs.t, place=cs.canon_place, offset=0))
    cast = CanonCast(play, places=pilot.CANON_PLACES)
    # the first scene never starts with him in it; he can only come in where canon brings him
    w = cast.whereabouts("char:geralt", cs.t, cs.place_id, cs.location)
    assert (w.status == HERE) == bool(sp["geralt_here"]), (cid, w)


@pytest.mark.parametrize("cid", IDS)
def test_one_turn_plays_and_nothing_unlearned_is_named(tmp_path, store, cid):
    g, stack = build(tmp_path, cid, store)
    g.start_turn("Роззираюсь і питаю когось поруч, що тут діється.")
    g.wait_idle(20)
    kinds = [t["kind"] for t in g.transcript]
    assert kinds[0] == "intro" and "narr" in kinds
    # names of the canon people and the seeded locals that the newcomer has not learned
    secret = {e.canonical for e in Glossary.for_world("witcher").entries if e.kind == "person"}
    named = {c: p for c, p in g.eng.profiles.items()
             if c != PLAYER and c != "innkeeper" and not c.startswith("vizim_")}  # a role is no name
    secret |= {p.name for p in named.values() if p.name}
    secret |= {p.name.split()[0] for p in named.values() if p.name}
    seen = " ".join([g.camp.title, g.camp.intro] + [t.get("text", "") for t in g.transcript
                                                    if t["kind"] == "intro"])
    seen += " " + json.dumps(g.cast(), ensure_ascii=False)
    for name in sorted(secret, key=len, reverse=True):
        if len(name) < 4 or name in ("Збислав",):
            continue
        assert name not in seen, f"{cid}: the unlearned name {name!r} is shown to the player"
    assert PLAYER not in {c["tok"] for c in g.cast()}


@pytest.mark.parametrize("cid", IDS)
def test_a_start_reopens_where_it_stopped(tmp_path, store, cid):
    g, stack = build(tmp_path, cid, store)
    name, t, loc = g.camp.name, g.eng.scene.time, g.eng.scene.location
    g.eng.close()
    stack2 = fake_stack()
    camp = newgame.reopen(stack2, name, root=tmp_path, canon_db=store)
    assert camp.engine.scene.time == t and camp.engine.scene.location == loc
    assert camp.title == POINTS[cid]["title"]
    sp = POINTS[cid]
    away = [x for x in sp["extras"] if x.get("home", sp["map_place"]) != sp["map_place"]]
    assert all(camp.world.cast[f"npc_{x['slot']}"] == x["home"] for x in away)


def test_canon_events_after_the_start_run_in_order(tmp_path, mini_canon):
    """The night start: the palace events of that night are still ahead of the clock."""
    g, _ = build(tmp_path, "vidmak_G_night_watch", mini_canon)
    cs = newgame.canon_start("vidmak_G_night_watch")
    ahead = g.camp.world.canon.scheduled(cs.t, cs.t + 2 * 60)
    assert ahead and all(e.t > cs.t for e in ahead)
    # and the gate start still has the arrival ahead
    g2, _ = build(tmp_path, "vidmak_B_gate", mini_canon)
    cb = newgame.canon_start("vidmak_B_gate")
    assert any(e.place == "gate" for e in g2.camp.world.canon.scheduled(cb.t, cb.t + 30))


# -- the card ---------------------------------------------------------------------------------

@pytest.mark.parametrize("cid", IDS)
def test_the_card_names_the_moment_the_company_and_where_geralt_is(cid):
    card = summary(pkg_for(cid))
    rows = {r["label"]: r["value"] for r in card["set"]}
    sp = POINTS[cid]
    assert sp["title"] in rows["Старт"] and card["title"] == sp["title"]
    assert rows["Ситуація"] == sp["pitch"] and rows["Хто поруч"] == sp["who"]
    assert rows["Де Ґеральт"] == sp["geralt"]


@pytest.mark.parametrize("cid", ["vidmak_A_tavern", "vidmak_B_gate"])
def test_canon_people_play_their_portraits(tmp_path, store, cid):
    """The start point's `portraits` binding: the canon people made at the start play their
    portraits; one the canon brings in later (Ґеральт) is bound when he is made."""
    g, _ = build(tmp_path, cid, store)
    eng = g.eng
    assert eng.profiles["velerad"].portrait == "velerad"
    assert eng.profiles["foltest"].portrait == "foltest"
    assert eng.profiles["innkeeper"].portrait == "innkeeper_vizima"
    assert eng.ctx.rung_of("innkeeper") == "stranger"
    play = g.camp.world.canon.play
    gid = play.ensure_character(eng, "char:geralt")
    assert eng.profiles[gid].portrait == "geralt_vidmak"
