"""Living dialogue, task 4: the director exchange loop. Inside one turn the scene director picks,
step by step, who takes the floor next and the shape of that response, until the player is
addressed, nobody speaks, the cap, or an interrupt. Fake providers and a scripted FakeJudge."""

import pytest

from harness.decisions import CODE_CHOICE_KINDS
from harness.director import NOBODY, PLAYER_FLOOR, decide_next, next_floor_questions
from harness.judge import FakeJudge, JudgeError
from harness.models import ACTION, PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.settings import MAX_EXCHANGE_LINES
from harness.shape import Shape, shape_instruction
from harness.streaming import InterruptHandle
from conftest import diff, fact

ME = "молодий незнайомець із мечем"
PROFILES = [
    CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance=ME),
    CharacterProfile("horst", "Горст", "Староста.", appearance="кремезний сивий чоловік"),
    CharacterProfile("elza", "Ельза", "Вдова.", appearance="жінка в темній хустці"),
]
NARRATION = "Дощ стукає у вікна корчми."


def scripted(answers, rules):
    """Pops one answer per exchange step. When the turn is narrated, the opening batch (asked
    before the narration exists, only to learn whether to narrate) does not use up the script."""
    left, narrated = list(answers), rules["director_narration"] is True

    def rule(q, state):
        if narrated and not any(str(x).startswith("Narration:") for x in state):
            return None
        return left.pop(0) if len(left) > 1 else (left[0] if left else None)

    return rule


def make(npc_lines, nxt, shape, *, present=(PLAYER, "horst", "elza"), extractor=None,
         rules=None, **kw):
    script = {"narrator": [NARRATION], "npc": list(npc_lines),
              "extractor": list(extractor or ["none", diff()])}
    rules = {"director_narration": True, **(rules or {})}
    judge = FakeJudge({"director_next": scripted(nxt, rules), "director_shape": scripted(shape, rules),
                       **rules})
    prov = FakeProvider(script=script)
    kw.setdefault("record_language", None)
    eng = Engine(prov, PROFILES, Scene("Inn", tuple(present), time=0), models=ModelConfig(),
                 judge=judge, narration="prose", **kw)
    eng.acquaint("horst", "elza")
    return eng, prov, judge


def npc_prompts(prov):
    return ["\n".join(x["content"] for x in m) for mod, m in prov.calls if mod == "npc"]


def next_asks(judge):
    """The exchange steps read with a narration (the opening need-narration batch is not one)."""
    return [(st, qs) for st, qs in judge.asked if "next" in qs and "narration" not in qs]


def speakers(res):
    return [u.payload["speaker"] for u in res.utterances]


# -- the director as a plain function -----------------------------------------------------------
def test_next_floor_questions_offer_npcs_player_and_nobody_and_shapes():
    qs = next_floor_questions({"horst": "Горст", "elza": "Ельза"})
    assert set(qs) == {"next", "shape"}
    assert set(qs["next"].options) == {"horst", "elza", PLAYER_FLOOR, NOBODY}
    assert "address" in qs["next"].options[PLAYER_FLOOR]
    assert set(qs["shape"].options) == {s.value for s in Shape}


def test_decide_next_returns_choice_and_shape_in_one_batch():
    j = FakeJudge({"director_next": "elza", "director_shape": "word"})
    assert decide_next(j, ["state"], {"horst": "Горст", "elza": "Ельза"}) == ("elza", Shape.WORD)
    assert len(j.asked) == 1
    j = FakeJudge({"director_next": PLAYER_FLOOR})
    assert decide_next(j, [], {"horst": "Горст"})[0] == PLAYER_FLOOR
    assert decide_next(FakeJudge(), [], {})[0] == NOBODY


# -- the loop ------------------------------------------------------------------------------------
def test_exchange_stops_when_player_addressed():
    """Review Focus 1: addressed by how he looks («чужинцю»), his name unknown to the speaker."""
    eng, prov, judge = make(["Чого тобі треба, чужинцю?"], ["horst", PLAYER_FLOOR], ["short"])
    res = eng.turn("Заходжу і сідаю біля вогню.")
    assert res.stop_reason == "player_addressed"
    assert speakers(res) == ["horst"] and len(res.utterances) == 1
    asks = next_asks(judge)
    assert len(asks) == 2
    state = "\n".join(asks[1][0])
    assert "Чого тобі треба, чужинцю?" in state, "the director sees the line just said"
    assert ME in state, "and how the others see the player character"
    assert "Рагнар" not in npc_prompts(prov)[0], "Horst does not know the player's name"


