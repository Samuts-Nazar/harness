"""Final whole-branch review: corrections in the slow lane, the game lock never held across model
calls, the stream never waiting for it, the drawer's wording and the ink endpoint (no network)."""
from __future__ import annotations

import tempfile
import threading
import time

import pytest
from starlette.testclient import TestClient

from app import campaigns
from app.campaigns import open_campaign
from app.game import Game, _as_the_character
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
    root = tempfile.mkdtemp(prefix="harness-app-final-")
    g = Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0, suggestions=False)
    g.floors = lambda: stack.judge.rules.__setitem__(NEXT_TAG, list(floors))  # type: ignore
    return g


def slow_settle(g: Game, gate: threading.Event) -> None:
    orig = g.eng.settle

    def settle(*a, **kw):  # the slow lane (when there is one) takes as long as the test says
        if g.eng._slow is not None:
            gate.wait(10)
        return orig(*a, **kw)
    g.eng.settle = settle


def in_slow_lane(g: Game, timeout=10.0) -> None:
    end = time.monotonic() + timeout
    while not (g.running and g.phase == "idle"):
        assert time.monotonic() < end, "the turn never reached its slow lane"
        time.sleep(0.01)


def last(g, kind):
    return dict([t for t in g.transcript if t["kind"] == kind][-1])


# -- finding 3: the actions are always listed ----------------------------------------------
def test_state_lists_the_corrections_during_the_slow_lane_and_settled_carries_them():
    g = make()
    gate = threading.Event()
    slow_settle(g, gate)
    g.start_turn("Що кажете?")
    in_slow_lane(g)
    assert g.state()["actions"] == ["model_error", "cut"]
    gate.set()
    g.wait_idle(20)
    settled = [e for e in g.events_after(0) if e["type"] == "settled"]
    assert settled and settled[-1]["actions"] == ["model_error", "cut"]
    g._ended = True
    g.challenging = True  # no database read while a correction runs (minor: _is_ended)
    assert g.state()["actions"] == []
    g.challenging = False


# -- finding 4: a correction asked for in the slow lane waits for it -------------------------
@pytest.mark.parametrize("kind", ["model_error", "cut"])
def test_correction_in_the_slow_lane_waits_and_succeeds(kind):
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    gate = threading.Event()
    slow_settle(g, gate)
    g.floors()
    g.start_turn("Ще одне.")
    in_slow_lane(g)
    c = TestClient(create_app(g))
    assert g.transcript[-1]["kind"] == "npc", g.transcript[-1]
    line = last(g, "npc")
    body = ({"event": line["event"], "explanation": "не так"} if kind == "model_error"
            else {"event": line["event"], "after_words": 1})
    threading.Timer(0.3, gate.set).start()
    t0 = time.monotonic()
    r = c.post(f"/api/{kind}", json=body)
    assert r.status_code == 200, r.text
    assert time.monotonic() - t0 >= 0.25, "it waited for the slow lane"
    assert not g.running and not g.challenging


def test_correction_while_the_turn_is_told_is_still_busy():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    g.phase = "speaking"
    c = TestClient(create_app(g))
    r = c.post("/api/model_error", json={"event": None, "explanation": "x"})
    assert r.status_code == 409
    g.phase = "idle"


def test_correction_gives_up_after_the_wait():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    gate = threading.Event()
    slow_settle(g, gate)
    g.start_turn("Ще одне.")
    in_slow_lane(g)
    from app.game import Busy
    with pytest.raises(Busy):
        g._claim(wait=0.1)
    assert not g.challenging
    gate.set()
    g.wait_idle(20)


# -- finding 5: no model call under the game lock; the stream never waits for it -------------
def test_stream_and_state_answer_while_slow_translations_run():
    g = make()
    g.eng._utterance("horst", "Раніше.")  # not the first turn of the scene (that one is narrated)
    started, gate = threading.Event(), threading.Event()
    calls: list[int] = []

    def slow_translate(texts):
        calls.append(len(texts))
        started.set()
        gate.wait(10)
        return list(texts)
    g.start_turn("Що кажете?")
    in_slow_lane(g)
    g.camp.translate = slow_translate
    try:
        assert started.wait(10), "the views were never computed"
        t0 = time.monotonic()
        g.events_after(0)
        g.state()
        g.cast()
        g.people()
        assert time.monotonic() - t0 < 0.5, "a request waited for the translator"
        c = TestClient(create_app(g))
        t0 = time.monotonic()
        assert c.get("/api/state").status_code == 200
        assert time.monotonic() - t0 < 1.0
    finally:
        gate.set()
    g.wait_idle(20)


