"""Task 19: the evaluation harness. Unit tests on synthetic logs (fake providers); the stored-session
tests are in tests/test_eval_sessions.py (`pytest -m eval`)."""
import json

import pytest

from conftest import PROFILES, change, diff, fact
from harness.evalkit.checks import (
    Labelled, agreement, check_canon_drift, check_isolation, check_metaphor, check_survival,
    names_in,
)
from harness.evalkit.replay import (
    Cassette, RecordingJudge, RecordingProvider, ReplayJudge, ReplayMiss, ReplayProvider,
)
from harness.judge import FakeJudge, yes_no_q
from harness.metaphor import literal_reading
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider


# -- record / replay -----------------------------------------------------------------------------
def test_provider_roundtrip_by_key_and_a_changed_prompt_is_a_miss(tmp_path):
    cas = Cassette(tmp_path / "c.jsonl", {"scenario": "t"})
    rec = RecordingProvider(FakeProvider(script={"m": ["one", "two", "three"]}), cas)
    msgs = [{"role": "user", "content": "hello"}]
    assert [rec.complete("m", msgs), rec.complete("m", msgs), rec.complete("m", [{"role": "user", "content": "x"}])] \
        == ["one", "two", "three"]
    rep = ReplayProvider(tmp_path / "c.jsonl")
    assert rep.complete("m", msgs) == "one" and rep.complete("m", msgs) == "two"   # a queue per key
    with pytest.raises(ReplayMiss):
        rep.complete("m", [{"role": "user", "content": "changed prompt"}])
    lenient = ReplayProvider(tmp_path / "c.jsonl", strict=False)
    assert lenient.complete("m", [{"role": "user", "content": "changed prompt"}]) == "one"
    assert lenient.misses and lenient.misses[0]["used"] == "next in order"


def test_prompts_are_not_stored_unless_asked(tmp_path):
    cas = Cassette(tmp_path / "c.jsonl", {})
    RecordingProvider(FakeProvider(script={"m": ["a"]}), cas).complete(
        "m", [{"role": "user", "content": "SECRET SOURCE TEXT"}])
    assert "SECRET SOURCE TEXT" not in (tmp_path / "c.jsonl").read_text()


def test_judge_roundtrip(tmp_path):
    cas = Cassette(tmp_path / "j.jsonl", {})
    rj = RecordingJudge(FakeJudge({"t": True}), cas)
    q = {"a": yes_no_q("is it?", "t")}
    assert rj.ask(["state"], q)["a"].answer is True
    rep = ReplayJudge(tmp_path / "j.jsonl")
    assert rep.ask(["state"], q)["a"].answer is True
    with pytest.raises(ReplayMiss):
        rep.ask(["other state"], q)


# -- the checks ----------------------------------------------------------------------------------
def make(script, profiles=PROFILES, **kw):
    prov = FakeProvider(script={k: list(v) for k, v in script.items()})
    return Engine(prov, profiles, Scene("Inn", (PLAYER, "innkeeper", "bard"), 0),
                  models=ModelConfig(), judge=FakeJudge({"director_first": "innkeeper"}),
                  record_language=None, **kw)


def test_names_in_finds_capitalised_names_and_skips_openers():
    assert names_in("Так, Фольтест казав. Гм.") == {"фольт"}


def test_isolation_flags_a_name_the_speaker_never_heard():
    eng = make({"narrator": ["N."], "npc": ["Я чув, що Остріт змовився з Велерадом."],
                "extractor": ["none", diff()]})
    eng.facts.add_canon("Остріт plots against the king.", knowers=[("bard", "told")])
    eng.facts.add_canon("Велерад rules the guard.", knowers=[("bard", "told")])
    eng.turn("Що чути?", speakers=["innkeeper"])
    rep = check_isolation(eng)
    assert not rep.ok and any("остр" in f.detail or "велер" in f.detail for f in rep.findings)
    assert rep.stats["npc_lines"] == 1


def test_isolation_passes_when_the_speaker_was_told():
    eng = make({"narrator": ["N."], "npc": ["Я чув, що Остріт змовився."],
                "extractor": ["none", diff()]})
    eng.facts.add_canon("Остріт plots against the king.", knowers=[("innkeeper", "told")])
    eng.turn("Що чути?", speakers=["innkeeper"])
    assert check_isolation(eng).ok


