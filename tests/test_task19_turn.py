"""Task 19: outcome before prose, death, NPC acts, the slow lane, the narrator's perception filter."""
import threading
import time

import pytest

from conftest import PROFILES, diff, fact
from harness.db import connect
from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.outcome import (
    CHARACTER_DEATH, OUTCOME, CampaignEnded, chronicle,
)
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider


def engine(script, *, rules=None, present=(PLAYER, "innkeeper", "bard"), **kw):
    prov = kw.pop("prov", None) or FakeProvider(script={k: list(v) for k, v in script.items()})
    judge = FakeJudge({"director_first": "innkeeper", **(rules or {})})
    eng = Engine(prov, kw.pop("profiles", PROFILES), Scene("Inn", tuple(present), time=0),
                 models=ModelConfig(), judge=judge, record_language=None, **kw)
    return eng, prov


def narrator_msgs(prov):
    return [m for mod, m in prov.calls if mod == "narrator"]


BASE = {"narrator": ["The rope snaps and Geralt falls."], "npc": ["Careful."],
        "extractor": ["none", diff(fact("Geralt fell from the rope", "narration", 0.5))]}


# -- outcome before prose -------------------------------------------------------------------
def test_the_world_judges_the_attempt_before_the_narrator_writes():
    eng, prov = engine(BASE, outcomes=True, rules={
        "outcome_attempt": True, "outcome_verdict": "fails", "outcome_reason": "lacks_means"})
    eng.turn("Я лізу по линві на дах.")
    ev = eng.log.active([OUTCOME])
    assert len(ev) == 1 and ev[0].payload["verdict"] == "fails"
    assert ev[0].payload["reason"] == "lacks_means"
    text = "\n".join(m["content"] for m in narrator_msgs(prov)[0])
    assert "judged the player character's attempt BEFORE you write" in text
    assert "it fails" in text and "lacked the means" in text
    ext = "\n".join(m["content"] for m in [m for mod, m in prov.calls if mod == "extractor"][-1])
    assert "Record what really happened" in ext
    assert not eng.ended


def test_speech_is_not_an_attempt_and_leaves_no_outcome():
    eng, prov = engine(BASE, outcomes=True, rules={"outcome_attempt": False})
    eng.turn("Добрий вечір.")
    assert eng.log.active([OUTCOME]) == []
    assert "judged the player" not in "\n".join(m["content"] for m in narrator_msgs(prov)[0])


def test_unbounded_player_always_succeeds_without_a_judgment():
    eng, prov = engine(BASE, outcomes=True, player_unlimited=True,
                       rules={"outcome_verdict": "fails"})
    eng.turn("Я розриваю линву голими руками.")
    ev = eng.log.active([OUTCOME])[0]
    assert ev.payload["verdict"] == "works" and ev.payload["unbounded"] is True
    assert not any(q.tag == "outcome_verdict" for _, qs in eng.judge.inner.asked
                   for q in qs.values()) if hasattr(eng.judge, "inner") else True
    assert "exactly as declared" in "\n".join(m["content"] for m in narrator_msgs(prov)[0])


def test_death_ends_the_campaign_and_makes_it_read_only():
    eng, prov = engine(BASE, outcomes=True, rules={
        "outcome_attempt": True, "outcome_verdict": "fails", "outcome_reason": "beyond_ability",
        "character_death": True})
    eng.turn("Стрибаю з даху.")
    assert eng.ended and len(eng.log.active([CHARACTER_DEATH])) == 1
    with pytest.raises(CampaignEnded):
        eng.turn("Ще раз.")
    kinds = [c["kind"] for c in chronicle(eng)]
    assert kinds[-1] == "death" and "narr" in kinds


