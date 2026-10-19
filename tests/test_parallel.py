"""The parallel turn: independent calls run together, results do not depend on timing."""
import json
import threading

import pytest

from harness.judge import FakeJudge
from harness.models import PLAYER, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from conftest import PROFILES, diff, fact, narr

LINES = {"Innkeeper": "Welcome, traveller.", "Dandelion": "Oh, I know that story."}


class RoleProvider:
    """Thread-safe provider answering by role and, for NPCs, by the name in the system prompt,
    so replies do not depend on which thread asks first. An optional barrier makes the NPC
    calls wait for each other: it only passes if they really run at the same time."""

    parallel_ok = True

    def __init__(self, narrators, extractors, barrier=None, delay_first=0.0):
        self.narrators, self.extractors = list(narrators), list(extractors)
        self.barrier, self.calls, self.lock = barrier, [], threading.Lock()
        self.delay_first = delay_first
        self.threads = set()
        self.npc_messages = {}

    def complete(self, model, messages):
        with self.lock:
            self.calls.append(model)
            self.threads.add(threading.current_thread().name)
        if model == "narrator":
            with self.lock:
                return self.narrators.pop(0)
        if model == "extractor":
            with self.lock:
                return self.extractors.pop(0)
        who = messages[0]["content"].split(".")[0].removeprefix("You are ")
        with self.lock:
            self.npc_messages.setdefault(who, []).append(messages[1]["content"])
        if self.barrier is not None:
            self.barrier.wait(timeout=5)  # BrokenBarrierError if the other call never starts
        if who == "Innkeeper" and self.delay_first:
            threading.Event().wait(self.delay_first)  # the first speaker is the slower one
        return LINES[who]

    def stream(self, model, messages):
        yield self.complete(model, messages)


def engine(provider, *, parallel, judge=None, **kw):
    scene = Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0)
    kw.setdefault("narration", "json")
    kw.setdefault("record_language", None)
    return Engine(provider, PROFILES, scene, models=ModelConfig(), parallel=parallel,
                  judge=judge, **kw)


def run(parallel, judge=None, **prov_kw):
    prov = RoleProvider(
        [narr("The fire pops.", ["The innkeeper nods"], ["innkeeper", "bard"])],
        [diff(fact("The bard knows the mill story", "bard", 0.7))], **prov_kw)
    eng = engine(prov, parallel=parallel, judge=judge)
    res = eng.turn("Hello, everyone.")
    return eng, prov, res


def log_dump(eng):
    return [(e.type, e.payload.get("speaker"), e.payload.get("text")) for e in eng.log.active()]


def test_a_later_npc_hears_the_earlier_line_of_the_turn():
    eng, prov, res = run(True)
    assert [u.payload["speaker"] for u in res.utterances] == ["innkeeper", "bard"]
    assert "Innkeeper: Welcome, traveller." in prov.npc_messages["Dandelion"][0]
    assert "Dandelion:" not in prov.npc_messages["Innkeeper"][0]  # the first one hears nothing yet
    # the checks ran too: the bard's line was judged knowing what the innkeeper said
    asked = [st for st, qs in eng.judge.inner.asked if any(q.tag == "unknown_claim" for q in qs.values())]
    assert any("Welcome, traveller." in " ".join(st) for st in asked)


def test_lines_are_delivered_in_narrator_order_even_when_the_first_is_slower():
    delivered = []
    prov = RoleProvider([narr("N.", [], ["innkeeper", "bard"])], [diff()], delay_first=0.3)
    eng = engine(prov, parallel=True)
    eng.turn("hi", on_word=lambda who, w: delivered.append(who))
    assert delivered[0] == "innkeeper" and delivered[-1] == "bard"
    assert delivered == sorted(delivered, key=["innkeeper", "bard"].index)