def test_exchange_runs_npc_to_npc():
    lines = ["Ельзо, знову ти тут?", "А де ж мені ще бути, старосто?", "Іди додому."]
    eng, prov, judge = make(lines, ["horst", "elza", "horst", NOBODY], ["short"])
    res = eng.turn("Мовчки п'ю.")
    assert speakers(res) == ["horst", "elza", "horst"]
    assert [u.payload["text"] for u in res.utterances] == lines
    assert res.stop_reason == "nobody"
    prompts = npc_prompts(prov)
    assert len(prompts) == 3
    assert lines[0] in prompts[1]
    assert lines[0] in prompts[2] and lines[1] in prompts[2]
    assert len(next_asks(judge)) == 4
    # each later decision sees every line so far
    assert all(x in "\n".join(next_asks(judge)[3][0]) for x in lines)


def test_repeat_speaker_gets_distinct_extractor_segments():
    lines = ["Ельзо, знову ти тут?", "А де ж мені ще бути?", "Іди додому."]
    eng, prov, _ = make(lines, ["horst", "elza", "horst", NOBODY], ["short"])
    eng.turn("Мовчки п'ю.")
    ex = [m for mod, m in prov.calls if mod == "extractor"][-1]
    body = "\n".join(x["content"] for x in ex)
    assert lines[0] in body and lines[2] in body
    assert "horst~2" in body


def test_exchange_cap():
    """Review Focus 4: a runaway exchange stops at the cap, without asking the director again."""
    lines = [f"Слово номер {i}." for i in range(MAX_EXCHANGE_LINES + 2)]
    eng, prov, judge = make(lines, ["horst", "elza"] * 10, ["short"])
    res = eng.turn("Слухаю.")
    assert MAX_EXCHANGE_LINES == 6
    assert len(res.utterances) == MAX_EXCHANGE_LINES
    assert res.stop_reason == "cap"
    assert len(next_asks(judge)) == MAX_EXCHANGE_LINES
    assert len(npc_prompts(prov)) == MAX_EXCHANGE_LINES
    assert any(n["kind"] == "exchange_cap" for n in eng.devlog)
    assert "exchange_cap" in CODE_CHOICE_KINDS
    assert res.decisions.code_choices >= 1


def test_interrupt_in_third_line_cancels_rest():
    """Review Focus 3: the cut is the last thing that happens; extraction sees the spoken part."""
    lines = ["Перший рядок тут.", "Другий рядок тут.", "Третій рядок довгий і не скінчиться.",
             "Четвертий рядок."]
    extractor = ["none", diff(fact("Horst starts a third remark", "horst~2"))]
    eng, prov, judge = make(lines, ["horst", "elza", "horst", "elza"], ["short"],
                            extractor=extractor)
    h = InterruptHandle()

    def on_word(npc, w):
        if w == "Третій":
            h.request()

    res = eng.turn("Слухаю.", handle=h, on_word=on_word)
    assert len(res.utterances) == 3
    assert res.interrupted and res.stop_reason == "interrupted"
    assert res.utterances[-1].payload["text"] == "Третій"
    assert res.utterances[-1].payload["interrupted"] is True
    assert len(npc_prompts(prov)) == 3, "no 4th line is generated"
    assert len(next_asks(judge)) == 3, "and the director is not asked again"
    ex = "\n".join(x["content"] for x in [m for mod, m in prov.calls if mod == "extractor"][-1])
    assert "Третій" in ex and "не скінчиться" not in ex
    assert "Четвертий" not in ex
    assert res.fact_ids, "the fact from the cut line's segment is stored"


def test_silence_shape_writes_no_speech():
    """Review Focus 2: silence is a legitimate result and the turn stays readable."""
    eng, prov, judge = make([], ["horst", NOBODY], ["silence"], present=(PLAYER, "horst"))
    res = eng.turn("Дивлюся на нього.")
    assert res.utterances == []
    assert npc_prompts(prov) == [], "no NPC call for silence"
    assert res.narration == NARRATION
    notes = [n for n in eng.devlog if n["kind"] == "silence"]
    assert notes and notes[0]["npc"] == "horst"
    assert ("silence", "horst", "") in res.exchange
    assert res.stop_reason == "nobody"


def test_gesture_shape_is_an_action_not_speech():
    eng, prov, _ = make(["Горст знизує плечима."], ["horst", NOBODY], ["gesture"],
                        present=(PLAYER, "horst"))
    res = eng.turn("Скільки?")
    assert res.utterances == []
    acts = [e for e in eng.log.active([ACTION]) if e.payload.get("by") == "horst"]
    assert len(acts) == 1 and "знизує плечима" in acts[0].payload["text"]
    assert res.exchange[0][0] == "gesture" and res.exchange[0][1] == "horst"
    assert shape_instruction(Shape.GESTURE, None, name="Горст") in npc_prompts(prov)[0]


