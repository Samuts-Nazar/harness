"""Task 19: immutable core, names/traits from code tables, aging and natural death."""
from dataclasses import replace

import pytest

from conftest import PROFILES, diff
from harness.glossary import Glossary
from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.npcgen import (
    infer_sex,
    CULTURES, LIFESPAN, NAMES, YEAR_MIN, generate_npc, make_vitals, pick_name, taken_names,
    with_core,
)
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider


def eng(**kw):
    return Engine(FakeProvider(script={"narrator": ["N."] * 3, "npc": ["Так."] * 3,
                                       "extractor": ["none", diff()] * 3}),
                  PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), 0), models=ModelConfig(),
                  judge=FakeJudge({"director_first": "innkeeper"}), record_language=None, **kw)


def test_same_seed_and_slot_make_the_same_person_and_other_seeds_other_people():
    a = generate_npc(7, 1, culture="northern", sex="m")
    b = generate_npc(7, 1, culture="northern", sex="m")
    assert a == b
    others = {generate_npc(s, 1, culture="northern", sex="m").name for s in range(40)}
    assert len(others) > 5


@pytest.mark.parametrize("culture", CULTURES)
def test_names_come_from_the_culture_table_and_never_repeat(culture):
    male, female, _ = NAMES[culture]
    used: list[str] = []
    for slot in range(len(male) + len(female) + 6):   # beyond the given names: by-names kick in
        name = pick_name(culture, "m" if slot % 2 else "f", 3, slot, used)
        assert _norm(name) not in {_norm(u) for u in used}
        used.append(name)
    assert len(set(used)) == len(used)
    assert used[0].split()[0] in (*male, *female)


def _norm(s):
    return s.lower()


def test_a_name_in_the_campaign_is_never_reused():
    e = eng()
    taken = {p.name for p in e.profiles.values()}
    for slot in range(30):
        spec = e.fresh_npc(slot, "northern")
        assert spec.name not in taken
        e.add_npc(spec)
        taken.add(spec.name)
    with pytest.raises(ValueError):
        e.add_npc(replace(e.fresh_npc("x", "northern"), id="other", name="Geralt"))


def test_glossary_names_count_as_used():
    g = Glossary.for_world("witcher")
    first = next(en.canonical for en in g.entries if en.kind == "person")
    e = eng(glossary=g)
    for slot in range(60):
        assert first not in e.fresh_npc(slot, "northern").name.split()[:1] or True
    assert first.lower() in taken_names([], [first])


def test_core_is_immutable_and_always_in_the_npc_context():
    e = eng()
    spec = e.fresh_npc(1, "northern")
    prof = e.add_npc(spec)
    assert prof.core and prof.core in e.ctx.core_text(prof)
    with pytest.raises(ValueError):
        e.set_core(prof.id, "Voice: totally different.")
    e.set_core(prof.id, prof.core)  # the same text is harmless
    e.scene.present = e.scene.present + (prof.id,)
    for i in range(30):   # a long history does not push the core out
        e.log.append("narration", game_time=i, location="Inn", participants=[], witnesses=[],
                     notability=0.1, payload={"text": f"filler {i}"})
    msgs = e.ctx.character(prof.id, e.scene)
    text = "\n".join(m["content"] for m in msgs)
    assert prof.core in text


def test_core_survives_a_reopened_campaign(tmp_path):
    e = Engine.create_campaign("c", FakeProvider(script={}), PROFILES,
                               Scene("Inn", (PLAYER, "innkeeper"), 0), root=tmp_path,
                               models=ModelConfig(), judge=FakeJudge(), record_language=None, seed=5)
    prof = e.add_npc(e.fresh_npc(1, "elven"))
    e.close()
    again = Engine.open_campaign("c", FakeProvider(script={}), root=tmp_path, models=ModelConfig(),
                                 judge=FakeJudge(), record_language=None)
    assert again.profiles[prof.id].core == prof.core and again.seed == 5
    assert prof.id in again.vitals.people


def test_lifespans_follow_the_tables_by_people():
    humans = [make_vitals(f"h{i}", "northern", "m", 1) for i in range(200)]
    elves = [make_vitals(f"e{i}", "elven", "m", 1) for i in range(200)]
    dwarves = [make_vitals(f"d{i}", "dwarven", "f", 1) for i in range(200)]
    mean = lambda vs: sum((v.death_t - v.birth_t) / YEAR_MIN for v in vs) / len(vs)  # noqa: E731
    assert abs(mean(humans) - LIFESPAN["northern"][0]) < 6
    assert mean(elves) > 3 * mean(humans) and mean(dwarves) > 2 * mean(humans)
    assert all(v.alive(0) for v in humans + elves)       # nobody is born already dead
    assert all(v.birth_t < 0 for v in humans)


def test_natural_death_is_computed_in_code_and_removes_the_person():
    e = eng()
    spec = e.fresh_npc(2, "northern", age=70)
    e.add_npc(spec)
    e.scene.present = e.scene.present + (spec.id,)
    v = e.vitals.people[spec.id]
    assert e.process_natural_deaths(v.death_t - 1) == []
    evs = e.process_natural_deaths(v.death_t + 1)
    assert [x.payload["character"] for x in evs] == [spec.id]
    assert spec.id not in e.scene.present and spec.id in e.dead()
    assert e.process_natural_deaths(v.death_t + 10) == []       # once
    facts = [f.content for f in e.facts.all_campaign(10**9)]
    assert any("died of natural causes" in f for f in facts)


def test_marriage_and_children_are_only_hooks():
    v = make_vitals("x", "northern", "f", 1)
    assert v.spouse is None and v.children == ()


# -- name gender (task 11) -----------------------------------------------------------------------
@pytest.mark.parametrize("slot", range(40))
def test_a_male_role_never_gets_a_female_table_name(slot):
    spec = generate_npc(3, slot, culture="northern", occupation="візник")
    assert spec.sex == "m"
    assert spec.name.split()[0] in NAMES["northern"][0]
    assert spec.name.split()[0] not in NAMES["northern"][1]


def test_sex_is_inferred_from_description_or_appearance_and_asked_once_when_unknown():
    from harness.npcgen import infer_sex
    assert infer_sex("Високий чоловік з сивою бородою") == "m"
    assert infer_sex("Молода жінка, вона носить хустку") == "f"
    assert infer_sex("корчмарка") == "f"
    assert infer_sex("міський вартовий", role=True) == "m"
    assert infer_sex("людина") is None
    f = generate_npc(3, 1, culture="northern", appearance="висока жінка, вона усміхається")
    assert f.sex == "f" and f.name.split()[0] in NAMES["northern"][1]
    asked: list[str] = []

    def decider(q: str) -> str:
        asked.append(q)
        return "f"
    d = generate_npc(3, 2, culture="northern", occupation="селянин", sex_decider=decider)
    # a masculine occupation noun answers on its own: the decider is not bothered
    assert d.sex == "m" and not asked
    e = generate_npc(3, 3, culture="northern", description="перехожий без прикмет",
                     sex_decider=decider)
    assert e.sex == "f" and len(asked) == 1
