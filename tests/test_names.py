"""Task 14: names are knowledge. A character knows another's name only through a channel; until
then the context shows what can be seen. Fake providers and judges only."""
import json

import pytest

from harness.glossary import Glossary
from harness.judge import FakeJudge
from harness.models import NAME_LEARNED, PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from conftest import diff, fact, narr

ME = "молодий незнайомець із мечем"
HORST = "кремезний сивий чоловік"
ELZA = "жінка в темній хустці"
PROFILES = [
    CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance=ME),
    CharacterProfile("horst", "Горст", "Староста.", appearance=HORST),
    CharacterProfile("elza", "Ельза", "Вдова.", appearance=ELZA),
]


def make(script, *, judge=None, glossary=None, acquaint=True, **kw):
    prov = FakeProvider(script=script)
    scene = Scene("Inn", (PLAYER, "horst", "elza"), time=0)
    kw.setdefault("narration", "json")
    kw.setdefault("record_language", None)
    eng = Engine(prov, PROFILES, scene, models=ModelConfig(), judge=judge, glossary=glossary, **kw)
    if acquaint:
        eng.acquaint("horst", "elza")  # neighbours: they know each other by name
    return eng, prov


def npc_prompts(prov):
    return ["\n".join(x["content"] for x in m[1]) for m in prov.calls if m[0] == "npc"]


def narr_prompts(prov):
    return ["\n".join(x["content"] for x in m[1]) for m in prov.calls if m[0] == "narrator"]


def learned(eng):
    return [(e.payload["viewer"], e.payload["subject"], e.payload["how"], e.payload["source"])
            for e in eng.log.active([NAME_LEARNED])]


# -- the registry -------------------------------------------------------------------------------
def test_nobody_knows_the_player_and_neighbours_know_each_other():
    eng, _ = make({})
    n = eng.names
    assert n.knows("horst", "elza") and n.knows("elza", "horst")
    assert not n.knows("horst", PLAYER) and not n.knows(PLAYER, "horst")
    assert n.knows(PLAYER, PLAYER)
    assert n.ref("horst", PLAYER) == ME and n.ref("horst", "elza") == "Ельза"
    assert n.ref(None, PLAYER) == "Рагнар", "code (judges) sees real names"


def test_a_profile_without_appearance_is_known_by_name_to_everyone():
    prof = [CharacterProfile(PLAYER, "Geralt"), CharacterProfile("innkeeper", "Innkeeper")]
    eng = Engine(FakeProvider(), prof, Scene("Inn", (PLAYER, "innkeeper")), narration="json")
    assert eng.names.ref("innkeeper", PLAYER) == "Geralt"
    assert eng.names.mentions("Geralt greets the Innkeeper") == []


def test_name_forms_in_any_case_are_found_and_masked():
    eng, _ = make({})
    n = eng.names
    assert n.mentions("Скільки коштує твоя робота, Рагнаре?") == [PLAYER]
    assert n.mentions("Ельзі й Горсту") == ["elza", "horst"] or set(
        n.mentions("Ельзі й Горсту")) == {"elza", "horst"}
    assert n.mask("horst", "Рагнара не видно") == f"{ME} не видно"
    assert n.mask("horst", "Ельза мовчить") == "Ельза мовчить"
    assert n.mentions("Горстінг") == [], "not inside a longer word"
    assert n.mentions("Ельзо, слухай") == ["elza"], "vocative of a name in -а"


# -- the contexts ---------------------------------------------------------------------------------
def test_the_npc_context_shows_what_is_seen_not_the_name_and_masks_records():
    eng, prov = make({})
    eng.facts.add_canon("You, Рагнар, came to Брідки.", knowers=[(PLAYER, "told")])
    eng.facts.add_canon("Рагнар carries a steel sword.", knowers=[("horst", "told")])
    text = "\n".join(m["content"] for m in eng.ctx.character("horst", eng.scene))
    assert "Рагнар" not in text
    assert f"{ME} carries a steel sword." in text
    assert "Present: " + ME in text and "Горст (you)" in text and "Ельза" in text
    mine = "\n".join(m["content"] for m in eng.ctx.character(PLAYER, eng.scene))
    assert "You, Рагнар, came to Брідки." in mine and "Рагнар (you)" in mine
    assert HORST in mine and "Горст" not in mine


