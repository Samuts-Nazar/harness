"""Final whole-branch review fixes (outsider plan 1). Fake stack, no network."""
from __future__ import annotations

import json
import pathlib

import pytest

from app import newgame
from app.game import Game
from app.stacks import fake_stack
from harness import readable
from harness.models import PLAYER

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _sources(tmp_path, text):
    stack = fake_stack()
    g = Game(lambda new: newgame.open_package(stack, newgame.parse(text), root=tmp_path,
                                              canon_db=False), pace=0.0)
    return g, {r[0] for r in g.eng.conn.execute(
        "SELECT k.source FROM facts f JOIN fact_knowers k ON k.fact_id=f.id "
        "WHERE f.content LIKE '%вважає (з власного життя%'")}


# -- 1. other-world source only for an outsider package -------------------------------------------
@pytest.mark.parametrize("path", ["worlds/witcher/packages/yennefer_rinde.yaml",
                                  "docs/game_package_example.yaml"])
def test_ordinary_packages_keep_own_life(tmp_path, path):
    g, src = _sources(tmp_path, (ROOT / path).read_text(encoding="utf-8"))
    assert src == {"own life"}
    lines = g.eng.ctx.knowledge_lines(g.eng.deriver.derive(PLAYER, g.eng.scene.time))
    assert not any("з іншого світу" in x for x in lines)


@pytest.mark.parametrize("path", ["app/tests/fixtures/outsider_generic.yaml",
                                  "app/tests/fixtures/outsider_ellander.yaml"])
def test_outsider_fixtures_get_other_world(tmp_path, path):
    import yaml
    d = yaml.safe_load((ROOT / path).read_text(encoding="utf-8"))
    d["player"]["knows"] = ["Джини живуть у лампах."]   # the fixtures list none of their own
    text = yaml.safe_dump(d, allow_unicode=True, sort_keys=False)
    assert newgame.parse(text).data["player"].get("outsider") is True
    _, src = _sources(tmp_path, text)
    assert src == {"own life, from another world"}


def test_outsider_flag_or_latent_decides(tmp_path):
    base = ("version: 1\nworld: witcher\nplayer:\n  description: Інженер.\n{extra}  knows:\n"
            "    - Джини живуть у лампах.\nstart:\n  place: ринок\n  situation: Ринок.\n")
    assert _sources(tmp_path / "a", base.format(extra=""))[1] == {"own life"}
    assert _sources(tmp_path / "b", base.format(extra="  outsider: true\n"))[1] == {
        "own life, from another world"}
    assert _sources(tmp_path / "c", base.format(extra="  latent:\n    - сила\n"))[1] == {
        "own life, from another world"}
    with pytest.raises(newgame.PackageError) as e:
        newgame.parse(base.format(extra="  outsider: можливо\n"))
    assert any(i.field == "player.outsider" for i in e.value.issues)


# -- 2. owner-only item details (condition, notes, power) -----------------------------------------
FIX = ROOT / "app/tests/fixtures/outsider_generic.yaml"


def _outsider_with_npc(tmp_path):
    text = FIX.read_text(encoding="utf-8").replace(
        "start:\n", "start:\n  who_is_here:\n    - role: торговка\n      appearance: у хустці\n", 1)
    stack = fake_stack()
    return Game(lambda new: newgame.open_package(stack, newgame.parse(text), root=tmp_path,
                                                 canon_db=False), pace=0.0)


def _text(msgs) -> str:
    return "\n".join(m["content"] for m in msgs)


