import json

import pytest

from harness.judge import FakeJudge
from harness.models import NARRATION
from harness.narrator import (NarrationError, has_quotes, has_speaker_line, parse_narration,
                              strip_speech)
from conftest import diff, make_engine, narr


def test_parse_narration_structure():
    o = parse_narration(narr("Rain.", ["Geralt nods"], ["innkeeper"]))
    assert (o.description, o.actions, o.speakers) == ("Rain.", ["Geralt nods"], ["innkeeper"])
    assert parse_narration('```json\n{"description": "x"}\n```').actions == []
    for bad in ["plain prose", "[]", json.dumps({"description": ""}),
                json.dumps({"description": "x", "extra": 1}),
                json.dumps({"description": "x", "observable_actions": "no"}),
                json.dumps({"description": "x", "speakers": [3]})]:
        with pytest.raises(NarrationError):
            parse_narration(bad)


def test_speech_detection_helpers():
    names = ["Innkeeper", "innkeeper"]
    assert has_speaker_line("Rain falls.\nInnkeeper: Welcome!", names)
    assert not has_speaker_line("The Innkeeper: a gruff man, nods.", names)
    assert has_quotes('He says "welcome, stranger".')
    assert strip_speech('The innkeeper grunts, "Welcome, stranger," and wipes a mug.', names) \
        == "The innkeeper grunts, and wipes a mug."
    assert strip_speech("Rain.\nInnkeeper: Welcome!\nThunder.", names) == "Rain.\n\nThunder."


def test_narrator_chooses_speakers_and_returns_structure():
    script = {"narrator": [narr("Rain.", ["The bard strums"], ["bard"])],
              "npc": ["Evening!"], "extractor": [diff()]}
    eng, prov = make_engine(script)
    res = eng.turn("hello")  # no speakers passed: the narrator decides
    assert [u.payload["speaker"] for u in res.utterances] == ["bard"]
    assert res.actions == ["The bard strums"]
    # description is narrator-only: stored as a narration event nobody witnessed
    [n] = eng.log.active([NARRATION])
    assert n.payload["text"] == "Rain." and n.witnesses == ()


def test_narrator_speakers_must_be_present_npcs():
    script = {"narrator": [narr("Rain.", [], ["spy", "player", "bard"])], "npc": ["Evening!"],
              "extractor": [diff()]}
    eng, _ = make_engine(script)
    res = eng.turn("hello")
    assert [u.payload["speaker"] for u in res.utterances] == ["bard"]
    assert any(n["kind"] == "narrator_bad_speakers" for n in eng.devlog)


def test_narrator_speech_is_rejected_and_regenerated():
    bad = narr('The innkeeper grunts.\nInnkeeper: "Get out of my inn!"')
    script = {"narrator": [bad, narr("The innkeeper grunts and points at the door.")],
              "npc": [], "extractor": [diff()]}
    eng, prov = make_engine(script)
    res = eng.turn("hello")
    assert res.narration == "The innkeeper grunts and points at the door."
    assert len([m for model, m in prov.calls if model == "narrator"]) == 2
    assert [n["kind"] for n in eng.devlog] == ["narrator_speech_rejected"]


def test_quoted_speech_goes_to_the_judge():
    quoted = narr('The innkeeper says "get out" and glares.')
    script = {"narrator": [quoted, narr("The innkeeper glares.")], "npc": [], "extractor": [diff()]}
    judge = FakeJudge({"narrator_speech": True})  # judge: yes, that is NPC speech
    eng, prov = make_engine(script, judge=judge)
    res = eng.turn("hello")
    assert res.narration == "The innkeeper glares."
    assert judge.asked and judge.asked[0][1]["q"].tag == "narrator_speech"
    # judge says the quotes are fine (e.g. the player's own words): accepted at once
    eng2, prov2 = make_engine({"narrator": [quoted], "npc": [], "extractor": [diff()]},
                              judge=FakeJudge({"narrator_speech": False}))
    assert "get out" in eng2.turn("hello").narration
    assert len([1 for model, _ in prov2.calls if model == "narrator"]) == 1


def test_narrator_speech_stripped_and_logged_after_two_retries():
    bad = narr('The innkeeper grunts, "Get out!" and turns away.', ["Innkeeper: Out!"])
    script = {"narrator": [bad, bad, bad], "npc": [], "extractor": [diff()]}
    eng, prov = make_engine(script, judge=FakeJudge({"narrator_speech": True}))
    res = eng.turn("hello")
    assert len([1 for model, _ in prov.calls if model == "narrator"]) == 3  # 1 + 2 retries
    assert res.narration == "The innkeeper grunts, and turns away."
    assert res.actions == []  # the speaker-line "action" was only speech
    kinds = [n["kind"] for n in eng.devlog]
    assert kinds.count("narrator_speech_rejected") == 3 and kinds[-1] == "narrator_speech_stripped"
    assert "Get out" not in " ".join(e.payload["text"] for e in eng.log.active([NARRATION]))


def test_single_quoted_speech_is_detected_but_apostrophes_are_not():
    names = ["Innkeeper", "innkeeper"]
    assert has_quotes("He swallows. 'A room, is it? Coin up front, witcher.' The fire crackles.")
    assert not has_quotes("Dandelion's lute falls silent and the innkeeper's hand hovers; it isn't odd.")
    assert strip_speech("He swallows. 'A room, is it?' The fire crackles.", names) \
        == "He swallows. The fire crackles."


def test_npc_line_stage_directions_and_wrapping_quotes_are_removed():
    from harness.narrator import clean_npc_line
    assert clean_npc_line("(leans forward) That's ten crowns. *wipes a mug* Up front.") \
        == "That's ten crowns. Up front."
    assert clean_npc_line('"Oh, the old mill?"') == "Oh, the old mill?"
    assert clean_npc_line('He said "no" and left') == 'He said "no" and left'
    assert clean_npc_line("(sighs)") == "(sighs)"  # never returns an empty line


def test_malformed_narrator_output_is_retried():
    script = {"narrator": ["{not json at all", narr("Fine.")], "npc": [], "extractor": [diff()]}
    eng, _ = make_engine(script)
    assert eng.turn("hello").narration == "Fine."
    assert eng.devlog[0]["kind"] == "narrator_malformed"
