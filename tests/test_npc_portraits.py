"""Character portraits task 5: short portraits for invented NPCs who matter (one extractor-role
call, cached in the campaign), and the canon portraits of the Vizima arc in the world folder."""
import pytest

from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.npcgen import generate_npc, short_portrait
from harness.pipeline import Engine, ModelConfig
from harness.portrait import LADDER, WORLDS, load_world_portraits
from harness.providers import FakeProvider
from harness.style import Style

REPLY = """```yaml
core: >-
  A ferryman who owes everyone a little and trusts nobody with the oar.
stances:
  - id: wary
    rung: [stranger, client]
    does: Answers what is asked, names the fare first, keeps the oar between them.
    sounds: Short and dry; «добродію» as distance.
    examples: ["— Два гроші. Наперед.", "— Тут мілко. Сиди й не крутись."]
  - id: easy
    rung: [ally, close]
    does: Jokes about the river and the toll men; lends the boat without asking why.
    sounds: Slow, warm, river slang.
    examples: ["— Бери човен. Повернеш, коли повернеш."]
  - id: soft
    rung: [lover]
    does: Quiet, rough tenderness; brings food without a word.
    sounds: Few words, low.
switches:
  - id: paid_fair
    trigger: Did the player pay without haggling?
    warmth: 0.2
    trust: 0.2
  - id: helped_boat
    trigger: Did the player help him with the boat or the cargo?
    warmth: 0.3
    trust: 0.9
  - id: mocked
    trigger: Did the player mock his poverty?
    warmth: -0.4
    trust: -0.2
hidden: He smuggles letters for the toll men's enemies.
leaks:
  - He glances at the bundle under the bench.
voice: Lines of about 8 words; numbers first; «ти» only to friends.
never: Never begs, never names who pays him for the letters.
```"""

PROFILES = [CharacterProfile(PLAYER, "Рагнар", "A traveller.", appearance="чоловік зі шрамом")]


def spec(slot="ferry"):
    return generate_npc("seed", slot, culture="northern", occupation="перевізник",
                        appearance="старий перевізник")


def test_short_portrait_parsed_from_fake_reply():
    seen = []

    def complete(messages):
        seen.append(messages)
        return REPLY
    s = spec()
    p = short_portrait(s, Style.load("witcher"), complete, text="Мовчун, що любить річку.")
    assert p is not None and len(seen) == 1
    assert seen[0][0]["content"].startswith("You write character portraits")
    assert "Мовчун, що любить річку." in seen[0][1]["content"]
    assert p.id == f"npc:{s.id}" and p.character == s.id and p.name == s.name
    assert len(p.stances) >= 3 and len(p.switches) >= 3 and p.voice
    assert all(-0.5 <= sw.warmth <= 0.5 and -0.5 <= sw.trust <= 0.5 for sw in p.switches)
    assert {r for st in p.stances for r in st.rung} >= set(LADDER)   # the ladder is covered
    assert all(len(st.examples) <= 2 for st in p.stances)


@pytest.mark.parametrize("bad", ["not yaml: [", "core: x", "just some prose, sorry"])
def test_short_portrait_unusable_reply_gives_none(bad):
    assert short_portrait(spec(), None, lambda m: bad) is None


def engine(script, tmp_path=None):
    prov = FakeProvider(script=script)
    kw = dict(models=ModelConfig(), judge=FakeJudge(), world="witcher")
    if tmp_path is not None:
        return Engine.create_campaign("c", prov, PROFILES, Scene("Рінде", (PLAYER,), 0),
                                      root=tmp_path, **kw), prov
    return Engine(prov, PROFILES, Scene("Рінде", (PLAYER,), 0), **kw), prov


def portrait_calls(prov):
    return [m for _, m in prov.calls if m[0]["content"].startswith("You write character portraits")]


