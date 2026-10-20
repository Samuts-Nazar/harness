"""Task 16: canon in play. A campaign that starts at a canon moment, background knowledge from a life,
scheduled canon events, proportional pull, the drift check, and the retrieval bar. Fake providers only."""
import json

import pytest
from canon_fixture import START, make_store

from harness.canon import api
from harness.canon.embed import HashEmbedder
from harness.canon.play import CanonGuard, CanonPlay, judge_event, knowledge_as_of, scheduled_events, what_knows
from harness.canon.retrieve import Canon
from harness.judge import FakeJudge
from harness.knowledge import BACKGROUND, items_for
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from conftest import diff, narr


@pytest.fixture()
def canon():
    con, ids = make_store()
    c = Canon(con)
    c.ids = ids
    return c


def engine(script=None, judge=None):
    prof = [CharacterProfile(PLAYER, "Рагнар", "Мандрівник.")]
    return Engine(FakeProvider(script=script or {}), prof, Scene("корчма", (PLAYER,), time=0), models=ModelConfig(),
                  judge=judge, narration="json", record_language=None)


# ---- scheduled events --------------------------------------------------------------------------
def test_scheduled_events_are_the_story_after_the_start(canon):
    evs = scheduled_events(canon, START)
    assert [e.summary for e in evs] == ["Ярош оголосив у ратуші комендантську годину.",
                                         "Стражники вночі полюють на звіра в старому лісі."]
    e4 = evs[0]
    assert e4.day == 4 and e4.place == "place:hall" and e4.place_name == "ратуша"
    assert set(e4.participants) == {"char:yarosh", "coll:guards"}
    assert {(k.entity, k.channel, k.source) for k in e4.knowers} == {
        ("char:yarosh", "witnessed", None), ("coll:guards", "heard", "char:yarosh")}
    assert e4.notability == 0.7
    assert [e.id for e in scheduled_events(canon, START, until_t=5 * 1440)] == [e4.id]
    assert scheduled_events(canon, 10 ** 7) == []
    assert api.scheduled_events(canon, START)[0].id == e4.id   # the contract wrapper


def test_campaign_clock_maps_story_time(canon):
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    assert play.start.start_t == START and play.start.to_campaign_t(START + 90) == 90
    up = play.upcoming(0)
    assert [e.day for e in up] == [4, 6]
    assert play.start.to_campaign_t(up[0].t) == 4 * 1440 + 720 - START


