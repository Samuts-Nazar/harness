"""Character portraits task 2: the portrait slice enters the NPC prompt in place of the flat
profile's core and manner notes; the binding survives a reopened campaign; copying an example
line into play is logged."""
from conftest import diff
from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.portrait import Portrait, Stance, Switch, copy_overlap
from harness.providers import FakeProvider
from harness.style import Style

DOES = "Tests the visitor with a concrete question about the body before any talk of price."
EXAMPLE = "— Підійди до світла, Рагнаре, і покажи мені руки, поки не почав брехати."


def portrait() -> Portrait:
    st = Stance("test", ("stranger",), {}, DOES, "Dry, exact, a little amused.",
                examples=(EXAMPLE,))
    close = Stance("warm", ("close",), {}, "Teases and then helps.", "Soft under the needles.")
    return Portrait("p_yen", "yen", "Йеннефер", "Rinde", "She wants what she cannot have.",
                    (st, close), (Switch("w", "Did the player help?", 0.2, 0.1),),
                    "Infertility.", ("A star pendant gesture.",), "About 15 words a line.",
                    "Never begs.", {})


PROFILES = [
    CharacterProfile(PLAYER, "Рагнар", "A traveller.", appearance="чоловік зі шрамом"),
    CharacterProfile("yen", "Йеннефер", "A sorceress.", manner="Talks through her teeth.",
                     appearance="чорнокоса жінка", core="Voice: clipped and proud."),
    CharacterProfile("inn", "Корчмар", "Gruff innkeeper.", manner="Grunts.",
                     appearance="корчмар", core="Voice: gruff."),
]


def eng(script=None, **kw):
    prov = FakeProvider(script=script or {})
    e = Engine(prov, PROFILES, Scene("Рінде", (PLAYER, "yen", "inn"), 0), models=ModelConfig(),
               judge=FakeJudge(), record_language=None, style=Style.load("witcher"), **kw)
    e.ctx.portraits = {"p_yen": portrait()}
    return e


def prompt(e, npc):
    v = e.ctx.character_view(npc, e.scene)
    return v.system + "\n" + "\n\n".join(v.sections)


def test_portrait_replaces_core_and_manner():
    e = eng()
    e.bind_portrait("yen", "p_yen")
    text = prompt(e, "yen")
    assert DOES in text
    assert "Who you are (fixed" not in text and "clipped and proud" not in text
    assert "Talks through her teeth" not in text
    assert "Never begs." in text                 # the bans travel with the slice
    assert e.ctx.rung_of("yen") == "stranger"
    # a seeded rung picks another stance
    e.bind_portrait("yen", "p_yen", rung="close")
    assert "Teases and then helps." in prompt(e, "yen") and DOES not in prompt(e, "yen")


def test_npc_without_portrait_is_unchanged():
    with_p = eng()
    with_p.bind_portrait("yen", "p_yen")
    bare = eng()
    bare.ctx.portraits = {}
    assert with_p.ctx.portrait_section("inn", with_p.scene) == ""
    assert (with_p.ctx.character_view("inn", with_p.scene).messages()
            == bare.ctx.character_view("inn", bare.scene).messages())


def test_slice_is_masked_for_the_npc():
    e = eng()
    e.bind_portrait("yen", "p_yen")
    sec = e.ctx.portrait_section("yen", e.scene)
    assert "Рагнар" not in sec and "Підійди до світла" in sec
    for m in e.ctx.character_view("yen", e.scene).messages():
        assert "Рагнар" not in m["content"]


def test_situation_from_the_scene():
    e = eng()
    sit = e.ctx.situation("yen", e.scene)
    assert sit.power == "even" and sit.stakes == "low" and sit.audience  # the innkeeper is here
    e.scene.present = (PLAYER, "yen")
    assert not e.ctx.situation("yen", e.scene).audience


def test_copy_overlap():
    assert copy_overlap("Ну то підійди до світла, Рагнаре, і покажи мені руки.", [EXAMPLE])
    assert not copy_overlap("Покажи руки. Швидко.", [EXAMPLE])


