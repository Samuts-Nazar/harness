"""The local model option: LocalProvider (llama.cpp server), local_stack, the --local flags.
No real server: httpx MockTransport."""
import json

import httpx
import pytest

from harness.judge import LLMJudge
from harness.policy import ModelNotAllowed, check_model, set_catalog
from harness.providers import LOCAL_URL, LocalProvider, ProviderError

NARRATOR_SYS = {"role": "system", "content": "You are the narrator of a game."}
JUDGE_SYS = {"role": "system", "content": LLMJudge.SYSTEM}


def local(handler, **kw):
    sleeps = []
    p = LocalProvider(client=httpx.Client(transport=httpx.MockTransport(handler)),
                      sleep=sleeps.append, **kw)
    return p, sleeps


def test_request_body_has_no_openrouter_fields_and_no_key():
    seen = []

    def handler(req):
        seen.append(req)
        return httpx.Response(200, json={"choices": [{"message": {"content": "Дощ."}}]})

    p, _ = local(handler)
    assert p.complete("gemma-local", [NARRATOR_SYS, {"role": "user", "content": "x"}]) == "Дощ."
    p.complete("gemma-local", [JUDGE_SYS, {"role": "user", "content": "x"}])
    body = json.loads(seen[0].content)
    assert str(seen[0].url) == LOCAL_URL
    assert "authorization" not in seen[0].headers
    assert set(body) == {"model", "messages", "temperature"}
    assert body["temperature"] == 0.8  # creative role
    assert json.loads(seen[1].content)["temperature"] < 0.8  # a narrow judgment: steadier
    assert p.spend.total == 0 and p.spend.calls == 2


def test_a_local_call_does_not_open_the_price_caps():
    """LocalProvider never consults the catalog, and it leaves no global state behind: the
    same name is still refused for the hosted client afterwards."""
    set_catalog({})  # an empty catalog: any hosted model would be refused
    try:
        p, _ = local(lambda req: httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]}))
        assert p.complete("my-local-gguf", [NARRATOR_SYS]) == "ok"
        assert p.complete("claude-local", [NARRATOR_SYS]) == "ok"
        with pytest.raises(ModelNotAllowed):
            check_model("my-local-gguf")
        with pytest.raises(ModelNotAllowed, match="Anthropic"):
            check_model("claude-local")
    finally:
        set_catalog(None)


def test_streaming_parses_sse_deltas():
    sse = "".join(f"data: {json.dumps(c)}\n\n" for c in [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"content": "Дощ "}}]},
        {"choices": [{"delta": {"content": "іде."}}]},
        {"choices": [{"delta": {}, "finish_reason": "stop"}]},
    ]) + "data: [DONE]\n\n"

    def handler(req):
        assert json.loads(req.content)["stream"] is True
        return httpx.Response(200, content=sse.encode(), headers={"content-type": "text/event-stream"})

    p, _ = local(handler)
    assert list(p.stream("gemma-local", [NARRATOR_SYS])) == ["Дощ ", "іде."]


def test_server_not_up_gives_a_clear_error_after_retries():
    def handler(req):
        raise httpx.ConnectError("Connection refused")

    p, sleeps = local(handler, url="http://127.0.0.1:9/v1/chat/completions")
    with pytest.raises(ProviderError) as e:
        p.complete("gemma-local", [NARRATOR_SYS])
    assert "http://127.0.0.1:9/v1/chat/completions" in str(e.value)
    assert "docs/local-llm.md" in str(e.value)
    assert len(sleeps) == p.retries
    with pytest.raises(ProviderError, match="docs/local-llm.md"):
        list(p.stream("gemma-local", [NARRATOR_SYS]))