def test_shape_is_passed_and_overlong_line_regenerated_then_trimmed():
    long = "Ні. " + " ".join(["Слово"] * 30) + "."
    eng, prov, _ = make([long, long], ["horst", NOBODY], ["word"], present=(PLAYER, "horst"))
    res = eng.turn("Так чи ні?")
    prompts = npc_prompts(prov)
    assert len(prompts) == 2, "regenerated once"
    assert shape_instruction(Shape.WORD, None, bounds=(1, 2), name="Горст") in prompts[0]
    assert res.utterances[0].payload["text"].split()[0] == "Ні."
    assert len(res.utterances[0].payload["text"].split()) <= 2
    kinds = [n["kind"] for n in eng.devlog]
    assert "shape_regenerated" in kinds and "shape_trimmed" in kinds


def test_director_unavailable_falls_back_then_stops():
    class Broken(FakeJudge):
        def ask(self, state, questions):
            if "next" in questions:
                raise JudgeError("down")
            return super().ask(state, questions)

    prov = FakeProvider(script={"narrator": ["Тиша."], "npc": ["Ну?"],
                                "extractor": ["none", diff()]})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "horst"), time=0), models=ModelConfig(),
                 judge=Broken(), narration="prose", record_language=None)
    res = eng.turn("Добрий вечір.")
    assert speakers(res) == ["horst"] and res.stop_reason == "nobody"
    assert any(n["kind"] == "director_unavailable" for n in eng.devlog)


def test_explicit_speakers_bypass_the_director():
    eng, prov, judge = make(["Ну?"], [NOBODY], ["short"])
    res = eng.turn("Добрий вечір.", speakers=["horst"])
    assert speakers(res) == ["horst"] and next_asks(judge) == []


def test_classic_mode_unchanged():
    """dialogue="classic": the task 12 director (first speaker, then who also speaks), at most
    MAX_SPEAKERS, no next-floor question. The task 12/14/19 suites that script that director run
    unchanged in classic mode (tests/conftest.py, CLASSIC_DIRECTOR_MODULES)."""
    judge = FakeJudge({"director_first": "elza",
                       "director_also": lambda q, st: "Горст" in q.text})
    prov = FakeProvider(script={"narrator": [NARRATION], "npc": ["Один.", "Два."],
                                "extractor": ["none", diff()]})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "horst", "elza"), time=0),
                 models=ModelConfig(), judge=judge, narration="prose", record_language=None,
                 dialogue="classic")
    res = eng.turn("Добрий вечір.")
    assert speakers(res) == ["elza", "horst"]
    assert next_asks(judge) == []
    assert all("next" not in qs for _, qs in judge.asked)
    with pytest.raises(ValueError):
        Engine(FakeProvider(), PROFILES, Scene("Inn", (PLAYER,)), dialogue="chaos")


def test_exchange_log_is_the_same_in_parallel_mode():
    """The next-floor decision reads only main-thread state: same events either way."""
    def run(parallel):
        lines = ["Ельзо, знову ти тут?", "А де ж мені бути?", "Іди додому."]
        eng, prov, _ = make(lines, ["horst", "elza", "horst", NOBODY], ["short"],
                            parallel=parallel)
        eng.turn("Мовчки п'ю.")
        return [(e.type, e.payload.get("speaker"), e.payload.get("text"))
                for e in eng.log.active()]

    assert run(False) == run(True)


# -- fix round 1 ---------------------------------------------------------------------------------
def test_interrupt_between_steps_stops_before_the_next_ask():
    """The player cuts in after line 1 is delivered, before step 2: nothing more is asked or said."""
    eng, prov, judge = make(["Перший рядок.", "Другий рядок."], ["horst", "elza", NOBODY],
                            ["short"])
    h = InterruptHandle()

    def on_word(npc, w):
        if w == "рядок.":  # the last word of line 1: delivered whole, then the handle fires
            h.request()

    res = eng.turn("Слухаю.", handle=h, on_word=on_word)
    assert [u.payload["text"] for u in res.utterances] == ["Перший рядок."]
    assert res.interrupted and res.stop_reason == "interrupted"
    assert len(next_asks(judge)) == 1 and len(npc_prompts(prov)) == 1
    assert all(u.payload["text"] for u in res.utterances), "no empty utterance"
    assert any(n["kind"] == "exchange_interrupted" for n in eng.devlog)