def test_copy_overlap_logged():
    e = eng({"narrator": ["N."] * 3,
             "npc": ["— Підійди до світла, чоловіче, і покажи мені руки, поки не почав брехати."],
             "extractor": [diff()] * 3})
    e.scene.present = (PLAYER, "yen")
    e.bind_portrait("yen", "p_yen")
    e.turn("Добрий день.", speakers=["yen"])
    e.settle()
    notes = [n for n in e.devlog if n["kind"] == "portrait_copy"]
    assert notes and notes[0]["npc"] == "yen" and "покажи мені руки" in notes[0]["line"]


def test_portrait_binding_survives_reopen(tmp_path):
    prov = FakeProvider(script={})
    e = Engine.create_campaign("c", prov, PROFILES, Scene("Рінде", (PLAYER, "yen"), 0),
                               root=tmp_path, models=ModelConfig(), judge=FakeJudge(),
                               world="witcher")
    assert "yennefer_rinde" in e.ctx.portraits
    e.bind_portrait("yen", "yennefer_rinde", rung="client")
    e.close()
    again = Engine.open_campaign("c", prov, root=tmp_path, models=ModelConfig(),
                                 judge=FakeJudge())
    assert again.profiles["yen"].portrait == "yennefer_rinde"
    assert "yennefer_rinde" in again.ctx.portraits
    assert again.ctx.rung_of("yen") == "client"
    assert again.ctx.portrait_section("yen", again.scene)


# -- review fixes (round 1) -----------------------------------------------------------------

def _world_portraits():
    from harness.portrait import WORLDS, load_world_portraits
    out = []
    for w in sorted(d.name for d in WORLDS.iterdir() if (d / "portraits").is_dir()):
        out += list(load_world_portraits(w).values())   # every bundled portrait loads
    return out


def test_all_bundled_portraits_load():
    assert "yennefer_rinde" in {p.id for p in _world_portraits()}


def test_section_with_header_fits_the_budget_for_every_stance():
    e = eng()
    for p in _world_portraits():
        for st in p.stances:
            sec = e.ctx.portrait_text(p, st, "yen")
            assert len(sec.split()) <= 260, (p.id, st.id, len(sec.split()))


def test_yennefer_prompt_has_no_desk_cliche_and_an_unconditional_echo_ban():
    e = eng()
    p = next(x for x in _world_portraits() if x.id == "yennefer_rinde")
    for st in p.stances:
        sec = e.ctx.portrait_text(p, st, "yen").lower()
        assert "papers" not in sec and "looking up" not in sec
        assert "never repeats the visitor's words back;" in sec and "sneer" not in sec
        assert "before she knows what he needs" in sec
    assert not any(ex.startswith("— Допомогти") for st in p.stances for ex in st.examples)
    first = e.ctx.portrait_text(p, p.stances[0], "yen")   # stranger_test keeps both examples
    assert all(ex in first for ex in p.stances[0].examples)


def test_copy_check_uses_the_masked_examples():
    e = eng()
    e.bind_portrait("yen", "p_yen")
    v = e.ctx.character_view("yen", e.scene)
    assert v.examples and not any("Рагнар" in x for x in v.examples)
    assert v.examples[0] in "\n".join(v.sections)


def test_a_broken_portrait_file_does_not_stop_the_engine(monkeypatch):
    from pathlib import Path

    import harness.pipeline as pl
    from harness.portrait import PortraitError

    def boom(world):
        raise PortraitError(Path("x/broken.yaml"), "core", "missing")
    monkeypatch.setattr(pl, "load_world_portraits", boom)
    e = Engine(FakeProvider(script={}), PROFILES, Scene("Рінде", (PLAYER,), 0),
               models=ModelConfig(), judge=FakeJudge(), world="witcher")
    assert e.ctx.portraits == {}
    note = next(n for n in e.devlog if n["kind"] == "portraits_failed")
    assert "broken.yaml" in note["error"]