def test_owner_sees_item_details_npc_does_not(tmp_path):
    from harness import assistant
    g = _outsider_with_npc(tmp_path)
    eng = g.eng
    narr = _text(eng.ctx.narrator(eng.scene, "Я озираюсь."))
    # the laptop lies in the closed backpack: hidden from others, known to its owner
    line = next(x for x in narr.splitlines() if "ноутбук" in x)
    assert "ЗАХИЩЕНИЙ ПАРОЛЕМ" in line and "тріснутий кут корпусу" in line
    detail = line.split("ноутбук — ", 1)[1].rsplit(" (", 1)[0]
    assert len(detail) <= 160
    a = assistant.context(eng)
    assert "ЗАХИЩЕНИЙ ПАРОЛЕМ" in a.system + a.user
    npc = next(c for c in eng.scene.present if c != PLAYER)
    seen = _text(eng.ctx.character(npc, eng.scene))
    assert "ЗАХИЩЕНИЙ ПАРОЛЕМ" not in seen and "тріснутий кут" not in seen
    obs = " | ".join(f.content for f in eng.facts.visible_to(npc, eng.scene.time))
    assert "ЗАХИЩЕНИЙ" not in obs


def test_long_item_details_are_cut(tmp_path):
    from harness.context import OWN_DETAILS
    from harness.state import Element
    g = _outsider_with_npc(tmp_path)
    el = Element("equipment", "ноутбук", False, "x1", None, True)
    s = g.eng.ctx.own_item(el, {"x1": {"notes": "слово " * 100}})
    assert s.startswith("ноутбук — notes: ") and len(s.split(" — ", 1)[1]) <= OWN_DETAILS
    assert g.eng.ctx.own_item(el, {}) == "ноутбук"


# -- 3. extractor: unaware elements tagged, realize rule ------------------------------------------
UNAWARE_TAG = "[unaware to bearer; perceptible by magic only]"


def test_extractor_tags_unaware_magic_and_teaches_realize(tmp_path):
    text = FIX.read_text(encoding="utf-8").replace(
        "player:\n", "player:\n  latent:\n    - у ньому дрімає Джерело\n", 1)
    stack = fake_stack()
    g = Game(lambda new: newgame.open_package(stack, newgame.parse(text), root=tmp_path,
                                              canon_db=False), pace=0.0)
    eng = g.eng
    assert eng.ctx.item_ids
    prompt = _text(eng.ctx.extractor(eng.scene, [("narration", "Він іде.")]))
    line = next(x for x in prompt.splitlines() if "Джерело" in x)
    assert UNAWARE_TAG in line
    assert prompt.count(UNAWARE_TAG) == 1  # aware items carry no tag
    assert '"realize" only when the text shows the bearer being told' in prompt
    eng.ctx.item_ids = False  # old prompts unchanged
    old = _text(eng.ctx.extractor(eng.scene, [("narration", "Він іде.")]))
    assert UNAWARE_TAG not in old and "being told" not in old


# -- 4. content files come from data/ only --------------------------------------------------------
def test_content_file_only_from_data(tmp_path, monkeypatch):
    from conftest import make_engine
    data, camp, outside = tmp_path / "data_real", tmp_path / "camp", tmp_path / "outside"
    for d in (data, camp / "memory", outside):
        d.mkdir(parents=True)
    link = tmp_path / "data"  # data/ itself a link to the main checkout: legitimate
    link.symlink_to(data, target_is_directory=True)
    (data / "book.txt").write_text("книга", encoding="utf-8")
    (camp / "memory" / "player.md").write_text("пам'ять", encoding="utf-8")
    (outside / "secret.txt").write_text("таємниця", encoding="utf-8")
    (data / "escape.txt").symlink_to(outside / "secret.txt")
    monkeypatch.setattr(readable, "DATA_DIR", link)
    eng, _ = make_engine({}, campaign_dir=camp, item_ids=True)
    assert readable.resolve_file(eng, "book.txt") == (data / "book.txt").resolve()
    assert readable.resolve_file(eng, "data/book.txt") == (data / "book.txt").resolve()
    assert readable.resolve_file(eng, "memory/player.md") != (camp / "memory" / "player.md").resolve()
    p = readable.resolve_file(eng, "memory/player.md")
    assert p is None or p.is_relative_to(data.resolve())
    for bad in ("../camp/memory/player.md", str(camp / "memory" / "player.md"), "escape.txt",
                "data/../camp/memory/player.md", "data"):
        assert readable.resolve_file(eng, bad) is None
