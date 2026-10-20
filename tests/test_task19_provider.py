"""Task 19: session id for sticky routing, cache counters, prompt layout for caching."""
import json

import httpx
import pytest

from conftest import PROFILES, diff
from harness.judge import FakeJudge
from harness.models import PLAYER, Scene
from harness.pipeline import Engine, ModelConfig
from harness.policy import Spend, set_catalog
from harness.providers import FakeProvider, OpenRouterProvider


@pytest.fixture(autouse=True)
def _reset_catalog():
    yield
    set_catalog(None)


def provider(handler, **kw):
    set_catalog({"m/cheap": (0.1, 0.5)})
    spend = Spend()
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return OpenRouterProvider("k" * 12, spend=spend, client=client, **kw), spend


def test_session_id_goes_in_the_body_and_cache_tokens_are_counted():
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"cost": 0.001, "prompt_tokens": 2000,
                      "prompt_tokens_details": {"cached_tokens": 1500, "cache_write_tokens": 100}}})

    p, spend = provider(handler, session_id="harness-abc")
    assert p.complete("m/cheap", [{"role": "user", "content": "hi"}]) == "ok"
    p.complete("m/cheap", [{"role": "user", "content": "hi again"}])
    assert all(b["session_id"] == "harness-abc" for b in seen)
    assert spend.prompt_tokens == 4000 and spend.cached_tokens == 3000
    assert spend.cache_write_tokens == 200 and spend.cache_hit_rate() == 0.75


def test_no_session_id_when_not_given_and_long_ids_are_cut():
    seen = []

    def handler(req):
        seen.append(json.loads(req.content))
        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "usage": {}})

    p, _ = provider(handler)
    p.complete("m/cheap", [{"role": "user", "content": "hi"}])
    assert "session_id" not in seen[0]
    p2, _ = provider(handler, session_id="x" * 400)
    p2.complete("m/cheap", [{"role": "user", "content": "hi"}])
    assert len(seen[1]["session_id"]) == 256


def test_the_prompt_prefix_is_stable_from_turn_to_turn():
    """Caching works on the longest identical prefix: the system message and the slowly growing
    knowledge come first, the changing scene and the player's input last. Two NPC calls in two turns
    share their whole system message and their user message up to the scene header."""
    prov = FakeProvider(script={"narrator": ["N."] * 2, "npc": ["Так."] * 2,
                                "extractor": ["none", diff()] * 2})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper"), 0), models=ModelConfig(),
                 judge=FakeJudge({"director_first": "innkeeper"}), record_language=None)
    eng.facts.add_canon("The innkeeper keeps a cellar.", knowers=[("innkeeper", "told")])
    eng.turn("Привіт.", speakers=["innkeeper"])
    eng.turn("Ще раз.", speakers=["innkeeper"])
    npc = [m for mod, m in prov.calls if mod == "npc"]
    assert npc[0][0] == npc[1][0]                                   # the system message: identical
    a, b = npc[0][1]["content"], npc[1][1]["content"]
    head = a.split("Location:")[0]
    assert "The innkeeper keeps a cellar." in head and b.startswith(head)
    nar = [m for mod, m in prov.calls if mod == "narrator"]
    assert nar[0][0] == nar[1][0]                                   # static rules live in the system message
    assert "Narrate what happens next." in nar[0][1]["content"].splitlines()[-1]
    assert nar[0][1]["content"].index("Location:") < nar[0][1]["content"].index("The player does/says")
