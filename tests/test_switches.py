"""Character portraits task 4: the portrait's switches move the NPC -> player relationship on the
slow lane (one batched judge call per NPC), paced (one positive switch a turn, capped, damped on
repeats, smaller on higher rungs, gated by scene changes, decaying when nothing warm happens), the
ladder climbs or drops one rung at a time, and a hidden-layer leak goes into the prompt only with
trust and at most once per scene, recorded in the log by the line that carried it."""
from dataclasses import replace

import pytest
from test_portrait_context import PROFILES, eng, portrait, prompt

from conftest import diff
from harness.judge import FakeJudge
from harness.models import PLAYER, PORTRAIT_LEAK, UTTERANCE, Scene
from harness.pipeline import Engine, ModelConfig
from harness.portrait import Switch
from harness.providers import FakeProvider
from harness.relations import Pace, Relations, Relationship, apply

LEAK = "A star pendant gesture."


def rel(rung, w, t):
    return Relationship("yen", PLAYER, rung, w, t, "", None)


def sw(id, w, t):
    return Switch(id, f"Did {id}?", w, t)


def nums(r):
    return (r.rung, r.warmth, r.trust)


# -- the ladder and its pacing ----------------------------------------------------------------
def test_apply_clamps_and_climbs():
    r = apply(rel("stranger", -0.2, 0.2), [sw("a", 0.3, 0.2)])
    assert (r.rung, r.warmth, r.trust, r.reason, r.counted) == ("client", 0.1, 0.4, "a", ("a",))
    # a positive turn is capped at +0.3 warmth and +0.3 trust, and climbs one rung only
    assert nums(apply(rel("stranger", -0.2, 0.2), [sw("x", 5, 5)])) == ("client", 0.1, 0.5)
    assert nums(apply(rel("ally", 0.9, 0.9), [sw("x", 5, 5)], Pace(held=5, distinct=frozenset(
        "abc")))) == ("close", 1.0, 1.0)
    # trust is clamped at 0
    assert apply(rel("client", 0.0, 0.4), [sw("y", -0.1, -2)]).trust == 0.0
    # thresholds are inclusive and float noise does not break them (0.7 - 0.4 is 0.2999...)
    r = apply(rel("client", 0.7, 0.45), [sw("z", -0.4, 0)])
    assert (r.rung, r.warmth) == ("ally", 0.3)


def test_only_the_largest_positive_and_every_negative_count():
    r = apply(rel("stranger", -0.2, 0.2), [sw("a", 0.3, 0.2), sw("b", 0.2, 0.1)])
    assert nums(r) == ("client", 0.1, 0.4) and r.reason == "a,b" and r.counted == ("a",)
    r = apply(rel("stranger", -0.2, 0.2), [sw("a", 0.3, 0.2), sw("p", -0.3, -0.2),
                                           sw("q", -0.4, -0.4)])
    assert nums(r) == ("stranger", -0.6, 0.0)                    # +0.3/+0.2, then -0.7/-0.6
    r = apply(rel("client", 0.0, 0.4), [sw("p", -0.4, -0.4), sw("q", -0.5, -0.3)])
    assert nums(r) == ("enemy", -0.9, 0.0)                       # negatives: uncapped


def test_rung_multiplier_on_positive_deltas():
    up = [sw("a", 0.2, 0.2)]
    assert nums(apply(rel("stranger", 0.0, 0.0), up))[1:] == (0.2, 0.2)
    assert nums(apply(rel("client", 0.0, 0.3), up))[1:] == (0.15, 0.45)
    assert nums(apply(rel("ally", 0.3, 0.45), up))[1:] == (0.4, 0.55)
    assert nums(apply(rel("close", 0.6, 0.65), up))[1:] == (0.67, 0.72)
    # negatives are not scaled
    assert apply(rel("close", 0.7, 0.7), [sw("p", -0.2, -0.2)]).warmth == 0.5


