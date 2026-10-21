"""Living dialogue in the app: a quick exchange is just the speakers' lines, no narration; each
line is its own block, gesture-only steps show as the NPC's action; typing cuts in; a tap skips
the pace."""
from __future__ import annotations

import tempfile
import threading
import time

import pytest
from starlette.testclient import TestClient

from app import campaigns
from app.game import Game
from app.server import create_app
from app.stacks import fake_stack
from harness.director import NEXT_TAG, SHAPE_TAG


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(pace=0.0, narration=False, floors=None, shapes=None) -> Game:
    stack = fake_stack()
    stack.judge.rules["director_narration"] = narration
    if floors:
        stack.judge.rules[NEXT_TAG] = list(floors)
    if shapes:
        stack.judge.rules[SHAPE_TAG] = list(shapes)
    root = tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: campaigns.open_campaign(stack, root=root, new=new), pace=pace)


def wait_phase(g, phase, timeout=10):
    end = time.time() + timeout
    while g.phase != phase and time.time() < end:
        time.sleep(0.005)
    assert g.phase == phase


def wait_event(g, type, timeout=10):
    """Until the running turn has emitted an event of this type (no fixed sleeps)."""
    end = time.time() + timeout
    while not any(e["type"] == type for e in g.events_after(0)) and time.time() < end:
        time.sleep(0.002)
    assert any(e["type"] == type for e in g.events_after(0))


def after(g, text):
    """Transcript entries after the player's `text`."""
    i = next(i for i, t in enumerate(g.transcript) if t.get("text") == text)
    return g.transcript[i + 1:]


def test_app_defaults_to_living_dialogue():
    assert campaigns.DIALOGUE == "living"
    assert make().eng.dialogue == "living"


def test_app_turn_without_narration():
    g = make()
    g.start_turn("Добрий вечір.")
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "speaker" in types and "word" in types and "turn_done" in types
    assert "narr_start" not in types and "narr_word" not in types
    assert not any(t["kind"] == "narr" for t in g.transcript)


def test_empty_exchange_turn_renders():
    """Nobody answers: the turn still ends cleanly (the engine narrates the silence), and no
    empty bubble or NPC block appears."""
    g = make(floors=["nobody"])
    g.start_turn("Мовчу.")
    g.wait_idle(20)
    types = [e["type"] for e in g.events_after(0)]
    assert "turn_done" in types and "error" not in types and "speaker" not in types
    assert not any(t["kind"] == "npc" for t in g.transcript)
    assert all(t["text"].strip() for t in g.transcript)
    assert g.phase == "idle"


def test_empty_narration_is_never_shown():
    g = make()
    spoken: list[str] = []
    g._stream_narration("   ", spoken, lambda: None)
    assert spoken == []
    assert not [e for e in g.events_after(0) if e["type"] in ("narr_start", "narr_word")]
    assert g.phase == "idle"


def test_each_line_of_an_exchange_is_its_own_block():
    g = make(floors=["horst", "elza", "horst", "player"])
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    evs = g.events_after(0)
    assert [e["who"] for e in evs if e["type"] == "speaker"] == ["horst", "elza", "horst"]
    npc = [t for t in g.transcript if t["kind"] == "npc"]
    assert [t["who"] for t in npc] == ["horst", "elza", "horst"]
    assert all(t["text"] for t in npc) and all(t["event"] for t in npc)
    done = next(e for e in evs if e["type"] == "turn_done")
    assert done["lines"] == [t["event"] for t in npc]


def test_gesture_step_is_shown_as_the_npcs_action_between_lines():
    g = make(floors=["horst", "elza", "horst", "player"], shapes=["normal", "gesture", "normal"])
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    kinds = [(t["kind"], t["who"]) for t in g.transcript if t["kind"] in ("npc", "npc_act")]
    assert kinds == [("npc", "horst"), ("npc_act", "elza"), ("npc", "horst")]
    act = next(t for t in g.transcript if t["kind"] == "npc_act")
    assert act["text"] and act["name"]
    order = [e["type"] for e in g.events_after(0) if e["type"] in ("speaker", "npc_act")]
    assert order == ["speaker", "npc_act", "speaker"]  # horst twice: two blocks


def test_send_during_exchange_interrupts_then_runs():
    g = make(pace=0.02, floors=["horst", "elza", "horst", "player"])
    g.start_turn("Перша.")
    wait_phase(g, "speaking")
    wait_event(g, "word")  # at least one word of the first line is out
    g.start_turn("Друга.")  # cuts in, waits for the first turn, runs the second
    g.wait_idle(30)
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша.", "Друга."]
    first = [t for t in g.transcript[:g.transcript.index(
        next(t for t in g.transcript if t.get("text") == "Друга."))] if t["kind"] == "npc"]
    assert first and first[-1].get("cut") is True
    first_line = [u for u in g.eng.log.active(["utterance"]) if u.payload["speaker"] != "player"][0]
    assert first_line.payload.get("interrupted") is True
    assert any(t["kind"] == "npc" for t in after(g, "Друга."))  # the second turn ran


def test_send_during_exchange_via_http_does_not_return_409():
    g = make(pace=0.02)
    c = TestClient(create_app(g))
    assert c.post("/api/turn", json={"text": "Перша."}).status_code == 202
    assert c.post("/api/turn", json={"text": "Друга."}).status_code == 202
    g.wait_idle(30)
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша.", "Друга."]


