import pytest

from harness.evalkit import session
from harness.models import INVENTORY, INJURY, PLAYER, STATE_CHANGE
from harness.state import LiveState, StateChange, StateError, check_change, payload
from conftest import make_engine


def _old_payload(**kw):
    p = {"character": PLAYER, "category": INVENTORY, "op": "add", "item": "map", "observable": True}
    p.update(kw)
    return p


def _live_with(*payloads):
    eng, _ = make_engine({})
    for p in payloads:
        eng.log.append(STATE_CHANGE, game_time=0, location="Inn", participants=[p["character"]],
                       witnesses=[], payload=p)
    return eng.live


def test_old_payload_replays_with_defaults():
    live = _live_with(_old_payload())
    (el,) = live.of(PLAYER)
    assert el.aware is True and el.location is None and el.id is None
    assert el.until is None and el.channel == "sight"
    assert [e.item for e in live.observable(PLAYER)] == ["map"]


def test_new_fields_roundtrip_through_payload():
    plain = StateChange(PLAYER, INVENTORY, "add", "map")
    assert payload(plain) == _old_payload()  # defaults are not written
    ch = StateChange(PLAYER, INVENTORY, "add", "ring", False, "a1", id="r1", location="cellar",
                     aware=False, until=40, channel="sound")
    p = payload(ch)
    assert p["id"] == "r1" and p["location"] == "cellar" and p["aware"] is False
    assert p["until"] == 40 and p["channel"] == "sound"
    live = _live_with(p)
    (el,) = live.of(PLAYER)
    assert (el.id, el.location, el.aware, el.until, el.channel) == ("r1", "cellar", False, 40, "sound")
    assert el.observable is False


def test_move_and_realize():
    live = _live_with(
        payload(StateChange(PLAYER, INJURY, "add", "fever", False, aware=False, location="a")),
        payload(StateChange(PLAYER, INJURY, "move", "fever", location="b")),
        payload(StateChange(PLAYER, INJURY, "realize", "fever")))
    (el,) = live.of(PLAYER)
    assert el.location == "b" and el.aware is True and el.observable is False


def test_move_and_realize_validation():
    state: dict = {}
    with pytest.raises(StateError):
        check_change(state, StateChange(PLAYER, INJURY, "move", "fever", location="b"))
    with pytest.raises(StateError):
        check_change(state, StateChange(PLAYER, INJURY, "realize", "fever"))
    live = _live_with(payload(StateChange(PLAYER, INJURY, "add", "fever")),
                      payload(StateChange(PLAYER, INJURY, "add", "chill", aware=False)))
    snap = live.snapshot()
    check_change(snap, StateChange(PLAYER, INJURY, "move", "fever", location="b"))
    check_change(snap, StateChange(PLAYER, INJURY, "realize", "chill"))
    with pytest.raises(StateError):
        check_change(snap, StateChange(PLAYER, INJURY, "realize", "fever"))  # already aware


@pytest.mark.eval
def test_recorded_session_replays_same_state():
    from harness.evalkit.__main__ import stored
    for path in stored():
        game, info = session.replay(path)
        assert info["same_story"]
        eng = game.eng
        legacy: dict = {}
        for e in eng.log.active([STATE_CHANGE]):
            p = e.payload
            els = legacy.setdefault(p["character"], {})
            key = (p["category"], p["item"])
            if p["op"] == "add":
                els[key] = p["observable"]
            elif p["op"] == "remove":
                del els[key]
            elif p["op"] in ("reveal", "hide"):
                els[key] = p["op"] == "reveal"
        now = {c: {k: bool(v) for k, v in els.items()} for c, els in eng.live.snapshot().items()}
        assert now == legacy
