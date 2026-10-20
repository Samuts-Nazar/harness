"""Task 16: story-day tracking (code checks, repair, arbitration) with fake providers and made-up text."""
import json

from harness.canon import timeline
from harness.canon.chunk import Para
from harness.canon.timeline import Scene
from harness.providers import FakeProvider

TEXTS = {
    1: "Він прийшов пізнього пообіддя до міста.",
    2: "Розмова в кабінеті тривала до вечора.",
    3: "Гінця привели на другий день, пізно ввечері, до кімнати.",
    4: "Вона сказала: до повного місяця ще чотири дні. Після повні.",
    5: "У залі було тихо і темно.",
    6: "Сутеніло. Він готувався.",
}


def paras():
    return [Para(i * 10, t, 0, "c") for i, t in TEXTS.items()]


def sc(i, lo, hi=None, part="evening", place="a"):
    return Scene(i * 10, i * 10, lo, hi if hi is not None else lo, part, place)


def test_cue_words_and_moon_counts_are_not_day_cues():
    assert timeline.has_day_cue(TEXTS[3])
    assert not timeline.has_day_cue(TEXTS[4]), "'four days to the full moon' is a calendar fact, not a new-day cue"
    assert timeline.moon_days(TEXTS[4]) == [4] and timeline.plan_after_moon(TEXTS[4]) == [4]


def test_check_flags_a_day_rise_without_a_cue_and_repair_fixes_it():
    scenes = [sc(1, 1), sc(2, 1), sc(3, 2), sc(4, 3), sc(5, 3)]
    issues = timeline.check(scenes, paras())
    assert 3 in issues and "no cue word" in issues[3][0]          # scene 4 jumped a day with no cue
    timeline.check(scenes, paras(), repair=True)
    assert scenes[3].day_lo == 2 and "repaired_continuation" in scenes[3].flags


def test_plan_after_the_full_moon_pulls_the_scene_after_the_gap():
    scenes = [sc(1, 1), sc(2, 1), sc(3, 2, part="night"), sc(4, 2, part="night"), sc(5, 2, part="night"), sc(6, 3, part="evening", place="b")]
    assert 5 in timeline.check(scenes, paras())                   # scene 6 follows a gap but is not on moon day 6 or 7
    timeline.check(scenes, paras(), repair=True)
    assert (scenes[5].day_lo, scenes[5].day_hi) == (6, 7) and "repaired_plan" in scenes[5].flags


def test_days_never_go_back_and_first_day_is_one():
    assert timeline.check([sc(1, 2), sc(2, 1)], paras()).keys() == {0, 1}


def reply(*rows):
    return json.dumps({"scenes": [dict(from_line=i * 10, to_line=i * 10, day_lo=lo, day_hi=hi, part="evening", place="a", cue="c")
                                  for i, lo, hi in rows]})


def test_build_two_readers_then_arbiter_decides_only_the_disputed_scene():
    a = reply((1, 1, 1), (2, 1, 1), (3, None, None), (4, 2, 2))
    b = reply((1, 1, 1), (2, 1, 1), (3, 2, 2), (4, 2, 2))
    arb = json.dumps({"scenes": [{"index": 2, "day_lo": 2, "day_hi": 2, "part": "night", "reason": "next day cue"}]})
    prov = FakeProvider({"m1": [a], "m2": [b], "arb": [arb]})
    cache = {}
    scenes, rep = timeline.build(prov, ("m1", "m2"), "arb", paras()[:4], cache=cache)
    assert [s.day_lo for s in scenes] == [1, 1, 2, 2]
    assert rep["arbitrated"] == [2] and "arbitrated" in scenes[2].flags and rep["issues_final"] == {}
    # a rerun with the cache makes no call
    prov2 = FakeProvider({})
    scenes2, _ = timeline.build(prov2, ("m1", "m2"), "arb", paras()[:4], cache=cache)
    assert [s.day_lo for s in scenes2] == [1, 1, 2, 2] and prov2.calls == []
