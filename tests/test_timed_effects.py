from __future__ import annotations

from harness.models import PLAYER, WITNESSED
from harness.state import StateChange
from tests.test_world import build

EQ = "equipment"


def _give(eng, until, who="drunk", item="a glowing charm", observable=True):
    eng.scene.present = tuple(eng.scene.present) + ((who,) if who not in eng.scene.present else ())
    return eng.apply_state_change(StateChange(who, EQ, "add", item, observable, until=until))


def _has(eng, who="drunk", item="a glowing charm"):
    return (EQ, item) in eng.live.snapshot().get(who, {})


def test_element_removed_when_until_passes():
    eng, w, _ = build(present=(PLAYER, "innkeeper", "drunk"))
    now = eng.scene.time
    _give(eng, now + 60)
    eng.apply_state_change(StateChange("drunk", EQ, "add", "a plain cup", True))  # no until
    w.tick(now + 30)
    assert _has(eng)
    w.tick(now + 120)
    assert not _has(eng)
    assert _has(eng, item="a plain cup")  # None never expires
    assert w.expire_state(now + 10_000) == []


def test_expiry_runs_on_day_skip():
    eng, w, _ = build(present=(PLAYER, "innkeeper", "drunk"))
    now = eng.scene.time
    _give(eng, now + 3 * 24 * 60)
    w.skip_days(4)
    assert not _has(eng)


def test_rollback_restores_expired_element():
    eng, w, _ = build(present=(PLAYER, "innkeeper", "drunk"))
    now = eng.scene.time
    add = _give(eng, now + 60)
    w.tick(now + 120)
    assert not _has(eng)
    rem = [e for e in eng.log.active(["state_change"]) if e.payload["op"] == "remove"][0]
    assert rem.cause_id == add.id
    eng.rollback(rem.id)
    assert _has(eng)
    # rolling back the add takes the removal with it, and nothing orphaned is left
    w.tick(now + 130)
    eng.rollback(add.id)
    assert not _has(eng)


def test_expiry_of_observable_element_is_observed_by_present():
    eng, w, _ = build(present=(PLAYER, "innkeeper", "drunk"))
    now = eng.scene.time
    _give(eng, now + 60)
    w.tick(now + 120)
    texts = [f.content for f in eng.facts.visible_to("innkeeper", eng.scene.time)]
    assert any("no longer has a glowing charm" in t for t in texts)
    assert any("no longer has a glowing charm" in t for t in
               [f.content for f in eng.facts.visible_to(PLAYER, eng.scene.time)])