def test_background_extra_gets_no_portrait_call(tmp_path):
    e, prov = engine({"extractor": [REPLY]}, tmp_path)
    extra = e.add_npc(e.fresh_npc("walkin1", "northern", sex="m"), appearance="худий візник")
    e.enter_scene(extra.id)
    assert e.promote_short_portraits() == []          # a background extra: no call
    assert portrait_calls(prov) == [] and not e.profiles[extra.id].portrait
    e.names.learn(PLAYER, extra.id, how="told", scene=e.scene)   # now he is named
    assert e.promote_short_portraits() == [extra.id]
    assert len(portrait_calls(prov)) == 1
    pid = e.profiles[extra.id].portrait
    assert pid == f"npc:{extra.id}" and e.ctx.portrait_of(extra.id) is not None
    assert e.promote_short_portraits() == [] and len(portrait_calls(prov)) == 1  # once
    e.close()
    again = Engine.open_campaign("c", FakeProvider(script={}), root=tmp_path,
                                 models=ModelConfig(), judge=FakeJudge())
    assert again.profiles[extra.id].portrait == pid
    assert again.ctx.portrait_of(extra.id).core.startswith("A ferryman")  # cached, no call


def test_a_recurring_extra_gets_a_portrait_and_a_failure_is_not_retried():
    e, prov = engine({"extractor": ["not a portrait"]})
    extra = e.add_npc(e.fresh_npc("walkin1", "northern", sex="m"), appearance="худий візник")
    e.enter_scene(extra.id)
    e.leave_scene(extra.id)
    e.enter_scene(extra.id)                            # the second time: recurring
    assert e.promote_short_portraits() == []           # the call failed: manner stays
    assert len(portrait_calls(prov)) == 1 and not e.profiles[extra.id].portrait
    assert any(n["kind"] == "short_portrait_failed" for n in e.devlog)
    assert e.promote_short_portraits() == [] and len(portrait_calls(prov)) == 1


def test_canon_people_are_never_sent_for_a_short_portrait():
    e, prov = engine({"extractor": [REPLY]})
    e.profiles["velerad"] = CharacterProfile("velerad", "Велерад", "burgomaster",
                                             appearance="бургомістр")
    e.enter_scene("velerad")
    e.names.learn(PLAYER, "velerad", how="told", scene=e.scene)
    assert e.promote_short_portraits() == [] and portrait_calls(prov) == []


# -- the canon portraits of the world -----------------------------------------------------------

CANON = ("innkeeper_vizima", "velerad", "geralt_vidmak", "foltest")


def test_all_world_portraits_load_and_fit():
    from harness.context import PORTRAIT_HEAD
    from harness.glossary import Glossary
    from harness.portrait import MAX_WORDS, slice_text

    world = load_world_portraits("witcher")
    assert set(CANON) <= set(world)
    files = sorted((WORLDS / "witcher" / "portraits").glob("*.yaml"))
    assert len(files) == len(world)
    wrong = [w for e in Glossary.for_world("witcher").entries for w in e.wrong]
    budget = MAX_WORDS - len(PORTRAIT_HEAD.split())
    for p in world.values():
        assert {r for st in p.stances for r in st.rung} >= set(LADDER), p.id
        assert all(-0.5 <= sw.warmth <= 0.5 and -0.5 <= sw.trust <= 0.5 for sw in p.switches)
        assert all(sw.trigger.rstrip().endswith("?") for sw in p.switches), p.id
        for st in p.stances:
            text = slice_text(p, st, None, budget)
            assert len(text.split()) <= MAX_WORDS, (p.id, st.id)
            # nothing is trimmed: the stance's examples and tail reach the model whole
            assert all(x in text for x in st.examples[:2]) and st.tail in text, (p.id, st.id)
        flat = str(p)
        assert not any(w in flat for w in wrong), p.id
    for pid in CANON:
        p = world[pid]
        assert len(p.stances) >= 6 and len(p.switches) >= 5 and p.leaks, pid
        assert "Відьмак" in p.phase, pid


def test_the_innkeeper_answers_direct_questions():
    p = load_world_portraits("witcher")["innkeeper_vizima"]
    text = " ".join([p.core, p.voice, p.never] + [st.does for st in p.stances]).lower()
    assert "answers" in text and "direct question" in text
