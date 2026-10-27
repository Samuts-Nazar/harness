"""Canon events whose people stand in the player's scene at another place are deferred (outsider
campaign Task 9 review, two rounds): Yennefer on the road with the player cannot meet Ciri in the temple
refectory at the same time. They happen once she reaches the event's site (or leaves the player's
scene), in story order per person, at most `CANON_LATE_PER_STEP` per world step. Fake judge, no network."""
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
    assert all(e.game_time == 21 * 60 + 30 for e in late)   # at the step's start, not the past
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


def test_story_order_per_person_and_stamp_order():
    """A later event of the same person waits behind an earlier deferred one, even where it
    could happen on time (the tavern is the scene's place); stamps follow story order."""
    canon = ListCanon([
        ScheduledEvent("away", T, "market", ("innkeeper",), "The innkeeper haggles at the market",
                       ("innkeeper",), 0.3),
        ScheduledEvent("home", T + 20, "tavern", ("innkeeper",), "The innkeeper opens a cask",
                       ("innkeeper",), 0.3),
        ScheduledEvent("other", T + 25, "market", ("drunk",), "The drunk buys a whip", (), 0.3),
    ])
    eng, w, _ = build(canon=canon)
    w.tick(21 * 60 + 30)
    ex = {e.payload["canon_id"]: e for e in eng.log.active([nw.CANON_EXECUTED])}
    assert set(ex) == {"other"}                       # someone else's event is not held
    held = {e.payload["canon_id"] for e in eng.log.active([nw.CANON_DEFERRED])}
    assert held == {"away", "home"}
    eng.leave_scene("innkeeper", stay_nearby=False)   # he goes about his day: both can happen
    w.tick(22 * 60 + 30)
    ex = [e for e in eng.log.active([nw.CANON_EXECUTED]) if e.payload["canon_id"] != "other"]
    assert [e.payload["canon_id"] for e in ex] == ["away", "home"]
    assert ex[0].game_time <= ex[1].game_time


def test_a_site_counts_as_reached_and_an_unknown_scene_place_holds_nothing():
    # the palace is 3 minutes from the guardhouse: one site
    canon = ListCanon([ScheduledEvent("g", T, "guardhouse", ("innkeeper",), "The innkeeper "
                                      "reports to the sergeant", ("innkeeper",), 0.3)])
    eng, w, _ = build(canon=canon, place="palace")
    w.tick(21 * 60 + 30)
    assert [e.payload["canon_id"] for e in eng.log.active([nw.CANON_EXECUTED])] == ["g"]
    eng, w, _ = build(canon=_canon(1))
    eng.scene.location = "a hut somewhere"            # not on the map: old behaviour
    w.tick(21 * 60 + 30)
    assert not eng.log.active([nw.CANON_DEFERRED])


class _Spy(ListCanon):
    """A ListCanon that records the windows it is asked for."""

    def __init__(self, events):
        super().__init__(events)
        self.calls: list[tuple[int, int]] = []

    def scheduled(self, after_t, up_to_t):
        self.calls.append((after_t, up_to_t))
        return super().scheduled(after_t, up_to_t)


def test_a_held_event_retires_after_stale_days_and_never_fires():
    from harness.world.world import STALE_DAYS
    canon = _Spy([ScheduledEvent("m", T, "market", ("innkeeper",), "The innkeeper haggles",
                                 ("innkeeper",), 0.3)])
    eng, w, _ = build(canon=canon)
    w.tick(21 * 60 + 30)
    assert len(eng.log.active([nw.CANON_DEFERRED])) == 1
    w.tick(T + (STALE_DAYS + 1) * 1440)               # he stays with the player for two weeks
    ret = eng.log.active([nw.CANON_RETIRED])
    assert len(ret) == 1 and ret[0].payload == {"canon_id": "m", "t": T, "reason": "stale",
                                                "logged_at": ret[0].payload["logged_at"]}
    canon.calls.clear()
    w.tick(eng.scene.time + 120)
    assert canon.calls and all(a >= eng.scene.time - 120 for a, _u in canon.calls)  # window bounded
    eng.scene.location = w.map.name("market")         # he reaches the place: too late now
    w.tick(eng.scene.time + 120)
    assert not eng.log.active([nw.CANON_EXECUTED])
    assert len(eng.log.active([nw.CANON_RETIRED])) == 1   # logged once
    # a rollback of the retirement restores the waiting event (still stale: retired again)
    eng.log.rollback(ret[0].id)
    assert "m" in w._deferred(w._executed())
    w.tick(eng.scene.time + 60)
    assert not eng.log.active([nw.CANON_EXECUTED])
    assert len(eng.log.active([nw.CANON_RETIRED])) == 1


def test_a_held_event_younger_than_stale_days_still_fires():
    from harness.world.world import STALE_DAYS
    eng, w, _ = build(canon=_canon(1))
    w.tick(21 * 60 + 30)
    w.tick(T + (STALE_DAYS - 1) * 1440)
    assert not eng.log.active([nw.CANON_RETIRED])
    eng.scene.location = w.map.name("market")
    w.tick(eng.scene.time + 60)
    assert [e.payload["canon_id"] for e in eng.log.active([nw.CANON_EXECUTED])
            if e.payload["canon_id"] != "d"] == ["m0"]
