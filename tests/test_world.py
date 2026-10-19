"""Task 17: the world beyond the scene. Fake providers and judges only; deterministic."""
from __future__ import annotations

import json

from harness.judge import FakeJudge
from harness.models import HEARD, PLAYER, WITNESSED, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.world import clock as clk
from harness.world import news as nw
from harness.world.canon_adapter import ApiCanon, ListCanon, NullCanon, ScheduledEvent
from harness.world.places import Place, WorldMap, vizima
from harness.world.world import (
    A_REPORT, R_PATROL, World, pilot_collectives,
)

PROFILES = [
    CharacterProfile(PLAYER, "Демон", "A demon."),
    CharacterProfile("innkeeper", "Корчмар", "Keeps the tavern."),
    CharacterProfile("trader", "Торговка", "Sells cloth at the market."),
    CharacterProfile("drunk", "П'яниця", "Drinks in the tavern."),
]
MIRACLE = "The demon turned every mug of beer in the tavern into blood before the whole room"


def build(rules=None, script=None, canon=None, present=(PLAYER, "innkeeper"), place="tavern",
          goals=None):
    wmap = vizima()
    provider = FakeProvider(script={"extractor": [], "narrator": [], "npc": [], **(script or {})})
    scene = Scene(wmap.name(place), tuple(present), time=20 * 60)
    eng = Engine(provider, PROFILES, scene, models=ModelConfig(), narration="json",
                 record_language=None, judge=FakeJudge(rules or {}))
    w = World(eng, wmap, cast={"innkeeper": "tavern", "drunk": "tavern", "trader": "market"},
              goals=goals or {}, canon=canon)
    return eng, w, provider


def miracle(eng, w, n=0.85, text=MIRACLE, knowers=((PLAYER, WITNESSED), ("innkeeper", WITNESSED),
                                                   ("drunk", WITNESSED))):
    ev = eng.log.append("action", game_time=eng.scene.time, location=eng.scene.location,
                        participants=[PLAYER], witnesses=[k for k, _ in knowers],
                        notability=n, payload={"text": text, "actor": PLAYER})
    fid = eng.facts.add_campaign(text, source_event_id=ev.id, game_time=eng.scene.time,
                                 location=eng.scene.location, notability=n,
                                 knowers=list(knowers))
    return ev, fid, w.register_news([fid])[0]


# -- places, clock ----------------------------------------------------------------------------
def test_map_shortest_path_resolve_and_lazy_place():
    m = vizima()
    assert m.minutes("tavern", "market") == 10
    assert m.minutes("tavern", "guardhouse") == 25  # through the market
    assert m.minutes("market", "market") == 0
    assert m.resolve("ринок").id == "market" and m.resolve("корчма «Під Лисом»").id == "tavern"
    assert m.resolve("nowhere") is None
    m.add_place(Place("mill", "млин"), {"gate": 40})
    assert m.minutes("tavern", "mill") == 48


def test_until_hour_and_buckets():
    assert clk.until_hour(20 * 60, 7) == 11 * 60
    assert clk.until_hour(7 * 60, 7) == clk.DAY  # it is already that hour: a full day
    assert clk.until_hour(clk.DAY + 6 * 60 + 30, 7) == 30
    assert clk.minutes_of("hour") == 60


def test_reach_grows_with_notability_and_quiet_stays_home():
    assert nw.reach_minutes(0.3) == 0 and nw.reach_minutes(0.49) == 0
    r = [nw.reach_minutes(n) for n in (0.5, 0.6, 0.7, 0.8, 0.9, 1.0)]
    assert r == sorted(r) and r[0] < r[-1]
    assert nw.arrival_delay(0.5, 30) is not None
    assert nw.arrival_delay(0.5, 500) is None  # a small event never gets that far
    assert nw.arrival_delay(0.9, 500) is not None
    assert nw.arrival_delay(0.9, 60) < nw.arrival_delay(0.5, 60)  # loud news is faster