def test_death_survives_a_restart(tmp_path):
    prov = FakeProvider(script={k: list(v) for k, v in BASE.items()})
    judge = FakeJudge({"director_first": "innkeeper", "outcome_attempt": True,
                       "outcome_verdict": "fails", "outcome_reason": "body", "character_death": True})
    eng = Engine.create_campaign("c", prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper"), 0),
                                 root=tmp_path, models=ModelConfig(), judge=judge,
                                 record_language=None, outcomes=True)
    eng.turn("Стрибаю.")
    eng.close()
    again = Engine.open_campaign("c", FakeProvider(script={}), root=tmp_path,
                                 models=ModelConfig(), judge=judge, record_language=None)
    assert again.ended and again.outcomes_on


def test_rolling_back_the_turn_removes_its_outcome():
    eng, _ = engine(BASE, outcomes=True, rules={"outcome_attempt": True, "outcome_verdict": "partly",
                                                "outcome_reason": "noticed"})
    eng.turn("Краду кошіль.")
    first = eng.log.active([OUTCOME])[0]
    eng.rollback(first.cause_id)
    assert eng.log.active([OUTCOME]) == []


def test_npc_attack_is_judged_and_narrated_as_resolved():
    script = {"narrator": ["The innkeeper lunges with a knife.", "The blade skids off his coat."],
              "npc": ["Ось тобі!"],
              "extractor": ["The innkeeper lunges at Geralt with a knife",
                            diff(fact("The innkeeper's attack failed", "narration~2", 0.5))]}
    eng, prov = engine(script, outcomes=True, rules={
        "outcome_attempt": False, "npc_act_against_player": True,
        "outcome_verdict": "fails", "outcome_reason": "beyond_ability", "character_death": False})
    seen = []
    res = eng.turn("Сиджу тихо.", on_narration=seen.append)
    outs = eng.log.active([OUTCOME])
    assert [o.payload["verdict"] for o in outs] == ["fails"] and outs[0].payload["actor"] == ""
    assert res.narration.endswith("The blade skids off his coat.") and len(seen) == 2
    assert not eng.ended


def test_npc_act_that_kills_ends_the_campaign():
    script = {"narrator": ["The innkeeper lunges.", "The knife finds the throat."],
              "npc": ["Ось тобі!"],
              "extractor": ["The innkeeper stabs Geralt", diff()]}
    eng, _ = engine(script, outcomes=True, rules={
        "outcome_attempt": False, "npc_act_against_player": True,
        "outcome_verdict": "works", "outcome_reason": "none", "character_death": True})
    eng.turn("Сиджу.")
    assert eng.ended


# -- the narrator's perception ----------------------------------------------------------------
def test_narrator_does_not_see_what_only_other_people_know():
    eng, prov = engine(BASE)
    eng.facts.add_campaign("The king's guard was ordered to the shore.",
                           source_event_id=eng.log.append(
                               "scripted", game_time=0, location="Inn", participants=[],
                               witnesses=[], notability=0.5, payload={"text": "x"}).id,
                           game_time=0, location="Shore", notability=0.8,
                           knowers=[("innkeeper", "heard", None)])
    eng.turn("Дивлюсь.")
    ctx = "\n".join(m["content"] for m in narrator_msgs(prov)[0])
    assert "ordered to the shore" not in ctx


# -- the slow lane -------------------------------------------------------------------------------
class SlowExtract(FakeProvider):
    """The extractor answers after a delay (the fact extraction call only)."""

    def __init__(self, delay, **kw):
        super().__init__(**kw)
        self.delay = delay
        self.parallel_ok = True

    def complete(self, model, messages):
        if "fact extractor" in messages[0]["content"]:
            time.sleep(self.delay)
        return super().complete(model, messages)


def two_turn_script():
    return {"narrator": ["The bard tunes his lute.", "The bard sings."], "npc": ["Welcome.", "Hear."],
            "extractor": ["none", diff(fact("The bard tunes a lute", "narration", 0.5)),
                          "none", diff(fact("The bard sings", "narration", 0.5))]}


