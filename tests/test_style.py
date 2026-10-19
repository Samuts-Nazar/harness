"""Task 15: Sapkowski style: NPC beats, foreign-voice check, exemplars, manner notes."""
import pytest

from harness.models import ACTION, PLAYER, CharacterProfile, Scene, UTTERANCE
from harness.narrator import has_dash_speech, strip_speech
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.style import (ExemplarIndex, Style, assistant_isms, beat_as_action, foreign_voice,
                           manner_messages, parse_manner, split_npc_output)
from conftest import PROFILES, diff, fact
from test_prose import director_judge

LINE = ("— Млин, кажете? — Горст озирнувся і стишив голос. — Тоді вже краще говорити тихіше, — "
        "додав він. — Тут і стіни слухають.")


# -- splitting ---------------------------------------------------------------------------------
def test_split_separates_speech_and_beats():
    out = split_npc_output(LINE)
    assert out.has_dash
    assert out.speech == "Млин, кажете? Тоді вже краще говорити тихіше. Тут і стіни слухають."
    assert out.beats == ["Горст озирнувся і стишив голос."]  # "додав він" is a bare tag


def test_plain_speech_without_dashes_is_all_speech():
    out = split_npc_output("Сто. І ані шеляга менше.")
    assert out.speech == "Сто. І ані шеляга менше." and out.beats == [] and not out.has_dash


def test_paragraph_that_starts_with_a_beat():
    out = split_npc_output("Горст почухав потилицю.\n— Ну… — сказав. — Сімдесят.")
    assert out.beats == ["Горст почухав потилицю."]
    assert out.speech == "Ну… Сімдесят."


def test_tail_comma_becomes_a_full_stop_and_long_piece_is_speech():
    long = " ".join(["слово"] * 45)
    out = split_npc_output(f"— Раз, — {long} — два,")
    assert out.beats == []  # the long middle piece is speech, not a beat
    assert not out.speech.endswith(",")


def test_beat_as_action_names_the_actor():
    assert beat_as_action("озирнувся", "Горст") == "Горст озирнувся."
    assert beat_as_action("Горст озирнувся", "Горст") == "Горст озирнувся."
    assert beat_as_action("він сплюнув", "Горст") == "Горст сплюнув."
    assert beat_as_action(" , ", "Горст") == ""


# -- foreign voice and the narration detectors --------------------------------------------------
def test_foreign_voice_catches_other_characters_acting_or_speaking():
    others = ["Горст", "Ельза", "Рагнар"]
    assert foreign_voice(LINE, "Горст", others) is None
    assert foreign_voice("— Ні. — Ельза стиснула губи. — Так.", "Горст", others)
    assert foreign_voice("Ельза: Не слухай його.", "Горст", others)
    assert foreign_voice("— Тихо. — Рагнар кивнув.", "Горст", others)


def test_narration_may_not_contain_npc_speech_but_npc_output_with_beats_is_one_voice():
    assert has_dash_speech("— Млин стоїть біля дамби, — каже вона.")
    assert "Млин" not in strip_speech("Дощ. — Млин стоїть біля дамби, — каже вона.", [])
    assert foreign_voice(LINE, "Горст", ["Горст", "Ельза"]) is None  # accepted on the NPC path


def test_assistant_isms():
    assert "є справа" in assistant_isms("Є справа. П'яту ніч виє.")
    assert "filler звісно" in assistant_isms("За плату, звісно.")
    assert assistant_isms("Сто. І ані шеляга менше.") == []


# -- exemplars ----------------------------------------------------------------------------------
BOOK = "\n".join([
    "Заголовок", "",
    "— Корчма вільна? — спитав він.",
    "— Нема місця, — буркнув корчмар, не відриваючись від кухля з пивом. Пиво було кисле.",
    "— Заплачу вдвічі, — сказав чужинець. — Тридцять марок.",
    "— Тридцять п'ять, — сказав корчмар. — І коні під дощем.",
    "— Згода.", "",
    "Він розсідлав конячку й сам відвів її у стайню, де пахло мокрою вовною, цибулею та кислим "
    "пивом, а в кутку чухався пес. Віддав грошву й подумав, що корчма в такий дощ вартує більше. "
    "Потім довго стояв під стріхою, дивлячись, як дощ розмиває двір, і рахував, скільки ще йти.",
    "Кінець.",
])