def test_interrupt_before_a_gesture_step_writes_nothing():
    eng, prov, judge = make(["Перший рядок."], ["horst", "elza", NOBODY],
                            ["short", "gesture"])
    h = InterruptHandle()
    res = eng.turn("Слухаю.", handle=h, on_word=lambda n, w: h.request() if w == "рядок." else None)
    assert len(res.utterances) == 1 and res.stop_reason == "interrupted"
    assert [e for e in eng.log.active([ACTION]) if e.payload.get("by") == "elza"] == []
    assert len(next_asks(judge)) == 1 and len(npc_prompts(prov)) == 1


def test_same_npc_never_takes_two_steps_in_a_row():
    lines = ["Раз.", "Два.", "Три."]
    eng, prov, judge = make(lines, ["horst", "horst", "elza"], ["short"])
    res = eng.turn("Слухаю.")
    assert speakers(res) == ["horst"]
    assert res.stop_reason == "nobody"
    assert any(n["kind"] == "same_speaker_stopped" for n in eng.devlog)
    assert "same_speaker_stopped" in CODE_CHOICE_KINDS


def test_default_offline_judge_gives_one_line_then_the_player():
    prov = FakeProvider(script={"narrator": ["Тиша."], "npc": [f"Рядок {i}." for i in range(8)],
                                "extractor": ["none", diff()]})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "horst", "elza"), time=0),
                 models=ModelConfig(), narration="prose", record_language=None)
    assert eng.dialogue == "living"
    res = eng.turn("Добрий вечір.")
    assert 1 <= len(res.utterances) <= 2 and res.stop_reason != "cap"


def test_offline_app_stack_in_living_mode_gives_one_or_two_lines():
    from app.stacks import fake_stack
    from harness.style import Style

    st = fake_stack()
    prof = [CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance=ME),
            CharacterProfile("horst", "Горст", "Староста."),
            CharacterProfile("elza", "Ельза", "Вдова.")]
    eng = Engine(st.provider, prof, Scene("Inn", (PLAYER, "horst", "elza"), time=0),
                 models=st.models, judge=st.judge, style=Style.load("witcher", exemplars=False),
                 dialogue="living")
    for text in ("Добрий вечір.", "Що чути?", "Ну?"):
        res = eng.turn(text)
        assert 1 <= len(res.utterances) <= 2, (text, res.stop_reason, len(res.utterances))


# -- task 5: narration only when needed ----------------------------------------------------------
def narrator_calls(prov):
    return [m for mod, m in prov.calls if mod == "narrator"]


def test_quick_exchange_skips_narrator():
    eng, prov, judge = make(["Чого тобі?"], ["horst", PLAYER_FLOOR], ["short"],
                            rules={"director_narration": False})
    words, narrated = [], []
    res = eng.turn("Так.", on_word=lambda n, w: words.append(w), on_narration=narrated.append)
    assert narrator_calls(prov) == [] and res.narration == "" and narrated == []
    assert speakers(res) == ["horst"] and words
    assert res.stop_reason == "player_addressed"
    assert eng.log.active(["narration"]) == []
    # one batch carried the narration question and the first step; the second step is its own call
    first = judge.asked[0][1]
    assert {"narration", "next", "shape"} <= set(first)
    assert "Narration:" not in "\n".join(judge.asked[0][0])
    assert any(n["kind"] == "narration_skipped" for n in eng.devlog)
    assert "narration_skipped" in CODE_CHOICE_KINDS


def test_narration_yes_narrates_as_before():
    eng, prov, judge = make(["Чого тобі?"], ["horst", PLAYER_FLOOR], ["short"])
    res = eng.turn("Заходжу.")
    assert len(narrator_calls(prov)) == 1 and res.narration == NARRATION
    assert not any(n["kind"] == "narration_skipped" for n in eng.devlog)


def test_classic_mode_always_narrates_and_never_asks():
    eng, prov, judge = make(["Привіт."], [], [], dialogue="classic",
                            rules={"director_narration": False})
    res = eng.turn("Заходжу.")
    assert len(narrator_calls(prov)) == 1 and res.narration == NARRATION
    assert all("narration" not in qs for _, qs in judge.asked)


def test_outcome_forces_narration():
    eng, prov, judge = make(["Чого тобі?"], ["horst", PLAYER_FLOOR], ["short"], outcomes=True,
                            rules={"director_narration": False, "outcome_attempt": True})
    res = eng.turn("Б'ю Горста кулаком.")
    assert res.narration and len(narrator_calls(prov)) == 1
    assert all("narration" not in qs for _, qs in judge.asked)


