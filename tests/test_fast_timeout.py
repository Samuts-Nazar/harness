"""A fast-lane model call (narrator, NPC) that hangs is cut after `fast_timeout` seconds and
retried once on the fallback route (smoke 2026-10-22: one NPC call took 47.8 s, first word at
61.7 s, no timeout, no fallback). Fake providers only."""
import threading

import pytest

from harness.pipeline import ModelConfig
from harness.providers import FakeProvider, ProviderError
from conftest import diff, make_engine, narr


class HangingOnce(FakeProvider):
    """The first call to `slow_model` blocks until released; later calls answer at once."""

    def __init__(self, slow_model, script):
        super().__init__(script=script)
        self.slow_model, self.release, self.hung = slow_model, threading.Event(), 0

    def complete(self, model, messages):
        if model == self.slow_model and self.hung == 0:
            self.hung += 1
            self.release.wait(5)
            raise ProviderError("late")  # whatever it says later is dropped
        return super().complete(model, messages)


def engine(script, models, slow="narrator", timeout=0.2):
    eng, prov = make_engine({})
    prov = HangingOnce(slow, script)
    eng.provider, eng.models, eng.fast_timeout = prov, models, timeout
    return eng, prov


def test_hanging_call_is_retried_on_the_fallback_model_and_recorded():
    eng, prov = engine({"narrator2": [narr("N.")], "extractor": [diff()], "npc": ["Hello."]},
                       ModelConfig(narrator_fallback="narrator2"))
    r = eng.turn("hi", speakers=["innkeeper"])
    prov.release.set()
    assert r.narration == "N."
    [n] = [n for n in eng.devlog if n["kind"] == "model_timeout"]
    assert (n["role"], n["model"], n["retry_on"], n["seconds"]) == ("narrator", "narrator", "narrator2", 0.2)


def test_hanging_call_without_a_fallback_model_is_retried_once_on_the_same_model():
    eng, prov = engine({"narrator": [narr("N.")], "extractor": [diff()], "npc": ["Hello."]},
                       ModelConfig())
    r = eng.turn("hi", speakers=["innkeeper"])
    prov.release.set()
    assert r.narration == "N."
    [n] = [n for n in eng.devlog if n["kind"] == "model_timeout"]
    assert n["retry_on"] == "narrator"


def test_two_timeouts_in_a_row_fail_the_call():
    class Always(FakeProvider):
        def complete(self, model, messages):
            threading.Event().wait(1)
            return "late"
    eng, _ = make_engine({})
    eng.provider, eng.fast_timeout = Always(), 0.05
    with pytest.raises(ProviderError, match="timed out"):
        eng._complete("npc", [{"role": "user", "content": "x"}])


def test_only_the_fast_lane_roles_are_timed():
    eng, _ = make_engine({"extractor": ["ok"]})
    eng.fast_timeout = 0.0001
    assert eng._complete("extractor", [{"role": "user", "content": "x"}]) == "ok"
