"""Task 14: "how does he know that?" The player marks an NPC line as impossible; the engine checks
the speaker's channels. Fake providers and judges only."""
import pytest

from harness import knowledge
from harness.judge import FakeJudge, JudgeError
from harness.models import CORRECTION, PLAYER, UTTERANCE
from conftest import diff, fact, narr
from test_names import HORST, ME, PROFILES, Engine, FakeProvider, ModelConfig, Scene, make


class BrokenJudge(FakeJudge):
    def ask(self, state, questions):
        raise JudgeError("down")


def pick(word):
    """A channel judge: choose the item whose text mentions `word`, else none."""
    def rule(q, state):
        for key, desc in q.options.items():
            if key != "none" and word in desc:
                return key
        return "none"
    return rule


def play(judge, npc_lines=("Під млином, кажуть, лежить підвал, повний кісток.", "Не знаю, що там."),
         extractor=None):
    script = {"narrator": [narr("N.")] * 3, "npc": list(npc_lines),
              "extractor": extractor or [diff(fact("Elza talks about the cellar", "elza", 0.4)),
                                         diff(), diff(), diff(), diff()]}
    eng, prov = make(script, judge=judge)
    eng.facts.add_canon("The mill by the dam is old.", knowers=[("elza", "told")])
    res = eng.turn("Що з млином?", speakers=["elza"])
    return eng, prov, res.utterances[0]


def test_no_channel_regenerates_the_line_with_the_explanation_and_remembers_it():
    eng, prov, line = play(FakeJudge({"knowledge_channel": "none"}))
    old_facts = [f.content for f in eng.facts.visible_to("elza", 10**6)]
    assert "Elza talks about the cellar" in old_facts
    out = eng.challenge_line(line.id, "про підвал їй ніхто не казав")
    assert out.verdict == "no_channel" and out.regenerated
    assert out.text == "Не знаю, що там."
    assert not eng.log.is_active(line.id), "the old line is gone"
    texts = [e.payload["text"] for e in eng.log.active([UTTERANCE]) if e.payload["speaker"] == "elza"]
    assert texts == ["Не знаю, що там."]
    assert "Elza talks about the cellar" not in [
        f.content for f in eng.facts.visible_to("elza", 10**6)], "what the old line implied is rolled back"
    note = eng.log.active([CORRECTION])[0].payload
    assert note["explanation"] == "про підвал їй ніхто не казав" and note["npc"] == "elza"
    # the player's turn stays, and the new line's context carries the correction
    assert any(e.payload["speaker"] == PLAYER for e in eng.log.active([UTTERANCE]))
    regen_prompt = "\n".join(m["content"] for m in [c for c in prov.calls if c[0] == "npc"][-1][1])
    assert "про підвал їй ніхто не казав" in regen_prompt and "do not repeat" in regen_prompt


def test_the_correction_is_fed_to_later_generations_of_that_character_only():
    eng, prov, line = play(FakeJudge({"knowledge_channel": "none"}),
                           npc_lines=("Підвал!", "Не знаю.", "Мовчу.", "Га."))
    eng.challenge_line(line.id, "не могла знати")
    eng.turn("А тепер?", speakers=["elza"])
    eng.turn("А ти?", speakers=["horst"])
    prompts = ["\n".join(m["content"] for m in c[1]) for c in prov.calls if c[0] == "npc"]
    assert "не могла знати" in prompts[2]
    assert "не могла знати" not in prompts[3]


def test_a_channel_is_reported_with_type_and_rough_time_and_changes_nothing():
    eng, _, line = play(FakeJudge({"knowledge_channel": pick("mill by the dam")}),
                        npc_lines=("Млин старий, ще з діда.",))
    eng.scene.time += 2 * 1440 + 30
    out = eng.challenge_line(line.id, "звідки вона знає про млин")
    assert out.verdict == "channel" and not out.regenerated
    assert out.public == "це загальновідоме в цих краях"
    assert "The mill by the dam is old." in out.detail, "the full event is in the spoiler"
    assert "The mill" not in out.public, "the content never appears in the public text"
    assert eng.log.is_active(line.id) and eng.log.active([CORRECTION]) == []