def test_interrupt_before_first_step_without_narration_writes_nothing():
    eng, prov, judge = make(["Не буде."], ["horst"], ["short"], rules={"director_narration": False})
    h = InterruptHandle()
    h.request()
    res = eng.turn("Так.", handle=h)
    assert res.interrupted and res.utterances == [] and res.narration == ""
    assert npc_prompts(prov) == []


def test_skipped_narration_in_parallel_mode_matches_sequential():
    def run(parallel):
        eng, prov, _ = make(["Чого тобі?"], ["horst", PLAYER_FLOOR], ["short"], parallel=parallel,
                            rules={"director_narration": False})
        eng.turn("Так.")
        return [(e.type, e.payload.get("speaker"), e.payload.get("text"))
                for e in eng.log.active()]

    assert run(False) == run(True)


def test_default_offline_judge_narrates_first_turn_then_usually_not():
    prov = FakeProvider(script={"narrator": ["Тиша."] * 4, "npc": [f"Рядок {i}." for i in range(8)],
                                "extractor": ["none", diff()] * 4})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "horst", "elza"), time=0),
                 models=ModelConfig(), narration="prose", record_language=None)
    assert eng.turn("Добрий вечір.").narration == "Тиша."
    assert eng.turn("Що чути?").narration == ""
    assert len(narrator_calls(prov)) == 1


def test_no_narration_but_nobody_to_answer_still_narrates():
    for first in (NOBODY, PLAYER_FLOOR):
        eng, prov, _ = make([], [first], ["short"], rules={"director_narration": False})
        res = eng.turn("Так.")
        assert res.narration == NARRATION and len(narrator_calls(prov)) == 1, first


def test_no_narration_in_a_scene_without_npcs_still_narrates():
    eng, prov, _ = make([], [NOBODY], ["short"], present=(PLAYER,),
                        rules={"director_narration": False})
    res = eng.turn("Дивлюсь у вікно.")
    assert res.narration == NARRATION and len(narrator_calls(prov)) == 1


def test_classic_launch_with_empty_narration_still_writes_the_narration_event():
    from harness.narrator import NarratorOutput

    eng, prov, _ = make([], [], [], dialogue="classic")
    evs = []
    launch = eng._launch(NarratorOutput(""), "Так.", None, evs, check=False)
    assert [e.type for e in launch.events][0] == "narration" and "narration" in launch.sources


# -- the engine uses the world profile (living dialogue, task 6) -------------------------------
def _witcher():
    from harness.profile import load_profile
    p = load_profile("witcher")
    assert p is not None
    return p


def test_distance_speech_only_leaves_out_narration_metrics():
    from harness.profile import distance
    p = _witcher()
    e = __import__("harness.profile", fromlist=["x"]).profile_of_lines(["— Ні.", "— Так, піду."])
    full, sp = distance(e, p), distance(e, p, speech_only=True)
    assert "speaker_run_mean" in full and "narration_median_words" in full
    assert set(sp) == {"median_words", "question_share", "no_beat_share", "length_bins_l1"}


def test_shape_question_prior_comes_from_the_profile():
    p = _witcher()
    pct = round(100 * (p.length_bins["1"] + p.length_bins["2-3"]))
    from harness.shape import shape_prior
    assert shape_prior(p) == f"In this world about {pct}% of replies are 1-3 words."
    assert shape_prior(None) == ""
    npcs = {"horst": "Горст"}
    with_prior = next_floor_questions(npcs, shape_prior(p))["shape"].text
    assert f"about {pct}% of replies" in with_prior
    assert "% of replies" not in next_floor_questions(npcs)["shape"].text


def test_engine_asks_with_prior_only_when_a_profile_is_loaded():
    for prof in (_witcher(), None):
        eng, prov, judge = make(["— Так."], ["horst", PLAYER_FLOOR], ["word"],
                                world_profile=prof)
        eng.turn("Добрий вечір.", speakers=None)
        texts = [qs["shape"].text for _, qs in next_asks(judge)]
        assert texts and all(("% of replies" in t) == (prof is not None) for t in texts)


def test_session_profile_in_debug():
    eng, prov, judge = make(["— Так.", "— Ні, не піду.", "— Гаразд."], ["horst", "elza", "horst", PLAYER_FLOOR],
                            ["word"], world_profile=_witcher())
    assert eng.dialogue_report() is None
    eng.turn("Добрий вечір.", speakers=None)
    rep = eng.dialogue_report()
    assert rep is not None and "median_words" in rep and rep["n_lines"] >= 1
    assert set(rep["distance"]) == {"median_words", "question_share", "no_beat_share",
                                    "length_bins_l1"}