def test_at_most_slots_requests_in_flight():
    import threading
    import time

    busy, peak, lock = [0], [0], threading.Lock()

    def handler(req):
        with lock:
            busy[0] += 1
            peak[0] = max(peak[0], busy[0])
        time.sleep(0.05)
        with lock:
            busy[0] -= 1
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}]})

    p, _ = local(handler, slots=2)
    ts = [threading.Thread(target=p.complete, args=("gemma-local", [JUDGE_SYS])) for _ in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert peak[0] == 2


def test_local_stack_wiring_needs_no_key(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    from app.stacks import LOCAL_TIMEOUT_S, local_stack

    s = local_stack("http://127.0.0.1:8099/v1/chat/completions", "my-gguf")
    assert isinstance(s.provider, LocalProvider) and s.provider.url.endswith(":8099/v1/chat/completions")
    m = s.models
    for role in ("narrator", "npc", "extractor", "judge", "assistant", "reader"):
        assert getattr(m, role) == "my-gguf" and getattr(m, role + "_fallback") is None
    assert type(s.judge) is LLMJudge and s.judge.provider is s.provider
    assert s.judge.system.endswith(LLMJudge.COMPACT)  # one-line JSON: a third of the tokens
    assert not LLMJudge(s.provider, "x").system.endswith(LLMJudge.COMPACT)
    assert s.judge.fallback_model is None
    # no abandoned calls (they would keep running in a server slot): the read timeout bounds a call
    assert s.live and s.local and s.fast_timeout is None
    assert s.provider.timeout == LOCAL_TIMEOUT_S >= 60


def test_local_timeout_reaches_the_engine_and_canon_has_no_hosted_embedder(monkeypatch):
    from app import vizima
    from app.stacks import local_stack

    s = local_stack()
    assert vizima.engine_kw(s)["fast_timeout"] == s.fast_timeout
    monkeypatch.setattr(vizima, "canon_path", lambda *a, **k: "be.db")
    monkeypatch.setattr(vizima, "Canon", lambda store, embedder: embedder)
    assert vizima.load_canon(s) is None  # full-text recall only: no network


def test_cli_local_flags():
    from app.__main__ import make_stack, parse_args

    a = parse_args(["--local", "--local-url", "http://h:1/v1/chat/completions", "--local-model", "x"])
    s = make_stack(a)
    assert s.local and s.provider.url == "http://h:1/v1/chat/completions" and s.models.narrator == "x"
    assert not parse_args([]).local
    with pytest.raises(SystemExit):
        parse_args(["--local", "--live"])
    with pytest.raises(SystemExit):
        parse_args(["--local-model", "x"])  # needs --local
    with pytest.raises(SystemExit):
        parse_args(["--local-timeout", "60"])
    assert make_stack(parse_args(["--local", "--local-timeout", "60"])).provider.timeout == 60


def test_llm_judge_accepts_answers_keyed_by_question_text_or_bare():
    """Gemma (local) keys its answer by the question's text, inside a code fence."""
    from harness.judge import choice_q, yes_no_q
    from harness.providers import FakeProvider

    q = "Does the line assert a fact this character had no channel to learn?"
    by_text = '```json\n{\n  "' + q + '": {\n    "answer": "no",\n    "p_yes": 0.05\n  }\n}\n```'
    bare = '{"answer": "yes", "p_yes": 0.9}'
    two = json.dumps({"[a] " + q: {"answer": "yes", "p_yes": 0.9},
                      "Who?": {"answer": "x", "probabilities": {"x": 0.7}}})
    prov = FakeProvider(script={"m": [by_text, bare, two]})
    j = LLMJudge(prov, "m")
    assert j.yes_no(q).answer is False
    assert j.yes_no(q).answer is True
    out = j.ask([], {"a": yes_no_q(q), "b": choice_q("Who?", ["x", "y"])})
    assert out["a"].answer is True and out["b"].answer == "x"
    assert len(prov.calls) == 3  # no retries needed


def test_a_server_that_never_answers_is_not_retried_and_frees_its_slot():
    """A read timeout is final: no retry storm holding the slot again; the slot is free after."""
    attempts = []

    def handler(req):
        attempts.append(1)
        raise httpx.ReadTimeout("timed out", request=req)

    p, sleeps = local(handler, slots=1, timeout=7)
    with pytest.raises(ProviderError, match="no answer in 7 s") as e:
        p.complete("gemma-local", [NARRATOR_SYS])
    assert "start it" not in str(e.value).lower()
    assert attempts == [1] and sleeps == []
    with pytest.raises(ProviderError):
        list(p.stream("gemma-local", [NARRATOR_SYS]))
    assert attempts == [1, 1]
    assert p._slots.acquire(blocking=False)  # released both times
    p._slots.release()


def test_mid_stream_drop_is_not_reported_as_server_down():
    class Broken(httpx.SyncByteStream):
        def __iter__(self):
            yield b'data: {"choices": [{"delta": {"content": "D"}}]}\n\n'
            raise httpx.ReadError("connection reset")

    p, sleeps = local(lambda req: httpx.Response(200, stream=Broken()))
    with pytest.raises(ProviderError, match="broke mid-answer") as e:
        list(p.stream("gemma-local", [NARRATOR_SYS]))
    assert "docs/local-llm.md" not in str(e.value) and sleeps == []


def test_an_answer_without_choices_is_a_provider_error():
    p, _ = local(lambda req: httpx.Response(200, json={"object": "chat.completion"}))
    with pytest.raises(ProviderError, match="no choices"):
        p.complete("gemma-local", [NARRATOR_SYS])
