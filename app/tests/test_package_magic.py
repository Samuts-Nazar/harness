"""Package keys for the magic sense: player.latent, person.senses, item.grants_sense."""
from __future__ import annotations

import json

import pytest

from app.newgame import PackageError, parse
from harness.models import INTERNAL, PLAYER
from test_package_inventory import START, build, issues  # noqa: F401  (shared fixtures)

BASE = "version: 1\nworld: witcher\nplayer:\n  description: Інженер.\n"


def test_keys_are_parsed():
    pkg = parse(BASE + "  latent:\n    - у ній дрімає Джерело\n  inventory:\n"
                "    - name: медальйон\n      grants_sense: Magic\n" + START +
                "  who_is_here:\n    - role: чарівниця\n      senses: [magic]\n")
    assert pkg.data["player"]["latent"] == ["у ній дрімає Джерело"]
    assert pkg.data["player"]["inventory"][0]["grants_sense"] == "magic"
    assert pkg.data["start"]["who_is_here"][0]["senses"] == ["magic"]


@pytest.mark.parametrize("text,field", [
    (BASE + "  inventory:\n    - name: а\n      grants_sense: smell\n" + START,
     "player.inventory[1].grants_sense"),
    (BASE + START + "  who_is_here:\n    - role: х\n      senses: [smell]\n",
     "start.who_is_here[1].senses"),
])
def test_unknown_sense_is_an_issue(text, field):
    assert [i.field for i in issues(text)] == [field]


def test_seeded_into_the_campaign(tmp_path):
    text = (BASE + "  latent:\n    - у ній дрімає Джерело\n  inventory:\n"
            "    - name: медальйон\n      grants_sense: magic\n" + START +
            "  who_is_here:\n    - role: чарівниця\n      senses: [magic]\n")
    eng, _ = build(tmp_path, text)
    src = next(e for e in eng.live.snapshot()[PLAYER].values() if e.item == "у ній дрімає Джерело")
    assert (src.category, src.aware, src.observable, src.channel) == (INTERNAL, False, True, "magic")
    assert "у ній дрімає Джерело" not in [e.item for e in eng.live.of(PLAYER, viewer=PLAYER)]
    meta = json.loads(eng.conn.execute(
        "SELECT value FROM campaign_meta WHERE key='inventory_meta'").fetchone()[0])
    assert [m.get("grants_sense") for m in meta.values()] == ["magic"]
    npc = next(c for c in eng.profiles if c != PLAYER)
    assert eng.profiles[npc].senses == ("sight", "magic")
    # the sorceress perceived the Source when the room formed
    assert any("дрімає Джерело" in f.content for f in eng.facts.visible_to(npc, eng.scene.time))