def test_repeat_dampening():
    up = [sw("a", 0.2, 0.2)]
    # once per scene: a second hit of the same id in the scene does nothing
    r = apply(rel("stranger", 0.0, 0.0), up, Pace(scene="A#0", this_scene=frozenset({"a"})))
    assert nums(r) == ("stranger", 0.0, 0.0) and r.counted == ()
    # another positive still counts in that scene
    r = apply(rel("stranger", 0.0, 0.0), up + [sw("b", 0.1, 0.1)],
              Pace(scene="A#0", this_scene=frozenset({"a"})))
    assert nums(r)[1:] == (0.1, 0.1) and r.counted == ("b",)
    # hit in the scene before: half
    r = apply(rel("stranger", 0.0, 0.0), up, Pace(scene="B#0", changed=True,
                                                 prev_scene=frozenset({"a"})))
    assert nums(r)[1:] == (0.1, 0.1) and r.counted == ("a",)


def test_gates_need_scene_changes_and_distinct_switches():
    hot = [sw("a", 0.3, 0.3)]
    assert apply(rel("ally", 0.6, 0.7), hot, Pace(held=0)).rung == "ally"
    assert apply(rel("ally", 0.6, 0.7), hot, Pace(held=1)).rung == "close"
    # lover: close held across 2 scene changes and 3 distinct positive ids (this turn's counts)
    assert apply(rel("close", 0.9, 0.9), hot, Pace(held=1, distinct=frozenset("abc"))).rung \
        == "close"
    assert apply(rel("close", 0.9, 0.9), hot, Pace(held=2, distinct=frozenset("b"))).rung \
        == "close"
    assert apply(rel("close", 0.9, 0.9), hot, Pace(held=2, distinct=frozenset("bc"))).rung \
        == "lover"


def test_decay_on_a_new_scene_without_warmth_in_the_last():
    cold = Pace(scene="B#0", changed=True, prev_had_positive=False)
    assert apply(rel("client", 0.3, 0.5), [], cold).warmth == 0.25      # toward 0.0
    assert apply(rel("ally", 0.1, 0.5), [], cold).warmth == 0.15        # toward 0.3
    assert apply(rel("ally", 0.32, 0.5), [], cold).warmth == 0.3        # never past it
    assert apply(rel("stranger", -0.5, 0.2), [], cold).warmth == -0.45  # toward the seed -0.2
    warm = Pace(scene="B#0", changed=True, prev_had_positive=True)
    assert apply(rel("client", 0.3, 0.5), [], warm).warmth == 0.3
    assert apply(rel("client", 0.3, 0.5), [], Pace(scene="A#0")).warmth == 0.3


def test_setback_drops_a_rung():
    r = apply(rel("ally", 0.5, 0.6), [sw("pity", -0.6, -0.2)])
    assert (r.rung, r.warmth, r.trust, r.reason) == ("client", -0.1, 0.4, "pity")
    assert apply(rel("close", 0.7, 0.7), [sw("p", -0.2, 0)]).rung == "close"   # 0.5 >= 0.3
    assert apply(rel("lover", 0.9, 0.9), [sw("p", -0.4, 0)]).rung == "close"   # 0.5 < 0.55
    assert apply(rel("ally", 0.5, 0.9), [sw("p", -0.2, 0)]).rung == "ally"     # 0.3: not below 0
    assert apply(rel("close", 0.7, 0.7), [sw("p", -1.0, 0)]).rung == "ally"    # one rung a turn
    assert apply(rel("stranger", -0.2, 0.2), [sw("p", -0.4, 0)]).rung == "stranger"


def test_no_drop_on_a_warming_turn():
    # a cold client (climbed on trust alone) does not flap back on a warm turn or a quiet one
    r = apply(rel("stranger", -0.5, 0.1), [sw("honest", -0.1, 0.3)])
    assert nums(r) == ("client", -0.6, 0.4)
    assert apply(r, [sw("warm", 0.1, 0.0)]).rung == "client"
    assert apply(r, []).rung == "client"
    assert apply(r, [sw("cold", -0.05, 0.0)]).rung == "stranger"


