"""Output/record language settings and saved (file-backed) campaigns."""
import sqlite3

import pytest

from harness import settings
from harness.db import connect
from harness.models import EQUIPMENT, PLAYER, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.state import StateChange
from conftest import PROFILES, change, diff, fact, make_engine, narr


# -- language ----------------------------------------------------------------------------------
def prompts(eng, prov):
    eng.turn("hi", speakers=["innkeeper"])
    by = {m: msgs for m, msgs in prov.calls}
    return {k: "\n".join(x["content"] for x in v) for k, v in by.items()}


def script():
    return {"narrator": ["N."], "npc": ["Hello."], "extractor": [diff()]}


def test_default_output_language_is_ukrainian_in_narrator_and_npc_prompts():
    assert settings.DEFAULT_OUTPUT_LANGUAGE == "Ukrainian"
    p = prompts(*make_engine(script()))
    assert "Speak in Ukrainian." in p["npc"]
    assert "description and the observable actions in Ukrainian" in p["narrator"]


def test_output_language_is_one_setting():
    p = prompts(*make_engine(script(), output_language="German"))
    assert "Speak in German." in p["npc"] and "in German" in p["narrator"]
    p = prompts(*make_engine(script(), output_language=None))
    assert "Speak in" not in p["npc"] and "Ukrainian" not in p["narrator"]


def test_records_and_judgment_questions_are_untouched_by_default():
    eng, prov = make_engine(script())
    p = prompts(eng, prov)
    assert "Ukrainian" not in p["extractor"]  # record language: the extractor's own choice
    for state, qs in eng.judge.inner.asked if hasattr(eng.judge.inner, "asked") else []:
        assert "Ukrainian" not in " ".join(state) + " ".join(q.text for q in qs.values())


def test_record_language_can_be_switched_in_one_place():
    p = prompts(*make_engine(script(), record_language="English"))
    assert "content and every item in English" in p["extractor"]


# -- campaigns ---------------------------------------------------------------------------------
def new_campaign(tmp_path, script, **kw):
    prov = FakeProvider(script=script)
    scene = Scene("Inn", (PLAYER, "innkeeper"), time=18 * 60, outside=("bard",))
    return Engine.create_campaign("t1", prov, PROFILES, scene, root=tmp_path,
                                  models=ModelConfig(), **kw), prov


def test_campaign_files_use_wal_and_foreign_keys(tmp_path):
    eng, _ = new_campaign(tmp_path, {})
    d = tmp_path / "t1"
    assert (d / "campaign.db").exists()
    assert eng.conn.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    assert eng.conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    eng.close()


def test_in_memory_stays_the_default():
    eng, _ = make_engine({})
    assert eng.campaign_dir is None
    assert eng.conn.execute("PRAGMA journal_mode").fetchone()[0] == "memory"


def test_campaign_survives_a_restart_and_continues(tmp_path):
    eng, _ = new_campaign(tmp_path, {
        "narrator": [narr("The fire pops.", ["Geralt draws a sword"], ["innkeeper"])],
        "npc": ["Welcome."],
        "extractor": [diff(fact("The innkeeper welcomed Geralt", "innkeeper", 0.5),
                           changes=(change(PLAYER, EQUIPMENT, "add", "a sword", "action1"),))]},
        output_language="German")
    eng.facts.add_canon("Witchers hunt monsters.", knowers=[("innkeeper", "told")])
    eng.enter_scene("bard")
    eng.turn("I walk in.", speakers=["innkeeper"])
    before = {
        "events": [(e.id, e.type, e.payload) for e in eng.log.active()],
        "facts": [f.content for f in eng.facts.all_campaign(10**9)],
        "state": eng.live.snapshot(),
        "scene": (eng.scene.location, eng.scene.present, eng.scene.outside, eng.scene.time),
    }
    eng.close()

    prov2 = FakeProvider(script={"narrator": [narr("Rain.", [], ["bard"])], "npc": ["Hm."],
                                 "extractor": [diff()]})
    eng2 = Engine.open_campaign("t1", prov2, root=tmp_path, models=ModelConfig())
    assert [(e.id, e.type, e.payload) for e in eng2.log.active()] == before["events"]
    assert [f.content for f in eng2.facts.all_campaign(10**9)] == before["facts"]
    assert eng2.live.snapshot() == before["state"]
    assert (eng2.scene.location, eng2.scene.present, eng2.scene.outside,
            eng2.scene.time) == before["scene"]
    assert eng2.output_language == "German"  # stored settings come back
    assert eng2.agents.agents() and "innkeeper" in eng2.agents.agents()  # promotion is in the log
    assert [i.fact.content for i in eng2.deriver.derive("innkeeper", eng2.scene.time).knows]
    r = eng2.turn("And now?", speakers=["bard"])
    assert r.utterances[0].payload["speaker"] == "bard"
    assert len(eng2.log.active()) > len(before["events"])
    assert (tmp_path / "t1" / "memory").exists()
    eng2.close()


def test_rollback_still_works_after_reopening(tmp_path):
    eng, _ = new_campaign(tmp_path, {"narrator": [narr("N.")], "npc": ["Hi."],
                                     "extractor": [diff(fact("A fact", "innkeeper"))]})
    res = eng.turn("hi", speakers=["innkeeper"])
    eng.close()
    eng2 = Engine.open_campaign("t1", FakeProvider(), root=tmp_path)
    eng2.rollback(res.utterances[0].id)
    assert eng2.facts.all_campaign(10**9) == []
    eng2.close()


def test_a_failed_turn_leaves_the_saved_campaign_consistent(tmp_path):
    eng, _ = new_campaign(tmp_path, {"narrator": [narr("N.")], "npc": ["Hi."], "extractor": ["junk", "junk"]})
    with pytest.raises(Exception):
        eng.turn("hi", speakers=["innkeeper"])
    eng.close()
    eng2 = Engine.open_campaign("t1", FakeProvider(), root=tmp_path)
    assert eng2.log.active(["utterance"]) == [] and eng2.scene.time == 18 * 60
    eng2.close()


def test_create_refuses_an_existing_campaign_and_open_a_missing_one(tmp_path):
    eng, _ = new_campaign(tmp_path, {})
    eng.close()
    with pytest.raises(FileExistsError):
        new_campaign(tmp_path, {})
    with pytest.raises(FileNotFoundError):
        Engine.open_campaign("nope", FakeProvider(), root=tmp_path)
    assert Engine.campaign_exists("t1", tmp_path) and not Engine.campaign_exists("nope", tmp_path)
    for bad in ("../x", "a/b", "", ".."):
        with pytest.raises(ValueError):
            Engine.campaign_path(bad, tmp_path)


def test_connect_sets_pragmas_only_for_files(tmp_path):
    c = connect(str(tmp_path / "x.db"))
    assert c.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    c2 = connect()
    assert c2.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        c2.execute("INSERT INTO fact_knowers (fact_id, character, how, learned_at) "
                   "VALUES (999, 'x', 'told', 0)")
