"""OpenRouter chat client and decision client: retry with backoff, usage, mid-stream errors."""
import json

import httpx
import pytest

from harness.judge import (
    DecisionJudge, EscalatingJudge, FallbackJudge, FakeJudge, JevJudge, JudgeError, LLMJudge,
)
from harness.models import PLAYER
from harness.policy import ModelNotAllowed, Spend
from harness.providers import FakeProvider, OpenRouterProvider, ProviderError
from conftest import diff, make_engine, narr

OK = {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}],
      "usage": {"cost": 0.0002}}


def provider(handler, **kw):
    sleeps = []
    p = OpenRouterProvider("sk-test", client=httpx.Client(transport=httpx.MockTransport(handler)),
                           sleep=sleeps.append, spend=kw.pop("spend", None), **kw)
    return p, sleeps


def test_retries_429_and_5xx_with_growing_backoff_then_succeeds():
    codes = iter([429, 503, 200])

    def handler(req):
        c = next(codes)
        return httpx.Response(c, json=OK if c == 200 else {"error": "x"})

    p, sleeps = provider(handler)
    assert p.complete("openai/gpt-6-luna", []) == "hi"
    assert len(sleeps) == 2 and sleeps[1] > sleeps[0]


def test_gives_up_after_the_retries_with_a_provider_error():
    n = []

    def handler(req):
        n.append(1)
        return httpx.Response(500, json={})

    p, sleeps = provider(handler, retries=3)
    with pytest.raises(ProviderError):
        p.complete("openai/gpt-6-luna", [])
    assert len(n) == 4 and len(sleeps) == 3


def test_a_400_is_not_retried_with_backoff():
    def handler(req):
        return httpx.Response(401, json={})

    p, sleeps = provider(handler)
    with pytest.raises(ProviderError):
        p.complete("openai/gpt-6-luna", [])
    assert not sleeps


def test_request_does_not_ask_for_deprecated_usage_and_spend_reads_the_response():
    seen = []
    spend = Spend()

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json=OK)

    p, _ = provider(handler, spend=spend)
    p.complete("openai/gpt-6-luna", [{"role": "user", "content": "x"}])
    assert "usage" not in seen[0] and "stream_options" not in seen[0]
    assert spend.total == pytest.approx(0.0002) and spend.calls == 1


def test_policy_is_enforced_before_any_request():
    p, _ = provider(lambda r: pytest.fail("no request expected"))
    for m in ("anthropic/claude-haiku-5.5", "acme/flagship-1"):
        with pytest.raises(ModelNotAllowed):
            p.complete(m, [])


def test_error_inside_a_200_response_is_an_error():
    p, _ = provider(lambda r: httpx.Response(200, json={"error": {"message": "upstream died"}}))
    with pytest.raises(ProviderError, match="upstream died"):
        p.complete("openai/gpt-6-luna", [])


def sse(*chunks):
    return "".join(f"data: {json.dumps(c)}\n\n" if isinstance(c, dict) else f"{c}\n\n"
                   for c in chunks)


def test_stream_skips_comments_and_reads_usage_from_the_final_chunk():
    spend = Spend()
    body = sse(": OPENROUTER PROCESSING",
               {"choices": [{"delta": {"content": "Hel"}}]},
               {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]},
               {"choices": [], "usage": {"cost": 0.0005}},
               "data: [DONE]")
    p, _ = provider(lambda r: httpx.Response(200, text=body), spend=spend)
    assert "".join(p.stream("openai/gpt-6-luna", [])) == "Hello"
    assert spend.total == pytest.approx(0.0005) and spend.calls == 1


def test_stream_mid_stream_error_chunk_is_an_error():
    body = sse({"choices": [{"delta": {"content": "Hel"}}]},
               {"choices": [{"delta": {"content": ""}, "finish_reason": "error"}],
                "error": {"message": "provider dropped"}})
    p, _ = provider(lambda r: httpx.Response(200, text=body))
    got = []
    with pytest.raises(ProviderError):
        for piece in p.stream("openai/gpt-6-luna", []):
            got.append(piece)
    assert got == ["Hel"]


def test_stream_retries_the_connection_on_429():
    codes = iter([429, 200])

    def handler(req):
        if next(codes) == 429:
            return httpx.Response(429, json={})
        return httpx.Response(200, text=sse({"choices": [{"delta": {"content": "ok"}}]},
                                            "data: [DONE]"))

    p, sleeps = provider(handler)
    assert "".join(p.stream("openai/gpt-6-luna", [])) == "ok" and len(sleeps) == 1


