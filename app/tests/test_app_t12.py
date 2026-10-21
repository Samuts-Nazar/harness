"""Task 12 app tests: saved campaigns, parallel turn, hooks (fake engine, no network)."""
from __future__ import annotations

import pathlib
import tempfile

from app.campaigns import open_campaign
from app.game import Game
from app.stacks import fake_stack


import pytest as _pytest
import app.campaigns as _campaigns


@_pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    """App tests never read the local, uncommitted character file (data/Ragnar.md)."""
    monkeypatch.setattr(_campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(root=None, pace: float = 0.0) -> Game:
    stack = fake_stack()
    root = root or tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: open_campaign(stack, root=root, new=new), pace=pace)


def test_restart_continues_the_saved_campaign_and_new_button_starts_another(tmp_path):
    g = make(tmp_path)
    g.start_turn("Привіт, Горсте.")
    g.wait_idle()
    before = [dict(t) for t in g.transcript]
    name = g.camp.name
    assert (tmp_path / "current.txt").read_text() == name
    g.eng.close()
    g2 = make(tmp_path)  # a server restart
    assert g2.camp.name == name and g2.transcript == before
    assert g2.panel()["chips"] and g2.eng.scene.time == g.eng.scene.time
    g2.start_turn("Ще раз.")
    g2.wait_idle()
    assert len(g2.transcript) > len(before)
    g2.reset()  # "new campaign"
    assert g2.camp.name != name and [t["kind"] for t in g2.transcript] == ["intro"]
    assert (tmp_path / name / "campaign.db").exists()  # the old one stays on disk


def test_app_turn_runs_parallel_with_director_prose_and_reports_repetition(monkeypatch):
    monkeypatch.setattr(_campaigns, "DIALOGUE", "classic")  # the classic director (A/B)
    g = make()
    assert g.eng.parallel and g.eng.narration == "prose"
    g.start_turn("Дивлюсь на Горста.")
    g.wait_idle()
    d = g.debug
    assert d["parallel"] is True and d["repetition"]["score"] == 0.0
    assert any(c["role"] == "director: actions" for c in d["calls"])
    assert any(j["tag"] == "director_first" for j in d["judgments"])
    assert {"fixed", "near_misses"} <= set(d["names"])
    narr = next(m for _, m in g.camp.recorder.inner.calls if "narrator" in m[0]["content"])
    assert "observable_actions" not in narr[1]["content"]  # no JSON contract on creative calls


def test_narration_streams_before_the_first_npc_word_and_second_npc_hears_the_first(monkeypatch):
    monkeypatch.setattr(_campaigns, "DIALOGUE", "classic")  # the classic director (A/B)
    g = make()
    for _ in range(3):  # the third scripted narration has both NPCs speaking
        g.start_turn("Кажу щось.")
        g.wait_idle()
    evs = g.events_after(0)
    types = [e["type"] for e in evs]
    assert types.index("narr_end") < types.index("speaker")
    assert [e["who"] for e in evs if e["type"] == "speaker"] == ["horst", "elza"]
    elza_ctx = [m for _, m in g.camp.recorder.inner.calls
                if m[0]["content"].startswith("You are Ельза")][-1][1]["content"]
    assert "Горст: " in elza_ctx.split("Recent conversation:")[-1]


def test_no_extra_allowed_workaround_left_in_the_app():
    root = pathlib.Path(__file__).resolve().parents[1]
    for f in [*root.glob("*.py"), root / "README.md", root / "tests" / "live_check.py"]:
        assert "HARNESS_EXTRA_ALLOWED" not in f.read_text(), f
