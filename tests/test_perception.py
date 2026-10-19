from harness.models import HEARD, PLAYER, TOLD, WITNESSED, Scene
from harness.perception import ACTION, DESCRIPTION, LOUD, SPEECH, perceivers
from conftest import diff, fact, make_engine, narr


def _by(ps):
    return {p.character: (p.how, p.source) for p in ps}


def test_perceivers_present_absent_outside():
    sc = Scene("Inn", (PLAYER, "innkeeper"), outside=("bard",))
    # a quiet action: present witness it; outside hears nothing; absent (spy) is nowhere
    assert _by(perceivers(sc, ACTION, 0.3)) == {PLAYER: (WITNESSED, None),
                                               "innkeeper": (WITNESSED, None)}
    # a loud one carries through the wall
    loud = _by(perceivers(sc, ACTION, LOUD))
    assert loud["bard"] == (HEARD, None) and "spy" not in loud
    # speech: speaker knows it, listeners are told by the speaker, outside hears loud only
    quiet = _by(perceivers(sc, SPEECH, 0.3, speaker="innkeeper"))
    assert quiet == {PLAYER: (TOLD, "innkeeper"), "innkeeper": (WITNESSED, None)}
    assert _by(perceivers(sc, SPEECH, 0.9, speaker="innkeeper"))["bard"] == (HEARD, "innkeeper")
    # narrator description is perceived by nobody
    assert perceivers(sc, DESCRIPTION, 1.0) == []


def test_engine_computes_knowers_from_scene_not_extractor():
    script = {
        "narrator": ["N."],
        "npc": ["The mill howls at night."],
        "extractor": [diff(fact("Something howls at the mill", "innkeeper", 0.3),
                           fact("A shout echoed from the cellar", "innkeeper", 0.9))],
    }
    # bard in the room, spy outside, nobody else exists in the scene
    eng, _ = make_engine(script, present=(PLAYER, "innkeeper", "bard"), outside=("spy",))
    eng.turn("Tell me", speakers=["innkeeper"])
    t = eng.scene.time
    assert [f.content for f in eng.facts.visible_to("bard", t)] == [
        "Something howls at the mill", "A shout echoed from the cellar"]
    # outside hears only the loud one
    assert [f.content for f in eng.facts.visible_to("spy", t)] == ["A shout echoed from the cellar"]
    # someone who is not in the scene at all knows nothing
    eng2, _ = make_engine({"narrator": ["N."], "npc": ["x"], "extractor": [diff(fact("q", "innkeeper"))]},
                          present=(PLAYER, "innkeeper"))
    eng2.turn("hi", speakers=["innkeeper"])
    assert eng2.facts.visible_to("bard", eng2.scene.time) == []


def test_observable_narration_actions_reach_present_characters():
    script = {
        "narrator": [narr("Rain.", actions=["Geralt draws his silver sword"])],
        "npc": ["Easy there, witcher."],
        "extractor": [diff(fact("Geralt drew a silver sword", "action1"),
                           fact("The inn smells of smoke", "narration"))],
    }
    eng, prov = make_engine(script, present=(PLAYER, "innkeeper", "bard"))
    eng.turn("I draw my sword", speakers=["innkeeper"])
    t = eng.scene.time
    for who in ("innkeeper", "bard", PLAYER):
        got = eng.facts.visible_to(who, t)
        assert [f.content for f in got] == ["Geralt drew a silver sword"], who
        assert got[0].knowers[0].how == WITNESSED
    # the raw action also shows up in the NPC's witnessed history, so the innkeeper's call saw it
    npc_prompt = [m for model, m in prov.calls if model == "npc"][0][1]["content"]
    assert "Geralt draws his silver sword" in npc_prompt
    # the scene description is not perceived by anyone
    assert "smells of smoke" not in npc_prompt


def test_source_recorded_on_second_hand_knowledge():
    script = {
        "narrator": ["N."],
        "npc": ["Something howled by the old mill."],
        "extractor": [diff(fact("Something howled by the old mill", "innkeeper"))],
    }
    eng, _ = make_engine(script)
    res = eng.turn("what happened?", speakers=["innkeeper"])
    ev = res.utterances[0]
    [f] = eng.facts.visible_to("bard", eng.scene.time)
    [k] = [k for k in f.knowers if k.character == "bard"]
    assert (k.how, k.source, k.event_id) == (TOLD, "innkeeper", ev.id)
    # the speaker's own knowledge is first-hand
    [ki] = [k for k in f.knowers if k.character == "innkeeper"]
    assert (ki.how, ki.source) == (WITNESSED, None)
    # NPC context shows the source
    prompt = " ".join(m["content"] for m in eng.ctx.character("bard", eng.scene))
    assert "Something howled by the old mill (heard from Innkeeper)" in prompt


def test_player_is_treated_like_any_other_source():
    script = {
        "narrator": ["N."],
        "npc": ["Hm."],
        "extractor": [diff(fact("A witcher is hunting a beast", "player"))],
    }
    eng, _ = make_engine(script)
    eng.turn("I am hunting a beast", speakers=["innkeeper"])
    [f] = eng.facts.visible_to("innkeeper", eng.scene.time)
    [k] = [k for k in f.knowers if k.character == "innkeeper"]
    assert (k.how, k.source) == (TOLD, PLAYER)
    prompt = " ".join(m["content"] for m in eng.ctx.character("innkeeper", eng.scene))
    assert "(heard from Geralt)" in prompt