def test_the_narrator_context_is_the_player_characters_view():
    eng, _ = make({})
    eng.facts.add_campaign("Горст wants the sword", source_event_id=eng._utterance(
        PLAYER, "x").id, game_time=0, location="Inn", notability=0.3, knowers=[])
    text = "\n".join(m["content"] for m in eng.ctx.narrator(eng.scene, "I wait."))
    assert "Горст" not in text and "Ельза" not in text
    assert f"{HORST} wants the sword" in text
    assert "Рагнар (you)" in text


def test_glossary_line_does_not_offer_names_the_viewer_does_not_know():
    eng, _ = make({}, glossary=Glossary.for_world("witcher"))
    # the glossary line now sits at the tail of the prompt (cache-friendly), so read all of it
    sys_n = "\n".join(m["content"] for m in eng.ctx.narrator(eng.scene, "I wait."))
    sys_h = "\n".join(m["content"] for m in eng.ctx.character("horst", eng.scene))
    assert "Горст" not in sys_n and "Ельза" not in sys_n
    assert "Рагнар" not in sys_h and "Ельза" in sys_h


# -- the original bug and its fix ---------------------------------------------------------------
def test_stranger_addressed_by_name_is_caught_and_regenerated():
    """Play test: Горст said "Рагнаре" with no channel for the name."""
    script = {"narrator": [narr("Горст не рухається.".replace("Горст", HORST), speakers=["horst"])],
              "npc": ["Ми шукаємо людину для справи. Скільки коштує твоя робота, Рагнаре?",
                      "Ми шукаємо людину для справи. Скільки коштує твоя робота, відьмаче?"],
              "extractor": [diff()]}
    eng, prov = make(script)
    res = eng.turn("Чого вам?", speakers=["horst"])
    assert res.utterances[0].payload["text"].endswith("відьмаче?")
    assert any(n["kind"] == "npc_name_leak" and n["names"] == ["Рагнар"] for n in eng.devlog)
    assert "do not use it" in npc_prompts(prov)[1], "the retry says which name is unknown"
    assert "Рагнар" not in "\n".join(npc_prompts(prov))


def test_if_every_try_leaks_the_name_never_reaches_the_player():
    bad = "Ну що, Рагнаре?"
    eng, _ = make({"narrator": [narr("N.")], "npc": [bad] * 3, "extractor": [diff()]})
    res = eng.turn("Чого вам?", speakers=["horst"])
    assert "Рагнар" not in res.utterances[0].payload["text"]
    assert ME in res.utterances[0].payload["text"]


def test_after_an_introduction_the_name_is_allowed():
    """The player says who they are; Горст may then use the name, and his context shows it."""
    script = {"narrator": [narr("N."), narr("N.")],
              "npc": ["Радий знайомству, Рагнаре.", "Раз ти Рагнар, слухай."],
              "extractor": [diff(), diff()]}
    eng, prov = make(script)
    eng.turn("Я Рагнар.", speakers=["horst"])
    assert ("horst", PLAYER, "introduced", PLAYER) in learned(eng)
    assert ("elza", PLAYER, "introduced", PLAYER) in learned(eng)
    assert not any(n["kind"] == "npc_name_leak" for n in eng.devlog)
    eng.turn("Слухаю.", speakers=["horst"])
    assert "Рагнар" in npc_prompts(prov)[1], "known now: the second context names the player"
    assert eng.names.ref("horst", PLAYER) == "Рагнар"


def test_a_name_the_player_types_is_known_to_the_player_character():
    eng, _ = make({"narrator": [narr("N.")], "npc": ["Га?"], "extractor": [diff()]},
                  judge=FakeJudge({"name_binds": True}))
    eng.turn("Горст, послухай.", speakers=["horst"])
    assert (PLAYER, "horst", "player", None) in learned(eng)
    assert ("elza", "horst", "told", PLAYER) not in learned(eng), "elza knew it already"


def test_a_name_said_aloud_is_learned_only_if_it_attaches_to_a_person():
    """Elza says "Горст" in front of the stranger: attached (he is addressed) or merely passing."""
    for verdict in (True, False):
        eng, _ = make({"narrator": [narr("N.")], "npc": ["Слухай, Горст, не кажи зайвого."],
                       "extractor": [diff()]}, judge=FakeJudge({"name_binds": verdict}))
        eng.turn("Мовчу.", speakers=["elza"])
        assert ((PLAYER, "horst", "told", "elza") in learned(eng)) is verdict
        if not verdict:
            assert any(n["kind"] == "name_not_attached" for n in eng.devlog)