# ---- a campaign that starts in the canon -------------------------------------------------------
def test_npcs_from_canon_carry_what_they_knew_at_the_start(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    ids = play.install(eng, ["char:bart", "char:mirko", "char:yarosh"])
    assert ids == ["bart", "mirko", "yarosh"]
    bart = what_knows(eng, "bart")
    texts = {k["text"]: k for k in bart}
    assert len(bart) == 2                                   # e1, e2: not the elder's bribe, not the curfew
    e2 = next(v for t, v in texts.items() if "miller" in t)
    assert e2["how"] == "heard" and e2["source"] == "стражники"
    assert all(k["t"] < 0 for k in bart), "the world's past sits before the campaign clock starts"
    assert {k["text"] for k in what_knows(eng, "yarosh")} == {"Ярош bribes the captain of the guard to hide a debt."}
    # the player character knows none of it
    assert what_knows(eng, PLAYER) == []


def test_names_known_to_each_other_per_canon(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    play.install(eng, ["char:bart", "char:mirko", "char:yarosh"])
    n = eng.names
    assert eng.profiles["yarosh"].appearance == "староста"   # a named person is hidden until introduced
    assert n.knows("bart", "mirko") and n.knows("mirko", "bart")   # they met in e1
    assert not n.knows("bart", "yarosh")                     # never in an event together
    assert not n.knows(PLAYER, "yarosh")


def test_group_knowledge_is_inherited_by_a_person_made_from_the_group(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    play.ensure_character(eng, "char:captain", cid="guard")
    assert {k["text"] for k in what_knows(eng, "guard")} == {
        "A miller was found dead in the forest; the guards tell Барт.",
        "Ярош bribes the captain of the guard to hide a debt."}


# ---- background knowledge from a life -----------------------------------------------------------
def test_background_is_judged_once_stored_and_marked_own_life(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    play.ensure_character(eng, "char:bart")
    judge = FakeJudge({"background_knowledge": True})
    b = play.know_from_life(eng, "char:bart", "ціни на ель у корчмах", judge)
    assert b is not None and b.source == "own life"
    asked = len(judge.asked)
    again = play.know_from_life(eng, "char:bart", "ціни на ель", judge)   # same topic, other words
    assert again is not None and len(judge.asked) == asked, "consistent: not asked twice"
    items = [i for i in items_for(eng, "bart") if i.kind == BACKGROUND and "ель" in i.text]
    assert items and items[0].how == "background"
    ctx = eng.ctx.knowledge_lines(eng.deriver.derive("bart", eng.scene.time))
    assert any("(from your own life)" in line for line in ctx)


def test_background_no_is_remembered_too(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    play.ensure_character(eng, "char:bart")
    judge = FakeJudge({"background_knowledge": False})
    assert play.know_from_life(eng, "char:bart", "риби Темерії", judge) is None
    n = len(judge.asked)
    assert play.know_from_life(eng, "char:bart", "риби Темерії", FakeJudge({"background_knowledge": True})) is None
    assert n == 1


def test_canon_secrets_never_come_through_background(canon):
    judge = FakeJudge({"background_knowledge": True, "canon_relevance": True})
    assert canon.secrets_about("char:bart", "Ярош підкупив капітана", START)        # a secret Bart does not know
    assert api.background(canon, "char:bart", "Ярош підкупив капітана", judge=judge, as_of=START) is None
    assert all(q.tag != "background_knowledge" for _, qs in judge.asked for q in qs.values()), "never asked whether he knows it"
    # a near-but-different record does not block an ordinary question
    assert api.background(canon, "char:bart", "Ярош підкупив капітана", judge=FakeJudge({"background_knowledge": True}), as_of=START) is not None
    assert api.background(canon, "char:bart", "ціни на ель", judge=judge, as_of=START) is not None


# ---- proportional pull ---------------------------------------------------------------------------
def test_unchanged_event_happens_without_a_judgment(canon):
    ev = scheduled_events(canon, START)[0]

    def boom(prompt):
        raise AssertionError("no call when nothing changed")
    v = judge_event(canon, ev, [], judge=boom, at_t=0)
    assert v.outcome == "happens"


def test_changed_event_is_rejudged_once_with_a_reason(canon):
    eng = engine()
    play = CanonPlay.at(canon, 3, 19, "place:owl")
    ev = play.upcoming()[0]
    eng.facts.add_campaign("Рагнар вбив старосту Ярош у корчмі.", source_event_id=eng.log.append(
        "scripted", game_time=0, location="x", payload={}).id, game_time=0, location="корчма", notability=0.9,
        knowers=[(PLAYER, "witnessed")])
    calls = []

    def llm(prompt):
        calls.append(prompt)
        return json.dumps({"outcome": "does_not_happen", "reason": "The elder is dead.", "new_summary": ""})
    v = play.rejudge(eng, ev, llm)
    assert v.outcome == "does_not_happen" and "dead" in v.reason
    assert "Ярош" in calls[0] and "proportional" in calls[0]
    assert play.rejudge(eng, ev, llm).outcome == "does_not_happen" and len(calls) == 1, "stored with its reason"
    play2_v = play.verdict(eng, ev.id)
    assert play2_v is not None and play2_v.reason == "The elder is dead."
    # a rollback of the log event removes the verdict with the facts it came from
    verdict_event = [e for e in eng.log.active(["scripted"]) if e.payload.get("canon_verdict")][0]
    eng.log.rollback(verdict_event.id)
    assert play.verdict(eng, ev.id) is None


def test_garbled_verdict_leaves_the_event_standing(canon):
    ev = scheduled_events(canon, START)[0]
    v = judge_event(canon, ev, ["something"], judge=lambda p: "I think maybe", at_t=0)
    assert v.outcome == "happens"
    v2 = judge_event(canon, ev, ["x"], judge=lambda p: '{"outcome": "differently", "reason": "r", "new_summary": "Він мовчить."}', at_t=0)
    assert v2.outcome == "differently" and v2.new_summary == "Він мовчить."


# ---- drift check ----------------------------------------------------------------------------------
def test_guard_no_canon_hit_means_no_judgment(canon):
    judge = FakeJudge({"canon_drift": True})
    g = CanonGuard(canon, judge)
    assert g.check("Світить місяць, пахне димом.", "narration") is None
    assert judge.asked == []


def test_guard_rejects_contradiction_and_accepts_justified_drift(canon):
    text = "Мірошника знайшли живим у лісі."
    j1 = FakeJudge({"canon_drift": True, "canon_drift_justified": False})
    g1 = CanonGuard(canon, j1)
    why = g1.check(text, "narration")
    assert why and why.startswith("contradicts canon") and g1.rejected
    j2 = FakeJudge({"canon_drift": True, "canon_drift_justified": True})
    g2 = CanonGuard(canon, j2)
    assert g2.check(text, "npc_line", "bart") is None and g2.drift[0]["speaker"] == "bart"
    j3 = FakeJudge({"canon_drift": False})
    assert CanonGuard(canon, j3).check(text, "narration") is None
    assert [q.tag for _, qs in j3.asked for q in qs.values()] == ["canon_drift"]


def test_engine_regenerates_narration_that_contradicts_canon(canon):
    class Stub:
        def __init__(self):
            self.calls = []

        def refresh(self, eng):
            pass

        def check(self, text, kind, speaker=None):
            self.calls.append(text)
            return "contradicts canon: x" if "живим" in text else None

    script = {"narrator": [narr("Мірошника знайшли живим."), narr("Мірошника знайшли мертвим.")],
              "npc": [], "extractor": [diff()]}
    eng = engine(script)
    eng.canon_guard = Stub()
    res = eng.turn("оглядаюсь")
    assert res.narration == "Мірошника знайшли мертвим."
    assert "canon_drift_rejected" in [n["kind"] for n in eng.devlog]
    assert len(eng.canon_guard.calls) == 2


def test_guard_text_from_a_worker_thread_does_not_break_sqlite(tmp_path):
    from concurrent.futures import ThreadPoolExecutor
    con, _ = make_store(tmp_path / "c.db")
    con.commit()
    con.close()
    canon = Canon(tmp_path / "c.db")
    g = CanonGuard(canon, FakeJudge({"canon_drift": False}))
    with ThreadPoolExecutor(2) as ex:
        out = list(ex.map(lambda t: g.check(t, "npc_line", "bart"), ["Мірошника знайшли живим.", "Ярош оголосив годину."]))
    assert out == [None, None]


# ---- retrieval: isolation and the relevance bar ------------------------------------------------------
def test_recall_isolation_and_cutoff(canon):
    assert canon.recall("char:bart", "мірошник у лісі", START)["events"]
    assert canon.recall("char:bart", "підкуп капітана", START)["events"] == [], "the bribe stayed with two people"
    assert canon.recall("char:yarosh", "підкуп капітана", START)["events"]
    assert canon.recall("char:bart", "яка погода в Новіграді і скільки коштує хліб", START)["events"] == []
    assert canon.recall("char:bart", "мірошник", 0)["events"] == [], "not learned yet at time 0"


def test_verifier_can_drop_events_that_only_share_names(canon):
    judge = FakeJudge({"canon_relevance": False})
    assert canon.recall("char:bart", "мірошник у лісі", START, verify=judge)["events"] == []
    assert FakeJudge({"canon_relevance": True}) and canon.recall(
        "char:bart", "мірошник у лісі", START, verify=FakeJudge({"canon_relevance": True}))["events"]


def test_persons_resolve_before_collectives(canon):
    ments = canon._mentioned("що староста сказав стражникам про Барта")
    assert ments.index("char:yarosh") < ments.index("coll:guards")


def test_semantic_signal_with_a_fake_embedder(canon):
    emb = HashEmbedder()
    from harness.canon.embed import pack
    for eid, txt in [(r["id"], r["gist_uk"] + " " + r["body"]) for r in canon.con.execute(
            "SELECT r.id, r.body, c.gist_uk FROM record r JOIN canon_event c ON c.id=r.id")]:
        canon.con.execute("INSERT OR REPLACE INTO canon_embedding VALUES (?,?,?,?)", (eid, emb.model, emb.dim, pack(emb.embed([txt])[0])))
    c = Canon(canon.con, emb)
    hit = c.recall("char:bart", "Мірошника знайшли мертвим у лісі, стражники розповіли Барту.", START)
    assert hit["events"] and "miller" in hit["events"][0]["what_en"]
    assert c.recall("char:bart", "Ярош підкупив капітана, щоб приховати борг", START)["events"] == []