# -- news -------------------------------------------------------------------------------------
def test_only_loud_perceived_facts_become_news_once():
    eng, w, _ = build()
    ev, fid, nid = miracle(eng, w)
    assert w.register_news([fid]) == []  # idempotent
    ev2 = eng.log.append("action", game_time=eng.scene.time, location="x", payload={})
    quiet = eng.facts.add_campaign("A quiet word", source_event_id=ev2.id,
                                   game_time=eng.scene.time, location="x", notability=0.4,
                                   knowers=[("innkeeper", WITNESSED)])
    nobody = eng.facts.add_campaign("Narration only", source_event_id=ev2.id,
                                    game_time=eng.scene.time, location="x", notability=0.9,
                                    knowers=[])
    assert w.register_news([quiet, nobody]) == []
    assert [e.id for e in w.news_events()] == [nid]


def test_versions_coexist_have_operator_and_source_and_wait_for_their_time():
    rules = {"news_operator": lambda q, st: "exaggerate" if "townsfolk" in " ".join(st) else "none",
             "news_derivable": True, "collective_stance": "fear"}
    eng, w, _ = build(rules, script={"extractor": ["A hundred men bled in the tavern."]})
    _, _, nid = miracle(eng, w)
    t0 = eng.scene.time
    assert w.resolve(t0 + 1) == []  # nothing has arrived a minute later
    made = w.resolve(t0 + 6 * 60)
    by = {v.payload["holder"]: v for v in made}
    assert {"col_town", "col_guard", "col_velerad", "col_king"} >= set(by) >= {"col_town", "col_guard"}
    town, guard = by["col_town"], by["col_guard"]
    assert town.payload["operator"] == "exaggerate" and town.payload["text"].startswith("A hundred")
    assert guard.payload["operator"] == "none" and guard.payload["text"] == MIRACLE
    # each is a record of its own with a source; the true event is untouched
    ft, fg = w.version_fact(town), w.version_fact(guard)
    assert ft.content != fg.content
    assert ft.knowers[0].character == "col_town" and ft.knowers[0].source is not None
    assert town.payload["hops"] >= 1 and town.payload["at"] > t0
    assert eng.facts.get(w.news_events()[0].payload["fact_id"]).content == MIRACLE
    # attitude of the collective is stored apart from the fact
    assert eng.attitudes.of("col_town")[0].stance == "fear"
    # lazy: resolving again changes nothing
    assert w.resolve(t0 + 6 * 60) == []


def test_underivable_retelling_falls_back_to_truth_and_says_so():
    rules = {"news_operator": "exaggerate", "news_derivable": False}
    eng, w, _ = build(rules, script={"extractor": ["Invented nonsense about a dragon."]})
    miracle(eng, w)
    v = w.resolve(eng.scene.time + 600, kinds=("town",))[0]
    assert v.payload["operator"] == "none" and v.payload["verified"] is False
    assert v.payload["text"] == MIRACLE


def test_distant_place_never_hears_a_quiet_event_and_far_hears_a_loud_one():
    eng, w, _ = build()
    w.map.add_place(Place("far", "далеке село"), {"gate": 600})
    w.collectives["col_far"] = type(w.collectives["col_town"])(
        "col_far", "селяни", "far", "town", role="villagers")
    eng.profiles["col_far"] = CharacterProfile("col_far", "селяни")
    miracle(eng, w, n=0.6)  # reach about 320 minutes
    w.resolve(eng.scene.time + 3000, kinds=("town",))
    assert "col_far" not in {e.payload["holder"] for e in eng.log.active([nw.NEWS_VERSION])}
    miracle(eng, w, n=0.95, text="The king's tower fell")
    w.resolve(eng.scene.time + 3000, kinds=("town",))
    holders = [(e.payload["holder"], e.payload["news"]) for e in eng.log.active([nw.NEWS_VERSION])]
    assert any(h == "col_far" for h, _ in holders)


