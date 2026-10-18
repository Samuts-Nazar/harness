import pytest

from harness.judge import FakeJudge
from harness.models import EQUIPMENT, INJURY, INVENTORY, PLAYER
from harness.state import StateChange, StateError
from conftest import change, diff, fact, make_engine, narr


def sc(character, category, item, observable=True, op="add"):
    return StateChange(character, category, op, item, observable)


def salient_for(*names):
    """Judge rule: the observation is salient for exactly these characters."""
    return FakeJudge({"salience": lambda q, st: any(n in q.text for n in names)})


def test_state_persists_until_an_event_changes_it():
    script = {"narrator": ["N."] * 3, "npc": ["Hm."] * 3,
              "extractor": [diff(), diff(), diff(changes=[
                  change("player", "equipment", "remove", "drawn sword", "player")])]}
    eng, _ = make_engine(script)
    eng.apply_state_change(sc(PLAYER, EQUIPMENT, "drawn sword"))
    eng.apply_state_change(sc(PLAYER, INJURY, "gash on the arm", observable=False))
    for _ in range(2):  # two turns later nothing has changed
        eng.turn("I wait", speakers=["innkeeper"])
        assert {(e.category, e.item) for e in eng.live.of(PLAYER)} == {
            ("equipment", "drawn sword"), ("injury", "gash on the arm")}
    eng.turn("I sheathe my sword", speakers=["innkeeper"])  # an event removes it
    assert [(e.category, e.item) for e in eng.live.of(PLAYER)] == [("injury", "gash on the arm")]


def test_scripted_changes_are_validated():
    eng, _ = make_engine({})
    with pytest.raises(StateError):
        eng.apply_state_change(sc(PLAYER, INVENTORY, "map", op="remove"))
    eng.apply_state_change(sc(PLAYER, INVENTORY, "map"))
    with pytest.raises(StateError):
        eng.apply_state_change(sc(PLAYER, INVENTORY, "map"))


def test_extractor_removal_of_missing_item_rejects_the_diff():
    from harness.pipeline import ExtractionRejected
    bad = diff(changes=[change("player", "equipment", "remove", "drawn sword", "player")])
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Hm."], "extractor": [bad, bad]})
    with pytest.raises(ExtractionRejected):
        eng.turn("I sheathe my sword", speakers=["innkeeper"])
    assert eng.live.of(PLAYER) == []


def test_scene_entry_is_perceived_and_salience_decides_surfacing():
    judge = salient_for("Innkeeper")  # the innkeeper cares; the bard does not
    eng, prov = make_engine({"narrator": ["N."], "npc": ["Halt!", "Hm."],
                             "extractor": [diff(), diff()]},
                            present=("innkeeper", "bard"), judge=judge)
    eng.apply_state_change(sc(PLAYER, EQUIPMENT, "a bloody drawn sword"))
    eng.apply_state_change(sc(PLAYER, INJURY, "a hidden scar", observable=False))
    # the player is not in the room yet: nobody has perceived anything
    assert eng.facts.visible_to("innkeeper", eng.scene.time) == []
    eng.enter_scene(PLAYER)

    t = eng.scene.time
    for who in ("innkeeper", "bard"):  # everyone present perceives the observable element
        assert [f.content for f in eng.facts.visible_to(who, t)] == [
            "Geralt has a bloody drawn sword in hand or at the belt"]
    # the hidden one is not perceived by anyone
    assert not any("scar" in f.content for who in ("innkeeper", "bard")
                   for f in eng.facts.visible_to(who, t))
    # ONE batched judge call about the observation, one question per NPC observer
    [(state, qs)] = [a for a in judge.asked if any(q.tag == "salience" for q in a[1].values())][-1:]
    assert set(qs) == {"innkeeper", "bard"} and "bloody drawn sword" in state[0]

    inn = " ".join(m["content"] for m in eng.ctx.character("innkeeper", eng.scene))
    bard = " ".join(m["content"] for m in eng.ctx.character("bard", eng.scene))
    assert "You have just noticed" in inn and "bloody drawn sword" in inn
    assert "You have just noticed" not in bard
    assert "bloody drawn sword" in bard  # but the bard still knows it


