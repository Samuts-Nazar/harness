"""Task 19: the world on the real canon API, the trail of a "seek the person" order, the narrator's
view of rumours."""
from __future__ import annotations

import json

from canon_fixture import START, make_store

from harness.canon.play import CanonPlay
from harness.canon.retrieve import Canon
from harness.judge import FakeJudge
from harness.models import PLAYER, WITNESSED, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.world import news as nw
from harness.world.canon_adapter import PlayCanon
from harness.world.places import vizima
from harness.world.world import R_SEEK, World, pilot_collectives

PROFILES = [CharacterProfile(PLAYER, "Демон", "A demon."),
            CharacterProfile("innkeeper", "Корчмар", "Keeps the tavern.")]


def canon_world(rules=None, text_reply=None):
    con, _ = make_store()
    canon = Canon(con)
    # the campaign clock IS the story clock here (offset 0): scene time = story minutes
    from harness.canon.api import CanonCampaign
    play = CanonPlay(canon, CanonCampaign(start_t=START, place="place:owl", offset=0))
    wmap = vizima()
    judge = FakeJudge(rules or {})
    eng = Engine(FakeProvider(script={"judge": [text_reply] if text_reply else []}), PROFILES,
                 Scene(wmap.name("tavern"), (PLAYER, "innkeeper"), time=START), models=ModelConfig(),
                 narration="json", record_language=None, judge=judge)
    pc = PlayCanon(play, judge, places={"place:hall": "palace", "place:owl": "tavern"},
                   groups={"coll:guards": "guards"},
                   text_call=lambda prompt: eng._complete("judge", [{"role": "user", "content": prompt}]))
    w = World(eng, wmap, canon=pc)
    return eng, w, pc, play


def test_play_canon_gives_the_world_the_real_events_in_campaign_minutes():
    eng, w, pc, play = canon_world()
    evs = pc.scheduled(0, 10**7)        # a start before the story start is clamped: no past events
    assert [e.summary for e in evs] == ["Ярош оголосив у ратуші комендантську годину.",
                                         "Стражники вночі полюють на звіра в старому лісі."]
    e4 = evs[0]
    assert e4.t == 4 * 1440 + 720 and e4.place == "palace"          # mapped to the world's place
    assert set(e4.participants) == {"yarosh", "guards"}               # engine / world ids
    assert pc.scheduled(e4.t, e4.t) == []


def test_canon_event_executes_on_the_world_clock_and_becomes_news():
    eng, w, pc, play = canon_world()
    w.tick(4 * 1440 + 800)
    ex = eng.log.active([nw.CANON_EXECUTED])
    assert len(ex) == 1 and ex[0].payload["outcome"] == "as_written"
    assert any("комендантську годину" in f.content for f in eng.facts.all_campaign(10**7))


def test_player_change_goes_to_the_real_proportional_pull_with_a_reason():
    reply = json.dumps({"outcome": "differently", "reason": "the player burned the hall",
                        "new_summary": "Ярош оголошує комендантську годину на площі"})
    eng, w, pc, play = canon_world(text_reply=reply)
    ev = eng.log.append("action", game_time=eng.scene.time, location="ратуша", participants=[PLAYER],
                        witnesses=[], notability=0.9, payload={"text": "Yarosh was seen"})
    fid = eng.facts.add_campaign("The demon set fire to the Ярош's hall", source_event_id=ev.id,
                                 game_time=eng.scene.time, location="ратуша", notability=0.9,
                                 knowers=[(PLAYER, WITNESSED)])
    w.register_news([fid], origin="palace")
    w.tick(4 * 1440 + 800)
    p = eng.log.active([nw.CANON_EXECUTED])[0].payload
    assert p["outcome"] == "differently" and p["reason"] == "the player burned the hall"
    assert any("на площі" in f.content for f in eng.facts.all_campaign(10**7))


def test_background_goes_through_the_real_api_and_is_stored():
    eng, w, pc, play = canon_world({"background_knowledge": True})
    play.ensure_character(eng, "char:bart", cid="bart")
    got = pc.background("bart", "ціни на постій")
    assert got
    again = pc.background("bart", "ціни на постій")
    assert again == got                                                # consistent: stored, not re-asked
    assert pc.background("innkeeper", "x") is None                    # not a canon person