def test_enemy_threshold():
    r = apply(rel("client", 0.0, 0.4), [sw("pressure", -0.4, -0.4), sw("wound", -0.3, -0.3)])
    assert nums(r) == ("enemy", -0.7, 0.0)
    assert apply(rel("lover", 0.9, 0.9), [sw("w", -1.6, 0)]).rung == "enemy"
    assert apply(rel("client", 0.0, 0.4), [sw("p", -0.6, 0)]).rung == "stranger"
    # back to stranger only at warmth >= -0.4 and after a scene change since becoming enemy
    up = [sw("c", 0.3, 0.2)]
    assert nums(apply(rel("enemy", -0.7, 0.0), up, Pace(held=0))) == ("enemy", -0.4, 0.2)
    assert apply(rel("enemy", -0.7, 0.0), up, Pace(held=1)).rung == "stranger"
    assert apply(rel("enemy", -0.8, 0.0), up, Pace(held=1)).rung == "enemy"


def test_pace_from_the_log():
    e = eng()
    rs = Relations(e.log)
    sc_a, sc_b = Scene("A", (PLAYER, "yen"), 0), Scene("B", (PLAYER, "yen"), 0)
    rs.seed("yen", PLAYER, "client", sc_a)
    assert rs.get("yen", PLAYER).scene == rs.scene_key("yen", sc_a)
    rs.set("yen", PLAYER, "ally", 0.3, 0.5, "a", sc_a, None, key="A#0", counted=("a",))
    p = rs.pace("yen", PLAYER, "A#0")
    assert (p.changed, p.this_scene, p.held, p.distinct) == (False, {"a"}, 0, {"a"})
    p = rs.pace("yen", PLAYER, "B#0")
    assert (p.changed, p.this_scene, p.prev_scene, p.prev_had_positive, p.held) == (
        True, frozenset(), {"a"}, True, 1)
    rs.set("yen", PLAYER, "ally", 0.3, 0.5, "", sc_b, None, key="B#0")
    p = rs.pace("yen", PLAYER, "C#0")
    assert (p.prev_scene, p.prev_had_positive, p.held, p.distinct) == (
        frozenset(), False, 2, {"a"})
    p = rs.pace("yen", PLAYER, "B#0")
    assert (p.changed, p.this_scene, p.prev_scene, p.held) == (False, frozenset(), {"a"}, 1)


# -- the slow lane --------------------------------------------------------------------------
def yen_engine(judge_rules=None, npc=("— Що тобі треба?", "— Кажи коротше."), **kw):
    e = eng({"narrator": ["N."] * 4, "npc": list(npc), "extractor": [diff()] * 8}, **kw)
    e.judge.inner.rules.update(judge_rules or {})
    e.scene.present = (PLAYER, "yen")
    e.bind_portrait("yen", "p_yen")
    return e


def switch_asks(e):
    return [(st, qs) for st, qs in e.judge.inner.asked
            if any(q.tag == "portrait_switch" for q in qs.values())]


def player_line(e):
    return [u for u in e.log.active([UTTERANCE]) if u.payload["speaker"] == PLAYER][-1]


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
    assert "what the player did or said this turn (toward her or others present)" in state
    r = e.ctx.relations.get("yen", PLAYER)
    assert (r.rung, r.warmth, r.trust, r.reason) == ("client", 0.0, 0.3, "w")
    notes = [n for n in e.devlog if n["kind"] == "relation_changed"]
    assert notes and notes[0]["npc"] == "yen" and notes[0]["from"] == "stranger" \
        and notes[0]["to"] == "client" and notes[0]["switches"] == ["w"]