def test_session_profile_without_world_profile_has_no_distance():
    eng, *_ = make(["— Так."], ["horst", PLAYER_FLOOR], ["word"])
    eng.turn("Добрий вечір.", speakers=None)
    rep = eng.dialogue_report()
    assert rep["median_words"] >= 1 and rep["distance"] is None


# -- task 12 fixes ---------------------------------------------------------------------------------
def test_extractor_citing_display_name_with_repeat_suffix_maps_to_segment_key():
    """The extractor names Horst's second line «Горст~2» (display name + ~N); it is the segment
    `horst~2`, not an unknown source that rolls the turn back."""
    lines = ["Ельзо, знову ти тут?", "А де ж мені ще бути?", "Іди додому."]
    extractor = ["none", diff(fact("Horst tells Elza to go home", "Горст~2"),
                              fact("Elza asks where else she would be", "Ельза"))]
    eng, prov, _ = make(lines, ["horst", "elza", "horst", NOBODY], ["short"], extractor=extractor)
    res = eng.turn("Мовчки п'ю.")
    assert eng.slow_failure is None
    assert len(res.fact_ids) == 2
    third = res.utterances[2].id
    assert [f.content for f in eng.facts.by_source_event(third)] == ["Horst tells Elza to go home"]


def test_pipeline_parses_npc_lines_with_the_known_names():
    """A beat with no verb the parser knows («Ельза знову до вікна») is still a beat because it
    names a character (Task 11 `names=`): the speech payload and the NPC's action follow it."""
    from harness.style import Style
    line = "— Ні, — Ельза знову до вікна. — Іди геть."
    eng, prov, _ = make([line], ["elza", NOBODY], ["short"], style=Style(), present=(PLAYER, "elza"),
                        extractor=["none", "говорить тихо", diff()])
    res = eng.turn("Ти підеш зі мною?")
    assert res.utterances[0].payload["speech"] == "Ні. Іди геть."
    acts = [e.payload["text"] for e in eng.log.active([ACTION]) if e.payload.get("by") == "elza"]
    assert acts == ["Ельза знову до вікна."]


def test_fit_to_shape_counts_speech_with_names():
    from harness.shape import fit_to_shape
    line = "— Ні, — Ельза знову до вікна і довго дивиться в темряву. — Іди."
    assert fit_to_shape(line, Shape.WORD, (1, 2), names=["Ельза"])[1] == "ok"
    assert fit_to_shape(line, Shape.WORD, (1, 2))[1] == "regenerate"


def test_tidy_speaker_strips_own_label_prefix_and_opens_with_speech():
    from harness.style import tidy_speaker
    own = ["Горст", "кремезний сивий чоловік"]
    # a description used as a speaker prefix
    assert tidy_speaker("кремезний сивий чоловік: — Двадцять крон. Не більше.", own) == \
        "— Двадцять крон. Не більше."
    # the name repeated after the label: the line opens with the speech, the beat follows it
    assert tidy_speaker("Ельза: Ельза потерла край фартуха. — А якщо вернеться не весь?",
                        ["Ельза", "жінка в темній хустці"], ["Ельза"]) == \
        "— А якщо вернеться не весь? — Ельза потерла край фартуха."
    assert tidy_speaker("Горст переклав очі на меч. — Скільки?", own, ["Горст"]) == \
        "— Скільки? — Горст переклав очі на меч."
    # untouched: book-form lines, another character's name, plain speech
    for t in ("— Ні, — Горст сплюнув. — Не піду.", "Ні. Не піду.", "Ельзо, йди додому."):
        assert tidy_speaker(t, own, ["Горст"]) == t


def test_npc_line_with_own_prefix_is_tidied_in_the_engine():
    from harness.style import Style
    line = "Горст: Горст переклав очі на меч. — Скільки?"
    eng, prov, _ = make([line], ["horst", NOBODY], ["short"], style=Style(),
                        present=(PLAYER, "horst"), extractor=["none", "говорить тихо", diff()])
    res = eng.turn("Я візьмуся.")
    text = res.utterances[0].payload["text"]
    assert text.startswith("— Скільки?") and "Горст:" not in text
    assert res.utterances[0].payload["speech"] == "Скільки?"


def test_script_switch_in_npc_line_is_regenerated_once():
    from harness.style import foreign_runs
    assert foreign_runs("— Так, Geralt. 天天爱彩票", "Ukrainian") == ["天天爱彩票"]
    assert foreign_runs("— Так, Geralt, — сказав він. «Ні!» 1272 р.", "Ukrainian") == []
    assert foreign_runs("Ні. 天天", None) == []  # no output language: no check
    eng, prov, _ = make(["— Так. 天天爱彩票", "— Так, піду."], ["horst", NOBODY], ["short"],
                        present=(PLAYER, "horst"), output_language="Ukrainian")
    res = eng.turn("Підеш?")
    assert res.utterances[0].payload["text"] == "— Так, піду."
    assert any(n["kind"] == "script_regenerated" for n in eng.devlog)


