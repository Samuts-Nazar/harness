from harness.agents import StubOffscreenUpdater
from harness.models import PLAYER
from conftest import diff, make_engine


def test_agent_promoted_after_first_interaction_only():
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Hi."], "extractor": [diff()]})
    assert not eng.agents.is_agent("innkeeper")
    eng.turn("hello", speakers=["innkeeper"])
    assert eng.agents.is_agent("innkeeper")
    assert not eng.agents.is_agent("bard")  # present but never interacted
    assert eng.agents.agents() == ["innkeeper"]


def test_offscreen_hook_called_for_absent_agents_only():
    up = StubOffscreenUpdater()
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Hi."], "extractor": [diff()]}, updater=up)
    eng.turn("hello", speakers=["innkeeper"])
    t = eng.scene.time
    eng.advance_offscreen(60)
    assert up.calls == []  # innkeeper is on screen
    eng.scene.present = (PLAYER, "bard")
    eng.advance_offscreen(30)
    assert up.calls == [("innkeeper", t + 60, t + 90)]


def test_stub_judge_shapes():
    from harness.judge import StubJudge
    j = StubJudge()
    assert j.yes_no("q").answer is True
    assert j.choice("q", ["a", "b"]).answer == "a"
    assert j.score("q", lo=0, hi=10).answer == 5