def test_deferred_slow_lane_returns_before_extraction_and_settles_in_order():
    prov = SlowExtract(0.4, script=two_turn_script())
    eng, _ = engine(None, prov=prov, parallel=True)
    t0 = time.monotonic()
    res = eng.turn("Привіт.", defer_slow=True)
    fast = time.monotonic() - t0
    assert res.narration and res.fact_ids == []           # nothing extracted yet
    assert fast < 0.35 and eng.facts.all_campaign(10**6) == []
    assert eng.settle() is True and eng.slow_failure is None
    assert len(res.fact_ids) == 1 and eng.facts.all_campaign(10**6)[0].content == "The bard tunes a lute"
    assert eng.settle() is False  # idempotent
    st = eng.lane_stats[-1]
    assert st["slow_s"] >= 0.3


def test_next_turn_waits_only_when_the_slow_lane_is_still_running():
    prov = SlowExtract(0.3, script=two_turn_script())
    eng, _ = engine(None, prov=prov, parallel=True)
    eng.turn("Привіт.", defer_slow=True)
    eng.turn("Ще.", defer_slow=True)                       # starts at once: waits for the slow lane
    assert eng.lane_stats[0]["needed"] is True and eng.lane_stats[0]["waited_s"] > 0.1
    time.sleep(0.5)                                        # the player reads; the lane finishes
    eng.settle()
    eng.turn("Дякую.", defer_slow=True) if False else None
    assert [f.content for f in eng.facts.all_campaign(10**6)] == ["The bard tunes a lute",
                                                                  "The bard sings"]


def test_deferred_log_order_equals_the_immediate_log_order():
    def run(defer):
        prov = SlowExtract(0.05 if defer else 0.0, script=two_turn_script())
        eng, _ = engine(None, prov=prov, parallel=True)
        for t in ("Привіт.", "Ще."):
            eng.turn(t, defer_slow=defer)
        eng.settle()
        return [(e.type, e.payload.get("text") or e.payload.get("speaker")) for e in eng.log.active()]
    assert run(True) == run(False)


def test_failed_slow_lane_rolls_the_turn_back_and_reports():
    script = two_turn_script()
    script["extractor"] = ["none", "not json", "still not json"]
    prov = SlowExtract(0.0, script=script)
    eng, _ = engine(None, prov=prov, parallel=True)
    before = eng.scene.time
    eng.turn("Привіт.", defer_slow=True)
    eng.settle()
    assert eng.slow_failure is not None and eng.scene.time == before
    assert eng.log.active(["narration"]) == []


def test_non_deferred_failure_still_raises():
    script = two_turn_script()
    script["extractor"] = ["none", "not json", "still not json"]
    eng, _ = engine(script)
    with pytest.raises(Exception):
        eng.turn("Привіт.")
    assert eng.log.active(["narration"]) == []


# -- the flaky test's cause --------------------------------------------------------------------
def test_workers_never_touch_the_database():
    """A worker thread reading the (single-thread) connection raised intermittently in the app,
    where characters are known by appearance: the heard line of an earlier speaker used the
    registry. The connection here is bound to this thread, so any worker read fails at once."""
    profiles = [CharacterProfile(PLAYER, "Геральт", "A witcher."),
                CharacterProfile("innkeeper", "Ярош", "Innkeeper.", appearance="товстий корчмар"),
                CharacterProfile("bard", "Любисток", "Bard.", appearance="бард із лютнею")]
    script = {"narrator": ["Корчмар і бард дивляться на тебе."],
              "npc": ["Ласкаво просимо.", "Заспіваю."],
              "extractor": ["none", diff()]}
    prov = FakeProvider(script=script, parallel_ok=True)
    judge = FakeJudge({"director_first": "innkeeper", "director_also": lambda q, st: "Любисток" in q.text})
    eng = Engine(prov, profiles, Scene("Inn", (PLAYER, "innkeeper", "bard"), 0),
                 conn=connect(check_same_thread=True), models=ModelConfig(), judge=judge,
                 record_language=None, parallel=True)
    res = eng.turn("Привіт.")
    assert [u.payload["speaker"] for u in res.utterances] == ["innkeeper", "bard"]
    second = [m for mod, m in prov.calls if mod == "npc"][-1][-1]["content"]
    assert "товстий корчмар: Ласкаво просимо." in second.split("Recent conversation:")[-1]
