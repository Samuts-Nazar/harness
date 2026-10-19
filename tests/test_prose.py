"""Task 12: free-prose narration, the scene director, NPCs hearing each other, callbacks."""
import json
import threading

import pytest

from harness.director import NOBODY, decide_speakers, parse_actions, speaker_questions
from harness.judge import FakeJudge, JudgeError
from harness.models import PLAYER, ACTION, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from conftest import PROFILES, diff, fact


def prose_engine(script, *, judge=None, present=(PLAYER, "innkeeper", "bard"), **kw):
    prov = FakeProvider(script=script)
    eng = Engine(prov, PROFILES, Scene("Inn", tuple(present), time=0), models=ModelConfig(),
                 judge=judge, record_language=None, **kw)
    return eng, prov


def director_judge(first, also=(), **rules):
    return FakeJudge({
        "director_first": first,
        "director_also": lambda q, st: any(n in q.text for n in also),
        **rules})


def calls(prov, model):
    return [m for mod, m in prov.calls if mod == model]


# -- the director as a plain function ---------------------------------------------------------
NPCS = {"innkeeper": "Innkeeper", "bard": "Dandelion"}


def test_decider_returns_the_first_speaker_then_those_who_also_speak():
    j = director_judge("bard", also=("Innkeeper",))
    assert decide_speakers(j, ["state"], NPCS) == ["bard", "innkeeper"]
    assert len(j.asked) == 1, "all questions about one state go in one batched call"


def test_nobody_is_an_answer():
    assert decide_speakers(director_judge(NOBODY, also=("Innkeeper",)), [], NPCS) == []
    assert decide_speakers(FakeJudge(), [], {}) == []


def test_cap_and_single_npc_asks_no_followups():
    three = {"a": "A", "b": "B", "c": "C"}
    j = director_judge("a", also=("B", "C"))
    assert len(decide_speakers(j, [], three, max_speakers=2)) == 2
    j = director_judge("a")
    decide_speakers(j, [], {"a": "A"})
    assert list(j.asked[0][1]) == ["first"]
    assert NOBODY in speaker_questions({"a": "A"})["first"].options


def test_followups_are_ordered_by_probability():
    from harness.judge import Judgment

    class J(FakeJudge):
        def ask(self, state, questions):
            out = super().ask(state, questions)
            out["also:b"] = Judgment(True, {"yes": 0.6, "no": 0.4}, 0.6)
            out["also:c"] = Judgment(True, {"yes": 0.9, "no": 0.1}, 0.9)
            return out

    assert decide_speakers(J({"director_first": "a"}), [], {"a": "A", "b": "B", "c": "C"},
                           max_speakers=3) == ["a", "c", "b"]


def test_parse_actions():
    assert parse_actions("- Horst draws a sword.\n2. Elza stands up.\n\n") == [
        "Horst draws a sword.", "Elza stands up."]
    assert parse_actions("none") == [] and parse_actions("None.") == []
    assert len(parse_actions("\n".join(f"A{i}." for i in range(20)), limit=3)) == 3


# -- prose narration in the engine -------------------------------------------------------------
def script():
  return {
    "narrator": ["The fire pops and the innkeeper wipes a mug."],
    "extractor": ["The innkeeper wipes a mug\nThe bard tunes a lute",
                  diff(fact("The innkeeper is wary", "narration", 0.5))],
    "npc": ["Welcome.", "Hear me sing."],
  }


def test_narrator_prompt_asks_for_prose_not_json_and_reply_is_stored_as_is():
    eng, prov = prose_engine(script(), judge=director_judge("innkeeper", also=("Dandelion",)))
    res = eng.turn("Hello.")
    p = calls(prov, "narrator")[0][1]["content"]
    assert "JSON" in p and "no JSON" in p and "observable_actions" not in p and "speakers" not in p
    assert res.narration == "The fire pops and the innkeeper wipes a mug."
    assert [u.payload["speaker"] for u in res.utterances] == ["innkeeper", "bard"]
    assert res.actions == ["The innkeeper wipes a mug", "The bard tunes a lute"]


def test_observable_actions_become_events_everyone_present_saw():
    eng, prov = prose_engine(script(), judge=director_judge("innkeeper"))
    eng.turn("Hello.")
    acts = eng.log.active([ACTION])
    assert [a.payload["text"] for a in acts] == ["The innkeeper wipes a mug",
                                                 "The bard tunes a lute"]
    assert all(set(a.witnesses) == {PLAYER, "innkeeper", "bard"} for a in acts)
    assert "[you see] The bard tunes a lute" in calls(prov, "npc")[0][1]["content"]


