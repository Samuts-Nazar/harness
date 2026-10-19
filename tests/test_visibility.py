import pytest

from harness.db import connect
from harness.eventlog import EventLog
from harness.facts import FactStore
from harness.models import PLAYER, Scene
from harness.pipeline import Engine
from harness.providers import FakeProvider
from conftest import PROFILES, diff, fact, make_engine


def test_visible_to_filters_by_character_and_time():
    conn = connect()
    log, facts = EventLog(conn), FactStore(conn)
    ev = log.append("narration", game_time=10, location="Inn")
    facts.add_campaign(
        "secret", source_event_id=ev.id, game_time=10, location="Inn",
        notability=0.5, knowers=[("a", "witnessed")],
    )
    assert [f.content for f in facts.visible_to("a", 10)] == ["secret"]
    assert facts.visible_to("b", 10) == []
    assert facts.visible_to("a", 9) == []  # not yet learned


def test_canon_is_immutable_and_campaign_needs_source():
    conn = connect()
    facts = FactStore(conn)
    fid = facts.add_canon("Kaer Morhen is a keep.", knowers=[("a", "told")])
    with pytest.raises(Exception):
        conn.execute("UPDATE facts SET content='x' WHERE id=?", (fid,))
    with pytest.raises(Exception):
        conn.execute("DELETE FROM facts WHERE id=?", (fid,))
    with pytest.raises(Exception):
        conn.execute(
            "INSERT INTO facts (store, content, source_event_id, game_time, location, notability)"
            " VALUES ('campaign','x',NULL,0,'',0.1)"
        )


def test_events_are_append_only():
    conn = connect()
    log = EventLog(conn)
    e = log.append("narration", game_time=0, location="Inn")
    with pytest.raises(Exception):
        conn.execute("UPDATE events SET type='x' WHERE id=?", (e.id,))
    with pytest.raises(Exception):
        conn.execute("DELETE FROM events WHERE id=?", (e.id,))


def test_no_leak_across_characters_in_prompts():
    secret = "The innkeeper hides a dagger under the counter"
    script = {
        "narrator": ["Night falls.", "The bard hums."],
        "npc": ["I hide a dagger under the counter.", "Hello again."],
        "extractor": [
            diff(fact(secret, "innkeeper")),
            diff(),
        ],
    }
    # the bard is not in the room when the innkeeper says it
    eng, prov = make_engine(script, present=(PLAYER, "innkeeper"))
    eng.turn("I enter", speakers=["innkeeper"])
    eng.enter_scene("bard")
    eng.turn("I greet the bard", speakers=["bard"])
    bard_prompts = [
        m["content"] for model, msgs in prov.calls if model == "npc" for m in msgs
    ][2:]  # the bard's call comes after the innkeeper's
    assert bard_prompts and all("dagger" not in p for p in bard_prompts)
    assert "dagger" in " ".join(m["content"] for m in eng.ctx.character("innkeeper", eng.scene))
    assert "dagger" not in " ".join(m["content"] for m in eng.ctx.character("bard", eng.scene))
    # unknown facts are never annotated as unknown
    for p in bard_prompts:
        assert "do not know" not in p.lower() and "secret" not in p.lower()


def test_narrator_sees_everything():
    script = {
        "narrator": ["Night falls.", "Next."],
        "npc": ["Welcome."],
        "extractor": [diff(fact("Hidden dagger", "narration")), diff()],
    }
    eng, prov = make_engine(script)
    eng.turn("I enter", speakers=["innkeeper"])
    eng.turn("I wait")
    narr = [m["content"] for model, msgs in prov.calls if model == "narrator" for m in msgs][-1]
    assert "Hidden dagger" in narr
    # scene description is narrator-only knowledge: no character perceived it
    assert eng.facts.visible_to("innkeeper", eng.scene.time) == []


def test_npc_does_not_see_narration_or_other_secrets_in_history():
    script = {
        "narrator": ["Secret narration text."],
        "npc": ["Hi."],
        "extractor": [diff()],
    }
    eng, prov = make_engine(script)
    eng.turn("hello", speakers=["innkeeper"])
    prompt = prov.calls[1][1][1]["content"]
    assert "Secret narration" not in prompt