def test_isolation_catches_a_leak_through_an_intent_note():
    eng = make({"narrator": ["N."], "npc": ["Добре."], "extractor": ["none", diff()]})
    eng.facts.add_canon("Остріт plots against the king.", knowers=[("bard", "told")])
    eng.intents.set("innkeeper", "tell the player that Остріт plots", eng.scene)
    rep = check_isolation(eng)
    assert any("intent note" in f.detail for f in rep.findings)


def test_isolation_catches_an_about_note_on_a_fact_the_character_does_not_know():
    eng = make({"narrator": ["N."], "npc": ["Добре."], "extractor": ["none", diff()]})
    ev = eng.log.append("scripted", game_time=0, location="Inn", participants=[], witnesses=[],
                        notability=0.1, payload={"text": "x"})
    eng.facts.add_campaign("Innkeeper went to report (about: the king is dead)", source_event_id=ev.id,
                           game_time=0, location="Inn", notability=0.4,
                           knowers=[("innkeeper", "witnessed", None)])
    rep = check_isolation(eng)
    assert any("does not know" in f.detail for f in rep.findings)


def test_metaphor_guard_drops_a_hand_from_took_his_hand():
    assert literal_reading("inventory", "add", "his hand", "Geralt took his hand.")
    assert literal_reading("inventory", "add", "severed hand", "He cut off the hand.") is None
    assert literal_reading("inventory", "add", "hand", "The mercenary cut off his hand.") is None
    assert literal_reading("inventory", "add", "courage")
    assert literal_reading("injury", "add", "hand")
    assert literal_reading("injury", "add", "cut hand") is None
    assert literal_reading("appearance", "add", "golden eyes") is None
    assert literal_reading("inventory", "add", "iron sword") is None
    assert literal_reading("inventory", "remove", "hand") is None


def test_extractor_output_with_a_literal_metaphor_is_dropped_in_the_turn():
    d = diff(fact("Geralt took the innkeeper's hand", "paction1", 0.3),
             changes=(change("player", "inventory", "add", "the innkeeper's hand", "paction1"),
                      change("player", "inventory", "add", "hand", "paction1"),
                      change("player", "equipment", "add", "steel sword", "paction1")))
    eng = make({"narrator": ["N."], "npc": ["Добре."], "extractor": ["none", d]})
    eng.turn("*Беру корчмаря за руку*", speakers=["innkeeper"])
    items = {e.item for e in eng.live.of(PLAYER)}
    assert "steel sword" in items and "hand" not in items
    assert any(n["kind"] == "state_change_dropped" for n in eng.devlog)


def test_check_metaphor_finds_a_literal_state_change_already_in_the_log():
    eng = make({})
    ev = eng.log.append("utterance", game_time=0, location="Inn", participants=[PLAYER],
                        witnesses=[], notability=0.3, payload={"speaker": PLAYER, "text": "took his hand"})
    eng.log.append("state_change", game_time=0, location="Inn", participants=[PLAYER], witnesses=[],
                   notability=0.3, cause_id=ev.id,
                   payload={"category": "inventory", "op": "add", "item": "his hand",
                            "observable": True, "text": "add his hand"})
    rep = check_metaphor(eng)
    assert len(rep.findings) == 1 and rep.stats["state_changes"] == 1


def _long_session(n, extra_fact=True):
    script = {"narrator": ["N."] * n, "npc": ["Гм."] * n, "extractor": ["none", diff()] * n}
    eng = make(script)
    eng.facts.add_canon("x", knowers=[("bard", "told")])
    for i in range(n):
        eng.turn(f"Хід {i}", speakers=["innkeeper"])
    return eng