def test_skip_delivers_rest_without_interrupt():
    g = make(pace=0.3, floors=["horst", "elza", "player"])
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Що кажете?"})
    wait_phase(g, "speaking")
    t0 = time.time()
    assert c.post("/api/skip").status_code == 200
    g.wait_idle(30)
    assert time.time() - t0 < 3, "the rest must come at once, not at 0.3 s a word"
    evs = g.events_after(0)
    assert next(e for e in evs if e["type"] == "turn_done")["interrupted"] is False
    assert not any(t.get("cut") for t in g.transcript)
    npc = [t for t in g.transcript if t["kind"] == "npc"]
    assert [t["who"] for t in npc] == ["horst", "elza"]
    assert " ".join(e["w"] for e in evs if e["type"] == "word") == " ".join(t["text"] for t in npc)
    assert g.pace == 0
    g.start_turn("Ще.")  # the next turn is paced again
    assert g.pace == 0.3
    g.skip()
    g.wait_idle(30)


def test_skip_when_idle_is_harmless():
    g = make(pace=0.1)
    assert TestClient(create_app(g)).post("/api/skip").status_code == 200
    assert g.pace == 0.1


def test_next_turn_waits_for_the_last_turns_slow_lane_and_reads_no_db_meanwhile():
    """The flaky failures: a new turn started while the last turn's thread was still in its slow
    lane (and the bookkeeping after it), and the request thread read the database (`ended`) at
    the same time; one SQLite connection used from two threads. Now the new turn's thread waits
    for the last one, and nothing reads the database from the request thread while a turn's
    thread is alive. Synchronised on events, no sleeps."""
    g = make()
    entered, release = threading.Event(), threading.Event()
    real_settle = g.eng.settle

    def settle():
        if g.phase == "idle" and not entered.is_set():  # the slow lane after the fast one
            entered.set()
            assert release.wait(10)
        return real_settle()

    g.eng.settle = settle
    g.start_turn("Перша.")
    assert entered.wait(10)  # the first turn is idle for the player, its thread still busy
    first = g.thread
    reads: list[object] = []
    real_active, real_turn = g.eng.log.active, g.eng.turn
    turns: list[str] = []

    def active(*a, **k):
        if threading.current_thread() is threading.main_thread():
            reads.append(a)
        return real_active(*a, **k)

    def turn(text, **k):
        assert not first.is_alive(), "the new turn ran next to the last turn's slow lane"
        turns.append(text)
        return real_turn(text, **k)

    g.eng.log.active, g.eng.turn = active, turn
    st = g.state()
    assert st["running"] and st["ended"] is False and st["phase"] == "idle"
    g.start_turn("Друга.")
    assert reads == [], "no database read from the request thread while a turn's thread runs"
    release.set()
    g.wait_idle(30)
    assert turns == ["Друга."]
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша.", "Друга."]


def test_death_in_a_turn_is_seen_as_soon_as_the_player_can_read():
    """Review round 1: the player character dies in a turn; while that turn's slow lane still
    runs, `state()` already says ended and a new turn is refused."""
    from app.game import Ended
    from harness.models import PLAYER
    from harness.outcome import CHARACTER_DEATH
    g = make()
    entered, release = threading.Event(), threading.Event()
    real_settle, real_turn = g.eng.settle, g.eng.turn

    def turn(text, **k):
        r = real_turn(text, **k)
        g.eng.log.append(CHARACTER_DEATH, game_time=g.eng.scene.time, location="x",
                         participants=[PLAYER], witnesses=[], notability=1.0,
                         payload={"text": "The player character dies: x", "reason": "body"})
        return r

    def settle():
        if g.phase == "idle" and not entered.is_set():
            entered.set()
            assert release.wait(10)
        return real_settle()

    g.eng.turn, g.eng.settle = turn, settle
    g.start_turn("Перша.")
    assert entered.wait(10)
    try:
        assert g.state()["ended"] is True
        with pytest.raises(Ended):
            g.start_turn("Друга.")
    finally:
        release.set()
        g.wait_idle(30)


def test_gesture_step_survives_a_reload():
    """Final review: a gesture-only step is an ACTION with {text, by, gesture}; the rebuilt
    transcript shows it as the NPC's action, in its place, masked like the live path."""
    g = make(floors=["horst", "elza", "horst", "player"], shapes=["normal", "gesture", "normal"])
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    live = [(t["kind"], t["who"], t.get("name"), t["text"]) for t in g.transcript
            if t["kind"] in ("npc", "npc_act")]
    rebuilt = [(t["kind"], t["who"], t.get("name"), t["text"]) for t in g.camp.transcript()
               if t["kind"] in ("npc", "npc_act")]
    assert rebuilt == live


def test_start_turn_rechecks_a_challenge_that_began_while_it_waited():
    """Final review: a challenge that starts while start_turn waits for the running turn to stop
    is seen in the second locked block (Busy), not raced."""
    from app.game import Busy
    g = make(pace=0.02, floors=["horst", "elza", "horst", "player"])
    g.start_turn("Перша.")
    wait_phase(g, "speaking")
    real = g.interrupt

    def interrupt(any_phase=False):
        g.challenging = True  # a challenge begins right after the first check
        return real(any_phase)

    g.interrupt = interrupt
    with pytest.raises(Busy):
        g.start_turn("Друга.")
    g.challenging = False
    g.wait_idle(30)
    assert [t["text"] for t in g.transcript if t["kind"] == "player"] == ["Перша."]
