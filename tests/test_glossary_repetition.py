"""Task 12: name glossary and repetition metric."""
import json

from harness.glossary import Glossary
from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.repetition import measure, measure_turn, shape
from conftest import diff, fact

G = Glossary.for_world("witcher")
PROFS = [CharacterProfile(PLAYER, "Рагнар", "Мандрівник."),
         CharacterProfile("horst", "Горст", "Староста."),
         CharacterProfile("elza", "Ельза", "Вдова.")]


def test_latin_and_wrong_forms_become_canonical_and_endings_survive():
    t, found = G.fix("Horst met Elza at Kaer Morhen; Хорста і Ельзі, Тріс, Рангару, Лютика.")
    assert t == "Горст met Ельза at Каер Морен; Горста і Ельзі, Трісс, Рагнару, Любистка."
    assert len(found) == 7


def test_correct_text_is_left_alone_and_no_false_variants():
    ok = "Ескеля, Трісс Мерігольд, Горсту, Ельза, Каер Морені, Цірі."
    assert G.fix(ok) == (ok, [])


def test_possessive_and_case():
    assert G.apply("Ragnar's sword, HORST said") == "Рагнар's sword, Горст said"


def test_near_misses_and_counts():
    assert G.near_misses("Горстт підійшов до Рагнара.") == [("Горстт", "Горст")]
    assert G.near_misses("Горст, Горсту, Ескель, Ескеля, Ельзи") == []
    assert G.canonical_count("Горст і Рагнара, Ельзи") == 3


def test_prompt_line_lists_only_names_that_occur():
    line = G.prompt_line("Horst waits", ["Рагнар"])
    assert "Горст" in line and "Рагнар" in line and "Цірі" not in line
    assert G.prompt_line("nothing here") == ""


def _eng(script, **kw):
    prov = FakeProvider(script=script)
    judge = FakeJudge({"director_first": "horst", "director_also": False})
    eng = Engine(prov, PROFS, Scene("Корчма", (PLAYER, "horst", "elza"), time=0),
                 models=ModelConfig(), judge=judge, glossary=G, **kw)
    return eng, prov


def test_names_are_fixed_in_narration_lines_actions_facts_and_state():
    eng, prov = _eng({
        "narrator": ["Horst looks at Ragnar's sword."],
        "extractor": ["Horst eyes Ragnar",
                      json.dumps({"new_facts": [fact("Horst offers Ragnar work at Kaer Morhen",
                                                     "narration")],
                                  "state_changes": [{"character": PLAYER, "category": "equipment",
                                                     "op": "add", "item": "sword of Хорст",
                                                     "observable": True, "source": "narration"}]})],
        "npc": ["Рангаре, чуєш?"]})
    res = eng.turn("hi")
    assert res.narration == "Горст looks at Рагнар's sword."
    assert res.actions == ["Горст eyes Рагнар"]
    assert res.utterances[0].payload["text"] == "Рагнаре, чуєш?" or "Рагнар" in res.utterances[0].payload["text"]
    assert "Горст offers Рагнар work at Каер Морен" in [
        f.content for f in eng.facts.all_campaign(10**6)]
    assert ("equipment", "sword of Горст") in eng.live.snapshot()[PLAYER]
    fixed = {(x["where"], x["form"]) for x in res.names["fixed"]}
    assert ("narration", "Horst") in fixed and ("record", "Хорст") in fixed
    assert eng.reports[-1]["names"] is res.names


def test_context_is_rendered_through_the_glossary_and_lists_names():
    eng, prov = _eng({"narrator": ["N."], "extractor": ["none", diff()], "npc": ["Так."]})
    eng.facts.add_canon("Horst fears the mill at Kaer Morhen.", knowers=[("horst", "told")])
    eng.turn("Я показую Kaer Morhen на мапі.")
    npc = [m for mod, m in prov.calls if mod == "npc"][0]
    assert "Горст fears the mill at Каер Морен." in npc[1]["content"]
    assert "Horst" not in npc[1]["content"] and "exactly in these forms" in npc[0]["content"]
    ext = [m for mod, m in prov.calls if mod == "extractor"][-1]
    assert "stay in Ukrainian" in ext[1]["content"]


