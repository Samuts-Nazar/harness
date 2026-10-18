import json

import httpx
import pytest

from harness.judge import (
    CHOICE, SCORE, YES_NO, EscalatingJudge, FakeJudge, Judge, JudgeError, Judgment, JevJudge,
    JudgmentLog, LLMJudge, LoggingJudge, Question, choice_q, score_q, yes_no_q,
)
from harness.providers import FakeProvider


class Scripted(Judge):
    """A backend that returns fixed Judgments and records what it was asked."""

    def __init__(self, answers):
        self.answers, self.asked = answers, []

    def ask(self, state, questions):
        self.asked.append((list(state), dict(questions)))
        return {n: self.answers[n] for n in questions}


def J(answer, p):
    return Judgment(answer, probability=p, backend="x")


# -- Jev client ------------------------------------------------------------------------------
def jev_with(reply, seen):
    def handler(req: httpx.Request) -> httpx.Response:
        seen.append((str(req.url), json.loads(req.content), req.headers["authorization"]))
        return httpx.Response(200, json=reply)
    return JevJudge("sk-test", client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_jev_request_format_and_batching():
    seen = []
    j = jev_with({"answers": {
        "a": {"noul": 0.9},
        "b": {"choice": "worse", "probabilities": {"worse": 0.7, "better": 0.3}},
        "c": {"score": 1.5, "probabilities": {"0": 0.1, "1": 0.5, "2": 0.4}},
    }}, seen)
    out = j.ask(["Scene: x"], {
        "a": yes_no_q("Is it?"),
        "b": choice_q("Which?", {"worse": "got worse", "better": "got better"}),
        "c": score_q("How much?", legend=("none", "small", "big")),
    })
    assert len(seen) == 1, "questions about the same state go out as one call"
    url, body, auth = seen[0]
    assert url == "https://openrouter.ai/api/alpha/decisions" and auth == "Bearer sk-test"
    assert body["model"] == "typesafe/jev-1.14" and body["state"] == ["Scene: x"]
    qs = body["questions"]
    assert qs["a"] == {"type": "noul", "instructions": "Is it?"}
    # choice.criteria is an object {option: description}, not an array
    assert qs["b"]["type"] == "choice"
    assert qs["b"]["criteria"] == {"worse": "got worse", "better": "got better"}
    assert qs["c"]["type"] == "score" and qs["c"]["criteria"] == ["none", "small", "big"]
    assert out["a"].answer is True and out["a"].probability == pytest.approx(0.9)
    assert out["b"].answer == "worse" and out["b"].probability == pytest.approx(0.7)
    assert out["c"].answer == pytest.approx(1.5)


def test_jev_no_answer_is_probability_of_no():
    j = jev_with({"answers": {"q": {"noul": 0.15}}}, [])
    r = j.yes_no("q?")
    assert r.answer is False and r.probability == pytest.approx(0.85)


def test_jev_errors_become_judge_errors():
    for handler in (lambda r: httpx.Response(500, json={}),
                    lambda r: httpx.Response(200, json={"answers": {}}),
                    lambda r: httpx.Response(200, json={"answers": {"q": {"nope": 1}}})):
        j = JevJudge("k", client=httpx.Client(transport=httpx.MockTransport(handler)))
        with pytest.raises(JudgeError):
            j.yes_no("q?")


# -- escalation ------------------------------------------------------------------------------
def test_escalates_below_threshold_and_not_at_or_above():
    primary = Scripted({"hi": J(True, 0.8), "lo": J(True, 0.79), "mid": J(False, 0.95)})
    llm = FakeJudge({"t": True})
    ej = EscalatingJudge(primary, llm)
    out = ej.ask(["s"], {n: Question(YES_NO, n, tag="t") for n in ("hi", "lo", "mid")})
    assert (out["hi"].escalated, out["lo"].escalated, out["mid"].escalated) == (False, True, False)
    assert out["lo"].backend == "fake"  # the LLM's answer replaced Jev's
    assert out["hi"].answer is True and out["mid"].answer is False
    # only the uncertain question went to the LLM, with the same state, in one batch
    [(state, qs)] = llm.asked
    assert list(qs) == ["lo"] and state == ["s"]
    # and Jev got all three in one call
    assert len(primary.asked) == 1 and set(primary.asked[0][1]) == {"hi", "lo", "mid"}


def test_llm_answer_is_used_when_it_disagrees():
    primary = Scripted({"q": J(True, 0.55)})
    ej = EscalatingJudge(primary, FakeJudge({"t": False}))
    r = ej.ask([], {"q": Question(YES_NO, "q", tag="t")})["q"]
    assert r.answer is False and r.escalated


def test_relationship_magnitude_goes_to_the_llm_directly():
    primary = Scripted({"dir": J("worse", 0.99)})
    llm = FakeJudge({"relationship_magnitude": 2})
    ej = EscalatingJudge(primary, llm)
    out = ej.ask(["s"], {
        "dir": choice_q("dir?", ["worse", "better"], tag="attitude_direction"),
        "mag": score_q("how much?", legend=("a", "b", "c"), tag="relationship_magnitude"),
    })
    assert out["mag"].answer == 2 and out["mag"].escalated
    assert set(primary.asked[0][1]) == {"dir"}, "Jev never saw the magnitude question"
    assert not out["dir"].escalated


def test_jev_down_falls_back_to_llm_for_everything():
    class Down(Judge):
        def ask(self, state, questions):
            raise JudgeError("boom")
    r = EscalatingJudge(Down(), FakeJudge({"t": True})).ask([], {"q": Question(YES_NO, "q", tag="t")})
    assert r["q"].answer is True and r["q"].escalated


def test_every_judgment_is_logged_with_probability_and_escalation():
    log = JudgmentLog()
    primary = Scripted({"a": J(True, 0.9), "b": J(True, 0.6)})
    lj = LoggingJudge(EscalatingJudge(primary, FakeJudge({"t": False})), log)
    lj.ask([], {"a": Question(YES_NO, "A?", tag="t"), "b": Question(YES_NO, "B?", tag="t")})
    assert [(e["question"], e["answer"], e["escalated"]) for e in log.entries] == [
        ("A?", True, False), ("B?", False, True)]
    assert log.entries[0]["probability"] == 0.9 and log.entries[0]["tag"] == "t"


def test_log_is_written_to_disk_when_a_path_is_given(tmp_path):
    log = JudgmentLog(tmp_path / "sub" / "judgments.jsonl")
    log.record("t", "Q?", J(True, 0.9))
    [line] = (tmp_path / "sub" / "judgments.jsonl").read_text().splitlines()
    assert json.loads(line)["question"] == "Q?"


# -- LLM judge -------------------------------------------------------------------------------
def test_llm_judge_parses_batched_answers():
    reply = json.dumps({"a": {"answer": "yes", "p_yes": 0.9},
                        "b": {"answer": "better", "probabilities": {"better": 0.6, "worse": 0.4}},
                        "c": {"answer": 2}})
    prov = FakeProvider(script={"llm": [reply]})
    out = LLMJudge(prov, "llm").ask(["state line"], {
        "a": yes_no_q("A?"), "b": choice_q("B?", ["better", "worse"]),
        "c": score_q("C?", legend=("x", "y", "z"))})
    assert len(prov.calls) == 1
    assert out["a"].answer is True and out["a"].probability == pytest.approx(0.9)
    assert out["b"].answer == "better" and out["c"].answer == 2
    assert "state line" in prov.calls[0][1][1]["content"]


def test_llm_judge_rejects_garbage_after_one_stricter_retry():
    prov = FakeProvider(script={"llm": ["no json here", "still prose"]})
    with pytest.raises(JudgeError):
        LLMJudge(prov, "llm").yes_no("q?")
    assert len(prov.calls) == 2 and "JSON object only" in prov.calls[1][1][1]["content"]
    ok = FakeProvider(script={"llm": ["sorry", '{"q": {"answer": "no", "p_yes": 0.1}}']})
    assert LLMJudge(ok, "llm").yes_no("q?").answer is False


def test_escalation_failure_names_the_cause():
    class Bad(Judge):
        def ask(self, state, questions):
            raise JudgeError("LLM exploded")
    ej = EscalatingJudge(Scripted({}), Bad())
    with pytest.raises(JudgeError, match="LLM exploded"):
        ej.ask([], {"m": score_q("how much?", legend=("a", "b"), tag="relationship_magnitude")})


def test_stub_judge_keeps_working():
    from harness.judge import StubJudge
    j = StubJudge()
    assert j.yes_no("q").answer is True
    assert j.choice("q", ["a", "b"]).answer == "a"
    assert j.score("q", lo=0, hi=10).answer == 5