def test_no_switch_hit_leaves_the_relationship():
    e = yen_engine({"portrait_switch": False})
    e.turn("Добрий день.", speakers=["yen"])
    assert len(switch_asks(e)) == 1
    r = e.ctx.relations.get("yen", PLAYER)
    assert nums(r) == ("stranger", -0.2, 0.2) and r.reason == ""
    assert not [n for n in e.devlog if n["kind"] == "relation_changed"]


def test_no_switch_questions_for_npc_without_portrait():
    e = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e.judge.inner.rules["portrait_switch"] = True
    e.scene.present = (PLAYER, "inn")
    e.turn("Пива.", speakers=["inn"])
    assert switch_asks(e) == []
    # a portrait NPC who stays silent and is not dealt with while another speaks: not asked
    e = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e.judge.inner.rules["portrait_switch"] = True
    e.bind_portrait("yen", "p_yen")
    e.turn("Пива.", speakers=["inn"])
    assert switch_asks(e) == []


def test_silent_npc_the_player_acts_toward_is_judged():
    e = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e.judge.inner.rules["portrait_switch"] = True
    e.bind_portrait("yen", "p_yen")                 # present, silent; the innkeeper talks
    e.turn("*мовчки подаю чорнокосій жінці кухоль води*", speakers=["inn"])
    asks = switch_asks(e)
    assert len(asks) == 1 and "Йеннефер" in asks[0][0][0]
    assert e.ctx.relations.get("yen", PLAYER).rung == "client"
    e2 = eng({"narrator": ["N."] * 4, "npc": ["— Пива?"] * 2, "extractor": [diff()] * 6})
    e2.judge.inner.rules["portrait_switch"] = True
    e2.bind_portrait("yen", "p_yen")
    e2.turn("Йеннефер, сядьте, прошу.", speakers=["inn"])    # by name
    assert len(switch_asks(e2)) == 1


def test_switch_failure_never_aborts_settle(monkeypatch):
    from harness import relations
    e = yen_engine({"portrait_switch": True})

    def boom(*a, **k):
        raise RuntimeError("bad pace")
    monkeypatch.setattr(relations, "apply", boom)
    e.turn("Добрий день.", speakers=["yen"])
    assert e.slow_failure is None and e.log.active(["narration"])
    assert [n for n in e.devlog if n["kind"] == "switches_failed"]
    assert e.ctx.relations.get("yen", PLAYER).reason == "seed"


# -- regeneration keeps the player's earned change --------------------------------------------
def test_regeneration_rejudges_and_keeps_the_earned_change():
    e = yen_engine({"portrait_switch": True})
    e.turn("Я приніс тобі води.", speakers=["yen"])
    r = e.ctx.relations.get("yen", PLAYER)
    first = e.log.get(r.event_id)
    assert r.rung == "client" and first.cause_id == player_line(e).id
    line = e.log.last_npc_utterance()
    assert first.payload["lines"] == [line.id]
    e.model_error(line.id, "вона б так не сказала")
    new_line = e.log.last_npc_utterance()
    r = e.ctx.relations.get("yen", PLAYER)
    assert not e.log.is_active(first.id) and r.event_id != first.id
    assert nums(r) == ("client", 0.0, 0.3)          # earned again, not counted twice
    ev = e.log.get(r.event_id)
    assert ev.cause_id == player_line(e).id and ev.payload["lines"] == [new_line.id]
    assert len(switch_asks(e)) == 2
    assert "Кажи коротше." in "\n".join(switch_asks(e)[-1][0])


def test_regeneration_rejudged_as_no_returns_to_the_earlier_state():
    e = yen_engine({"portrait_switch": [True, False]})
    e.turn("Я приніс тобі води.", speakers=["yen"])
    assert e.ctx.relations.get("yen", PLAYER).rung == "client"
    e.model_error(e.log.last_npc_utterance().id, "не так")
    assert nums(e.ctx.relations.get("yen", PLAYER)) == ("stranger", -0.2, 0.2)


