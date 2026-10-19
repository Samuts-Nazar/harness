"""Task 14: the player's actions (asterisks) are observable actions; only speech is said."""
import pytest

from harness.models import ACTION, PLAYER, UTTERANCE
from harness.player_input import ACTION as A, SPEECH as S, Part, render_for_model, split_input
from conftest import diff, fact, make_engine, narr


def test_plain_text_is_one_speech_part_untouched():
    assert split_input("  Привіт  ") == [Part(S, "  Привіт  ")]
    assert split_input("   ") == []


def test_actions_in_asterisks_and_speech_in_order():
    text = "*не піднімаючи очей* Я так розумію, ви маєте справу? *киває*"
    assert split_input(text) == [Part(A, "не піднімаючи очей"),
                                 Part(S, "Я так розумію, ви маєте справу?"), Part(A, "киває")]


def test_unclosed_asterisk_makes_the_rest_an_action_and_runs_count_once():
    assert split_input("Стою. *підходжу до столу") == [Part(S, "Стою."),
                                                      Part(A, "підходжу до столу")]
    assert split_input("**киваю** Так.") == [Part(A, "киваю"), Part(S, "Так.")]
    assert split_input("* *") == []


def test_model_sees_what_is_done_and_what_is_said():
    parts = split_input("*сідаю* Добрий вечір.")
    assert render_for_model(parts, "*сідаю* Добрий вечір.") == "does: сідаю\nsays: Добрий вечір."
    assert render_for_model(split_input("Добрий вечір."), "Добрий вечір.") == "Добрий вечір."


RAW = "*не піднімаючи очей* Ви до мене? *повільно п'є*"


def run():
    script = {"narrator": [narr("N.")], "npc": ["Так."], "extractor": [diff(
        fact("The stranger keeps his eyes down", "paction1", 0.4),
        fact("The stranger asks if they came for him", "player", 0.3))]}
    eng, prov = make_engine(script, present=(PLAYER, "innkeeper", "bard"))
    res = eng.turn(RAW, speakers=["innkeeper"])
    return eng, prov, res


def test_actions_are_events_everyone_present_saw_and_speech_is_said():
    eng, prov, _ = run()
    acts = [e for e in eng.log.active([ACTION]) if e.payload.get("actor") == PLAYER]
    assert [a.payload["text"] for a in acts] == ["не піднімаючи очей", "повільно п'є"]
    assert all(set(a.witnesses) == {PLAYER, "innkeeper", "bard"} for a in acts)
    said = [e for e in eng.log.active([UTTERANCE]) if e.payload["speaker"] == PLAYER]
    assert [s.payload["text"] for s in said] == ["Ви до мене?"], "only the speech is said"
    first = min(acts + said, key=lambda e: e.id)
    assert first.payload["raw"] == RAW, "the player's text is kept verbatim"


def test_npc_sees_the_action_as_an_action_and_the_speech_as_a_line():
    eng, prov, _ = run()
    npc = "\n".join(m["content"] for m in next(c for c in prov.calls if c[0] == "npc")[1])
    assert "[you see] Geralt does: не піднімаючи очей" in npc
    assert "Geralt: Ви до мене?" in npc
    assert "*" not in npc


def test_narrator_is_told_which_is_which():
    eng, prov, _ = run()
    nar = "\n".join(m["content"] for m in next(c for c in prov.calls if c[0] == "narrator")[1])
    assert "does: не піднімаючи очей\nsays: Ви до мене?\ndoes: повільно п'є" in nar


def test_facts_from_an_action_are_witnessed_and_from_speech_told():
    eng, _, res = run()
    by_text = {f.content: f for f in (eng.facts.get(i) for i in res.fact_ids)}
    a = by_text["The stranger keeps his eyes down"]
    s = by_text["The stranger asks if they came for him"]
    assert {(k.character, k.how) for k in a.knowers} >= {("bard", "witnessed")}
    assert {(k.character, k.how) for k in s.knowers} >= {("bard", "told")}


def test_a_failed_turn_rolls_the_action_events_back():
    from harness.pipeline import ExtractionRejected

    eng, _ = make_engine({"narrator": ["N."], "npc": ["Так."], "extractor": ["junk", "junk"]})
    with pytest.raises(ExtractionRejected):
        eng.turn("*киваю* Ну?", speakers=["innkeeper"])
    assert eng.log.active([ACTION]) == [] and eng.log.active([UTTERANCE]) == []


def test_pure_action_makes_no_utterance_for_the_player():
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Га?"], "extractor": [diff()]})
    eng.turn("*мовчки сідаю*", speakers=["innkeeper"])
    assert [e.payload["speaker"] for e in eng.log.active([UTTERANCE])] == ["innkeeper"]
