"""Character portraits task 4: the portrait's switches move the NPC -> player relationship on the
slow lane (one batched judge call per NPC), the ladder climbs or drops one rung at a time, and a
hidden-layer leak goes into the prompt only with trust and at most once per scene."""
from test_portrait_context import eng, prompt

from conftest import diff
from harness.models import PLAYER, RELATION, UTTERANCE
from harness.portrait import Switch
from harness.relations import Relationship, apply

LEAK = "A star pendant gesture."


def rel(rung, w, t):
    return Relationship("yen", PLAYER, rung, w, t, "", None)


def sw(id, w, t):
    return Switch(id, f"Did {id}?", w, t)


# -- the ladder -----------------------------------------------------------------------------
def test_apply_clamps_and_climbs():
    r = apply(rel("stranger", -0.2, 0.2), [sw("a", 0.3, 0.2)])
    assert (r.rung, r.warmth, r.trust, r.reason) == ("client", 0.1, 0.4, "a")
    r = apply(r, [sw("a", 0.2, 0.1), sw("b", 0.1, 0.0)])
    assert (r.rung, r.warmth, r.trust, r.reason) == ("ally", 0.4, 0.5, "a,b")
    # a huge turn clamps and still climbs only one rung
    r = apply(rel("stranger", -0.2, 0.2), [sw("x", 5, 5)])
    assert (r.rung, r.warmth, r.trust) == ("client", 1.0, 1.0)
    r = apply(r, [sw("x", 0, 0)])
    assert r.rung == "ally"
    r = apply(r, [sw("x", 0, 0)])
    assert r.rung == "close"
    r = apply(r, [sw("x", 0, 0)])
    assert r.rung == "lover"
    r = apply(r, [sw("x", 0, 0)])
    assert r.rung == "lover"
    r = apply(rel("client", 0.0, 0.4), [sw("y", -0.1, -2)])
    assert r.trust == 0.0
    # thresholds are inclusive and float noise does not break them (0.7 - 0.4 is 0.2999...)
    r = apply(rel("client", 0.7, 0.45), [sw("z", -0.4, 0)])
    assert (r.rung, r.warmth) == ("ally", 0.3)


def test_setback_drops_a_rung():
    r = apply(rel("ally", 0.5, 0.6), [sw("pity", -0.6, -0.2)])
    assert (r.rung, r.warmth, r.trust, r.reason) == ("client", -0.1, 0.4, "pity")
    assert apply(rel("close", 0.7, 0.7), [sw("p", -0.2, 0)]).rung == "close"   # 0.5 >= 0.3
    assert apply(rel("lover", 0.9, 0.9), [sw("p", -0.4, 0)]).rung == "close"   # 0.5 < 0.55
    assert apply(rel("ally", 0.5, 0.9), [sw("p", -0.2, 0)]).rung == "ally"     # 0.3: not below 0
    # one rung at a time, even after a heavy blow
    assert apply(rel("close", 0.7, 0.7), [sw("p", -1.0, 0)]).rung == "ally"
    # never below stranger except to enemy
    assert apply(rel("stranger", -0.2, 0.2), [sw("p", -0.4, 0)]).rung == "stranger"


def test_enemy_threshold():
    r = apply(rel("client", 0.0, 0.4), [sw("pressure", -0.4, -0.4), sw("wound", -0.3, -0.3)])
    assert (r.rung, r.warmth, r.trust) == ("enemy", -0.7, 0.0)
    assert apply(rel("lover", 0.9, 0.9), [sw("w", -1.6, 0)]).rung == "enemy"
    assert apply(rel("client", 0.0, 0.4), [sw("p", -0.6, 0)]).rung == "stranger"
    # an enemy stays one until warmth climbs back to -0.4, then is a stranger again
    assert apply(rel("enemy", -0.8, 0.0), [sw("c", 0.3, 0.2)]).rung == "enemy"
    assert apply(rel("enemy", -0.8, 0.0), [sw("c", 0.4, 0.2)]).rung == "stranger"


# -- the slow lane --------------------------------------------------------------------------
def yen_engine(judge_rules=None, **kw):
    e = eng({"narrator": ["N."] * 4, "npc": ["— Що тобі треба?", "— Кажи коротше."],
             "extractor": [diff()] * 6}, **kw)
    e.judge.inner.rules.update(judge_rules or {})
    e.scene.present = (PLAYER, "yen")
    e.bind_portrait("yen", "p_yen")
    return e


