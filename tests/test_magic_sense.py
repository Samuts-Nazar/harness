"""Task 7: the magic sense. An element on the "magic" channel is perceived only by observers
with that sense (a sorceress, a portrait or package person with `senses: [magic]`, a wearer of
an item with `grants_sense: magic`); sight elements are perceived as ever."""
import json

import pytest
import yaml

from harness.judge import FakeJudge
from harness.models import EQUIPMENT, INTERNAL, PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.portrait import PortraitError, parse_portrait
from harness.providers import FakeProvider
from harness.state import StateChange

SOURCE = "a dormant Source"
PROFILES = [
    CharacterProfile(PLAYER, "Ragnar", "A traveller."),
    CharacterProfile("sorc", "Yennefer", "A sorceress.", senses=("sight", "magic")),
    CharacterProfile("inn", "Innkeeper", "Gruff innkeeper."),
]


def make(present=("sorc", "inn"), profiles=PROFILES, script=None, judge=None):
    judge = judge or FakeJudge({"salience": True})
    eng = Engine(FakeProvider(script=script or {}), profiles, Scene("Inn", tuple(present), 0),
                 models=ModelConfig(), judge=judge, record_language=None)
    return eng, judge


def latent(eng):
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "add", SOURCE, True, aware=False,
                                       channel="magic"))


def known(eng, who):
    return [f.content for f in eng.facts.visible_to(who, eng.scene.time)]


def salience_asked(judge):
    return [(st, qs) for st, qs in judge.asked if any(q.tag == "salience" for q in qs.values())]


def test_sorceress_notices_unaware_source_on_entry():
    eng, judge = make()
    latent(eng)
    eng.enter_scene(PLAYER)
    [seen] = known(eng, "sorc")
    assert SOURCE in seen and "magic sense" in seen and "Ragnar" in seen
    [(state, qs)] = salience_asked(judge)
    assert set(qs) == {"sorc"} and SOURCE in state[0]  # one judgment, for the sorceress only
    text = " ".join(m["content"] for m in eng.ctx.character("sorc", eng.scene))
    assert "You have just noticed" in text and SOURCE in text


def test_sight_only_npc_does_not():
    eng, _ = make()
    latent(eng)
    eng.enter_scene(PLAYER)
    assert known(eng, "inn") == []
    inn = " ".join(m["content"] for m in eng.ctx.character("inn", eng.scene))
    assert SOURCE not in inn
    eng2, judge2 = make(present=("inn",))  # nobody with the sense: no fact, no judge call
    latent(eng2)
    eng2.enter_scene(PLAYER)
    assert known(eng2, "inn") == [] and salience_asked(judge2) == []


def test_sorceress_entering_perceives_the_players_source():
    eng, _ = make(present=(PLAYER, "inn"))
    latent(eng)
    eng.enter_scene("sorc")
    assert any(SOURCE in c for c in known(eng, "sorc"))
    assert known(eng, "inn") == []


def test_source_stays_out_of_player_panel_until_realize():
    eng, _ = make()
    latent(eng)
    eng.enter_scene(PLAYER)
    assert SOURCE not in [e.item for e in eng.live.of(PLAYER, viewer=PLAYER)]
    assert SOURCE not in [e.item for e in eng.deriver.derive(PLAYER, eng.scene.time).state]
    assert SOURCE in [e.item for e in eng.live.of(PLAYER, viewer=PLAYER, debug=True)]
    # the sorceress noticing it does not tell the player anything
    assert not any(SOURCE in c for c in known(eng, PLAYER))
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "realize", SOURCE, False))
    assert SOURCE in [e.item for e in eng.live.of(PLAYER, viewer=PLAYER)]


def test_realize_after_told_by_sorceress():
    eng, _ = make()
    latent(eng)
    eng.enter_scene(PLAYER)
    assert SOURCE not in [e.item for e in eng.live.of(PLAYER, viewer=PLAYER)]
    eng.facts.add_canon("Yennefer tells Ragnar that he carries " + SOURCE,
                        game_time=eng.scene.time, knowers=[(PLAYER, "told", "sorc")])
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "realize", SOURCE, False))
    assert SOURCE in [e.item for e in eng.deriver.derive(PLAYER, eng.scene.time).state]


