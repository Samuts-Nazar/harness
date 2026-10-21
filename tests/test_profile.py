import pytest

from harness.profile import (WorldProfile, dialogue_lines, distance, profile_from_text,
                             profile_of_lines)


def test_dialogue_lines_split_speech_and_beats():
    text = "— Ні. — буркнув він.\nВін пішов.\n— Так, звісно, ми підемо туди разом."
    ls = dialogue_lines(text)
    assert len(ls) == 2
    assert ls[0].words == 1 and ls[0].has_beat and not ls[0].is_question
    assert ls[0].paragraph == 0 and ls[1].paragraph == 2
    assert ls[1].words == 6 and not ls[1].has_beat


def _synthetic():
    lens = [1] * 6 + [2] * 6 + [3] * 6 + [5] * 12 + [10] * 12 + [20] * 12 + [40] * 6
    paras = []
    for i, n in enumerate(lens):
        w = " ".join(["слово"] * (n - 1) + ["кінець?" if i % 2 == 0 else "кінець."])
        paras.append(f"— {w}")
        if i % 3 == 2:
            paras.append("Він мовчав і дивився у вікно.")
    return "\n".join(paras), lens


def test_profile_bins_and_median():
    text, lens = _synthetic()
    p = profile_from_text(text, "synthetic")
    assert p.n_lines == 60 and p.source == "synthetic"
    assert p.length_bins == pytest.approx({"1": 0.1, "2-3": 0.2, "4-7": 0.2, "8-15": 0.2,
                                           "16-30": 0.2, "31+": 0.1})
    assert p.median_words == 7.5
    assert p.question_share == pytest.approx(0.5)
    assert p.no_beat_share == 1.0
    assert p.narration_median_words == 6
    assert 0 < p.narration_between_share < 1
    assert p.speaker_run_mean == pytest.approx(3.0)


def test_profile_rejects_quote_format():
    text = "\n".join(f"«Це репліка номер {i}, досить довга.» — сказав він." for i in range(80))
    with pytest.raises(ValueError, match="no dialogue lines found in dash format"):
        profile_from_text(text, "quotes")


def test_distance_zero_for_identical():
    text, _ = _synthetic()
    p = profile_from_text(text, "s")
    d = distance(p, p)
    assert d and all(v == 0 for v in d.values()) and "length_bins_l1" in d


def test_roundtrip_and_engine_lines():
    text, _ = _synthetic()
    p = profile_from_text(text, "s")
    assert WorldProfile.from_dict(p.to_dict()) == p
    e = profile_of_lines(["— Ні, — буркнув він.", "Гаразд, піду."])
    assert e.n_lines == 2 and e.length_bins["1"] == 0.5