def test_silence_when_the_director_says_nobody():
    eng, _ = prose_engine({"narrator": ["Nothing moves."], "extractor": ["none", diff()]},
                          judge=director_judge(NOBODY))
    res = eng.turn("I wait.")
    assert res.utterances == [] and res.narration == "Nothing moves."


def test_explicit_speakers_override_the_decider():
    eng, _ = prose_engine({"narrator": ["N."], "extractor": ["none", diff()], "npc": ["Hm."]},
                          judge=director_judge("innkeeper"))
    res = eng.turn("hi", speakers=["bard"])
    assert [u.payload["speaker"] for u in res.utterances] == ["bard"]
    assert not any(t == "director_first" for _, qs in eng.judge.inner.asked
                   for t in (q.tag for q in qs.values()))


def test_decider_failure_falls_back_to_the_npcs_named_in_the_narration():
    class Down(FakeJudge):
        def ask(self, state, questions):
            if any(q.tag == "director_first" for q in questions.values()):
                raise JudgeError("down")
            return super().ask(state, questions)

    eng, _ = prose_engine({"narrator": ["Dandelion grins at you."],
                           "extractor": ["none", diff()], "npc": ["Ha."]}, judge=Down())
    res = eng.turn("hi")
    assert [u.payload["speaker"] for u in res.utterances] == ["bard"]
    assert any(n["kind"] == "director_unavailable" for n in eng.devlog)


def test_speech_in_prose_is_rejected_and_regenerated():
    judge = director_judge("innkeeper",
                           narrator_speech=lambda q, st: "go away" in st[0])
    eng, _ = prose_engine({
        "narrator": ['He growls: "go away".', "He glowers."],
        "extractor": ["none", diff()], "npc": ["Out."]}, judge=judge)
    res = eng.turn("hi")
    assert res.narration == "He glowers."
    assert any(n["kind"] == "narrator_speech_rejected" for n in eng.devlog)


def test_dialogue_dash_speech_is_caught_by_code_and_regenerated():
    from harness.narrator import has_dash_speech, strip_speech

    dashed = "Ельза опускає кухоль. — Млин стоїть біля дамби, — каже вона. За вікном дощ — ніби плаче."
    assert has_dash_speech(dashed) and not has_dash_speech("Дощ шумить — ніби хтось ступив.")
    assert strip_speech(dashed, []) == "Ельза опускає кухоль. За вікном дощ — ніби плаче."
    eng, _ = prose_engine({"narrator": [dashed, "Ельза мовчить."], "extractor": ["none", diff()],
                           "npc": ["x"]}, judge=director_judge("innkeeper"))
    assert eng.turn("hi").narration == "Ельза мовчить."


def test_a_json_answer_from_a_prose_narrator_is_tolerated():
    eng, _ = prose_engine({"narrator": [json.dumps({"description": "Rain."})],
                           "extractor": ["none", diff()], "npc": ["x"]},
                          judge=director_judge("innkeeper"))
    assert eng.turn("hi").narration == "Rain."


def test_empty_narration_is_retried():
    eng, _ = prose_engine({"narrator": ["  ", "Rain."], "extractor": ["none", diff()],
                           "npc": ["x"]}, judge=director_judge("innkeeper"))
    assert eng.turn("hi").narration == "Rain."
    assert any(n["kind"] == "narrator_malformed" for n in eng.devlog)


def test_direct_is_reusable_on_its_own():
    eng, _ = prose_engine({"extractor": ["Dandelion bows"]}, judge=director_judge("bard"))
    # the public function needs no turn: a live scene calls it on a fragment
    spk, act = eng._direct_jobs("Dandelion bows.", "I nod.", None)
    assert spk() == ["bard"] and act() == ["Dandelion bows"]


def test_json_mode_is_still_available():
    eng = Engine(FakeProvider(script={
        "narrator": [json.dumps({"description": "D.", "observable_actions": ["A"],
                                 "speakers": ["innkeeper"]})],
        "extractor": [diff()], "npc": ["x"]}), PROFILES,
        Scene("Inn", (PLAYER, "innkeeper"), time=0), narration="json")
    res = eng.turn("hi")
    assert res.actions == ["A"] and [u.payload["speaker"] for u in res.utterances] == ["innkeeper"]
    with pytest.raises(ValueError):
        Engine(FakeProvider(), PROFILES, Scene("Inn", (PLAYER,), time=0), narration="yaml")