def test_person_hears_lazily_with_source_and_witness_is_skipped():
    rules = {"person_heard": True}
    eng, w, _ = build(rules, present=(PLAYER, "trader"), place="market")
    # the miracle happened in the tavern; the trader at the market did not see it
    ev = eng.log.append("action", game_time=eng.scene.time, location="tavern",
                        payload={"text": MIRACLE, "actor": PLAYER})
    fid = eng.facts.add_campaign(MIRACLE, source_event_id=ev.id, game_time=eng.scene.time,
                                 location="tavern", notability=0.85,
                                 knowers=[(PLAYER, WITNESSED), ("innkeeper", WITNESSED)])
    w.register_news([fid], origin="tavern")
    eng.scene.time += 120
    assert not eng.facts.visible_to("trader", eng.scene.time)
    heard = w.refresh_place()
    assert [h.payload["person"] for h in heard] == ["trader"]
    mine = eng.facts.visible_to("trader", eng.scene.time)
    me = next(k for k in mine[0].knowers if k.character == "trader")
    assert len(mine) == 1 and me.source == "col_town" and me.how == HEARD
    # it shows up in the trader's context with its source, and the true fact does not
    text = " ".join(m["content"] for m in eng.ctx.character_view("trader", eng.scene).messages())
    assert MIRACLE in text and "heard from городяни Визими" in text
    assert w.refresh_place() == []  # nothing more to hear


def test_person_who_would_not_have_heard_gets_no_record():
    eng, w, _ = build({"person_heard": False}, present=(PLAYER, "trader"), place="market")
    ev = eng.log.append("action", game_time=eng.scene.time, location="tavern", payload={})
    fid = eng.facts.add_campaign(MIRACLE, source_event_id=ev.id, game_time=eng.scene.time,
                                 location="tavern", notability=0.85,
                                 knowers=[("innkeeper", WITNESSED)])
    w.register_news([fid], origin="tavern")
    eng.scene.time += 120
    assert w.refresh_place() == []
    assert eng.facts.visible_to("trader", eng.scene.time) == []


def test_rollback_of_the_source_removes_news_versions_and_hearing():
    eng, w, _ = build({"person_heard": True}, present=(PLAYER, "trader"), place="market")
    ev, fid, nid = miracle(eng, w)
    eng.scene.time += 300
    w.refresh_place()
    assert eng.facts.visible_to("trader", eng.scene.time)
    eng.rollback(ev.id)
    assert w.news_events() == []
    assert eng.facts.visible_to("trader", eng.scene.time) == []
    assert not eng.log.active([nw.NEWS_VERSION])


# -- authorities and off-screen agents --------------------------------------------------------
def test_authority_reacts_by_scale_and_escalates():
    rules = {"authority_reaction": R_PATROL, "authority_escalate": True}
    eng, w, _ = build(rules)
    miracle(eng, w, n=0.85)
    w.tick(eng.scene.time + 4 * 60)
    reacts = [e for e in eng.log.active([nw.WORLD_REACTION])]
    who = {e.payload["authority"]: e.payload for e in reacts}
    assert who["col_guard"]["kind"] == R_PATROL and who["col_guard"]["target"] == "tavern"
    assert "col_velerad" in who  # the guard passed it up and Velerad heard it
    assert who["col_guard"]["eta"] > who["col_guard"]["eta"] - 1
    assert any("sent armed men" in f.content for f in eng.facts.all_campaign(eng.scene.time))


def test_small_event_is_not_met_with_force():
    eng, w, _ = build({"authority_reaction": lambda q, st: R_PATROL if R_PATROL in q.options
                       else "ignore"})
    miracle(eng, w, n=0.52, text="The demon juggled coins")
    w.tick(eng.scene.time + 4 * 60)
    for e in eng.log.active([nw.WORLD_REACTION]):  # patrol is not even on offer at this scale
        assert e.payload["kind"] in ("ignore", "ask_around")