def test_parallel_and_sequential_give_the_same_log_judgments_and_notes():
    a, _, ra = run(False)
    b, _, rb = run(True)
    assert log_dump(a) == log_dump(b)
    assert [j["tag"] for j in a.judgments.entries] == [j["tag"] for j in b.judgments.entries]
    assert a.devlog == b.devlog
    assert ra.narration == rb.narration and len(ra.fact_ids) == len(rb.fact_ids)


def test_event_order_is_fixed_whatever_the_timing():
    dumps = set()
    for delay in (0.0, 0.15):
        prov = RoleProvider([narr("N.", ["The bard grins"], ["innkeeper", "bard"])], [diff()],
                            delay_first=delay)
        eng = engine(prov, parallel=True)
        eng.turn("hi")
        dumps.add(tuple(log_dump(eng)))
    assert len(dumps) == 1


def test_a_rejected_narration_discards_the_started_chains_and_is_regenerated():
    quoted = narr('He says "go away".', [], ["innkeeper"])  # the judge flags speech
    prov = RoleProvider([quoted, narr("Quiet.", [], ["innkeeper"])], [diff()])
    judge = FakeJudge({"narrator_speech": lambda q, st: "go away" in st[0]})
    eng = engine(prov, parallel=True, judge=judge)
    res = eng.turn("hi")
    assert res.narration == "Quiet."
    texts = [e.payload["text"] for e in eng.log.active(["narration"])]
    assert texts == ["Quiet."]  # the rejected narration left no active event
    assert any(n["kind"] == "narrator_speech_rejected" for n in eng.devlog)
    assert any(n["kind"] == "speculative_chains_discarded" for n in eng.devlog)
    assert [u.payload["speaker"] for u in res.utterances] == ["innkeeper"]


def test_failure_in_a_worker_rolls_the_turn_back():
    class Broken(RoleProvider):
        def complete(self, model, messages):
            if model == "npc":
                raise RuntimeError("model fell over")
            return super().complete(model, messages)

    eng = engine(Broken([narr("N.", [], ["innkeeper"])], [diff()]), parallel=True)
    with pytest.raises(RuntimeError, match="fell over"):
        eng.turn("hi")
    assert eng.log.active(["utterance", "narration"]) == []


def test_interruption_in_parallel_mode_keeps_the_rest_as_intent():
    prov = RoleProvider([narr("N.", [], ["innkeeper", "bard"])], [diff()])
    eng = engine(prov, parallel=True)
    from harness.streaming import InterruptHandle
    h, n = InterruptHandle(), []

    def on_word(who, w):
        n.append(w)
        if len(n) == 1:
            h.request()

    res = eng.turn("hi", handle=h, on_word=on_word)
    assert res.interrupted and len(res.utterances) == 1
    assert eng.intents.pending("innkeeper")
    assert any(x["kind"] == "chains_unused_after_interruption" for x in eng.devlog)


def test_fake_provider_stays_sequential_unless_it_opts_in():
    assert Engine(FakeProvider(), PROFILES, Scene("x", (PLAYER,))).parallel is False
    assert Engine(RoleProvider([], []), PROFILES, Scene("x", (PLAYER,))).parallel is True
    assert Engine(FakeProvider(), PROFILES, Scene("x", (PLAYER,)), parallel=True).parallel is True


def test_state_change_judgments_run_in_one_wave_and_apply_in_order():
    ch = {"character": "player", "category": "equipment", "op": "add", "item": "a sword",
          "observable": True, "source": "action1"}
    ch2 = dict(ch, item="a torch", source="action2")
    out = {}
    for par in (False, True):
        eng = engine(RoleProvider(
            [narr("N.", ["Geralt draws a sword", "Geralt lights a torch"], [])],
            [json.dumps({"new_facts": [], "state_changes": [ch, ch2]})]), parallel=par)
        eng.turn("go")
        out[par] = [(e.type, e.payload.get("text") or e.payload.get("item")) for e in eng.log.active()]
        assert [j["tag"] for j in eng.judgments.entries].count("salience") == 4  # 2 changes x 2 observers
    assert out[False] == out[True]