def test_extractor_that_answers_with_a_display_name_instead_of_an_id_is_understood():
    eng, _ = _eng({"narrator": ["N."], "npc": ["Так."], "extractor": [
        "none", json.dumps({"new_facts": [{"content": "Horst agreed", "source": "Горст",
                                            "notability": 0.5}], "state_changes": []})]})
    res = eng.turn("hi")
    assert len(res.fact_ids) == 1


def test_default_record_language_is_english():
    eng, prov = _eng({"narrator": ["N."], "extractor": ["none", diff()], "npc": ["x"]})
    eng.turn("hi")
    ext = [m for mod, m in prov.calls if mod == "extractor"][-1]
    assert "every state item in English" in ext[1]["content"]


# -- repetition --------------------------------------------------------------------------------
A = "Дощ барабанить по ґонту. Горст дивиться на меч. Вогонь тріскає у каміні."


def test_identical_output_scores_high_and_new_text_low():
    same = measure(A, [("narration", A)], "narration")
    assert same.ngram == 1.0 and same.opening == 1.0 and same.shape == 1.0 and same.examples
    new = measure("Ніч була тиха, і ніхто не озвався.", [("narration", A)], "narration")
    assert new.score < 0.4 and new.ngram == 0.0


def test_repeated_openings_without_repeated_ngrams():
    prior = [("narration", "Горст киває. Вона мовчить.")]
    r = measure("Горст киває головою вдруге. Нічого не змінилось.", prior, "narration")
    assert r.opening == 0.5 and "горст киває ..." in r.examples


def test_window_and_empty_prior():
    assert measure(A, [], "narration").score == 0.0
    old = [("narration", A)] + [("npc", f"Інше {i} слово тут.") for i in range(8)]
    assert measure(A, old, "narration").ngram == 0.0  # the match fell out of the window


def test_shape_signature_and_turn_report():
    assert shape("Раз. Два.\n\nТри.")[0] == 2
    t = measure_turn([("narration", A), ("npc", "Ні.")], [("narration", A)])
    assert t["outputs"][0]["ngram"] == 1.0 and 0 < t["score"] < 1


def test_engine_reports_repetition_per_turn():
    eng, _ = _eng({"narrator": ["Дощ іде."] * 2, "extractor": ["none", diff()] * 2,
                   "npc": ["Так."] * 2})
    r1 = eng.turn("a").repetition
    r2 = eng.turn("b").repetition
    assert r1["score"] == 0.0 and r2["ngram"] >= 0 and r2["outputs"][0]["shape"] == 1.0
    assert len(eng.reports) == 2


# -- one glossary for play and canon (task 14) ----------------------------------------------------
def test_one_loader_serves_play_and_canon_entries():
    assert {"Горст", "Ґеральт", "Велерад", "Визім", "відьмак"} <= set(G.canonical_names())
    assert G.apply("Velerad told Geralt that Foltest's sister Adda died in Vizim.") == \
        "Велерад told Ґеральт that Фольтеста sister Адда died in Визім."


def test_cases_are_kept_and_a_possessive_without_cases_keeps_its_s():
    assert G.apply("Ґеральта і Ґеральту") == "Ґеральта і Ґеральту"
    assert G.apply("Horst's sword") == "Горст's sword"
    assert G.apply("Foltest’s sister") == "Фольтеста sister"


def test_common_nouns_are_never_swapped_or_offered_as_names():
    assert G.apply("the witcher paid in orens, a silver sword") == \
        "the witcher paid in orens, a silver sword"
    assert "відьмак" not in G.prompt_line("witcher orens burgomaster", [])
    assert "відьмак" in G.canonical_names()  # still there for checks on Ukrainian text


def test_a_name_already_in_guillemets_is_not_quoted_twice():
    assert G.apply("«Під Лисом» гуде, а в Старий Наракорт не йдемо") == \
        "«Під Лисом» гуде, а в Старий Наракорт не йдемо"
    assert G.apply("Under the Fox") == "«Під Лисом»"


def test_wrong_stems_keep_their_case_endings_in_the_canon_entries_too():
    assert G.apply("Геральта, Фолтестом, Візіміра") == "Ґеральта, Фольтестом, Визіміра"