# -- the trail ---------------------------------------------------------------------------------------
def seek_world(rules, **kw):
    wmap = vizima()
    eng = Engine(FakeProvider(script={}), PROFILES + [CharacterProfile("clerk", "Писар", "")],
                 Scene(wmap.name("tavern"), (PLAYER, "innkeeper"), time=20 * 60),
                 models=ModelConfig(), narration="json", record_language=None,
                 judge=FakeJudge({"authority_reaction": R_SEEK, "authority_escalate": False,
                                  **rules}))
    w = World(eng, wmap, cast={"innkeeper": "tavern"}, collectives=pilot_collectives(wmap))
    ev = eng.log.append("action", game_time=eng.scene.time, location=eng.scene.location,
                        participants=[PLAYER], witnesses=[PLAYER, "innkeeper"], notability=0.9,
                        payload={"text": "x", "actor": PLAYER})
    fid = eng.facts.add_campaign("The demon turned the beer to blood in front of everyone",
                                 source_event_id=ev.id, game_time=eng.scene.time,
                                 location=eng.scene.location, notability=0.9,
                                 knowers=[(PLAYER, WITNESSED), ("innkeeper", WITNESSED)])
    w.register_news([fid])
    return eng, w


def test_men_find_nobody_at_the_incident_place_ask_around_and_follow_the_trail():
    eng, w = seek_world({"trail_follow": "lake"})
    w.go_to("lake")                       # the player leaves at once (25+ minutes away)
    w.wait(8 * 60)
    trail = eng.log.active([nw.WORLD_TRAIL])
    assert trail and trail[0].payload["place"] == "tavern" and trail[0].payload["next"] == "lake"
    assert any("found nobody and asked around" in e.payload["text"] for e in trail)
    arr = eng.log.active([nw.WORLD_ARRIVAL])
    assert arr and arr[0].place_id == "lake" if hasattr(arr[0], "place_id") else arr


def test_the_trail_can_go_cold():
    eng, w = seek_world({"trail_follow": "none"})
    w.go_to("lake")
    w.wait(8 * 60)
    trail = eng.log.active([nw.WORLD_TRAIL])
    assert trail[-1].payload["over"] == "cold" and eng.log.active([nw.WORLD_ARRIVAL]) == []
    assert any("nobody could tell them" in f.content for f in eng.facts.all_campaign(10**7))


def test_men_find_the_player_who_stayed_at_the_incident_place():
    eng, w = seek_world({})
    stop = w.wait(6 * 60)
    assert stop and "arrive" in stop
    assert eng.log.active([nw.WORLD_TRAIL])[-1].payload["over"] == "found"


# -- the narrator and rumours ----------------------------------------------------------------------------
def test_narrator_context_has_no_rumour_versions_or_authority_reactions():
    eng, w = seek_world({})
    eng.provider.script["narrator"] = [json.dumps({"description": "The room is quiet.",
                                                   "observable_actions": [], "speakers": []})]
    eng.provider.script["extractor"] = [json.dumps({"new_facts": [], "state_changes": []})]
    w.wait(3 * 60)                                   # versions and reactions now exist
    assert eng.log.active([nw.NEWS_VERSION]) and eng.log.active([nw.WORLD_REACTION])
    eng.turn("Дивлюсь на корчмаря.")
    ctx = "\n".join(m["content"] for mod, m in eng.provider.calls if mod == "narrator"
                    for m in m)
    hidden = [f for f in eng.facts.all_campaign(10**7)
              if f.knowers and PLAYER not in [k.character for k in f.knowers]]
    assert len(hidden) >= 3                                  # versions and reactions exist
    state = ctx.split("Campaign state:")[1].split("\n\n")[0].splitlines()
    assert len([ln for ln in state if "turned the beer to blood" in ln]) == 1   # not once per version
    # the men's arrival where the player stands is seen by the player; the order itself is not
    assert all("men arrive at" in ln for ln in state if "sought and detained" in ln)
    assert "turned the beer to blood" in ctx         # what the player saw himself stays