def test_the_name_of_an_absent_person_is_learned_without_a_judge():
    prof = [*PROFILES, CharacterProfile("miller", "Гостомил", appearance="мірошник")]
    prov = FakeProvider(script={"narrator": [narr("N.")], "npc": ["Гостомил помер."],
                                "extractor": [diff()]})
    eng = Engine(prov, prof, Scene("Inn", (PLAYER, "horst"), 0), narration="json",
                 record_language=None, models=ModelConfig())
    eng.acquaint("horst", "miller")
    eng.turn("?", speakers=["horst"])
    assert (PLAYER, "miller", "overheard", "horst") in learned(eng)


def test_narrator_naming_a_stranger_is_rejected_then_masked():
    script = {"narrator": [narr("Горст киває."), narr("Горст киває знову."),
                           narr("Горст киває втретє.")],
              "extractor": [diff()]}
    eng, prov = make(script)
    res = eng.turn("Чекаю.", speakers=[])
    assert "Горст" not in res.narration and HORST in res.narration
    kinds = [n["kind"] for n in eng.devlog]
    assert kinds.count("narrator_unknown_name") == 3


def test_narrator_may_name_someone_the_player_has_learned():
    script = {"narrator": [narr("Горст киває.")], "extractor": [diff()]}
    eng, _ = make(script)
    eng.names.learn(PLAYER, "horst", how="canon", scene=eng.scene)
    res = eng.turn("Чекаю.", speakers=[])
    assert res.narration == "Горст киває."


def test_player_facing_label_follows_what_was_known_at_the_time():
    eng, _ = make({"narrator": [narr("N.")], "npc": ["Я Горст, староста."], "extractor": [diff()]})
    res = eng.turn("Хто ви?", speakers=["horst"])
    ev = res.utterances[0]
    assert eng.ctx.label(PLAYER, "horst", ev.id) == HORST.capitalize(), "unknown when he spoke"
    assert eng.ctx.label(PLAYER, "horst") == "Горст", "known afterwards"


def test_rolling_back_the_line_takes_the_learned_name_with_it():
    eng, _ = make({"narrator": [narr("N.")], "npc": ["Я Горст, староста."], "extractor": [diff()]})
    res = eng.turn("Хто ви?", speakers=["horst"])
    assert eng.names.knows(PLAYER, "horst")
    eng.rollback(res.utterances[0].id)
    assert not eng.names.knows(PLAYER, "horst")


def test_extractor_gets_the_names_of_people_it_must_write_about():
    eng, prov = make({"narrator": [narr("N.")], "npc": ["Га."], "extractor": [diff()]})
    eng.turn("Привіт.", speakers=["horst"])
    ex = next(m for m in prov.calls if m[0] == "extractor")[1][1]["content"]
    assert f"Горст ({HORST})" in ex and f"Рагнар ({ME})" in ex


def test_an_npcs_own_beat_neither_shows_nor_teaches_his_name():
    """Live check: "— У справі, — Горст покрутив мідяк." named the stranger to the player."""
    from harness.style import Style

    line = "— Слухаю, — Горст покрутив мідяк. — Скільки просиш?"
    eng, _ = make({"narrator": [narr("N.")], "npc": [line], "extractor": ["- terse", diff(), diff()]},
                  style=Style.load("witcher"))
    res = eng.turn("Ну?", speakers=["horst"])
    shown = res.utterances[0].payload["text"]
    assert "Горст" not in shown and HORST in shown and "Скільки просиш?" in shown
    assert not eng.names.knows(PLAYER, "horst")
    eng2, _ = make({"narrator": [narr("N.")], "npc": ["— Я Горст, староста."],
                    "extractor": ["- terse", diff(), diff()]}, style=Style.load("witcher"))
    eng2.turn("Ну?", speakers=["horst"])
    assert eng2.names.knows(PLAYER, "horst"), "said aloud: learned"


def test_appearance_survives_reopening_a_saved_campaign(tmp_path):
    prov = FakeProvider()
    eng = Engine.create_campaign("c", prov, PROFILES, Scene("Inn", (PLAYER, "horst"), 0),
                                 root=tmp_path, narration="json")
    eng.acquaint("horst", PLAYER)
    eng.close()
    again = Engine.open_campaign("c", prov, root=tmp_path)
    assert again.profiles["horst"].appearance == HORST
    assert again.names.knows("horst", PLAYER), "the registry is read back from the log"
    again.close()
