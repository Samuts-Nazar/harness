"""The character's own view hides what the character is not aware of; debug and the world see it."""
from harness import assistant
from harness.judge import FakeJudge
from harness.models import EQUIPMENT, INVENTORY, PLAYER, INTERNAL, Scene
from harness.outcome import _state_lines
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider
from harness.state import StateChange
from conftest import PROFILES, diff, make_engine

SECRET = "ZXQ-TRACKER-IMPLANT"


def implant(eng):
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "add", SECRET, False, aware=False))
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "steel sword", True))


def items_of(elems):
    return [e.item for e in elems]


def test_unaware_element_absent_from_own_view():
    eng, _ = make_engine({})
    implant(eng)
    mem = eng.deriver.derive(PLAYER, eng.scene.time)
    assert items_of(mem.state) == ["steel sword"]
    assert items_of(eng.live.of(PLAYER, viewer=PLAYER)) == ["steel sword"]


def test_unaware_element_present_in_debug_view():
    eng, _ = make_engine({})
    implant(eng)
    assert SECRET in items_of(eng.live.of(PLAYER, viewer=PLAYER, debug=True))
    assert SECRET in items_of(eng.live.of(PLAYER))  # no viewer: today's result
    assert SECRET in items_of(eng.live.of(PLAYER, viewer="innkeeper"))
    assert SECRET in items_of(eng.deriver.derive(PLAYER, eng.scene.time, debug=True).state)


def test_realize_makes_it_appear():
    eng, _ = make_engine({})
    implant(eng)
    eng.apply_state_change(StateChange(PLAYER, INTERNAL, "realize", SECRET, False))
    assert SECRET in items_of(eng.deriver.derive(PLAYER, eng.scene.time).state)


def test_owner_still_sees_what_is_inside_own_closed_pack():
    eng, _ = make_engine({})
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "backpack", True,
                                       id="item:backpack", location="worn"))
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "lantern", True,
                                       id="item:lantern", location="in:item:backpack"))
    mem = eng.deriver.derive(PLAYER, eng.scene.time)
    assert items_of(mem.state) == ["backpack", "lantern"]
    assert [e.observable for e in mem.state] == [True, False]  # hidden from others, known to owner


def test_world_judge_state_stays_unfiltered():
    eng, _ = make_engine({})
    implant(eng)
    assert any(SECRET in line for line in _state_lines(eng))


def test_player_context_prompt_has_no_unaware_text():
    script = {"narrator": ["The innkeeper lunges with a knife.", "The blade skids off his coat."],
              "npc": ["Ось тобі!"],
              "extractor": ["The innkeeper lunges at Geralt with a knife", diff()]}
    prov = FakeProvider(script={k: list(v) for k, v in script.items()})
    judge = FakeJudge({"director_first": "innkeeper", "outcome_attempt": False,
                       "npc_act_against_player": True, "outcome_verdict": "fails",
                       "outcome_reason": "beyond_ability", "character_death": False})
    eng = Engine(prov, PROFILES, Scene("Inn", (PLAYER, "innkeeper", "bard"), time=0),
                 models=ModelConfig(), judge=judge, record_language=None, outcomes=True)
    implant(eng)
    eng.turn("Сиджу тихо.")
    narrator = ["\n".join(m["content"] for m in msgs) for mod, msgs in prov.calls
                if mod == "narrator"]
    assert len(narrator) == 2  # the turn narration and the outcome's resolution paragraph
    assert not any(SECRET in t for t in narrator)
    assert "steel sword" in narrator[0]  # what the character is aware of stays
    seen = []

    class Spy:
        models = None

        def complete(self, model, messages):
            seen.append("\n".join(m["content"] for m in messages))
            return "1. Що вам потрібно?"

        def stream(self, model, messages):
            yield self.complete(model, messages)

    eng.provider = Spy()
    assistant.suggest(eng, 3)
    assert seen and SECRET not in seen[-1] and "steel sword" in seen[-1]
