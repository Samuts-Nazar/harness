from harness.judge import FakeJudge
from harness.pipeline import FALLBACK_LINE
from conftest import diff, fact, make_engine


def leaks(word):
    """Judge rule: the line makes an unlearnable claim iff it mentions `word`."""
    return FakeJudge({"unknown_claim": lambda q, st: word in st[0].rsplit("Line:", 1)[1]})


def _npc_calls(prov):
    return [m for model, m in prov.calls if model == "npc"]


def test_clean_line_is_accepted_without_regeneration():
    eng, prov = make_engine({"narrator": ["N."], "npc": ["Welcome, traveller."],
                             "extractor": [diff()]}, judge=leaks("Ciri"))
    res = eng.turn("hi", speakers=["innkeeper"])
    assert res.utterances[0].payload["text"] == "Welcome, traveller."
    assert len(_npc_calls(prov)) == 1


def test_line_with_unlearnable_claim_is_regenerated():
    script = {"narrator": ["N."], "extractor": [diff()],
              "npc": ["Ciri is hiding at Kaer Morhen.",   # pretraining knowledge
                      "Ciri sleeps in the cellar.",
                      "I know nothing about that."]}
    eng, prov = make_engine(script, judge=leaks("Ciri"))
    res = eng.turn("where is she?", speakers=["innkeeper"])
    assert res.utterances[0].payload["text"] == "I know nothing about that."
    assert len(_npc_calls(prov)) == 3  # first call + at most 2 retries
    assert [n["kind"] for n in eng.devlog] == ["npc_line_rejected", "npc_line_rejected"]
    # rejected lines never reach the log, the extractor or other characters
    ext = [m for model, m in prov.calls if model == "extractor"][0][1]["content"]
    assert "Ciri" not in ext
    assert all("Ciri" not in e.payload["text"] for e in eng.log.active(["utterance"]))


def test_all_retries_rejected_shows_the_least_suspicious_candidate_and_logs_it():
    script = {"narrator": ["N."], "extractor": [diff()],
              "npc": ["Ciri is here.", "Ciri is there.", "Ciri is everywhere."]}
    suspicion = iter([0.95, 0.75, 0.9])

    def rule(q, st):
        return True

    class Graded(FakeJudge):
        def ask(self, state, questions):
            out = super().ask(state, questions)
            from harness.judge import Judgment
            if next(iter(questions.values())).tag != "unknown_claim":
                return out
            p = next(suspicion)
            return {n: Judgment(True, {"yes": p, "no": 1 - p}, p, backend="fake") for n in out}

    eng, prov = make_engine(script, judge=Graded({"unknown_claim": rule}))
    res = eng.turn("where is she?", speakers=["innkeeper"])
    assert res.utterances[0].payload["text"] == "Ciri is there."  # p = 0.75, the lowest
    assert FALLBACK_LINE not in res.utterances[0].payload["text"]
    assert len(_npc_calls(prov)) == 3
    [fb] = [n for n in eng.devlog if n["kind"] == "npc_lowest_suspicion"]
    assert fb["npc"] == "innkeeper" and len(fb["rejected"]) == 3 and fb["suspicion"] == 0.75
    checks = [j for j in eng.judgments.entries if j["tag"] == "unknown_claim"]
    assert len(checks) == 3 and all(j["answer"] is True for j in checks)


def test_a_line_below_the_threshold_is_not_rejected():
    class P(FakeJudge):
        def __init__(self, p):
            super().__init__()
            self.p = p

        def ask(self, state, questions):
            from harness.judge import Judgment
            if next(iter(questions.values())).tag != "unknown_claim":
                return super().ask(state, questions)
            return {n: Judgment(True, {"yes": self.p, "no": 1 - self.p}, self.p, backend="fake")
                    for n in questions}

    eng, prov = make_engine({"narrator": ["N."], "npc": ["Maybe."], "extractor": [diff()]},
                            judge=P(0.69))  # a "yes" answer, but p < 0.7: accepted
    eng.turn("x", speakers=["innkeeper"])
    assert len(_npc_calls(prov)) == 1 and not eng.devlog
    eng2, prov2 = make_engine({"narrator": ["N."], "npc": ["Maybe.", "Again."], "extractor": [diff()]},
                              judge=P(0.7), npc_reject_p=0.9)  # configurable
    eng2.turn("x", speakers=["innkeeper"])
    assert len(_npc_calls(prov2)) == 1


def test_check_judges_against_the_npcs_visible_knowledge_only():
    script = {"narrator": ["N.", "N."], "extractor": [diff(fact("The mill howls", "innkeeper")), diff()],
              "npc": ["The mill howls at night.", "Hello."]}
    judge = FakeJudge()
    eng, _ = make_engine(script, present=("player", "innkeeper"), judge=judge)
    eng.turn("any news?", speakers=["innkeeper"])
    eng.enter_scene("bard")
    eng.turn("hi", speakers=["bard"])
    state_for_bard = [st[0] for st, qs in judge.asked if "Character: Dandelion" in st[0]][-1]
    assert "The mill howls" not in state_for_bard.split("Line:")[0]
    state_for_inn = [st[0] for st, qs in judge.asked if "Character: Innkeeper" in st[0]][0]
    assert "The mill howls" not in state_for_inn.split("Line:")[0]  # not yet learned at that point
    assert "Geralt: any news?" in state_for_inn  # what the NPC heard is part of its knowledge