def wear_medallion(eng, who, location="worn"):
    eng.apply_state_change(StateChange(who, EQUIPMENT, "add", "wolf medallion", True,
                                       id="item:medallion", location=location))
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("inventory_meta", json.dumps({"item:medallion":
                                                        {"grants_sense": "magic"}})))


def test_medallion_grants_sense_when_worn():
    profs = [PROFILES[0], CharacterProfile("wit", "Witcher", "A witcher."), PROFILES[2]]
    eng, _ = make(present=("wit", "inn"), profiles=profs)
    eng.profiles["wit"] = profs[1]
    assert "magic" not in eng.senses_of("wit")
    wear_medallion(eng, "wit", location="in_hand")  # carried, not worn: nothing
    assert "magic" not in eng.senses_of("wit")
    eng.apply_state_change(StateChange("wit", EQUIPMENT, "move", "wolf medallion",
                                       location="worn"))
    assert "magic" in eng.senses_of("wit") and "magic" not in eng.senses_of("inn")
    latent(eng)
    eng.enter_scene(PLAYER)
    assert any(SOURCE in c for c in known(eng, "wit")) and not any(
        SOURCE in c for c in known(eng, "inn"))
    eng.apply_state_change(StateChange("wit", EQUIPMENT, "remove", "wolf medallion"))
    assert "magic" not in eng.senses_of("wit")


def test_old_profiles_and_portraits_keep_sight_only():
    assert CharacterProfile("x", "X").senses == ("sight",)
    eng, judge = make(profiles=[PROFILES[0], PROFILES[2]], present=("inn",))
    assert eng.senses_of("inn") == {"sight"}
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "a sword", True))
    eng.enter_scene(PLAYER)  # a sight element: perceived as before, one judgment
    assert known(eng, "inn") == ["Ragnar has a sword in hand or at the belt"]
    assert len(salience_asked(judge)) == 1
    base = yaml.safe_load("""
id: p
character: c
name: N
phase: x
core: c
stances: [{id: s, rung: [stranger], does: d, sounds: s}]
hidden: h
leaks: []
voice: v
never: n
""")
    assert parse_portrait(base).senses == ("sight",)
    assert parse_portrait({**base, "senses": ["magic"]}).senses == ("sight", "magic")
    with pytest.raises(PortraitError):
        parse_portrait({**base, "senses": ["smell"]})


def test_portrait_senses_apply_to_the_npc_who_plays_it():
    eng, _ = make(profiles=[PROFILES[0], CharacterProfile("y", "Yen", "x", portrait="p")],
                  present=("y",))
    base = {"id": "p", "character": "y", "name": "N", "phase": "x", "core": "c",
            "stances": [{"id": "s", "rung": ["stranger"], "does": "d", "sounds": "s"}],
            "hidden": "h", "leaks": [], "voice": "v", "never": "n", "senses": ["magic"]}
    eng.ctx.portraits = {"p": parse_portrait(base)}
    assert "magic" in eng.senses_of("y")


def test_senses_survive_reopen(tmp_path):
    Engine.create_campaign("c", FakeProvider(), PROFILES, Scene("Inn", ("sorc",), 0),
                           root=tmp_path, models=ModelConfig()).conn.close()
    eng = Engine.open_campaign("c", FakeProvider(), root=tmp_path, models=ModelConfig())
    assert eng.profiles["sorc"].senses == ("sight", "magic")
    assert eng.profiles["inn"].senses == ("sight",)


def test_removal_of_a_magic_element_is_perceived_only_by_the_sense():
    eng, judge = make(present=(PLAYER, "inn"))
    latent(eng)
    n = len(salience_asked(judge))
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "remove", SOURCE, True))
    assert known(eng, "inn") == [] and len(salience_asked(judge)) == n
    eng2, judge2 = make(present=(PLAYER, "inn", "sorc"))
    latent(eng2)
    eng2.apply_state_change(StateChange(PLAYER, INTERNAL, "remove", SOURCE, True))
    assert any("no longer has" in c and SOURCE in c for c in known(eng2, "sorc"))
    assert known(eng2, "inn") == []
    for _, qs in salience_asked(judge2):
        assert set(qs) == {"sorc"}
