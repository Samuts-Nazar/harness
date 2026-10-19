import json

import pytest

from harness import policy
from harness.policy import ModelNotAllowed, check_model, load_catalog


def test_cheap_non_anthropic_models_in_the_catalog_are_allowed():
    for m in ("openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017", "qwen/qwen3.8-omni-flash",
              "google/gemini-3.5-flash-lite", "acme/free-model:free"):
        check_model(m)


def test_price_ceiling_on_input_and_output():
    with pytest.raises(ModelNotAllowed, match="costs"):
        check_model("acme/flagship-1")
    with pytest.raises(ModelNotAllowed, match="costs"):  # input fine, output 3.00 > 2.50
        check_model("acme/cheap-in-dear-out")
    with pytest.raises(ModelNotAllowed):
        check_model("elorian/glimpse")  # output 3.00 per M


def test_anthropic_is_refused_even_when_cheap():
    assert policy.prices()["anthropic/claude-haiku-5.5"][0] <= policy.MAX_INPUT_PER_M
    with pytest.raises(ModelNotAllowed, match="Anthropic"):
        check_model("anthropic/claude-haiku-5.5")


def test_deny_list_variable_prices_and_unknown_models():
    with pytest.raises(ModelNotAllowed, match="deny"):
        check_model("openrouter/auto")
    with pytest.raises(ModelNotAllowed, match="variable"):
        check_model("acme/variable")
    with pytest.raises(ModelNotAllowed, match="not in the OpenRouter catalog"):
        check_model("nobody/never-heard-of-it")


def test_decision_models_are_allowed_by_list_not_by_catalog():
    for m in ("liquid/d1-ultra", "perplexity/pplx-decider-v1.2",
              "perplexity/pplx-decider-flash-v1.2", "typesafe/jev-1.13", "typesafe/jev-1.14"):
        assert m not in policy.prices()
        check_model(m)
    with pytest.raises(ModelNotAllowed):
        check_model("typesafe/jev-9.99")


def test_env_deny_list(monkeypatch):
    monkeypatch.setenv("HARNESS_DENY", "openai/gpt-6-luna")
    with pytest.raises(ModelNotAllowed, match="deny"):
        check_model("openai/gpt-6-luna")


def test_surcharge_tiers_count_towards_the_ceiling():
    table = policy.parse_catalog({"data": [{"id": "a/b", "pricing": {
        "prompt": "0.0000001", "completion": "0.0000005",
        "overrides": [{"min_prompt_tokens": 100000, "prompt": "0.000001", "completion": "0.000005"}]}}]})
    assert table["a/b"] == pytest.approx((1.0, 5.0))


def test_no_anthropic_default_anywhere():
    for m in (policy.DEFAULT_NARRATOR, policy.DEFAULT_NPC, policy.DEFAULT_EXTRACTOR,
              policy.DEFAULT_JUDGE_FIRST, policy.DEFAULT_JUDGE_LLM, *policy.FALLBACKS.values()):
        assert "anthropic" not in m and "claude" not in m
    assert policy.DEFAULT_JUDGE_FIRST in policy.DECISION_MODELS
    assert policy.FALLBACKS["judge_first"] in policy.DECISION_MODELS


# -- the price cache ---------------------------------------------------------------------------
RAW = {"data": [{"id": "x/y", "pricing": {"prompt": "0.0000002", "completion": "0.000001"}}]}


def test_catalog_is_fetched_once_cached_with_a_date_and_refreshed_after_a_day(tmp_path):
    path, now, fetched = tmp_path / "c.json", [1_000_000.0], []

    def fetch():
        fetched.append(1)
        return RAW

    kw = dict(path=path, fetch=fetch, now=lambda: now[0])
    assert load_catalog(**kw)["x/y"] == pytest.approx((0.2, 1.0))
    saved = json.loads(path.read_text())
    assert saved["fetched_at"] == 1_000_000.0 and saved["date"] == "1970-01-12"
    load_catalog(**kw)
    now[0] += 23 * 3600
    load_catalog(**kw)
    assert len(fetched) == 1  # still fresh
    now[0] += 2 * 3600
    load_catalog(**kw)
    assert len(fetched) == 2  # older than a day


def test_failed_refresh_uses_the_old_cache_and_no_cache_fails_closed(tmp_path):
    path = tmp_path / "c.json"
    path.write_text(json.dumps({"fetched_at": 0, "catalog": RAW}))

    def boom():
        raise OSError("offline")

    assert "x/y" in load_catalog(path=path, fetch=boom, now=lambda: 10**9)
    with pytest.raises(ModelNotAllowed, match="cannot verify"):
        load_catalog(path=tmp_path / "none.json", fetch=boom)