def switch_asks(e):
    return [(st, qs) for st, qs in e.judge.inner.asked
            if any(q.tag == "portrait_switch" for q in qs.values())]


def test_switch_batch_runs_on_slow_lane_only():
    order = []

    def hit(q, state):
        order.append("switch")
        return True

    e = yen_engine({"portrait_switch": hit}, parallel=True)
    e.turn("Я приніс тобі води.", speakers=["yen"], defer_slow=True,
           on_word=lambda s, w: order.append("word"))
    assert "word" in order and "switch" not in order      # the fast lane is done, no question yet
    e.settle()
    assert order.index("word") < order.index("switch")
    asks = switch_asks(e)
    assert len(asks) == 1 and len(asks[0][1]) == len(e.ctx.portraits["p_yen"].switches)
    state = "\n".join(asks[0][0])
    assert "Я приніс тобі води." in state and "Що тобі треба?" in state
    r = e.ctx.relations.get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.reason) == ("client", 0.0, 0.3, "w")
    notes = [n for n in e.devlog if n["kind"] == "relation_changed"]
    assert notes and notes[0]["npc"] == "yen" and notes[0]["from"] == "stranger" \
        and notes[0]["to"] == "client" and notes[0]["switches"] == ["w"]


def test_no_switch_hit_leaves_the_relationship():
    e = yen_engine({"portrait_switch": False})
    e.turn("Добрий день.", speakers=["yen"])
    assert len(switch_asks(e)) == 1
    assert e.ctx.relations.get("yen", PLAYER).reason == "seed"


def test_no_switch_questions_for_npc_without_portrait():
    e = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e.judge.inner.rules["portrait_switch"] = True
    e.scene.present = (PLAYER, "inn")
    e.turn("Пива.", speakers=["inn"])
    assert switch_asks(e) == []
    # a portrait NPC who stays silent while another speaks is not asked about either
    e = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e.judge.inner.rules["portrait_switch"] = True
    e.bind_portrait("yen", "p_yen")
    e.turn("Пива.", speakers=["inn"])
    assert switch_asks(e) == []


def test_rollback_reverts_switch_effect():
    e = yen_engine({"portrait_switch": True})
    e.turn("Я приніс тобі води.", speakers=["yen"])
    r = e.ctx.relations.get("yen", PLAYER)
    assert r.rung == "client"
    ev = e.log.get(r.event_id)
    player = [u for u in e.log.active([UTTERANCE]) if u.payload["speaker"] == PLAYER][-1]
    assert ev.cause_id == player.id
    line = e.log.last_npc_utterance()
    e.model_error(line.id, "вона б так не сказала")
    r = e.ctx.relations.get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.reason) == ("stranger", -0.2, 0.2, "seed")
    assert not e.log.is_active(ev.id)
    assert e.log.active([RELATION])[-1].payload["reason"] == "seed"


# -- leaks ----------------------------------------------------------------------------------
def test_leak_needs_trust_and_one_per_scene():
    e = eng()
    e.bind_portrait("yen", "p_yen")                  # stranger: trust 0.2
    assert LEAK not in prompt(e, "yen")
    e.ctx.relations.set("yen", PLAYER, "client", 0.1, 0.4, "test", e.scene, None)
    assert LEAK in prompt(e, "yen")                  # trust 0.4: one leak
    notes = [n for n in e.devlog if n["kind"] == "portrait_leak"]
    assert len(notes) == 1 and notes[0]["npc"] == "yen"
    assert LEAK not in prompt(e, "yen")              # not twice in the same scene
    e.leave_scene("yen")
    e.enter_scene("yen")                             # a new scene entry: one more
    assert LEAK in prompt(e, "yen")
    assert LEAK not in prompt(e, "yen")
    assert len([n for n in e.devlog if n["kind"] == "portrait_leak"]) == 2


def test_a_cold_stranger_becomes_a_client_on_trust_alone():
    r = apply(rel("stranger", -0.5, 0.1), [sw("honest", -0.1, 0.3)])
    assert (r.rung, r.warmth, r.trust) == ("client", -0.6, 0.4)
