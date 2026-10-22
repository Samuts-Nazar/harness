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
