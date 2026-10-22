"""The turn assistant in the app: suggestions come after turn_done, in their own thread, and are
dropped when a new turn starts."""
from __future__ import annotations

import tempfile
import threading

import pytest
from starlette.testclient import TestClient

from app import campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack
from harness.director import NEXT_TAG


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(floors=("horst", "player")) -> Game:
    stack = fake_stack()
    stack.judge.rules["director_narration"] = False
    stack.judge.rules[NEXT_TAG] = list(floors)
    root = tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0)


def types(g: Game) -> list[str]:
    return [e["type"] for e in g.events_after(0)]


def test_suggestions_emitted_after_turn_done_not_before():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    t = types(g)
    assert "suggestions" in t
    assert t.index("suggestions") > t.index("turn_done")
    assert t.index("suggestions") > max(i for i, x in enumerate(t) if x == "word")
    ev = next(e for e in g.events_after(0) if e["type"] == "suggestions")
    assert ev["turn"] == g.turn_no and len(ev["items"]) == 3
    assert all(isinstance(x, str) and x for x in ev["items"])


def test_assistant_runs_off_the_turn_thread():
    g = make()
    names: list[str] = []
    from harness import assistant
    real = assistant.ask

    def spy(*a, **k):
        names.append(threading.current_thread().name)
        return real(*a, **k)

    import app.game as gm
    gm.assistant.ask = spy
    try:
        g.start_turn("Що кажете?")
        g.wait_idle(20)
    finally:
        gm.assistant.ask = real
    assert names and names[0] != g.thread.name


def test_more_avoids_shown():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    c = TestClient(create_app(g))
    first = c.get("/api/suggestions").json()
    assert first["turn"] == g.turn_no and len(first["items"]) == 3
    more = c.get("/api/suggestions?more=1").json()
    assert len(more["items"]) == 3
    assert not set(more["items"]) & set(first["items"])
    again = c.get("/api/suggestions").json()
    assert again["items"] == first["items"] + more["items"]
    prompt = "\n".join(m["content"] for m in g.eng.provider.inner.calls[-1][1])
    assert first["items"][0] in prompt, "the shown ones are in the prompt"
    assert g.eng.provider.calls[-1]["role"] == "assistant"


def test_new_turn_discards_pending_suggestions():
    g = make()
    gate = threading.Event()
    from harness import assistant
    import app.game as gm
    real = assistant.ask

    def slow(*a, **k):
        out = real(*a, **k)
        gate.wait(10)  # the answer is ready only after the next turn began
        return out

    gm.assistant.ask = slow
    try:
        g.start_turn("Що кажете?")
        first = g.turn_no
        g.thread.join(20)  # the turn is over; the suggestion thread is still waiting
        g.start_turn("Ще одне.")
        assert g.turn_no == first + 1
        gate.set()
        g.wait_idle(20)
    finally:
        gm.assistant.ask = real
        gate.set()
    evs = [e for e in g.events_after(0) if e["type"] == "suggestions"]
    assert all(e["turn"] == g.turn_no for e in evs), "nothing of the first turn survives"
    c = TestClient(create_app(g))
    assert c.get("/api/suggestions").json()["turn"] == g.turn_no


def test_slow_suggestions_do_not_delay_the_next_turns_first_word():
    import time

    import app.game as gm
    from harness import assistant
    g = make()
    real = assistant.ask
    gm.assistant.ask = lambda *a, **k: (time.sleep(1.5), real(*a, **k))[1]
    try:
        g.start_turn("Що кажете?")
        g.thread.join(20)  # the model for the suggestions is still "thinking"
        t0 = time.monotonic()
        g.start_turn("Ще одне.")
        g.thread.join(20)
        took = time.monotonic() - t0
        assert g.debug["timing"]["first_word_s"] is not None
        assert took < 1.0, f"the next turn waited for the suggestions ({took:.2f}s)"
    finally:
        gm.assistant.ask = real
        g.wait_idle(20)