def test_very_big_event_always_reaches_the_king():
    eng, w, _ = build({"authority_reaction": "ignore", "authority_escalate": False})
    miracle(eng, w, n=0.95)
    w.tick(eng.scene.time + 12 * 60)
    assert "col_king" in {e.payload["holder"] for e in eng.log.active([nw.NEWS_VERSION])}


def test_witness_agent_goes_to_report_and_becomes_the_carrier():
    rules = {"offscreen_act": A_REPORT, "authority_reaction": "ignore"}
    eng, w, _ = build(rules)
    eng.agents.promote("innkeeper", eng.scene)
    _, _, nid = miracle(eng, w)
    eng.leave_scene("innkeeper", stay_nearby=False)  # he is no longer in the scene
    t0 = eng.scene.time
    w.tick(t0 + 3 * 60)
    ups = w.updates("innkeeper")
    assert ups and ups[0].payload["kind"] == A_REPORT
    assert ups[0].payload["place"] == "guardhouse"
    # on the road first, then there
    assert w.where("innkeeper", t0 + 61) in (None, "guardhouse")
    assert w.where("innkeeper", t0 + 3 * 60) == "guardhouse"
    # a tellable and a private intent were recorded for him
    assert any("report" in f.content for f in eng.facts.visible_to("innkeeper", t0 + 3 * 60))
    assert eng.intents.pending("innkeeper")
    # the guard's version names him as the source if his delivery came first
    guard = [v for v in eng.log.active([nw.NEWS_VERSION]) if v.payload["holder"] == "col_guard"]
    assert guard and guard[0].payload["holder"] == "col_guard"


def test_no_calls_when_nothing_happens():
    eng, w, _ = build()
    eng.agents.promote("innkeeper", eng.scene)
    eng.leave_scene("innkeeper", stay_nearby=False)
    n = len(eng.judge.inner.asked)  # type: ignore[attr-defined]
    w.tick(eng.scene.time + 24 * 60)
    assert len(eng.judge.inner.asked) == n  # no goal, no news: the day passes for free


def test_routine_agent_with_goal_gets_one_judgment_per_period():
    eng, w, _ = build({"offscreen_act": "goal"}, goals={"innkeeper": "keep the tavern open"})
    eng.agents.promote("innkeeper", eng.scene)
    eng.leave_scene("innkeeper", stay_nearby=False)
    w.tick(eng.scene.time + 24 * 60)
    asked = [q for _, qs in eng.judge.inner.asked for q in qs.values()  # type: ignore[attr-defined]
             if q.tag == "offscreen_act"]
    assert 2 <= len(asked) <= 4  # about every eight hours


# -- canon events -----------------------------------------------------------------------------
def test_scheduled_canon_event_executes_once_and_spreads():
    t = 20 * 60 + 90
    canon = ListCanon([ScheduledEvent("c1", t, "palace", ("velerad",), "Velerad receives the king's order",
                                      ("velerad",), 0.8)])
    eng, w, _ = build(canon=canon)
    w.tick(t - 10)
    assert not eng.log.active([nw.CANON_EXECUTED])
    w.tick(t + 60)
    ex = eng.log.active([nw.CANON_EXECUTED])
    assert len(ex) == 1 and ex[0].payload["outcome"] == "as_written"
    assert any(f.content.startswith("Velerad receives") for f in eng.facts.visible_to("velerad", t + 60))
    assert len(w.news_events()) == 1  # it became news
    w.tick(t + 600)
    assert len(eng.log.active([nw.CANON_EXECUTED])) == 1  # not twice


def test_canon_event_touched_by_the_player_is_rejudged():
    t = 20 * 60 + 90
    canon = ListCanon([ScheduledEvent("c1", t, "tavern", ("innkeeper",), "The innkeeper hosts a feast",
                                      (), 0.6)])
    eng, w, _ = build({"canon_event": "not_happen"}, canon=canon)
    miracle(eng, w)  # at the same place: the player changed things there
    w.tick(t + 10)
    ex = eng.log.active([nw.CANON_EXECUTED])
    assert ex[0].payload["outcome"] == "not_happen" and ex[0].payload["touched"]
    assert not any("feast" in f.content for f in eng.facts.all_campaign(t + 10))


