import json

import pytest

from harness import items
from harness.extractor import validate_diff
from harness.models import EQUIPMENT, INVENTORY, PLAYER
from harness.state import StateChange, StateError
from conftest import diff, fact, make_engine


def seen(eng, who="innkeeper"):
    return [f.content for f in eng.facts.visible_to(who, eng.scene.time)]


def pack(eng):
    """Player carries a closed backpack holding a lantern; the innkeeper is in the room."""
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "backpack", True,
                                       id="item:backpack", location="worn"))
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "lantern", True,
                                       id="item:lantern", location="in:item:backpack"))


def test_backpack_contents_hidden_until_opened():
    eng, _ = make_engine({})
    pack(eng)
    snap = eng.live.snapshot()
    lantern = snap[PLAYER][(INVENTORY, "lantern")]
    assert lantern.observable is True  # stored flag untouched...
    assert not items.is_observable(lantern, snap)  # ...but derived: a closed container hides it
    assert items.is_observable(snap[PLAYER][(INVENTORY, "backpack")], snap)
    assert [e.item for e in eng.live.observable(PLAYER)] == ["backpack"]
    assert seen(eng) == ["Geralt is carrying backpack"]


def test_opening_makes_contents_observable_once():
    eng, _ = make_engine({})
    pack(eng)
    assert items.open_container(eng, PLAYER, "item:backpack") == ["item:lantern"]
    assert seen(eng) == ["Geralt is carrying backpack", "Geralt is carrying lantern"]
    n = len(eng.log.active())
    assert items.open_container(eng, PLAYER, "item:backpack") == []  # second open: nothing new
    assert len(eng.log.active()) == n and len(seen(eng)) == 2
    assert [e.item for e in eng.live.observable(PLAYER)] == ["backpack", "lantern"]


def test_open_empty_container_is_noop():
    eng, _ = make_engine({})
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "chest", True,
                                       id="item:chest", location="on:floor"))
    n = len(eng.log.active())
    assert items.open_container(eng, PLAYER, "item:chest") == []
    assert len(eng.log.active()) == n
    with pytest.raises(StateError):
        items.open_container(eng, PLAYER, "item:nothing")


def test_container_cycle_rejected():
    eng, _ = make_engine({})
    pack(eng)
    with pytest.raises(StateError):  # backpack into the lantern it contains
        eng.apply_state_change(StateChange(PLAYER, INVENTORY, "move", "backpack",
                                           location="in:item:lantern"))
    with pytest.raises(StateError):  # into itself
        eng.apply_state_change(StateChange(PLAYER, INVENTORY, "move", "backpack",
                                           location="in:item:backpack"))
    with pytest.raises(StateError):  # missing container
        eng.apply_state_change(StateChange(PLAYER, INVENTORY, "move", "lantern",
                                           location="in:item:ghost"))
    with pytest.raises(StateError):  # move needs a location
        eng.apply_state_change(StateChange(PLAYER, INVENTORY, "move", "lantern"))


def _validate(eng, changes, texts=None, fuzzy=True):
    srcs = {"player", "narration"}
    return validate_diff(json.loads(diff(fact("f", "narration"), changes=changes)),
                         present=eng.scene.present, sources=srcs, state=eng.live.snapshot(),
                         characters=set(eng.scene.present), texts=texts, fuzzy=fuzzy)


def ch(op, item, **kw):
    return {"character": PLAYER, "category": "inventory", "op": op, "item": item,
            "observable": True, "source": "player", **kw}


def test_extractor_add_mints_id():
    eng, _ = make_engine({})
    d = _validate(eng, (ch("add", "Silver Ring", id="item:evil"),
                        ch("add", "Silver Ring", location="worn")))
    assert d.changes[0].id == "item:silver-ring"  # a model-proposed id is ignored
    assert len(d.dropped) == 1 and "already has" in d.dropped[0]["reason"]  # same text, same key
    eng2, _ = make_engine({})
    eng2.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "ring", True, id="item:ring"))
    d = _validate(eng2, (ch("add", "ring of power"), ch("add", "ring spare")))
    assert [c.id for c in d.changes] == ["item:ring-of-power", "item:ring-spare"]


def test_unresolved_remove_dropped_but_unresolved_add_creates_item():
    eng, _ = make_engine({})
    pack(eng)
    d = _validate(eng, (ch("remove", "x", id="item:ghost"), ch("remove", "a sword"),
                        ch("add", "a sword")))
    assert [c.op for c in d.changes] == ["add"] and len(d.dropped) == 2
    # by id, and by normalised text, an existing item resolves
    d = _validate(eng, (ch("move", "whatever", id="item:lantern", location="in_hand"),
                        ch("remove", "The Lantern")))
    assert [(c.op, c.item) for c in d.changes] == [("move", "lantern"), ("remove", "lantern")]


def test_text_keyed_items_without_ids_unchanged():
    eng, _ = make_engine({})
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "drawn sword", True))
    snap = eng.live.snapshot()
    el = snap[PLAYER][(EQUIPMENT, "drawn sword")]
    assert el.id is None and items.is_observable(el, snap)
    assert items.resolve("drawn sword", PLAYER, snap) is None  # no id to resolve to
    d = _validate(eng, ({**ch("remove", "drawn sword"), "category": "equipment"},))
    assert [(c.op, c.item, c.id) for c in d.changes] == [("remove", "drawn sword", None)]
    assert items.mint_id("x", {"item:x"}) == "item:x-2"


def test_extractor_prompt_lists_ids_only_when_enabled():
    def prompt(**kw):
        eng, _ = make_engine({}, **kw)
        pack(eng)
        return eng.ctx.extractor(eng.scene, [("narration", "x")])[-1]["content"]
    old, new = prompt(), prompt(item_ids=True)
    assert "[id:" not in old and '"move"' not in old  # old recordings keep their prompt
    assert "[id: item:lantern] [location: in:item:backpack] (hidden)" in new
    assert '"move"|"realize"' in new and '"id": optional existing item id' in new


def test_inexact_remove_dropped_when_item_ids_off():
    eng, _ = make_engine({})
    pack(eng)
    d = _validate(eng, (ch("remove", "The Lantern"),), fuzzy=False)
    assert d.changes == [] and "does not have" in d.dropped[0]["reason"]
    assert [c.item for c in _validate(eng, (ch("remove", "The Lantern"),)).changes] == ["lantern"]


def test_hidden_danger_in_closed_container_does_not_raise_stakes():
    eng, _ = make_engine({})
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "backpack", True,
                                       id="item:backpack", location="worn"))
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "drawn dagger", True,
                                       id="item:dagger", location="in:item:backpack"))
    assert eng.ctx.situation("innkeeper", eng.scene).stakes == "low"
    items.open_container(eng, PLAYER, "item:backpack")
    assert eng.ctx.situation("innkeeper", eng.scene).stakes == "high"


def test_memory_state_shows_derived_observability():
    eng, _ = make_engine({})
    pack(eng)
    mem = eng.deriver.derive(PLAYER, eng.scene.time)
    assert {e.item: e.observable for e in mem.state} == {"backpack": True, "lantern": False}
