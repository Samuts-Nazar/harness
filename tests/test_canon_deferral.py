"""Canon events whose people stand in the player's scene at another place are deferred (outsider
campaign Task 9 review): Yennefer on the road with the player cannot meet Ciri in the temple
refectory at the same time. They happen once she reaches the event's place (or leaves the player's
scene), in story order, at most `CANON_LATE_PER_STEP` per world step. Fake judge, no network."""
from __future__ import annotations

from harness.models import PLAYER
from harness.world import news as nw
from harness.world.canon_adapter import ListCanon, ScheduledEvent
from harness.world.world import CANON_LATE_PER_STEP
from test_world import build

T = 20 * 60 + 30


def _canon(n: int = 8) -> ListCanon:
    evs = [ScheduledEvent(f"m{i}", T + i, "market", ("innkeeper",), f"The innkeeper haggles {i}",
                          ("innkeeper",), 0.3) for i in range(n)]
    evs.append(ScheduledEvent("d", T, "market", ("drunk",), "The drunk sells a cart", (), 0.3))
    return ListCanon(evs)


def _market_facts(eng, who, at):
    return [f.content for f in eng.facts.visible_to(who, at) if "haggles" in f.content]


def test_event_with_a_person_in_the_players_scene_elsewhere_waits():
    eng, w, _ = build(canon=_canon())
    w.tick(21 * 60 + 30)
    ex = [e.payload["canon_id"] for e in eng.log.active([nw.CANON_EXECUTED])]
    assert ex == ["d"]                                 # nobody of it is with the player: on time
    assert _market_facts(eng, "innkeeper", eng.scene.time) == []
    held = eng.log.active([nw.CANON_DEFERRED])
    assert len(held) == 8 and all(e.payload["held"] == ["innkeeper"] for e in held)
    w.tick(22 * 60 + 30)                               # still with the player in the tavern
    assert len(eng.log.active([nw.CANON_EXECUTED])) == 1
    assert len(eng.log.active([nw.CANON_DEFERRED])) == 8   # logged once each


def test_deferred_events_fire_in_order_when_the_person_reaches_the_place():
    eng, w, _ = build(canon=_canon())
    w.tick(21 * 60 + 30)
    eng.scene.location = w.map.name("market")         # scripted: the scene (with him) is there
    w.tick(22 * 60 + 30)                               # one world step
    late = [e for e in eng.log.active([nw.CANON_EXECUTED]) if "deferred_from" in e.payload]
    assert [e.payload["canon_id"] for e in late] == [f"m{i}" for i in range(CANON_LATE_PER_STEP)]
    assert all(e.game_time == 22 * 60 + 30 for e in late)   # they happen now, not in the past
    assert [e.payload["deferred_from"] for e in late] == [T + i for i in range(CANON_LATE_PER_STEP)]
    w.tick(23 * 60 + 30)
    late = [e for e in eng.log.active([nw.CANON_EXECUTED]) if "deferred_from" in e.payload]
    assert [e.payload["canon_id"] for e in late] == [f"m{i}" for i in range(8)]
    assert len(_market_facts(eng, "innkeeper", eng.scene.time)) == 8
    w.tick(24 * 60 + 30)
    assert len(eng.log.active([nw.CANON_EXECUTED])) == 9   # nothing twice


def test_leaving_the_players_scene_releases_them():
    eng, w, _ = build(canon=_canon(2))
    w.tick(21 * 60 + 30)
    eng.leave_scene("innkeeper", stay_nearby=False)
    w.tick(22 * 60 + 30)
    assert len(_market_facts(eng, "innkeeper", eng.scene.time)) == 2
    assert PLAYER in eng.scene.present
