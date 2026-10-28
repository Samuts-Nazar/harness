"""What Yennefer is given at the Ellander start (live report 2026-10-28: her lines made no sense).
Her first NPC prompt, captured on the fake stack: she witnessed the player's arrival (the start
point's `arrival`), her identity is the one of the start day (not yet anyone's teacher), she knows
Geralt's letter (be.db fixed by experiments/canon_be_fix.py), worn clothes are «wearing», and the
portrait slice carries no teaching talk. Plus the inventory `category` defaults (no store needed).

The canon store be.db is local and git-ignored: the prompt test skips when it is absent."""
from __future__ import annotations

import pathlib

import pytest

from app import newgame
from app.campaigns import item_category
from app.game import Game
from app.stacks import fake_stack
import harness.pipeline as P

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "app" / "tests" / "fixtures" / "outsider_ellander.yaml"
_CANDIDATES = [ROOT / "campaigns/canon/be.db",
               pathlib.Path("/home/cock/projects/harness/campaigns/canon/be.db")]
BE = next((p for p in _CANDIDATES if p.is_file()), None)


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)
    monkeypatch.delenv("HARNESS_CANON_DB_BE", raising=False)


@pytest.mark.skipif(BE is None, reason="local canon store be.db is absent")
def test_yennefer_first_prompt_fits_the_moment(tmp_path, monkeypatch):
    stack = fake_stack()
    pkg = newgame.parse(FIX.read_text(encoding="utf-8"))
    g = Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=BE), pace=0.0)
    cap: list[str] = []
    orig = P.Engine._complete_text

    def spy(self, role, messages):
        if role == "npc":
            cap.append("\n".join(m["content"] for m in messages))
        return orig(self, role, messages)

    monkeypatch.setattr(P.Engine, "_complete_text", spy)
    g.start_turn("*Підводжуся з дороги*")
    g.wait_idle(30)
    assert cap, "Yennefer was not asked to speak"
    text = cap[0]
    label = g.eng.ctx.ref("yennefer", "player")
    recent = text.split("Recent conversation:", 1)[1]
    assert f"[you see] {label} з'являється зі спалаху світла" in recent
    assert "падає на дорогу перед конем" in recent
    assert "teacher and guardian" not in text and "has not met Цірі yet" in text
    assert "Ґеральт wrote to her, asking for her help" in text
    assert f"{label} is wearing куртка" in text and "куртка in hand or at the belt" not in text
    assert f"{label} is carrying рюкзак" in text
    assert "Хто тебе вчив" not in text and "teacher" not in text.split("What you know:")[0]
    assert "narr" in [t["kind"] for t in g.transcript]   # the first turn is still narrated


def test_inventory_category_defaults_and_override():
    assert item_category({"name": "куртка", "where": "worn"}) == "clothing"
    assert item_category({"name": "рюкзак", "where": "worn", "container": True}) == "inventory"
    assert item_category({"name": "ліхтарик", "where": "in hand"}) == "equipment"
    assert item_category({"name": "ніж", "where": "pocket"}) == "inventory"
    assert item_category({"name": "мачете", "where": "worn", "category": "equipment"}) == "equipment"
    got = newgame.parse(FIX.read_text(encoding="utf-8").replace(
        "    - name: куртка\n", "    - name: куртка\n      category: equipment\n"))
    assert got.data["player"]["inventory"][1]["category"] == "equipment"
    with pytest.raises(newgame.PackageError, match="category"):
        newgame.parse(FIX.read_text(encoding="utf-8").replace(
            "    - name: куртка\n", "    - name: куртка\n      category: зброя\n"))