def test_script_switch_twice_cuts_the_foreign_run():
    eng, prov, _ = make(["— Так. 天天爱彩票", "— Ні 天天, не піду."], ["horst", NOBODY], ["short"],
                        present=(PLAYER, "horst"), output_language="Ukrainian")
    res = eng.turn("Підеш?")
    assert res.utterances[0].payload["text"] == "— Ні, не піду."
    kinds = [n["kind"] for n in eng.devlog]
    assert "script_regenerated" in kinds and "script_cut" in kinds
    assert {"script_regenerated", "script_cut"} <= CODE_CHOICE_KINDS


def test_script_switch_in_narration_is_regenerated():
    eng, prov, _ = make(["— Так."], ["horst", NOBODY], ["short"], present=(PLAYER, "horst"),
                        output_language="Ukrainian")
    prov.script["narrator"] = ["Дощ стукає у вікна. 天天爱彩票", NARRATION]
    res = eng.turn("Сідаю.")
    assert res.narration == NARRATION


# -- shapes sampled against the profile, the beat drawn per line (Task 12) ----------------------
def _style_make(lines, nxt, shape, **kw):
    from harness.style import Style
    return make(lines, nxt, shape, style=Style(), world_profile=_witcher(),
                extractor=["none", "говорить тихо", "говорить повільно", diff()], **kw)


def test_with_a_profile_code_samples_the_shape_and_logs_it(monkeypatch):
    import harness.pipeline as pl
    seen = {}

    def fake_sample(weights, rng):
        seen["weights"] = dict(weights)
        return Shape.LONG

    monkeypatch.setattr(pl, "sample_shape", fake_sample)
    eng, prov, _ = _style_make(["— " + " ".join(["слово"] * 20) + "."], ["horst", NOBODY],
                               ["short"], present=(PLAYER, "horst"))
    eng.turn("Розкажи.")
    note = next(n for n in eng.devlog if n["kind"] == "shape_sampled")
    assert note["decider"] == "short" and note["shape"] == "long"
    assert "shape_sampled" in CODE_CHOICE_KINDS
    assert seen["weights"][Shape.LONG] > 0, "the profile's long tail is reachable"
    prompt = npc_prompts(prov)[0]
    assert shape_instruction(Shape.LONG, None, bounds=(16, 80), name="Горст") in prompt


def test_sampling_is_reproducible_for_the_same_seed():
    def run():
        eng, *_ = _style_make(["— Так.", "— Ні, не піду.", "— Гаразд."],
                              ["horst", "elza", "horst", PLAYER_FLOOR], ["normal"])
        eng.turn("Добрий вечір.")
        return [(n["shape"], n["beat"]) for n in eng.devlog if n["kind"] == "shape_sampled"]
    a = run()
    assert a and a == run()


def test_no_beat_line_is_told_so_and_a_beat_written_anyway_is_stripped(monkeypatch):
    import harness.pipeline as pl
    monkeypatch.setattr(pl, "beat_wanted", lambda *a, **k: False)
    monkeypatch.setattr(pl, "sample_shape", lambda w, r: Shape.SHORT)
    eng, prov, _ = _style_make(["— Не знаю, — Горст почухав потилицю. — Спитай Ельзу."],
                               ["horst", NOBODY], ["short"], present=(PLAYER, "horst"))
    res = eng.turn("Хто знає?")
    assert "No gesture this line" in npc_prompts(prov)[0]
    assert res.utterances[0].payload["text"] == "— Не знаю. Спитай Ельзу."
    assert any(n["kind"] == "beat_stripped" for n in eng.devlog)
    assert "beat_stripped" in CODE_CHOICE_KINDS
    assert not [e for e in eng.log.active([ACTION]) if e.payload.get("by") == "horst"]


def test_beat_line_is_told_to_carry_one(monkeypatch):
    import harness.pipeline as pl
    monkeypatch.setattr(pl, "beat_wanted", lambda *a, **k: True)
    eng, prov, _ = _style_make(["— Так, — Горст кивнув."], ["horst", NOBODY], ["short"],
                               present=(PLAYER, "horst"))
    eng.turn("Так?")
    assert "one small action" in npc_prompts(prov)[0]