def test_index_finds_dialogue_and_prose():
    idx = ExemplarIndex(BOOK * 3)
    assert idx.dialogue and idx.prose
    got = idx.pick("корчма пиво марок", k=1)
    assert got and got[0].startswith("— ")
    assert idx.pick("корчма", kind="prose", k=1)[0].startswith("Він розсідлав")


def test_style_without_books_degrades_to_no_examples(monkeypatch, tmp_path):
    monkeypatch.setenv("HARNESS_BOOKS", str(tmp_path / "missing.txt"))
    import harness.style as st
    monkeypatch.setattr(st, "REPO", tmp_path)
    s = Style.load("witcher")
    assert s.npc_examples_section("корчма") == ""


def test_prompts_carry_the_sheet_manner_and_the_limits():
    s = Style.load("witcher", exemplars=False)
    prof = CharacterProfile("horst", "Горст", "Староста.", manner="Крутить шапку в руках.")
    sys = s.npc_system(prof)
    assert "Горст" in sys and "Крутить шапку" in sys and "haggl" in sys.lower()
    ins = s.npc_instruction(prof, "Ukrainian")
    assert "Never another character" in ins and "Ukrainian" in ins and "dash" in ins
    assert "Sapkowski" in s.narrator_system()


# -- manner notes -------------------------------------------------------------------------------
def test_manner_messages_and_parse():
    msgs = manner_messages(CharacterProfile("h", "Горст", "Староста."))
    assert "Горст" in msgs[1]["content"]
    assert parse_manner("1. Крутить шапку.\n- Повторює слово.\n\n") == "Крутить шапку. Повторює слово."


# -- the engine ---------------------------------------------------------------------------------
def engine(script, **kw):
    prov = FakeProvider(script=script)
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0),
                 models=ModelConfig(), judge=director_judge("innkeeper"), record_language=None,
                 style=Style.load("witcher", exemplars=False), **kw)
    return eng, prov


def test_npc_beats_become_that_npcs_observable_actions():
    script = {"narrator": ["The fire pops."], "extractor": ["none", "Manner one.\nManner two.",
                                                            diff()],
              "npc": ["— Hm, — Innkeeper glanced at the door. — Ten orens. — and spat."]}
    eng, prov = engine(script)
    res = eng.turn("How much?")
    u = res.utterances[0]
    assert u.payload["text"].startswith("— Hm") and u.payload["speech"].startswith("Hm")
    acts = eng.log.active([ACTION])
    mine = [a for a in acts if a.payload.get("by") == "innkeeper"]
    assert mine and all(a.cause_id == u.id for a in mine)
    assert all(PLAYER in a.witnesses and "bard" in a.witnesses for a in mine)
    # the stored speech excludes the beats; the beats reach others as [you see]
    prof = eng.profiles["innkeeper"]
    assert prof.manner == "Manner one. Manner two."


def test_npc_that_writes_for_someone_else_is_regenerated():
    script = {"narrator": ["N."], "extractor": ["none", "m", diff()],
              "npc": ["— No. — Dandelion nodded. — Go.", "— No."]}
    eng, _ = engine(script)
    res = eng.turn("hi")
    assert res.utterances[0].payload["text"] == "— No."
    assert any(n["kind"] == "npc_line_rejected" and "Dandelion" in n.get("why", "")
               for n in eng.devlog)


def test_profiles_with_manner_round_trip_through_a_saved_campaign(tmp_path):
    prov = FakeProvider(script={"narrator": ["N."], "extractor": ["none", "m", diff()],
                                "npc": ["— Fine."]})
    eng = Engine.create_campaign("c", prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper"), time=0),
                                 root=tmp_path, judge=director_judge("innkeeper"),
                                 record_language=None, style=Style.load("witcher", exemplars=False))
    eng.turn("hi")
    eng.close()
    again = Engine.open_campaign("c", FakeProvider(), root=tmp_path)
    assert again.profiles["innkeeper"].manner
    again.close()
