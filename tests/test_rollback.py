from harness.models import INTENT_SET, PLAYER, UTTERANCE
from conftest import diff, fact, make_engine, narr


def test_rollback_hides_event_and_derived_facts_and_cascades():
    script = {
        "narrator": [narr("N.", actions=["Geralt enters"])],
        "npc": ["I saw a stranger near the well yesterday."],
        "extractor": [
            diff(
                fact("A stranger was near the well", "innkeeper"),
                fact("Geralt entered", "action1"),
            )
        ],
    }
    eng, _ = make_engine(script)
    res = eng.turn("I enter", speakers=["innkeeper"])
    utt = res.utterances[0]
    assert len(eng.facts.visible_to("bard", eng.scene.time)) == 2  # told + saw the action
    rolled = eng.log.rollback(utt.id)
    assert utt.id in rolled
    assert [f.content for f in eng.facts.visible_to("bard", eng.scene.time)] == ["Geralt entered"]
    # facts from other segments survive
    assert [f.content for f in eng.facts.visible_to("innkeeper", eng.scene.time)] == ["Geralt entered"]
    assert eng.rollback(utt.id) == []  # engine wrapper is idempotent too
    assert utt.id not in [e.id for e in eng.log.active([UTTERANCE])]
    # events still physically in the log (append-only)
    assert eng.log.get(utt.id).id == utt.id
    # idempotent
    assert eng.log.rollback(utt.id) == []


def test_rollback_cascades_to_caused_events():
    eng, _ = make_engine({})
    a = eng.log.append("narration", game_time=0, location="Inn")
    b = eng.log.append(INTENT_SET, game_time=0, location="Inn", cause_id=a.id,
                       payload={"character": "bard", "text": "x"})
    assert set(eng.log.rollback(a.id)) == {a.id, b.id}
    assert eng.intents.pending("bard") == []


def test_failed_extraction_rolls_back_whole_turn():
    import pytest
    from harness.pipeline import ExtractionRejected

    script = {
        "narrator": ["N."],
        "npc": ["Hi."],
        "extractor": ["not json", "still not json"],
    }
    eng, _ = make_engine(script)
    with pytest.raises(ExtractionRejected):
        eng.turn("hello", speakers=["innkeeper"])
    assert eng.log.active([UTTERANCE]) == []
    assert eng.agents.agents() == []
