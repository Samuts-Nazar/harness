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


def make(npc_lines, nxt, shape, *, present=(PLAYER, "horst", "elza"), extractor=None,
         rules=None, **kw):
    script = {"narrator": [NARRATION], "npc": list(npc_lines),
              "extractor": list(extractor or ["none", diff()])}
    judge = FakeJudge({"director_next": list(nxt), "director_shape": list(shape),
                       **(rules or {})})
    prov = FakeProvider(script=script)
    kw.setdefault("record_language", None)
    eng = Engine(prov, PROFILES, Scene("Inn", tuple(present), time=0), models=ModelConfig(),
                 judge=judge, narration="prose", **kw)
    eng.acquaint("horst", "elza")
    return eng, prov, judge


def npc_prompts(prov):
    return ["\n".join(x["content"] for x in m) for mod, m in prov.calls if mod == "npc"]


def next_asks(judge):
    return [(st, qs) for st, qs in judge.asked if "next" in qs]


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
    assert "Рагнар" not in res.utterances[0].payload["text"]


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