def test_notice_appears_in_the_next_npc_call_then_is_consumed():
    eng, prov = make_engine({"narrator": ["N.", "N."], "npc": ["Halt!", "Hm."],
                             "extractor": [diff(), diff()]},
                            present=("innkeeper", "bard"), judge=salient_for("Innkeeper"))
    eng.apply_state_change(sc(PLAYER, EQUIPMENT, "a bloody drawn sword"))
    eng.enter_scene(PLAYER)
    eng.turn("Easy now", speakers=["innkeeper"])
    eng.turn("Easy now", speakers=["innkeeper"])
    first, second = [m[1]["content"] for model, m in prov.calls if model == "npc"]
    assert "You have just noticed:\n- Geralt has a bloody drawn sword" in first
    assert "You have just noticed" not in second


def test_entrant_perceives_observable_state_of_those_already_present():
    eng, _ = make_engine({}, present=("innkeeper", "bard"))
    eng.apply_state_change(sc("bard", INVENTORY, "a lute"))
    eng.apply_state_change(sc("bard", INVENTORY, "a love letter", observable=False))
    eng.enter_scene(PLAYER)
    seen = [f.content for f in eng.facts.visible_to(PLAYER, eng.scene.time)]
    assert seen == ["Dandelion is carrying a lute"]


def test_observable_change_during_a_turn_is_perceived_by_those_present():
    script = {"narrator": [narr("N.", ["Geralt draws his sword"]), narr("N.", ["Geralt sheathes it"])],
              "npc": ["Hm.", "Hm."],
              "extractor": [
                  diff(changes=[change("player", "equipment", "add", "drawn sword", "action1")]),
                  diff(changes=[change("player", "equipment", "remove", "drawn sword", "action1")]),
              ]}
    eng, _ = make_engine(script)
    eng.turn("I draw", speakers=["innkeeper"])
    assert [f.content for f in eng.facts.visible_to("bard", eng.scene.time)
            if "drawn sword" in f.content] == [
        "Geralt has drawn sword in hand or at the belt"]
    eng.turn("I sheathe", speakers=["innkeeper"])
    assert "Geralt no longer has drawn sword" in [
        f.content for f in eng.facts.visible_to("bard", eng.scene.time)]


def test_reveal_makes_hidden_state_perceivable_and_absent_characters_see_nothing():
    script = {"narrator": ["N."], "npc": ["Hm."], "extractor": [
        diff(changes=[change("player", "injury", "reveal", "stab wound", "player")])]}
    eng, _ = make_engine(script, present=(PLAYER, "innkeeper"))
    eng.apply_state_change(sc(PLAYER, INJURY, "stab wound", observable=False))
    assert eng.facts.visible_to("innkeeper", eng.scene.time) == []  # hidden: not perceived
    eng.turn("I pull my cloak aside", speakers=["innkeeper"])
    assert [f.content for f in eng.facts.visible_to("innkeeper", eng.scene.time)] == [
        "Geralt is visibly injured: stab wound"]
    assert eng.facts.visible_to("bard", eng.scene.time) == []  # bard is not in the room


def test_state_and_perception_roll_back_with_their_source_event():
    script = {"narrator": ["N."], "npc": ["I limp."], "extractor": [
        diff(changes=[change("innkeeper", "injury", "add", "twisted ankle", "innkeeper")])]}
    eng, _ = make_engine(script)
    res = eng.turn("hello", speakers=["innkeeper"])
    assert [e.item for e in eng.live.of("innkeeper")] == ["twisted ankle"]
    assert any("twisted ankle" in f.content for f in eng.facts.visible_to("bard", eng.scene.time))
    eng.rollback(res.utterances[0].id)
    assert eng.live.of("innkeeper") == []
    assert eng.facts.visible_to("bard", eng.scene.time) == []
