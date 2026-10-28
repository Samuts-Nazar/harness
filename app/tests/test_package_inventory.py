"""Explicit starting inventory in game packages: validation (Ukrainian issues) and seeding
(ids, locations, containers). Fake stack, no network."""
from __future__ import annotations

import json
import pathlib

import pytest

from app import newgame
from app.game import Game
from app.newgame import PackageError, parse
from app.stacks import fake_stack
from harness import items
from harness.models import PLAYER

FIX = pathlib.Path(__file__).parent / "fixtures" / "outsider_generic.yaml"
HEAD = """\
version: 1
world: witcher
player:
  description: Інженер з іншого світу.
  inventory:
"""
START = "start:\n  place: ринок\n  situation: Ринок.\n"


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)


def pkg_text(*entries: str) -> str:
    return HEAD + "".join(entries) + START


def issues(text):
    with pytest.raises(PackageError) as e:
        parse(text)
    return e.value.issues


def build(tmp_path, text):
    stack = fake_stack()
    g = Game(lambda new: newgame.open_package(stack, parse(text), root=tmp_path, canon_db=False),
             pace=0.0)
    return g.eng, g


def test_parse_accepts_25_items():
    pkg = parse(FIX.read_text(encoding="utf-8"))
    inv = pkg.data["player"]["inventory"]
    assert len(inv) == 25 and pkg.warnings == []
    assert {"ноутбук", "смартфон", "лінзи збільшувальні", "сонячна панель складана",
            "аптечка"} <= {e["name"] for e in inv}


def test_parse_rejects_81_items_with_issue():
    text = pkg_text(*(f"    - name: річ {i}\n" for i in range(81)))
    got = issues(text)
    assert any(i.field == "player.inventory" and "81" in i.problem for i in got)
    assert parse(pkg_text(*(f"    - name: річ {i}\n" for i in range(80))))


def test_entry_limits_and_shape():
    got = issues(pkg_text("    - name: " + "а" * 81 + "\n",
                          "    - name: x\n      notes: " + "б" * 401 + "\n",
                          "    - просто рядок\n",
                          "    - name: y\n      content: " + "в" * 4001 + "\n"))
    fields = [i.field for i in got]
    assert "player.inventory[1].name" in fields and "player.inventory[2].notes" in fields
    assert "player.inventory[3]" in fields and "player.inventory[4].content" in fields


def test_where_must_name_a_container_or_known_place():
    got = issues(pkg_text("    - name: ключ\n      where: на місяці\n",
                          "    - name: торба\n"))
    assert [i.field for i in got] == ["player.inventory[1].where"]
    assert "container" in got[0].fix
    # a non-container entry is not a place
    got = issues(pkg_text("    - name: торба\n", "    - name: ключ\n      where: торба\n"))
    assert [i.field for i in got] == ["player.inventory[2].where"]
    ok = parse(pkg_text("    - name: торба\n      container: true\n",
                        "    - name: ключ\n      where: торба\n",
                        "    - name: монета\n      where: в кишені\n",
                        "    - name: свічка\n      where: «в руці»\n".replace("«", "").replace("»", ""),
                        "    - name: плащ\n      where: на тілі\n"))
    assert len(ok.data["player"]["inventory"]) == 5
    assert any("кола" in i.problem or "по колу" in i.problem for i in issues(pkg_text(
        "    - name: а\n      container: true\n      where: б\n",
        "    - name: б\n      container: true\n      where: а\n")))
    assert any("повторюється" in i.problem for i in issues(pkg_text(
        "    - name: а\n", "    - name: А\n")))


def test_seed_puts_laptop_in_backpack_hidden(tmp_path):
    eng, _ = build(tmp_path, FIX.read_text(encoding="utf-8"))
    snap = eng.live.snapshot()
    els = {e.item: e for e in snap[PLAYER].values() if e.id}
    pack, laptop = els["рюкзак"], els["ноутбук"]
    assert pack.location == "worn" and not pack.open
    assert laptop.location == items.IN + pack.id
    assert laptop.observable and not items.is_observable(laptop, snap)
    assert items.is_observable(pack, snap)
    assert len({e.id for e in els.values()}) == len(els) >= 25
    assert eng.ctx.item_ids is True
    meta = json.loads(eng.conn.execute(
        "SELECT value FROM campaign_meta WHERE key='inventory_meta'").fetchone()[0])
    assert meta[laptop.id]["condition"] == "тріснутий кут корпусу"
    assert meta[laptop.id]["notes"] == "ЗАХИЩЕНИЙ ПАРОЛЕМ"


def test_open_container_shows_contents_and_pocket_is_hidden(tmp_path):
    text = pkg_text("    - name: торба\n      container: true\n      open: true\n",
                    "    - name: яблуко\n      where: торба\n",
                    "    - name: ніж\n      where: pocket\n",
                    "    - name: перстень\n      where: worn\n      hidden: true\n")
    eng, _ = build(tmp_path, text)
    snap = eng.live.snapshot()
    els = {e.item: e for e in snap[PLAYER].values() if e.id}
    assert els["торба"].open and items.is_observable(els["яблуко"], snap)
    assert els["ніж"].location == "worn" and not els["ніж"].observable
    assert not els["перстень"].observable


def test_worn_jacket_observable_to_npc_on_entry(tmp_path):
    text = FIX.read_text(encoding="utf-8").replace(
        "start:\n", "start:\n  who_is_here:\n    - role: торговка\n      appearance: у хустці\n", 1)
    eng, _ = build(tmp_path, text)
    snap = eng.live.snapshot()
    jacket = next(e for e in snap[PLAYER].values() if e.item == "куртка")
    assert jacket.location == "worn" and items.is_observable(jacket, snap)
    npc = next(c for c in eng.scene.present if c != PLAYER)
    seen = " | ".join(f.content for f in eng.facts.visible_to(npc, eng.scene.time))
    assert "куртка" in seen and "рюкзак" in seen
    assert "ноутбук" not in seen and "аптечка" not in seen  # inside the closed backpack
    assert "ніж складаний" not in seen and "дрібні гроші" not in seen  # pockets


def test_package_without_inventory_unchanged(tmp_path):
    text = ("version: 1\nworld: witcher\nplayer:\n  description: Мандрівник.\n" + START)
    pkg = parse(text)
    assert "inventory" not in pkg.data["player"]
    eng, _ = build(tmp_path, text)
    assert eng.ctx.item_ids is False
    assert eng.conn.execute(
        "SELECT value FROM campaign_meta WHERE key='inventory_meta'").fetchone() is None
    assert not any(e.id for e in eng.live.snapshot().get(PLAYER, {}).values())
