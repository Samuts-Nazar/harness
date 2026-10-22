"""Without the canon store the tavern start still has its innkeeper (smoke 2026-10-22 item 6: the
narrator described a mute innkeeper counting on his fingers because he was not a character, so
only the guard ever answered). Fake stack, no network."""
from __future__ import annotations

import tempfile

import pytest

from app import campaigns
from app.stacks import fake_stack
from app.vizima import open_vizima


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def test_the_tavern_start_without_canon_has_an_innkeeper_who_can_speak():
    camp = open_vizima(fake_stack(), root=tempfile.mkdtemp(), new=True, canon_db=False)
    eng = camp.engine
    assert "npc_innkeeper" in eng.scene.present
    prof = eng.profiles["npc_innkeeper"]
    assert "корчмар" in (prof.appearance + prof.description).lower()
    assert eng.names.knows("npc_guard", "npc_innkeeper"), "the locals know the innkeeper"
    assert "npc_innkeeper" in camp.world.cast
