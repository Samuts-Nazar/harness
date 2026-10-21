"""Task 2 (living dialogue): the decision counter."""
from conftest import PROFILES, diff, fact
from harness.decisions import CODE_CHOICE_KINDS, DecisionCount, aggregate, count_since
from harness.judge import FakeJudge
from harness.models import PLAYER, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider


def _engine(script):
    prov = FakeProvider(script={k: list(v) for k, v in script.items()})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0),
                 models=ModelConfig(), judge=FakeJudge({"director_first": "innkeeper"}),
                 record_language=None)
    return eng


def test_turn_reports_decision_counts():
    eng = _engine({"narrator": ["The rope snaps."], "npc": ["Careful.", "Mind the floor."],
                   "extractor": ["none", diff(fact("Geralt fell", "narration", 0.5))]})
    r = eng.turn("Hello.", speakers=["innkeeper", "bard"])
    assert len(r.utterances) == 2
    d = r.decisions
    assert d is not None
    assert d.llm_calls_by_role["npc"] == 2
    assert d.judgments >= 1
    assert d.total == d.judgments + sum(d.llm_calls_by_role.values()) + d.code_choices


def test_aggregate_sums():
    a = DecisionCount(2, 1, {"npc": 2, "narrator": 1}, 1)
    b = DecisionCount(3, 0, {"npc": 1}, 2)
    s = aggregate([a, b])
    assert (s.judgments, s.escalations, s.code_choices) == (5, 1, 3)
    assert s.llm_calls_by_role == {"npc": 3, "narrator": 1}
    assert aggregate([]) == DecisionCount(0, 0, {}, 0)


def test_code_choices_count_only_registered_note_kinds():
    eng = _engine({})
    kind = sorted(CODE_CHOICE_KINDS)[0]
    eng._note(kind)
    eng._note("model_fallback")  # not a code-made choice
    d = count_since(eng, 0, 0, 0, note_mark=0)
    assert d.code_choices == 1