def test_known_facts_are_translated_in_one_batch():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    calls: list[list[str]] = []
    g.camp.translate = lambda texts: (calls.append(list(texts)), list(texts))[1]
    cast = [{"tok": g.camp.tok(c), "label": "x", "ink": "#000000", "present": True}
            for c in ("horst", "elza")]
    g.eng.facts.add_canon("Elza (a young woman in a shawl) owns the mill.",
                          knowers=[("player", "told")])
    g.eng.facts.add_canon("Horst (a stout grey-haired man) keeps the inn.",
                          knowers=[("player", "told")])
    known = g._compute_known(cast)
    assert len(calls) <= 1
    assert sum(len(v) for v in known.values()) == sum(len(c) for c in calls)


def test_ink_flushes_never_collide(tmp_path):
    from app.inks import InkBook
    book = InkBook(tmp_path / "inks.json")
    errors: list[BaseException] = []

    def worker(i):
        try:
            for k in range(30):
                book.set(f"t{i}", "#%06x" % (i * 1000 + k))
                book.flush()
        except BaseException as e:  # noqa: BLE001
            errors.append(e)
    ts = [threading.Thread(target=worker, args=(i,)) for i in range(6)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    assert not errors, errors
    import json
    assert set(json.loads((tmp_path / "inks.json").read_text())) == {f"t{i}" for i in range(6)}
    assert not list(tmp_path.glob("*.tmp"))


# -- minors ------------------------------------------------------------------------------------
def test_set_ink_validates_against_the_cast_and_errors_are_clean():
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    c = TestClient(create_app(g), raise_server_exceptions=False)
    tok = g.camp.tok("horst")
    assert c.post("/api/ink", json={"tok": tok, "ink": "#8fb8e8"}).status_code == 200
    never_met = g.camp.tok("elza") if not any(x["tok"] == g.camp.tok("elza") for x in g.cast()) \
        else "zzzzzzzz"
    assert c.post("/api/ink", json={"tok": never_met, "ink": "#8fb8e8"}).status_code == 404
    assert c.post("/api/ink", json={"tok": tok, "ink": 5}).status_code == 400

    def boom(*_a, **_k):
        raise RuntimeError("disk")
    g.set_ink = boom
    r = c.post("/api/ink", json={"tok": tok, "ink": "#8fb8e8"})
    assert r.status_code == 500 and "error" in r.json()


def test_drawer_says_vy_in_the_case_of_the_replaced_word():
    f = lambda t: _as_the_character(t, "Рагнар")
    assert f("Гравець бачив його вчора.") == "Рагнар бачив його вчора."          # nominative
    assert f("Він бачив, що гравець мовчить.") == "Він бачив, що Рагнар мовчить."
    assert f("Розмовляв з гравцем про млин.") == "Розмовляв з вами про млин."   # instrumental
    assert f("Він розповів гравцеві про млин.") == "Він розповів вам про млин."  # dative
    assert f("Він довірився гравцю.") == "Він довірився вам."
    assert f("Він не знає гравця.") == "Він не знає вас."                      # genitive
    assert f("Він розповів про це the player.") == "Він розповів про це Рагнар."
    assert _as_the_character("Гравець бачив.") == "Ви бачив."   # no name: «ви»
    assert f("") == ""
    assert f("Ігровий гравецький стіл.") == "Ігровий гравецький стіл."


def test_translated_panel_and_known_facts_never_show_an_unlearned_name():
    """Smoke 2026-10-22: a record in English wrote the name in Latin ("Horst"), the mask (which
    knows the Ukrainian spelling) let it through, and the translator turned it into «Горст».
    The mask runs again on the translated text, in every case form the translator may produce."""
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    assert not g.eng.names.knows("player", "horst")
    g.camp.translate = lambda texts: [t.replace("Horst", "Горста").replace("asks", "питає")
                                      for t in texts]
    g.eng.facts.add_canon("The player asks Horst (a stout man) about the mill.",
                          knowers=[("player", "witnessed")])
    panel = g._compute_panel()
    assert panel["prose"] and not any("Горст" in p for p in panel["prose"])
    cast = [{"tok": g.camp.tok("horst"), "label": "x", "ink": "#000000", "present": True}]
    known = g._compute_known(cast)
    assert not any("Горст" in f for facts in known.values() for f in facts)


def test_model_error_without_event_on_an_npc_line_says_what_to_send():
    """Smoke 2026-10-22 item 14: `event: null` on a turn that ends with an NPC line answered
    «Це вже не воно»; the message now says to send the event number."""
    g = make()
    g.start_turn("Що кажете?")
    g.wait_idle(20)
    assert g.transcript[-1]["kind"] == "npc"
    c = TestClient(create_app(g))
    r = c.post("/api/model_error", json={"event": None, "explanation": "не так"})
    assert r.status_code == 400
    assert "event" in r.json()["error"] and "номер" in r.json()["error"]
    assert "Це вже не воно" not in r.json()["error"]
    ok = c.post("/api/model_error", json={"event": last(g, "npc")["event"], "explanation": "не так"})
    assert ok.status_code == 200
