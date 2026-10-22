"""The relation line is for judges and the NPC itself: never the panel, people or suggestions."""
from __future__ import annotations

import json
import tempfile

from app import campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.stacks import fake_stack
from harness.models import PLAYER
from harness.portrait import Portrait, Stance


def test_panel_people_suggestions_carry_no_relation_line(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")
    stack = fake_stack()
    g = Game(lambda new: open_campaign(stack, root=tempfile.mkdtemp(prefix="harness-app-"),
                                       new=new), pace=0.0)
    eng = g.camp.engine
    npc = next(c for c in eng.scene.present if c != PLAYER)
    eng.ctx.portraits = {"p": Portrait("p", npc, eng.ctx.name(npc), "x", "core",
                                       (Stance("s", ("stranger",), {}, "Does.", "Sounds."),),
                                       (), "", (), "", "", {})}
    eng.bind_portrait(npc, "p", rung="ally")
    line = eng.ctx.relation_line(npc, eng.scene)
    assert "warmth" in line
    for out in (g.panel(), g.people(), g.suggestions(False)):
        text = json.dumps(out, ensure_ascii=False, default=str)
        assert "warmth" not in text and line not in text and "→ the player" not in text