def test_without_a_profile_the_deciders_shape_is_used_as_before():
    eng, prov, _ = make(["— Так."], ["horst", NOBODY], ["word"], present=(PLAYER, "horst"))
    eng.turn("Так?")
    assert not any(n["kind"] == "shape_sampled" for n in eng.devlog)
    assert shape_instruction(Shape.WORD, None, bounds=(1, 2), name="Горст") in npc_prompts(prov)[0]


# -- Task 12 fix round 1 ----------------------------------------------------------------------
LIVE_1 = ("Горст притиснув рукавом пивну калюжу, а другою рукою перевернув на столі стертий мідяк. "
          "На меч глянув і відразу — до дверей. — За двох хлопців мірошник би дав більше. Та "
          "мірошника нема. — Він замовк, потер великим пальцем мідяк. — І не за самий лемент.")
LIVE_2 = ("Ельза витерла палець об фартух. Очі ковзнули до дверей млина — ні, до дверей корчми, — "
          "й назад. — Кров була. А хто її змивав, Горсте?")


def test_tidy_speaker_never_splits_at_a_dash_inside_the_opening_beat():
    """Review round 1: a dash inside a multi-sentence opening beat is punctuation; the live lines
    are left intact (they are never reordered at that dash)."""
    from harness.style import tidy_speaker
    assert tidy_speaker(LIVE_1, ["Горст", "кремезний сивий чоловік"], ["Горст", "Ельза"]) == LIVE_1
    assert tidy_speaker(LIVE_2, ["Ельза", "жінка в темній хустці"], ["Горст", "Ельза"]) == LIVE_2
    # a one-sentence beat that ends before the dash that opens speech is still put in book form
    assert tidy_speaker("Горст кивнув, не підводячи очей. — Добре.", ["Горст"], ["Горст"]) == \
        "— Добре. — Горст кивнув, не підводячи очей."
    # a dash inside a one-sentence beat (no full stop before it): left alone
    t = "Горст глянув на меч — тоді на двері. — Ні."
    assert tidy_speaker(t, ["Горст"], ["Горст"]) == t
    # the self-prefix is still dropped from these lines
    assert tidy_speaker("Горст: " + LIVE_1, ["Горст"], ["Горст"]) == LIVE_1


def test_whole_description_marks_a_beat_not_its_first_word():
    """Review round 1: «жінка» alone is not a name; speech that says it stays speech, while the
    whole masked description still marks a beat."""
    eng, *_ = make(["— Так."], ["horst", NOBODY], ["short"])
    words = eng._name_words
    assert "жінка" not in words and "жінка в темній хустці" in words
    from harness.style import split_npc_output
    line = "— Ти що, віриш їй? — жінка ж бреше, — Горст ляснув долонею по столу."
    out = split_npc_output(line, words)
    assert "жінка ж бреше" in out.speech
    masked = "— Ні, — жінка в темній хустці відвела очі. — Іди."
    assert split_npc_output(masked, words).beats == ["жінка в темній хустці відвела очі."]


# -- final review fix wave ------------------------------------------------------------------------
def test_skipped_narration_first_step_never_draws_silence_or_gesture():
    """A skipped-narration turn whose first step the decider calls silence still says something:
    step 0 draws only speech shapes."""
    eng, prov, _ = make(["— Ну?"], ["horst", NOBODY], ["silence"], present=(PLAYER, "horst"),
                        rules={"director_narration": False})
    res = eng.turn("Добрий вечір.")
    assert any(n["kind"] == "narration_skipped" for n in eng.devlog)
    assert [u.payload["text"] for u in res.utterances] == ["— Ну?"]
    # with a profile too: the sampled shape of step 0 is a speech shape
    eng, prov, _ = make(["— Ну?"], ["horst", NOBODY], ["gesture"], present=(PLAYER, "horst"),
                        rules={"director_narration": False}, world_profile=_witcher())
    res = eng.turn("Добрий вечір.")
    note = next(n for n in eng.devlog if n["kind"] == "shape_sampled")
    assert note["shape"] not in ("silence", "gesture") and res.utterances


def test_skipped_narration_with_nothing_delivered_is_narrated():
    """Safety net: an exchange that delivers nothing (the gesture came back empty) after a
    skipped narration gets one narrator passage, so the player sees more than their own line."""
    eng, prov, _ = make([], ["horst", NOBODY], ["short"], present=(PLAYER, "horst"),
                        rules={"director_narration": False})
    eng._shaped_line = lambda *a, **k: ""  # the NPC call gives nothing usable
    res = eng.turn("Добрий вечір.")
    assert res.narration == NARRATION
    assert any(n["kind"] == "empty_exchange_narrated" for n in eng.devlog)
    assert "empty_exchange_narrated" in CODE_CHOICE_KINDS
