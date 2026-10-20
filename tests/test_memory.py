from harness.belief import NEUTRAL
from harness.judge import FakeJudge
from harness.models import EQUIPMENT, PLAYER
from harness.state import StateChange
from conftest import change, diff, fact, make_engine, narr


def read(eng, name):
    return (eng.campaign_dir / "memory" / "characters" / f"{name}.md").read_text()


def script_one_turn():
    return {
        "narrator": [narr("N.", ["Geralt draws his sword"])],
        "npc": ["Something howled by the old mill."],
        "extractor": [diff(
            fact("Something howled by the old mill", "innkeeper", 0.8),
            fact("Geralt drew a sword", "action1"),
            changes=[change("player", "equipment", "add", "silver sword", "action1",
                            observable=False)])],
    }


def test_files_are_written_after_a_committed_turn(tmp_path):
    judge = FakeJudge({"attitude_direction": "negative", "relationship_magnitude": 2})
    eng, _ = make_engine(script_one_turn(), campaign_dir=tmp_path / "camp", judge=judge)
    eng.turn("What happened?", speakers=["innkeeper"])
    mem = tmp_path / "camp" / "memory"
    assert {p.name for p in (mem / "characters").glob("*.md")} == {
        "player.md", "innkeeper.md", "bard.md", "spy.md"}
    bard = read(eng, "bard")
    # knowledge with its source and the event it came from, plus wikilinks
    assert "Something howled by the old mill (told by [[innkeeper|Innkeeper]]" in bard
    assert "[[event-" in bard and "[[place-inn]]" in bard and f"belief {NEUTRAL:.2f}" in bard
    assert "Geralt drew a sword (perceived directly" in bard
    # first-hand for the speaker, hidden live state for the owner only
    inn = read(eng, "innkeeper")
    assert "Something howled by the old mill (perceived directly" in inn
    assert "equipment: silver sword (hidden)" in read(eng, "player")
    assert "silver sword" not in bard
    # attitudes point at the facts they are about
    assert "toward [[innkeeper#^fact-1]]: negative (2)" in inn
    assert "^fact-1" in inn
    # event and place notes exist for the links
    assert list((mem / "events").glob("event-*.md")) and (mem / "places" / "place-inn.md").exists()


def test_pending_intents_are_in_the_file_and_files_regenerate_after_rollback(tmp_path):
    from harness.streaming import InterruptHandle
    eng, _ = make_engine(script_one_turn(), campaign_dir=tmp_path / "camp")
    h, n = InterruptHandle(), [0]

    def cut(npc, w):
        n[0] += 1
        if n[0] == 2:
            h.request()

    res = eng.turn("What happened?", speakers=["innkeeper"], handle=h, on_word=cut)
    assert res.interrupted
    inn = read(eng, "innkeeper")
    assert '"by the old mill."' in inn  # the unsaid remainder is a pending intent
    assert "interrupted" in read(eng, "bard")


def test_memory_files_regenerate_after_rollback(tmp_path):
    eng, _ = make_engine(script_one_turn(), campaign_dir=tmp_path / "camp")
    res = eng.turn("What happened?", speakers=["innkeeper"])
    assert "old mill" in read(eng, "bard") and "silver sword" in read(eng, "player")
    before_events = {p.name for p in (tmp_path / "camp" / "memory" / "events").glob("*.md")}
    assert before_events
    eng.rollback(res.utterances[0].id)
    # the utterance and the fact it carried are gone from the files
    assert "old mill" not in read(eng, "bard")
    assert "old mill" not in read(eng, "innkeeper")
    assert "toward" not in read(eng, "innkeeper")
    # the sword change came from the narrated action, not the utterance, so it stays
    assert "silver sword" in read(eng, "player")
    eng.rollback(eng.log.active(["action"])[0].id)
    assert "silver sword" not in read(eng, "player")
    after_events = {p.name for p in (tmp_path / "camp" / "memory" / "events").glob("*.md")}
    assert after_events < before_events
    # rolling back the action as well removes what it carried
    assert "Geralt drew a sword" not in read(eng, "bard")
    # the log itself is still append-only: the event is still there
    assert eng.log.get(res.utterances[0].id)


def test_files_regenerate_after_retroactive_interrupt_and_failed_turn(tmp_path):
    script = {"narrator": ["N.", "N."], "npc": ["I saw the stranger near the well and he carried a black sword"],
              "extractor": [diff(fact("Stranger with black sword near well", "innkeeper")),
                            diff(fact("Innkeeper saw a stranger", "innkeeper"))]}
    eng, _ = make_engine(script, campaign_dir=tmp_path / "camp")
    eng.turn("hello", speakers=["innkeeper"])
    assert "black sword" in read(eng, "bard")
    eng.interrupt_retroactive(4)
    bard = read(eng, "bard")
    assert "black sword" not in bard and "interrupted" in bard
    # a turn that fails also leaves the files consistent with the log
    import pytest
    from harness.pipeline import ExtractionRejected
    bad_eng, _ = make_engine({"narrator": ["N."], "npc": ["Hi."], "extractor": ["x", "y"]},
                             campaign_dir=tmp_path / "camp2")
    with pytest.raises(ExtractionRejected):
        bad_eng.turn("hello", speakers=["innkeeper"])
    assert "Hi." not in read(bad_eng, "innkeeper")


def test_npc_context_comes_from_the_same_derivation(tmp_path):
    eng, _ = make_engine(script_one_turn(), campaign_dir=tmp_path / "camp")
    eng.turn("What happened?", speakers=["innkeeper"])
    mem = eng.deriver.derive("bard", eng.scene.time)
    ctx = " ".join(m["content"] for m in eng.ctx.character("bard", eng.scene, mem))
    for it in mem.knows:
        assert it.fact.content in ctx
    # and the file lists exactly the same facts
    assert read(eng, "bard").count("^fact-") == len(mem.knows)


def test_belief_is_a_swappable_slot(tmp_path):
    seen = []

    def my_belief(character, fact_, knower):
        seen.append((character, fact_.content, knower.source))
        return 0.9 if knower.source else 1.0

    eng, _ = make_engine(script_one_turn(), campaign_dir=tmp_path / "camp", belief=my_belief)
    eng.turn("What happened?", speakers=["innkeeper"])
    assert "belief 0.90" in read(eng, "bard") and "belief 1.00" in read(eng, "innkeeper")
    assert ("bard", "Something howled by the old mill", "innkeeper") in seen


def test_nothing_is_written_without_a_campaign_dir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    eng, _ = make_engine(script_one_turn())
    eng.turn("What happened?", speakers=["innkeeper"])
    assert eng.memory is None and list(tmp_path.iterdir()) == []


def test_gitignore_covers_campaign_directory():
    import pathlib
    root = pathlib.Path(__file__).resolve().parents[1]
    assert "/campaigns" in (root / ".gitignore").read_text().split()