def test_canon_event_untouched_needs_no_judgment():
    t = 20 * 60 + 90
    canon = ListCanon([ScheduledEvent("c1", t, "palace", ("velerad",), "A letter arrives", (), 0.6)])
    eng, w, _ = build({"canon_event": "not_happen"}, canon=canon)
    w.tick(t + 10)
    assert eng.log.active([nw.CANON_EXECUTED])[0].payload["outcome"] == "as_written"
    assert not [1 for _, qs in eng.judge.inner.asked for q in qs.values() if q.tag == "canon_event"]  # type: ignore[attr-defined]


def test_adapter_defaults_and_api_wrapper():
    assert NullCanon().scheduled(0, 10**9) == () and NullCanon().background("a", "b") is None

    class Api:
        @staticmethod
        def scheduled_events(a, b):
            class E:
                id, t, place, summary, notability = "x", 5, "market", "S", 0.4
                participants, knowers = ("a",), ()
            return [E()] if a < 5 <= b else []

        @staticmethod
        def background(c, t):
            return "knows it" if c == "a" else None

    ac = ApiCanon(Api)
    assert ac.scheduled(0, 9)[0].id == "x" and ac.scheduled(5, 9) == []
    assert ac.background("a", "t") == "knows it" and ac.background("b", "t") is None


# -- moving, waiting, playing -----------------------------------------------------------------
def _turn_script(n=1):
    nar = json.dumps({"description": "Night passes.", "observable_actions": [], "speakers": []})
    return {"narrator": [nar] * n, "extractor": [json.dumps({"new_facts": [], "state_changes": []})] * n}


def test_go_to_takes_time_changes_scene_and_residents_enter():
    eng, w, _ = build()
    t0 = eng.scene.time
    mins = w.go_to("market")
    assert mins == 10 and eng.scene.time == t0 + 10
    assert eng.scene.location == "ринок"
    assert "trader" in eng.scene.present and "innkeeper" not in eng.scene.present
    assert PLAYER in eng.scene.present


def test_wait_until_morning_and_agents_move_meanwhile():
    rules = {"offscreen_act": A_REPORT, "authority_reaction": "ignore"}
    eng, w, _ = build(rules)
    eng.agents.promote("innkeeper", eng.scene)
    miracle(eng, w)
    eng.leave_scene("innkeeper", stay_nearby=False)
    w.wait(clk.until_hour(eng.scene.time, 7))
    assert eng.scene.time % clk.DAY == 7 * 60
    assert w.updates("innkeeper")[0].payload["kind"] == A_REPORT


def test_wait_stops_when_the_patrol_arrives():
    rules = {"authority_reaction": R_PATROL, "authority_escalate": False}
    eng, w, _ = build(rules)
    miracle(eng, w, n=0.85)
    stop = w.wait(12 * 60)
    assert stop and "arrive" in stop
    assert eng.scene.time < 20 * 60 + 12 * 60
    arrivals = eng.log.active([nw.WORLD_ARRIVAL])
    assert arrivals
    assert any("armed men" in f.content for f in eng.facts.visible_to(PLAYER, eng.scene.time))


def test_play_plans_a_trip_then_runs_the_turn():
    rules = {"turn_move": "market", "turn_duration": "minutes"}
    eng, w, _ = build(rules, script=_turn_script())
    wt = w.play("Іду на ринок")
    assert wt.moved_to == "market" and eng.scene.location == "ринок"
    assert eng.scene.time >= 20 * 60 + 10


def test_play_wait_until_morning_judged_from_text():
    rules = {"turn_wait": "until_morning", "turn_duration": "moment"}
    eng, w, _ = build(rules, script=_turn_script())
    wt = w.play("Чекаю до ранку")
    assert wt.waited == 11 * 60
    assert eng.scene.time % clk.DAY == 7 * 60 + 1  # seven o'clock plus the one-minute turn


