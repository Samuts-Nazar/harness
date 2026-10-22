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
        ({**base, "kind": "act", "event": False}, both, ["ink"]),   # an old server's gesture: no id
        ({**base, "kind": "act"}, both, ["model_error", "ink"]),    # the last gesture can be rewritten
        ({**base, "kind": "act", "lastWorld": False}, both, ["ink"]),
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


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_every_npc_line_and_gesture_carries_the_masked_label():
    """Speaker names are a CSS switch (body.names): the label is in every NPC speech and gesture
    paragraph, in the masked form the page was given; player and narration have none."""
    t = "a1b2c3d4"
    state = {"title": "t", "live": False, "clock": "x", "panel": PANEL, "transcript": [
        {"kind": "npc", "tok": t, "label": "сивий чоловік", "text": "Сто п'ятдесят?"},
        {"kind": "npc_act", "tok": t, "label": "сивий чоловік", "text": "Сивий чоловік кашляє."},
        {"kind": "npc", "tok": t, "label": "сивий чоловік", "text": "Ну?"},
        {"kind": "npc", "tok": "e5f6", "label": "жінка в хустці",
         "text": "*жінка в хустці хитає головою* Ні."},
    ]}
    texts = [p["text"] for p in run({"state": state})["feed"]]
    assert texts[0].startswith("сивий чоловік: — Сто")
    assert texts[1] == "сивий чоловік: Сивий чоловік кашляє.", "a gesture is labelled too"
    assert texts[2] == "сивий чоловік: — Ну?", "the same speaker twice: labelled both times"
    assert texts[3].startswith("жінка в хустці: жінка в хустці хитає головою"), texts[3]


def _reload_state(last_player, pending):
    # the turn id decides what the transcript holds: the running turn is 2, the error case's
    # last player entry belongs to turn 1
    t = 2 if last_player == pending else 1
    return {"title": "t", "live": False, "clock": "x", "panel": PANEL, "running": True,
            "phase": "idle", "pending_turn": pending, "turn": 2, "transcript": [
                {"kind": "player", "text": "Перша.", "turn": 1},
                {"kind": "npc", "tok": "aa", "label": "він", "text": "Раз.", "event": 1, "turn": 1},
                {"kind": "player", "text": last_player, "turn": t},
                {"kind": "npc", "tok": "aa", "label": "він", "text": "Два.", "event": 2, "turn": t},
            ]}


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_reload_in_the_slow_lane_skips_only_that_turn_and_a_retract_removes_it():
    replayed = [
        {"type": "turn_start", "turn": 2, "text": "Друга."},
        {"type": "speaker", "turn": 2, "tok": "aa", "label": "він"},
        {"type": "word", "turn": 2, "tok": "aa", "w": "Два."},
        {"type": "turn_done", "turn": 2, "clock": "x", "panel": PANEL, "lines": [2], "cut_lines": []},
    ]
    got = run({"load": _reload_state("Друга.", "Друга."), "events": replayed})
    assert [p["text"] for p in got["feed"]] == ["Перша.", "він: — Раз.", "Друга.", "він: — Два."], "no duplicate"
    retracted = run({"load": _reload_state("Друга.", "Друга."), "events": replayed + [
        {"type": "retract", "turn": 2, "text": "Друга.", "message": "збій"}]})
    assert [p["text"] for p in retracted["feed"]] == ["Перша.", "він: — Раз."]
    assert retracted["input"] == "Друга."
    nxt = run({"load": _reload_state("Друга.", "Друга."), "events": replayed + [
        {"type": "turn_start", "turn": 3, "text": "Третя."},
        {"type": "speaker", "turn": 3, "tok": "aa", "label": "він"},
        {"type": "word", "turn": 3, "tok": "aa", "w": "Три."}]})
    assert [p["text"] for p in nxt["feed"]][-2:] == ["Третя.", "він: — Три."], "the next turn is shown"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_reload_after_an_error_does_not_swallow_the_next_turn():
    """The error path: phase idle, thread still alive, no turn_done ever comes for that turn and
    the transcript does not hold it. Nothing is skipped; the error drops the replayed turn, and
    the next turn is shown."""
    state = _reload_state("Перша-б.", "Друга.")
    evs = [
        {"type": "turn_start", "turn": 2, "text": "Друга."},
        {"type": "speaker", "turn": 2, "tok": "aa", "label": "він"},
        {"type": "word", "turn": 2, "tok": "aa", "w": "Ох"},
        {"type": "error", "turn": 2, "text": "Друга.", "message": "збій"},
        {"type": "turn_start", "turn": 3, "text": "Третя."},
        {"type": "speaker", "turn": 3, "tok": "aa", "label": "він"},
        {"type": "word", "turn": 3, "tok": "aa", "w": "Три."},
        {"type": "turn_done", "turn": 3, "clock": "x", "panel": PANEL, "lines": [5], "cut_lines": []},
    ]
    got = run({"load": state, "events": evs})
    texts = [p["text"] for p in got["feed"]]
    assert texts == ["Перша.", "він: — Раз.", "Перша-б.", "він: — Два.", "Третя.", "він: — Три."], texts