# -- NPCs hear each other ----------------------------------------------------------------------
def test_sequential_mode_second_npc_hears_the_first():
    eng, prov = prose_engine(script(), judge=director_judge("innkeeper", also=("Dandelion",)))
    eng.turn("Hello.")
    bard_ctx = calls(prov, "npc")[1][1]["content"]
    assert "Innkeeper: Welcome." in bard_ctx


class Slow:
    """Thread-safe provider with per-call delays, to see ordering and overlap."""
    parallel_ok = True

    def __init__(self, delay=0.0):
        self.delay, self.lock, self.npc_ctx, self.t = delay, threading.Lock(), {}, []

    def complete(self, model, messages):
        import time
        sys_ = messages[0]["content"]
        if "narrator" in sys_:
            return "The fire pops."
        if "list the observable actions" in sys_:
            return "none"
        if "fact extractor" in sys_:
            return diff()
        time.sleep(self.delay)
        who = sys_.split(".")[0].removeprefix("You are ")
        with self.lock:
            self.npc_ctx[who] = messages[1]["content"]
        return {"Innkeeper": "Welcome.", "Dandelion": "Hear me sing."}[who]


def test_parallel_mode_second_npc_hears_the_first_and_delivery_order_holds():
    prov = Slow(0.05)
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0),
                 models=ModelConfig(), record_language=None,
                 judge=director_judge("innkeeper", also=("Dandelion",)))
    got = []
    res = eng.turn("Hello.", on_word=lambda who, w: got.append(who))
    assert eng.parallel
    assert "Innkeeper: Welcome." in prov.npc_ctx["Dandelion"]
    assert "Dandelion" not in prov.npc_ctx["Innkeeper"].split("Recent conversation")[-1]
    assert got[0] == "innkeeper" and got[-1] == "bard"
    assert [u.payload["speaker"] for u in res.utterances] == ["innkeeper", "bard"]


def test_hearing_can_be_switched_off_to_measure_its_cost():
    prov = Slow()
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0),
                 models=ModelConfig(), record_language=None, hear_each_other=False,
                 judge=director_judge("innkeeper", also=("Dandelion",)))
    eng.turn("Hello.")
    assert "Innkeeper: Welcome." not in prov.npc_ctx["Dandelion"]


def test_the_check_of_the_second_npc_knows_what_the_first_said():
    seen = []

    def rule(q, st):
        seen.append(" ".join(st))
        return False

    eng, _ = prose_engine(script(), judge=director_judge(
        "innkeeper", also=("Dandelion",), unknown_claim=rule))
    eng.turn("Hello.")
    assert "Innkeeper: Welcome." not in seen[0] and "Innkeeper: Welcome." in seen[1]


# -- hooks -------------------------------------------------------------------------------------
def test_on_narration_is_called_once_with_the_accepted_text_before_any_word():
    order = []
    judge = director_judge("innkeeper", narrator_speech=lambda q, st: "go away" in st[0])
    eng, _ = prose_engine({
        "narrator": ['He says "go away".', "He glowers."],
        "extractor": ["none", diff()], "npc": ["Out."]}, judge=judge)
    eng.turn("hi", on_narration=lambda t: order.append(("narr", t)),
             on_word=lambda who, w: order.append(("word", w)))
    assert order[0] == ("narr", "He glowers.") and order[1] == ("word", "Out.")
    assert sum(1 for k, _ in order if k == "narr") == 1


def test_on_narration_in_parallel_mode_never_announces_a_rejected_narration():
    prov = Slow()
    judge = director_judge("innkeeper")
    calls_ = []

    class Judge(FakeJudge):
        pass

    j = FakeJudge({"director_first": "innkeeper", "director_also": False,
                   "narrator_speech": [True, False]})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper"), time=0),
                 models=ModelConfig(), record_language=None, judge=j)
    eng.turn("hi", on_narration=calls_.append)
    assert len(calls_) == 1


def test_event_log_observers_see_every_append_and_can_unsubscribe():
    eng, _ = prose_engine(script(), judge=director_judge("innkeeper"))
    seen = []
    off = eng.log.subscribe(lambda e: seen.append(e.type))
    eng.turn("Hello.")
    assert seen[0] == "utterance" and "narration" in seen and "action" in seen
    n = len(seen)
    off()
    with pytest.raises(RuntimeError):
        eng.turn("again")  # scripts are exhausted; the turn rolls back
    assert len(seen) == n