def test_survival_structural_a_promise_is_still_in_memory_after_twenty_turns():
    d0 = diff(fact("The innkeeper promised to keep the room until morning", "innkeeper", 0.5))
    script = {"narrator": ["N."] * 22, "npc": ["Обіцяю."] + ["Гм."] * 21,
              "extractor": ["none", d0] + ["none", diff()] * 21}
    eng = make(script)
    for i in range(22):
        eng.turn(f"Хід {i}", speakers=["innkeeper"])
    rep = check_survival(eng, min_gap=20)
    assert rep.ok and rep.stats["facts_checked"] >= 1 and rep.stats["turns"] == 22


def test_survival_reports_a_fact_lost_from_memory():
    d0 = diff(fact("The innkeeper promised to keep the room until morning", "innkeeper", 0.5))
    script = {"narrator": ["N."] * 3, "npc": ["Обіцяю."] + ["Гм."] * 2,
              "extractor": ["none", d0] + ["none", diff()] * 2}
    eng = make(script)
    for i in range(3):
        eng.turn(f"Хід {i}", speakers=["innkeeper"])
    from harness.memory import MemoryDeriver
    real = MemoryDeriver.derive

    def forgetful(self, character, at_time):
        mem = real(self, character, at_time)
        mem.knows = []
        return mem
    MemoryDeriver.derive = forgetful
    try:
        rep = check_survival(eng, min_gap=1)
    finally:
        MemoryDeriver.derive = real
    assert not rep.ok and "no longer in" in rep.findings[0].detail


def test_survival_judged_contradiction_uses_the_record_as_reference():
    d0 = diff(fact("The innkeeper promised to keep the room until morning", "innkeeper", 0.5))
    script = {"narrator": ["N."] * 3, "npc": ["Обіцяю."] + ["Кімнати немає, йди геть."] * 2,
              "extractor": ["none", d0] + ["none", diff()] * 2}
    eng = make(script)
    for i in range(3):
        eng.turn(f"Хід {i}", speakers=["innkeeper"])
    rep = check_survival(eng, min_gap=1, judge=FakeJudge({"commitment_contradiction": True}), sample=3)
    assert rep.stats["judged_pairs"] >= 1
    assert any("contradicts the record" in f.detail for f in rep.findings)


def test_canon_drift_check_reports_what_the_guard_rejects():
    eng = make({"narrator": ["Фольтест мертвий."], "npc": ["Гм."], "extractor": ["none", diff()]})
    eng.turn("Що?", speakers=["innkeeper"])

    class Guard:
        drift: list = []

        def check(self, text, kind, speaker=None):
            return "contradicts canon: Foltest lives" if "мертвий" in text else None

    rep = check_canon_drift(eng, Guard())
    assert len(rep.findings) == 1 and rep.stats["texts"] >= 2


def test_agreement_with_reference_answers():
    items = [Labelled("a", "ctx", "q?", True), Labelled("b", "ctx", "q?", False),
             Labelled("c", "ctx", "q?", True)]
    r = agreement(FakeJudge({"eval_reference": True}), items)
    assert r["n"] == 3 and r["agree"] == 2 and r["agreement"] == 0.667


def test_story_ignores_salted_tokens_and_maps_old_speaker_keys():
    """Final review, finding 6: the speaker's token is salted per campaign, so a replay compares
    the label; an older recording's `who`/`name` counts as that label."""
    from harness.evalkit.session import _story
    rec = [{"kind": "npc", "tok": "aaaa1111", "label": "Вартовий", "text": "Гм.", "event": 5,
            "turn": 1}]
    rep = [{"kind": "npc", "tok": "bbbb2222", "label": "Вартовий", "text": "Гм.", "event": 5,
            "turn": 1}]
    assert _story(rec) == _story(rep)
    old = [{"kind": "npc", "name": "Вартовий", "text": "Гм.", "event": 5}]
    assert _story(old) == _story(rep)
    assert _story(rec) != _story([{**rep[0], "label": "Корчмар"}])


def test_a_stored_living_session_has_npc_lines():
    from harness.evalkit.__main__ import stored
    from harness.evalkit.replay import load
    living = [p for p in stored() if load(p)[0].get("dialogue") == "living"]
    assert living, "a living-dialogue session is among the stored ones"
    _, recs = load(living[0])
    footer = next(r for r in recs if r["k"] == "f")
    assert any(e["kind"] == "npc" for e in footer["transcript"])