# -- final whole-branch review -------------------------------------------------------------------
def _slow_lane_state(actions):
    return {"title": "t", "live": False, "clock": "x", "panel": PANEL, "running": True,
            "phase": "idle", "turn": 1, "actions": actions, "transcript": [
                {"kind": "player", "text": "Перша.", "turn": 1},
                {"kind": "npc", "tok": "aa", "label": "він", "text": "Раз два три.", "event": 4,
                 "turn": 1}]}


LAST_SAY_ITEMS = "sheetItems(lineInfo(lines()[lines().length - 1]), actions)"


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_reload_in_the_slow_lane_still_offers_the_corrections_afterwards():
    """Finding 3: a load() during the slow lane keeps «Помилка моделі» and the cut (the server
    lists them always), and a settled event refreshes them."""
    got = run({"load": _slow_lane_state(["model_error", "cut"]), "events": [
        {"type": "settled", "turn": 1, "clock": "x", "panel": PANEL,
         "actions": ["model_error", "cut"]}], "eval": LAST_SAY_ITEMS})
    assert "model_error" in got["value"] and "cut" in got["value"]
    # an older server's empty list during the slow lane is corrected by settled
    got = run({"load": _slow_lane_state([]), "events": [
        {"type": "settled", "turn": 1, "clock": "x", "panel": PANEL,
         "actions": ["model_error", "cut"]}], "eval": LAST_SAY_ITEMS})
    assert "model_error" in got["value"] and "cut" in got["value"]


FAIL_FETCH = ("fetch = () => Promise.resolve({ ok: false, "
              "json: () => Promise.resolve({ error: 'Хід триває.' }) });")


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_model_error_button_is_enabled_again_after_a_failure():
    """Finding 4: the dialog's button says «Зачекайте…» while it waits and comes back on error."""
    expr = ("(async () => { " + FAIL_FETCH +
            " const p = lines()[lines().length - 1]; openModelError(p);"
            " const box = p.children[p.children.length - 1];"
            " const [note, go] = box.children; note.value = 'не так';"
            " const seen = []; const orig = postAndReload;"
            " postAndReload = async (u, b) => { seen.push([go.disabled, go.textContent]);"
            " return orig(u, b); };"
            " await go.click(); return [seen[0], go.disabled, go.textContent,"
            " document.getElementById('errbar').textContent]; })()")
    got = run({"state": _slow_lane_state(["model_error", "cut"]), "eval": expr})["value"]
    assert got[0] == [True, "Зачекайте…"]
    assert got[1] is False and got[2] == "Переписати" and got[3] == "Хід триває."


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_cut_picker_skips_beats_and_the_last_word_and_recovers_after_a_failure():
    pts = run({"events": [], "eval": f"cutPoints({json.dumps(SAID)})"})["value"]
    assert [p["text"] for p in pts if "*" in p["text"]] == []
    cuts = [p["after"] for p in pts if p["cut"]]
    assert cuts == [1, 2, 7, 8, 9, 10, 11, 12], cuts   # not in the beat, not after «живуть.»
    beats = [p["text"] for p in pts if p["beat"]]
    assert beats == ["потер", "палець", "об", "палець"]
    one = run({"events": [], "eval": "cutPoints('*киває* Так.')"})["value"]
    assert [p["cut"] for p in one] == [False, False]
    expr = ("(async () => { " + FAIL_FETCH +
            " const p = lines()[lines().length - 1]; openCut(p);"
            " const bs = p._body.children.filter((c) => c.className === 'cw');"
            " await bs[0].click(); return [bs.length, bs.every((b) => !b.disabled), bs[0].textContent]; })()")
    got = run({"state": _slow_lane_state(["model_error", "cut"]), "eval": expr})["value"]
    assert got == [2, True, "Раз"]


@pytest.mark.skipif(NODE is None, reason="node is not installed")
def test_reset_event_reloads_the_page():
    expr = ("(() => { let n = 0; fetch = () => { n++; return new Promise(() => {}); };"
            " handlers.reset({}); return n; })()")
    assert run({"events": [], "eval": expr})["value"] >= 1
