"""Task 3: response shape and fitting."""
from harness.decisions import CODE_CHOICE_KINDS
from harness.models import CharacterProfile
from harness.profile import WorldProfile
from harness.shape import Shape, fit_to_shape, shape_instruction, word_bounds
from harness.style import Style, split_npc_output

LONG_SPEECH = ("— " + " ".join(f"Слово{i} сказав він." for i in range(10)) + " — озирнувся Горст.")


def spoken(text):
    return len(split_npc_output(text).speech.split())


def test_default_bounds():
    assert word_bounds(Shape.WORD, None) == (1, 2)
    assert word_bounds(Shape.SHORT, None) == (3, 9)
    assert word_bounds(Shape.NORMAL, None) == (10, 25)
    assert word_bounds(Shape.LONG, None) == (26, 80)
    assert word_bounds(Shape.SILENCE, None) == (0, 0)
    assert word_bounds(Shape.GESTURE, None) == (0, 0)


def test_profile_bounds_follow_the_book_bins():
    prof = WorldProfile(length_bins={"1": .1, "2-3": .1, "4-7": .2, "8-15": .3, "16-30": .2, "31+": .1},
                        median_words=10)
    assert word_bounds(Shape.WORD, prof) == (1, 3)
    assert word_bounds(Shape.NORMAL, prof) == (8, 15)


def test_word_shape_rejects_long_speech():
    text, how = fit_to_shape(LONG_SPEECH, Shape.WORD, (1, 2))
    assert how == "regenerate"


def test_within_tolerance_is_ok_untouched():
    t = "— Один. Два. Три."
    assert fit_to_shape(t, Shape.WORD, (1, 2)) == (t, "ok")  # 3 words <= 1.5 * 2


def test_trim_at_sentence_boundary():
    text = "— Сто. І ані шеляга менше. Іди собі, відьмаче, поки цілий, і не лізь у мої справи."
    out, how = fit_to_shape(text, Shape.SHORT, (3, 9), allow_trim=True)
    assert how == "trimmed"
    assert spoken(out) <= 9 and out.rstrip()[-1] in ".!?…"
    assert out.startswith("— Сто. І ані шеляга менше.")


def test_trim_keeps_beats_and_reparses():
    out, how = fit_to_shape(LONG_SPEECH, Shape.SHORT, (3, 9), allow_trim=True)
    assert how == "trimmed"
    parsed = split_npc_output(out)
    assert len(parsed.speech.split()) <= 9 and parsed.beats == ["озирнувся Горст."]


def test_single_overlong_sentence_is_cut_on_a_word():
    text = "— " + " ".join(["слово"] * 30) + "."
    out, how = fit_to_shape(text, Shape.SHORT, (3, 9), allow_trim=True)
    assert how == "trimmed" and spoken(out) <= 9 and out.rstrip()[-1] in ".!?…"


def test_gesture_keeps_only_beats():
    out, how = fit_to_shape("— Сто. — озирнувся Горст. — Ні.", Shape.GESTURE, (0, 0))
    assert how == "ok" and "озирнувся Горст" in out and "Сто" not in out and "Ні" not in out


def test_gesture_without_beats_regenerates_then_goes_silent():
    assert fit_to_shape("— Сто.", Shape.GESTURE, (0, 0))[1] == "regenerate"
    assert fit_to_shape("— Сто.", Shape.GESTURE, (0, 0), allow_trim=True) == ("", "ok")


def test_silence_is_empty():
    assert fit_to_shape("— Сто. — кивнув він.", Shape.SILENCE, (0, 0)) == ("", "ok")


def test_short_enough_text_is_ok():
    t = "— Сто. І ані шеляга менше."
    assert fit_to_shape(t, Shape.NORMAL, (10, 25)) == (t, "ok")


def test_shape_instruction_per_shape():
    for s in Shape:
        assert shape_instruction(s, "Ukrainian").strip()
    assert "2" in shape_instruction(Shape.WORD, None)
    assert "nothing" in shape_instruction(Shape.SILENCE, None).lower()


def test_npc_instruction_mentions_shape():
    s = Style.load("witcher", exemplars=False)
    prof = CharacterProfile("horst", "Горст", "Староста.")
    ins = s.npc_instruction(prof, "Ukrainian", Shape.WORD)
    assert shape_instruction(Shape.WORD, "Ukrainian") in ins
    assert "last thing said" in ins
    assert "one to three" not in ins
    assert shape_instruction(Shape.WORD, None) not in s.npc_instruction(prof, "Ukrainian")


def test_style_sheet_no_longer_requires_a_gesture_every_line():
    sheet = Style.load("witcher").sheet["dialogue"]
    assert "Gesture and business carry the speech tags" not in sheet and "many lines have none" in sheet


def test_note_kinds_registered():
    assert {"shape_trimmed", "shape_regenerated"} <= CODE_CHOICE_KINDS