def test_public_wording_for_each_kind_of_channel():
    eng, _, _ = play(FakeJudge())
    eng.scene.time = 3 * 1440
    mk = lambda kind, how, source=None, when=0, canon=False: knowledge.Item(  # noqa: E731
        "1", kind, "x", how, source, when, None, None, canon)
    pub = lambda it: knowledge.public_channel(eng, it)  # noqa: E731
    assert pub(mk("fact", "heard", "horst")) == "чув про це від когось 3 дні тому"
    assert pub(mk("fact", "told", PLAYER, 3 * 1440 - 10)) == "почув це від тебе щойно"
    assert pub(mk("fact", "witnessed", None, 2 * 1440)) == "бачив це на власні очі вчора"
    assert pub(mk("fact", "told", None, 0, canon=True)).startswith("це загальновідоме")
    assert pub(mk("name", "acquainted", None, None)) == "вони знайомі раніше"
    assert pub(mk("background", "background", None, None)) == "це з його власного життя"
    assert knowledge.rough_time(eng, 3 * 1440 - 3 * 60) == "сьогодні"
    assert knowledge.rough_time(eng, 3 * 1440 - 5 * 1440) == "5 днів тому"
    assert knowledge.rough_time(eng, 0 - 18 * 1440) == "21 день тому"


def test_a_name_without_a_channel_is_found_without_asking_the_judge():
    judge = FakeJudge({"knowledge_channel": pick("never")})
    eng, _, _ = play(judge)
    bad = eng._utterance("horst", "Ну що, Рагнаре, згоден?")  # got through some other way
    out = eng.challenge_line(bad.id)
    assert out.verdict == "no_channel" and "Рагнар" in out.detail
    tags = [q.tag for _, qs in judge.asked for q in qs.values()]
    assert "knowledge_channel" not in tags, "a hidden name is certain: no channel question"


def test_a_name_with_a_channel_is_not_a_leak():
    eng, _, _ = play(FakeJudge({"knowledge_channel": "none"}))
    eng.names.learn("horst", PLAYER, how="introduced", scene=eng.scene, source=PLAYER)
    ok = eng._utterance("horst", "Ну що, Рагнаре?")
    out = eng.challenge_line(ok.id)  # the judge says "none", but the name itself is no longer the issue
    assert out.verdict == "no_channel" and "Рагнар" not in out.detail


def test_only_the_last_line_is_regenerated_but_the_note_is_always_stored():
    eng, _, first = play(FakeJudge({"knowledge_channel": "none"}), npc_lines=("Перша.", "Друга."))
    eng.turn("Ще?", speakers=["elza"])
    out = eng.challenge_line(first.id, "не могла")
    assert out.verdict == "no_channel" and not out.regenerated
    assert eng.log.is_active(first.id) and len(eng.log.active([CORRECTION])) == 1


def test_no_judge_means_unavailable_and_nothing_changes():
    eng, _, line = play(FakeJudge())
    eng.judge = BrokenJudge()
    out = eng.challenge_line(line.id, "?")
    assert out.verdict == "unavailable" and eng.log.is_active(line.id)
    assert eng.log.active([CORRECTION]) == []


def test_a_failed_regeneration_puts_the_old_line_back():
    eng, prov, line = play(FakeJudge({"knowledge_channel": "none"}), npc_lines=("Підвал!",))
    with pytest.raises(RuntimeError):  # the script has no second NPC line
        eng.challenge_line(line.id, "не могла")
    texts = [e.payload["text"] for e in eng.log.active([UTTERANCE]) if e.payload["speaker"] == "elza"]
    assert texts == ["Підвал!"]


def test_only_npc_lines_can_be_challenged():
    eng, _, _ = play(FakeJudge())
    mine = next(e for e in eng.log.active([UTTERANCE]) if e.payload["speaker"] == PLAYER)
    with pytest.raises(ValueError):
        eng.challenge_line(mine.id)


def test_knowledge_report_lists_what_each_character_knows_and_from_where():
    eng, _, line = play(FakeJudge(), npc_lines=("Млин старий.",))
    rep = eng.knowledge_report("elza")
    kinds = {r["kind"] for r in rep}
    assert {"fact", "name", "seen", "background"} <= kinds
    fact_row = next(r for r in rep if r["text"] == "The mill by the dam is old.")
    assert fact_row["how"] == "told" and fact_row["when_text"] == "day 1, 00:00"
    name_row = next(r for r in rep if r["kind"] == "name")
    assert "Горст" in name_row["text"] and name_row["how"] == "acquainted"
    heard = next(r for r in eng.knowledge_report("horst") if r["kind"] == "seen"
                 and "Що з млином?" in r["text"])
    assert heard["source"] == PLAYER and heard["source_name"] == "Рагнар"
    assert not any(r["kind"] == "name" and "Рагнар" in r["text"] for r in rep), \
        "she never learned the stranger's name"
