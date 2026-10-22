"""The client (app/static/app.js) under a DOM stub in node: a late retract of an earlier turn
removes only that turn's elements and leaves the running turn alone (final review)."""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

HERE = Path(__file__).resolve().parent
APP_JS = HERE.parent / "static" / "app.js"
NODE = shutil.which("node")
PANEL = {"name": "Рагнар", "chips": [], "prose": []}


def replay(events):
    out = subprocess.run([NODE, str(HERE / "client_harness.js"), str(APP_JS), json.dumps(events)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_late_retract_removes_only_its_own_turn():
    evs = [
        {"type": "turn_start", "turn": 1, "text": "Перша."},
        {"type": "speaker", "turn": 1, "tok": "tk_horst", "label": "Горст"},
        {"type": "word", "turn": 1, "tok": "tk_horst", "w": "Так."},
        {"type": "turn_done", "turn": 1, "clock": "x", "panel": PANEL, "lines": [], "cut_lines": []},
        {"type": "turn_start", "turn": 2, "text": "Друга."},
        {"type": "retract", "turn": 1, "text": "Перша.", "message": "збій"},
    ]
    got = replay(evs)
    texts = [x["text"] for x in got["feed"]]
    assert texts == ["Друга."], texts
    assert got["input"] == "", "an earlier turn's text is not put back into the composer"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_retract_of_the_current_turn_still_clears_it():
    evs = [
        {"type": "turn_start", "turn": 1, "text": "Перша."},
        {"type": "turn_done", "turn": 1, "clock": "x", "panel": PANEL, "lines": [], "cut_lines": []},
        {"type": "retract", "turn": 1, "text": "Перша.", "message": "збій"},
    ]
    got = replay(evs)
    assert got["feed"] == [] and got["input"] == "Перша." and got["busy"] is False


def run(job):
    out = subprocess.run([NODE, str(HERE / "client_harness.js"), str(APP_JS), json.dumps(job)],
                         capture_output=True, text=True, timeout=30, check=True)
    return json.loads(out.stdout.strip().splitlines()[-1])


SAID = "Сто п'ятдесят? *потер палець об палець* За такі гроші в Брідках рік живуть."


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_live_stream_and_reload_give_the_same_paragraphs():
    """Review Focus 3: the page built from the stream equals the page built from the transcript
    (speech with its beats, a gesture, the same speaker twice = two paragraphs, a cut line)."""
    words = SAID.split()
    live = run([
        {"type": "turn_start", "turn": 1, "text": "Скільки?"},
        {"type": "narr_start", "turn": 1},
        *({"type": "narr_word", "turn": 1, "w": w} for w in "Двері рипнули.".split()),
        {"type": "narr_end", "turn": 1},
        {"type": "speaker", "turn": 1, "tok": "a1b2c3d4", "label": "сивий чоловік"},
        *({"type": "word", "turn": 1, "tok": "a1b2c3d4", "w": w} for w in words),
        {"type": "npc_act", "turn": 1, "tok": "a1b2c3d4", "label": "сивий чоловік",
         "text": "Він кладе кошіль на стіл."},
        {"type": "speaker", "turn": 1, "tok": "a1b2c3d4", "label": "сивий чоловік"},
        {"type": "word", "turn": 1, "tok": "a1b2c3d4", "w": "Ну?"},
        {"type": "turn_done", "turn": 1, "clock": "x", "panel": PANEL, "lines": [7, 9],
         "cut_lines": [9]},
    ])
    state = {"title": "t", "live": False, "clock": "x", "panel": PANEL, "transcript": [
        {"kind": "player", "text": "Скільки?"},
        {"kind": "narr", "text": "Двері рипнули."},
        {"kind": "npc", "tok": "a1b2c3d4", "label": "сивий чоловік", "text": SAID, "event": 7},
        {"kind": "npc_act", "tok": "a1b2c3d4", "label": "сивий чоловік",
         "text": "Він кладе кошіль на стіл."},
        {"kind": "npc", "tok": "a1b2c3d4", "label": "сивий чоловік", "text": "Ну?", "event": 9,
         "cut": True},
    ]}
    reloaded = run({"state": state})
    assert live["feed"] == reloaded["feed"]
    assert [p["line"] for p in live["feed"]] == ["me", "narr", "say", "act", "say"]
    say = live["feed"][2]
    assert say["q"] == ["— Сто п'ятдесят?", "— За такі гроші в Брідках рік живуть."]
    assert say["beat"] == ["— потер палець об палець."], "a beat is base italic between dashes"
    assert say["ink"] == "var(--ink-a1b2c3d4, var(--ink-none))", "speech is keyed on the token"
    assert live["feed"][4]["cut"] and live["feed"][4]["event"] == 9


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_ink_event_sets_one_root_property():
    got = run([{"type": "ink", "tok": "a1b2c3d4", "ink": "#8fb8e8"}])
    assert got["root"]["--ink-a1b2c3d4"] == "#8fb8e8"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_sheet_items_follow_the_spec_rules():
    """Review Focus 5: challenge on NPC speech only; model error on the last world output only;
    retroactive cut on the last NPC line only (and only once); ink on any line of a character.
    Model error and cut appear only when the server offers them."""
    base = {"kind": "say", "tok": "t", "event": True, "cut": False, "lastWorld": True,
            "lastLine": True, "busy": False}
    both = ["model_error", "cut"]
    cases = [
        (base, both, ["challenge", "model_error", "cut", "ink"]),
        (base, [], ["challenge", "ink"]),
        ({**base, "lastWorld": False, "lastLine": False}, both, ["challenge", "ink"]),
        ({**base, "lastLine": False}, both, ["challenge", "model_error", "ink"]),
        ({**base, "cut": True}, both, ["challenge", "model_error", "ink"]),
        ({**base, "busy": True, "event": False}, both, ["ink"]),
        ({**base, "kind": "act", "event": False}, both, ["model_error", "ink"]),
        ({**base, "kind": "narr", "tok": "", "event": False}, both, ["model_error"]),
        ({**base, "kind": "narr", "tok": "", "event": False, "lastWorld": False}, both, []),
        ({**base, "kind": "me", "tok": "", "event": False, "lastWorld": False}, both, []),
    ]
    expr = "[" + ",".join(f"sheetItems({json.dumps(x)}, {json.dumps(o)})" for x, o, _ in cases) + "]"
    got = run({"events": [], "eval": expr})["value"]
    assert got == [want for _, _, want in cases]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_client_palette_is_the_server_palette():
    from app.inks import PALETTE as SERVER
    got = run({"events": [], "eval": "PALETTE"})["value"]
    assert tuple(got) == SERVER


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_suggestions_of_the_current_turn_only_and_cleared_by_a_new_turn():
    evs = [
        {"type": "turn_start", "turn": 1, "text": "Перша."},
        {"type": "turn_done", "turn": 1, "clock": "x", "panel": PANEL, "lines": [], "cut_lines": []},
        {"type": "suggestions", "turn": 1, "items": ["Торгуватись", "Мовчки чекати"]},
    ]
    assert run({"events": evs, "eval": "sugg.items"})["value"] == ["Торгуватись", "Мовчки чекати"]
    evs2 = evs + [{"type": "turn_start", "turn": 2, "text": "Друга."},
                  {"type": "suggestions", "turn": 1, "items": ["Застаріле"]}]
    assert run({"events": evs2, "eval": "sugg.items"})["value"] == []