def test_failed_regeneration_rejudges_with_the_restored_line():
    e = yen_engine({"portrait_switch": True}, npc=("— Що тобі треба?",))
    e.turn("Я приніс тобі води.", speakers=["yen"])
    line = e.log.last_npc_utterance()
    with pytest.raises(Exception):
        e.model_error(line.id, "не так")             # the npc script is exhausted
    restored = e.log.last_npc_utterance()
    assert restored.id != line.id and restored.payload.get("restored")
    r = e.ctx.relations.get("yen", PLAYER)
    assert r.rung == "client" and e.log.get(r.event_id).payload["lines"] == [restored.id]
    assert len(switch_asks(e)) == 2


def test_cut_rejudges_with_the_kept_part():
    e = yen_engine({"portrait_switch": True}, npc=("— Що тобі треба тут у мене?",))
    e.turn("Я приніс тобі води.", speakers=["yen"])
    kept = e.interrupt_retroactive(2)
    r = e.ctx.relations.get("yen", PLAYER)
    assert r.rung == "client" and e.log.get(r.event_id).payload["lines"] == [kept.id]
    assert len(switch_asks(e)) == 2


def test_regeneration_of_one_npc_never_touches_another():
    e = yen_engine({"portrait_switch": True}, npc=("— Що тобі треба?", "— Пива?", "— Вина?"))
    p_inn = replace(portrait(), id="p_inn", character="inn")
    e.ctx.portraits["p_inn"] = p_inn
    e.scene.present = (PLAYER, "yen", "inn")
    e.bind_portrait("inn", "p_inn")
    e.turn("Добрий день усім.", speakers=["yen", "inn"])
    yen_ev = e.ctx.relations.get("yen", PLAYER).event_id
    inn_ev = e.ctx.relations.get("inn", PLAYER).event_id
    yen_line = [u for u in e.log.active([UTTERANCE]) if u.payload["speaker"] == "yen"][-1]
    assert e.log.get(yen_ev).payload["lines"] == [yen_line.id]       # only her own line
    e.model_error(e.log.last_npc_utterance().id, "корчмар так не каже")
    assert e.log.is_active(yen_ev) and e.ctx.relations.get("yen", PLAYER).event_id == yen_ev
    assert not e.log.is_active(inn_ev) and e.ctx.relations.get("inn", PLAYER).rung == "client"
    assert len(switch_asks(e)) == 3                   # one per NPC, then inn again


# -- leaks ----------------------------------------------------------------------------------
def test_leak_needs_trust_and_one_per_scene():
    e = yen_engine(npc=("— Що тобі треба?", "— Кажи.", "— Ну?", "— Іди."))
    assert LEAK not in prompt(e, "yen")                      # stranger: trust 0.2
    e.ctx.relations.set("yen", PLAYER, "client", 0.1, 0.4, "test", e.scene, None)
    assert LEAK in prompt(e, "yen") and LEAK in prompt(e, "yen")   # building a prompt: not used
    e.turn("Добрий день.", speakers=["yen"])
    line = e.log.last_npc_utterance()
    used = e.log.active([PORTRAIT_LEAK])
    assert len(used) == 1 and used[0].cause_id == line.id and used[0].payload["npc"] == "yen"
    assert [n for n in e.devlog if n["kind"] == "portrait_leak"]
    assert LEAK not in prompt(e, "yen")                      # not twice in the same scene
    e.log.rollback(line.id)                                  # the line is gone: the leak is free
    assert LEAK in prompt(e, "yen")
    e.turn("Ще раз добрий день.", speakers=["yen"])
    assert LEAK not in prompt(e, "yen")
    e.leave_scene("yen")
    e.enter_scene("yen")                                     # a new scene entry: one more
    assert LEAK in prompt(e, "yen")


