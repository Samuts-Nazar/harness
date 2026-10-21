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


def test_shape_instruction_uses_given_bounds_and_name():
    line = shape_instruction(Shape.SHORT, None, bounds=(4, 7), name="Горст")
    assert "4-7" in line and "The character" not in line
    assert "Горст" in shape_instruction(Shape.GESTURE, None, name="Горст")


def test_gesture_without_dash_is_the_action_itself():
    assert fit_to_shape("Горст знизує плечима", Shape.GESTURE, (0, 0)) == (
        "Горст знизує плечима.", "ok")


def test_shape_instruction_per_shape():
    for s in Shape:
        assert shape_instruction(s, "Ukrainian").strip()
    assert "2" in shape_instruction(Shape.WORD, None)
    assert "nothing" in shape_instruction(Shape.SILENCE, None).lower()


def test_npc_instruction_mentions_shape():
    s = Style.load("witcher", exemplars=False)
    prof = CharacterProfile("horst", "Горст", "Староста.")
    ins = s.npc_instruction(prof, "Ukrainian", Shape.WORD)
    assert shape_instruction(Shape.WORD, None, name="Горст") in ins
    assert ins.count("Write in Ukrainian.") == 1, "the language line appears once"
    with_bounds = s.npc_instruction(prof, "Ukrainian", Shape.SHORT, bounds=(4, 7))
    assert "4-7 words" in with_bounds and "Горст" in with_bounds
    assert "last thing said" in ins
    assert "one to three" not in ins
    assert shape_instruction(Shape.WORD, None) not in s.npc_instruction(prof, "Ukrainian")


def test_style_sheet_no_longer_requires_a_gesture_every_line():
    sheet = Style.load("witcher").sheet["dialogue"]
    assert "Gesture and business carry the speech tags" not in sheet and "many lines have none" in sheet


def test_note_kinds_registered():
    assert {"shape_trimmed", "shape_regenerated"} <= CODE_CHOICE_KINDS


# -- Task 12: the session's shape distribution follows the world profile ----------------------
import random

from harness.profile import BINS, load_profile, profile_of_lines
from harness.shape import (SPEECH_SHAPES, beat_wanted, decider_dist, sample_shape, shape_targets,
                           shape_weights)

WITCHER = load_profile("witcher")


def _line(n, beat=False):
    words = " ".join(["слово"] * n)
    return f"— {words}." + (" — Горст кивнув." if beat else "")


def test_shape_targets_sum_the_profile_bins_per_speech_shape():
    t = shape_targets(WITCHER)
    lb = WITCHER.length_bins
    assert abs(t[Shape.WORD] - (lb["1"] + lb["2-3"])) < 1e-9
    assert abs(t[Shape.LONG] - (lb["16-30"] + lb["31+"])) < 1e-9
    assert abs(sum(t.values()) - 1) < 1e-9 and set(t) == set(SPEECH_SHAPES)


def test_decider_dist_fills_missing_options():
    assert decider_dist({"normal": 1.0, "short": 0.0}, "normal", 1.0)[Shape.NORMAL] == 1.0
    d = decider_dist({}, "short", 0.6)  # only the answer's own probability is known
    assert abs(d[Shape.SHORT] - 0.6) < 1e-9 and abs(sum(d.values()) - 1) < 1e-9
    assert d[Shape.LONG] > 0


def test_weights_keep_the_deciders_non_speech_mass():
    w = shape_weights(decider_dist({}, "silence", 1.0), WITCHER, [])
    assert w[Shape.SILENCE] == 1.0 and sum(w[s] for s in SPEECH_SHAPES) == 0


def test_weights_blend_the_profile_and_lean_against_the_session_gap():
    one_hot = decider_dist({"normal": 1.0}, "normal", 1.0)
    fresh = shape_weights(one_hot, WITCHER, [])
    assert fresh[Shape.LONG] > 0.1, "the profile's long tail is reachable even if never chosen"
    short_session = [_line(5) for _ in range(20)]
    leaned = shape_weights(one_hot, WITCHER, short_session)
    assert leaned[Shape.LONG] > fresh[Shape.LONG] and leaned[Shape.SHORT] < fresh[Shape.SHORT]
    assert abs(sum(leaned.values()) - 1) < 1e-9


def test_sample_shape_is_deterministic_for_a_seeded_rng():
    w = shape_weights(decider_dist({}, "normal", 0.6), WITCHER, [])
    a = [sample_shape(w, random.Random(f"s{i}")) for i in range(30)]
    assert a == [sample_shape(w, random.Random(f"s{i}")) for i in range(30)]
    assert len(set(a)) > 2


def test_simulated_session_tracks_the_profile():
    """A decider that always says normal/short, and a writer that undershoots like the live
    model (Task 8: no line over 15 words): with code sampling, the realized length bins end up
    near the book's."""
    rng = random.Random(1)
    lengths = {Shape.WORD: (1, 3), Shape.SHORT: (4, 7), Shape.NORMAL: (5, 15), Shape.LONG: (16, 45)}
    lines: list[str] = []
    for i in range(200):
        dec = decider_dist({}, "normal" if i % 2 else "short", 0.6)
        s = sample_shape(shape_weights(dec, WITCHER, lines), rng)
        if s in lengths:
            lines.append(_line(rng.randint(*lengths[s])))
    got = profile_of_lines(lines).length_bins
    l1 = sum(abs(got[b] - WITCHER.length_bins[b]) for b in BINS)
    assert l1 < 0.3, (l1, got)


def test_beat_wanted_follows_no_beat_share_and_the_session():
    rng = random.Random(3)
    fresh = sum(not beat_wanted(WITCHER, [], rng) for _ in range(400)) / 400
    assert abs(fresh - WITCHER.no_beat_share) < 0.08
    all_beats = [_line(6, beat=True) for _ in range(20)]
    leaned = sum(not beat_wanted(WITCHER, all_beats, rng) for _ in range(400)) / 400
    assert leaned > fresh + 0.1
    assert beat_wanted(None, [], rng) is None  # no profile: left to the model


def test_long_and_normal_instructions_name_the_lower_bound():
    """Task 8: the model never wrote over 15 words; a long line is asked for its minimum."""
    assert "at least 16" in shape_instruction(Shape.LONG, None, bounds=(16, 80))
    assert "8-15" in shape_instruction(Shape.NORMAL, None, bounds=(8, 15))


def test_profile_of_lines_with_names_does_not_count_a_masked_beat_as_speech():
    line = "— Так і є. — кремезний сивий чоловік глянув на меч."
    assert profile_of_lines([line]).median_words == 10
    p = profile_of_lines([line], ["кремезний"])
    assert p.median_words == 3 and p.no_beat_share == 0


def test_decider_dist_does_not_spread_leftover_to_silence_and_gesture():
    """Review round 1: a decider that names only its answer does not make silence likely."""
    d = decider_dist({}, "short", 0.6)
    assert d[Shape.SILENCE] == 0 and d[Shape.GESTURE] == 0
    assert abs(d[Shape.SHORT] - 0.6) < 1e-9 and abs(sum(d.values()) - 1) < 1e-9
    g = decider_dist({"silence": 0.3}, "short", 0.6)
    assert abs(g[Shape.SILENCE] - 0.3) < 1e-9 and g[Shape.GESTURE] == 0
