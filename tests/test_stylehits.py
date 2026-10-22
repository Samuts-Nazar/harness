"""Prose-quality detector: the user's rejected shapes are flagged, plain lines are not."""
from harness.stylehits import count_by_kind, style_hits


def kinds(text):
    return [h.kind for h in style_hits(text)]


def test_aphorism_not_x_but_y():
    assert kinds("— Не кажіть «люди» — люди це не відповідь, це погода.") == ["aphorism"]


def test_simile_with_relative_clause():
    assert kinds("— Швидкий, професійний, як у коняка, що дивиться на коня.") == ["simile"]
    assert kinds("Погляд, наче вуглина, що вже згасла.") == ["simile"]


def test_plain_comparison_passes():
    assert kinds("Він сидів, як пеньок. Очі як у кота.") == []


def test_long_simile_without_relative():
    long = "Він говорив так, ніби " + " ".join(["слово"] * 16) + "."
    assert kinds(long) == ["simile"]
    assert style_hits(long, long_simile=30) == []


def test_definition_only_in_speech():
    assert kinds("— Кров — це вже дарма, кров я змию.") == ["aphorism"]
    assert kinds("Два десятки кроків — це рівно стільки, скільки треба.") == []
    assert kinds("— Так. — Це буде довга ніч.") == []


def test_material_metonymy():
    assert kinds("Він ходить у шовках, а ти тримаєш мідь.") == ["metonymy", "metonymy"]
    assert kinds("Ходить на срібло.") == ["metonymy"]
    assert kinds("Хто ж на срібло ходить, га?") == ["metonymy"]


def test_material_adjective_and_plain_object_pass():
    assert kinds("На оксамитовій стрічці зірка. Тримає мідний кухоль. Носить срібний меч.") == []
    assert kinds("Тримає кухоль, ходить у дорогому вбранні.") == []


def test_mystic_non_event():
    t = ("Склянка повільно випрямилася сама — хтось із них двох підсунув її рівніше, і краще не "
         "розмірковувати, хто саме.")
    assert kinds(t) == ["mystic"]
    assert kinds("Двері скрипнули, і краще не питати чому.") == ["mystic"]
    assert kinds("Вона сама підсунула склянку рівніше.") == []


def test_counts():
    hits = style_hits("— Це не відповідь, це погода. Тримає мідь.")
    assert count_by_kind(hits) == {"aphorism": 1, "metonymy": 1}


def test_engine_logs_style_hits_and_counts_them():
    from harness.judge import FakeJudge
    from harness.models import PLAYER, CharacterProfile, Scene
    from harness.pipeline import Engine, ModelConfig
    from harness.providers import FakeProvider
    profs = [CharacterProfile(PLAYER, "Рагнар", "Мандрівник."), CharacterProfile("horst", "Горст", "Староста.")]
    from conftest import diff
    prov = FakeProvider(script={"narrator": ["Горст ходить у шовках."], "extractor": ["", diff()],
                                "npc": ["— Люди це не відповідь, це погода. Він ходить у шовках."]})
    eng = Engine(prov, profs, Scene("Корчма", (PLAYER, "horst"), time=0), models=ModelConfig(),
                 judge=FakeJudge({"director_first": "horst", "director_also": False}))
    res = eng.turn("привіт")
    # the first turn at a place keeps its narration, so the narrator's line is counted too
    assert res.style["count"] == 3 and res.style["by_kind"] == {"metonymy": 2, "aphorism": 1}
    notes = [n for n in eng.devlog if n["kind"] == "style_hit"]
    assert {n["hit"] for n in notes} == {"metonymy", "aphorism"}
    assert eng.reports[-1]["style"] is res.style
