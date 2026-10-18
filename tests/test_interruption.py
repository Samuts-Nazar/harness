import pytest

from harness.models import INTERRUPTION, PLAYER, UTTERANCE
from harness.pipeline import InterruptionError
from harness.streaming import InterruptHandle, iter_words, run_stream
from conftest import diff, fact, make_engine

LINE = "I saw the stranger near the well and he carried a black sword"


def _script(extra_ext=None, lines=(LINE,)):
    return {
        "narrator": ["N.", "N2.", "N3."],
        "npc": list(lines),
        "extractor": extra_ext
        or [diff(fact("Stranger with black sword near well", "innkeeper"))],
    }


def test_iter_words_handles_chunk_boundaries():
    assert list(iter_words(["he", "llo wor", "ld ", " a", "b"])) == ["hello", "world", "ab"]


def test_run_stream_cut_position():
    h = InterruptHandle()
    seen = []

    def on_word(w):
        seen.append(w)
        if len(seen) == 3:
            h.request()

    r = run_stream(["one two three four five"], h, on_word)
    assert r.spoken == ("one", "two", "three")
    assert r.tail == ("four", "five")
    assert r.interrupted and seen == ["one", "two", "three"]


def test_live_interrupt_cuts_stores_intent_and_records_event():
    # live interruption happens before extraction, so the extractor only sees the spoken part
    eng, prov = make_engine(_script(extra_ext=[diff()]))
    h = InterruptHandle()
    count = 0

    def on_word(npc, w):
        nonlocal count
        count += 1
        if count == 4:
            h.request()

    res = eng.turn("hello", speakers=["innkeeper"], handle=h, on_word=on_word)
    assert res.interrupted
    assert res.utterances[0].payload["text"] == "I saw the stranger"
    pend = eng.intents.pending("innkeeper")
    assert [e.payload["text"] for e in pend] == ["near the well and he carried a black sword"]
    # interruption visible to everyone present, and not the intent
    ints = eng.log.active([INTERRUPTION])
    assert len(ints) == 1 and set(ints[0].witnesses) == {PLAYER, "innkeeper", "bard"}
    assert any("interrupted" in f.content for f in eng.facts.visible_to("bard", eng.scene.time))
    assert not any("black sword" in f.content for f in eng.facts.visible_to("bard", eng.scene.time))
    # the tail never reaches the extractor
    ext_prompt = [m for model, m in prov.calls if model == "extractor"][0][1]["content"]
    assert "black sword" not in ext_prompt


def test_retroactive_interrupt_rolls_back_state_from_tail():
    script = _script(extra_ext=[
        diff(fact("Stranger with black sword near well", "innkeeper")),
        diff(fact("Innkeeper saw a stranger", "innkeeper")),
    ])
    eng, _ = make_engine(script)
    eng.turn("hello", speakers=["innkeeper"])
    assert any("black sword" in f.content for f in eng.facts.visible_to("bard", eng.scene.time))
    kept = eng.interrupt_retroactive(4)
    assert kept.payload["text"] == "I saw the stranger"
    contents = [f.content for f in eng.facts.visible_to("bard", eng.scene.time)]
    assert not any("black sword" in c for c in contents)
    assert any("interrupted" in c for c in contents)
    assert [e.payload["text"] for e in eng.log.active([UTTERANCE]) if e.payload["speaker"] == "innkeeper"] \
        == ["I saw the stranger"]
    assert eng.intents.pending("innkeeper")[0].payload["text"].startswith("near the well")
    # the truncated utterance's own facts were re-extracted
    assert any("saw a stranger" in f.content for f in eng.facts.visible_to("innkeeper", eng.scene.time))


def test_retroactive_limited_to_last_npc_utterance_and_once():
    script = {
        "narrator": ["N", "N"],
        "npc": [LINE, "Another line here for the bard to say"],
        "extractor": [diff(), diff(), diff()],
    }
    eng, _ = make_engine(script)
    with pytest.raises(InterruptionError):
        eng.interrupt_retroactive(2)  # nothing to interrupt
    eng.turn("a", speakers=["innkeeper"])
    eng.turn("b", speakers=["bard"])
    # last NPC utterance is the bard's; the innkeeper's can no longer be cut
    kept = eng.interrupt_retroactive(3)
    assert kept.payload["speaker"] == "bard"
    with pytest.raises(InterruptionError):
        eng.interrupt_retroactive(1)  # already interrupted
    texts = {e.payload["speaker"]: e.payload["text"] for e in eng.log.active([UTTERANCE])
             if e.payload["speaker"] != PLAYER}
    assert texts["innkeeper"] == LINE  # untouched


@pytest.mark.parametrize("bad", [0, -1, 13, 99])
def test_retroactive_cut_must_be_inside_utterance(bad):
    eng, _ = make_engine(_script(extra_ext=[diff()]))
    eng.turn("a", speakers=["innkeeper"])
    with pytest.raises(InterruptionError):
        eng.interrupt_retroactive(bad)
    assert len(eng.log.active([INTERRUPTION])) == 0


def test_intent_retained_and_shown_only_to_owner():
    eng, prov = make_engine(_script(extra_ext=[diff(), diff(), diff()],
                                    lines=[LINE, "Well then."]))
    eng.turn("a", speakers=["innkeeper"])
    eng.interrupt_retroactive(3)
    owner = " ".join(m["content"] for m in eng.ctx.character("innkeeper", eng.scene))
    other = " ".join(m["content"] for m in eng.ctx.character("bard", eng.scene))
    assert "the well and he carried" in owner
    assert "the well and he carried" not in other
    eng.turn("b", speakers=["innkeeper"])  # intent persists across turns
    assert len(eng.intents.pending("innkeeper")) == 1
    last_prompt = [m for model, m in prov.calls if model == "npc"][-1][1]["content"]
    assert "the well and he carried" in last_prompt