# -- decision client --------------------------------------------------------------------------
def decider(handler, model="liquid/d1-ultra", **kw):
    sleeps = []
    j = DecisionJudge("sk-test", model, client=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=sleeps.append, **kw)
    return j, sleeps


def test_decision_client_retries_429_then_answers_and_uses_the_systemone_endpoint():
    codes, urls = iter([429, 429, 200]), []

    def handler(req):
        urls.append(str(req.url))
        c = next(codes)
        return httpx.Response(c, json={"answers": {"q": {"noul": 0.9}}} if c == 200 else {})

    j, sleeps = decider(handler)
    r = j.yes_no("q?")
    assert r.answer is True and r.backend == "liquid/d1-ultra"
    assert len(sleeps) == 2 and set(urls) == {"https://openrouter.ai/api/v1/systemone"}


def test_decision_client_gives_up_with_a_judge_error():
    j, sleeps = decider(lambda r: httpx.Response(503, json={}), retries=2)
    with pytest.raises(JudgeError):
        j.yes_no("q?")
    assert len(sleeps) == 2


def test_one_client_serves_jev_pplx_and_d1_and_refuses_other_models():
    for m in ("typesafe/jev-1.14", "perplexity/pplx-decider-v1.2", "liquid/d1-ultra"):
        decider(lambda r: httpx.Response(200, json={}), m)
    with pytest.raises(ModelNotAllowed):
        decider(lambda r: httpx.Response(200, json={}), "openai/gpt-6-luna")
    assert JevJudge is DecisionJudge  # old name


def test_fallback_judge_uses_the_backup_when_the_primary_is_down():
    down, up = decider(lambda r: httpx.Response(500, json={}), retries=0)[0], FakeJudge(yes=True)
    seen = []
    fj = FallbackJudge(down, up, on_fallback=seen.append)
    assert fj.yes_no("q?").answer is True and len(seen) == 1


def test_llm_judge_switches_to_its_fallback_model():
    prov = FakeProvider(script={"a": [ProviderError("down")],
                                "b": ['{"q": {"answer": "yes", "p_yes": 0.9}}']})
    j = LLMJudge(prov, "a", fallback_model="b")
    assert j.yes_no("q?").answer is True
    assert [m for m, _ in prov.calls] == ["a", "b"]
    with pytest.raises(JudgeError):
        LLMJudge(FakeProvider(script={"a": [ProviderError("down")]}), "a").yes_no("q?")
    # an escalating judge degrades through a failing LLM as before
    assert EscalatingJudge(FakeJudge(), FakeJudge()) is not None


# -- engine: role fallbacks ---------------------------------------------------------------------
def test_engine_uses_the_fallback_model_when_a_call_fails():
    from harness.pipeline import ModelConfig
    eng, prov = make_engine({"narrator": [ProviderError("boom")], "narrator2": [narr("N.")],
                             "extractor": [diff()], "npc": ["Hello."]})
    eng.models = ModelConfig(narrator_fallback="narrator2")
    r = eng.turn("hi", speakers=["innkeeper"])
    assert r.narration == "N."
    [n] = [n for n in eng.devlog if n["kind"] == "model_fallback"]
    assert n["role"] == "narrator" and n["fallback"] == "narrator2"


def test_engine_without_a_fallback_fails_the_turn_and_rolls_it_back():
    eng, prov = make_engine({"narrator": [ProviderError("boom")]})
    with pytest.raises(ProviderError):
        eng.turn("hi", speakers=[])
    assert eng.log.active(["utterance"]) == []
    assert PLAYER in eng.scene.present


def test_model_temperature_is_sent_only_for_listed_models():
    import httpx
    from harness.policy import set_catalog
    from harness.providers import OpenRouterProvider
    set_catalog({"xiaomi/mimo-v2.6-pro": (0.435, 0.87), "openai/gpt-6-luna": (0.1, 0.5)})
    bodies = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json
        bodies.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    p = OpenRouterProvider(api_key="test", client=httpx.Client(transport=httpx.MockTransport(handler)))
    p.complete("xiaomi/mimo-v2.6-pro", [{"role": "user", "content": "hi"}])
    p.complete("openai/gpt-6-luna", [{"role": "user", "content": "hi"}])
    assert bodies[0]["temperature"] == 0.8
    assert "temperature" not in bodies[1]
    set_catalog(None)