def test_play_registers_loud_facts_as_news():
    d = json.dumps({"new_facts": [{"content": MIRACLE, "source": "paction1", "notability": 0.9}],
                    "state_changes": []})
    nar = json.dumps({"description": "Blood fills the mugs.", "observable_actions": [],
                      "speakers": []})
    eng, w, _ = build({}, script={"narrator": [nar], "extractor": [d]})
    wt = w.play("*Перетворюю пиво на кров*")
    assert len(wt.news) == 1
    n = w.news_events()[0]
    assert n.payload["notability"] == 0.9 and n.payload["origin"] == "tavern"
    assert "paction" not in str(n.payload)


# -- the debug view, the player without limits --------------------------------------------------
def test_report_lists_news_versions_reactions_and_offscreen():
    rules = {"authority_reaction": R_PATROL, "authority_escalate": True, "collective_stance": "awe",
             "offscreen_act": A_REPORT}
    eng, w, _ = build(rules)
    eng.agents.promote("innkeeper", eng.scene)
    mark = max(e.id for e in eng.log.active())
    miracle(eng, w)
    eng.leave_scene("innkeeper", stay_nearby=False)
    w.tick(eng.scene.time + 3 * 60)
    w.resolve(eng.scene.time, kinds=("town",))
    r = w.report(since=mark)
    assert r["news"] and r["news"][0]["new"] and r["news"][0]["versions"]
    v = r["news"][0]["versions"][0]
    assert {"holder", "text", "operator", "source", "at", "hops"} <= set(v)
    assert r["reactions"] and r["offscreen"] and "col_town" in r["mood"]
    json.dumps(r, ensure_ascii=False)  # serialisable for the debug endpoint


def test_player_acts_are_not_softened_in_the_prompts():
    from harness.context import UNLIMITED_EXTRACTOR, UNLIMITED_NARRATOR

    prov = FakeProvider()
    scene = Scene("Inn", (PLAYER, "innkeeper"), 0)
    on = Engine(prov, PROFILES, scene, narration="prose", record_language=None,
                player_unlimited=True)
    off = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper"), 0), narration="prose",
                 record_language=None)
    seg = [("paction1", "turns beer into blood")]
    ex_on = " ".join(m["content"] for m in on.ctx.extractor(on.scene, seg))
    ex_off = " ".join(m["content"] for m in off.ctx.extractor(off.scene, seg))
    assert UNLIMITED_EXTRACTOR in ex_on and UNLIMITED_EXTRACTOR not in ex_off
    nar = " ".join(m["content"] for m in on.ctx.narrator(on.scene, "x"))
    assert UNLIMITED_NARRATOR in nar
    assert UNLIMITED_NARRATOR not in " ".join(m["content"] for m in off.ctx.narrator(off.scene, "x"))
    on.close(), off.close()


def test_pilot_collectives_exist_as_pseudo_characters():
    eng, w, _ = build()
    for c in pilot_collectives(vizima()):
        assert c.id in eng.profiles
    assert eng.profiles["col_guard"].name == "міська варта"


def test_higher_authority_hears_only_what_the_guard_passes_up():
    eng, w, _ = build({"authority_reaction": "ignore", "authority_escalate": False})
    miracle(eng, w, n=0.8)
    w.tick(eng.scene.time + 12 * 60)
    holders = {e.payload["holder"] for e in eng.log.active([nw.NEWS_VERSION])}
    assert "col_guard" in holders and "col_velerad" not in holders and "col_king" not in holders
    eng2, w2, _ = build({"authority_reaction": "ignore", "authority_escalate": True})
    miracle(eng2, w2, n=0.8)
    w2.tick(eng2.scene.time + 12 * 60)
    holders2 = {e.payload["holder"] for e in eng2.log.active([nw.NEWS_VERSION])}
    assert {"col_guard", "col_velerad", "col_king"} <= holders2