def test_used_leak_survives_reopen(tmp_path):
    leak = "The way she addresses him changes"
    prov = FakeProvider(script={"narrator": ["N."] * 3, "npc": ["— Кажіть."] * 3,
                                "extractor": [diff()] * 6})
    e = Engine.create_campaign("c", prov, PROFILES, Scene("Рінде", (PLAYER, "yen"), 0),
                               root=tmp_path, models=ModelConfig(), judge=FakeJudge(),
                               world="witcher")
    e.bind_portrait("yen", "yennefer_rinde", rung="client")         # trust 0.4
    assert leak in prompt(e, "yen")
    e.turn("Добрий день.", speakers=["yen"])
    assert leak not in prompt(e, "yen")
    e.close()
    again = Engine.open_campaign("c", prov, root=tmp_path, models=ModelConfig(),
                                 judge=FakeJudge())
    assert leak not in prompt(again, "yen") and again.log.active([PORTRAIT_LEAK])


def test_the_directors_addressee_is_judged_even_when_silent():
    from types import SimpleNamespace
    e = eng()
    e.bind_portrait("yen", "p_yen")                  # yen and the innkeeper present
    result = SimpleNamespace(utterances=[], exchange=[("silence", "yen", "")], addressee="yen")
    slow = SimpleNamespace(result=result, turn_events=[])
    assert e._switch_npcs(slow) == ["yen"]
    result.addressee = ""
    assert e._switch_npcs(slow) == []


def test_yennefer_helpless_trigger_excludes_her_and_the_player():
    from harness.portrait import load_world_portraits
    sw = {s.id: s for s in load_world_portraits("witcher")["yennefer_rinde"].switches}
    assert "other than her and the player" in sw["helpless_nearby"].trigger
    assert "not someone else's child" in sw["wound"].trigger


def test_scene_key_advances_with_game_time():
    e = eng()
    rs = Relations(e.log)
    sc = Scene("Кімната", (PLAYER, "yen"), 10 * 60)                 # day 1, 10:00
    rs.seed("yen", PLAYER, "stranger", sc)
    k0 = rs.scene_key("yen", sc)
    assert k0 == rs.get("yen", PLAYER).scene
    sc.time += 119                                                  # under 2 h: same scene
    assert rs.scene_key("yen", sc) == k0
    rs.set("yen", PLAYER, "stranger", -0.2, 0.2, "", sc, None, key=k0)   # judged at 11:59
    sc.time += 119
    assert rs.scene_key("yen", sc) == k0                            # 2 h since the start, < 2 h gap
    sc.time += 1                                                    # a 2 h gap since last judged
    k1 = rs.scene_key("yen", sc)
    assert k1 != k0
    rs.set("yen", PLAYER, "stranger", -0.2, 0.2, "", sc, None, key=k1)   # judged 13:59
    sc.time = 24 * 60 + 30                                          # next day 00:30, same room
    k2 = rs.scene_key("yen", sc)
    assert k2 not in (k0, k1)
    assert rs.pace("yen", PLAYER, k2).changed
    # judged again in the new scene: it continues
    rs.set("yen", PLAYER, "stranger", -0.2, 0.2, "", sc, None, key=k2)
    assert rs.scene_key("yen", sc) == k2


def test_a_positive_switch_counts_again_in_a_later_scene_of_the_same_room():
    e = yen_engine({"portrait_switch": True}, npc=("— Що?", "— Ну?", "— Знову ти."))
    e.turn("Я приніс тобі води.", speakers=["yen"])
    assert e.ctx.relations.get("yen", PLAYER).counted == ("w",)
    e.turn("Я приніс тобі ще води.", speakers=["yen"])
    r = e.ctx.relations.get("yen", PLAYER)
    assert r.counted == () and nums(r) == ("client", 0.0, 0.3)       # once per scene
    e.scene.time += 24 * 60                                             # the next day, same room
    e.turn("Я знову приніс тобі води.", speakers=["yen"])
    r = e.ctx.relations.get("yen", PLAYER)
    assert r.counted == ("w",) and nums(r) == ("client", 0.075, 0.3375)  # x0.75 client, x0.5 repeat
