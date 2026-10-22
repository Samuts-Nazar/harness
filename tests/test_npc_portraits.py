"""Character portraits task 5: short portraits for invented NPCs who matter (one extractor-role
call, cached in the campaign), and the canon portraits of the Vizima arc in the world folder."""
import pytest

from harness.judge import FakeJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.npcgen import PORTRAIT_PREFIX, generate_npc, short_portrait
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
    assert seen[0][0]["content"].startswith(PORTRAIT_PREFIX)
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
    return [m for _, m in prov.calls if m[0]["content"].startswith(PORTRAIT_PREFIX)]


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


# -- fix round 1 ------------------------------------------------------------------------------

@pytest.mark.parametrize("pid,client", [("innkeeper_vizima", "keeper_client"),
                                        ("velerad", "velerad_client"),
                                        ("foltest", "foltest_client"),
                                        ("geralt_vidmak", "geralt_client")])
def test_client_with_an_audience_plays_the_client_stance(pid, client):
    from harness.portrait import Situation, select_stance
    p = load_world_portraits("witcher")[pid]
    crowd = Situation("even", True, "low")
    assert select_stance(p, "client", crowd).id == client
    assert "crowd" in select_stance(p, "stranger", crowd).id or \
        "court" in select_stance(p, "stranger", crowd).id


def test_failure_note_carries_the_reason():
    e, prov = engine({"extractor": ["not a portrait"]})
    extra = e.add_npc(e.fresh_npc("walkin1", "northern", sex="m"), appearance="візник")
    e.enter_scene(extra.id)
    e.leave_scene(extra.id)
    e.enter_scene(extra.id)
    e.promote_short_portraits()
    note = next(n for n in e.devlog if n["kind"] == "short_portrait_failed")
    assert "unparseable" in note["reason"]


def test_a_bad_cached_portrait_does_not_stop_the_campaign_opening(tmp_path):
    e, prov = engine({"extractor": [REPLY]}, tmp_path)
    extra = e.add_npc(e.fresh_npc("walkin1", "northern", sex="m"), appearance="худий візник")
    e.enter_scene(extra.id)
    e.names.learn(PLAYER, extra.id, how="told", scene=e.scene)
    e.promote_short_portraits()
    with e.conn:
        e.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                       ("short_portraits", '{"%s": {"id": "npc:%s"}}' % (extra.id, extra.id)))
    e.close()
    again = Engine.open_campaign("c", FakeProvider(script={}), root=tmp_path,
                                 models=ModelConfig(), judge=FakeJudge())
    assert again.ctx.portrait_of(extra.id) is None
    assert any(n["kind"] == "short_portrait_unreadable" for n in again.devlog)


# -- final review fix wave ----------------------------------------------------------------------

def test_at_most_two_portraits_per_settle_the_rest_follow():
    e, prov = engine({"extractor": [REPLY] * 6})
    ids = []
    for i in range(6):
        x = e.add_npc(e.fresh_npc(f"p{i}", "northern", sex="m"), appearance=f"гість {i}")
        e.enter_scene(x.id)
        e.names.learn(PLAYER, x.id, how="told", scene=e.scene)
        ids.append(x.id)
    got = []
    for _ in range(4):
        before = len(portrait_calls(prov))
        done = e.promote_short_portraits()
        assert len(portrait_calls(prov)) - before <= 2 and len(done) <= 2
        got += done
    assert sorted(got) == sorted(ids) and len(portrait_calls(prov)) == 6


def test_a_promotion_error_is_noted_not_raised(monkeypatch):
    e, _ = engine({"extractor": [REPLY]})
    monkeypatch.setattr(e, "promote_short_portraits", lambda: 1 / 0)
    e._promote_portraits()
    assert any(n["kind"] == "short_portraits_failed" for n in e.devlog)


def test_an_overlong_generated_portrait_is_capped_and_keeps_never():
    from harness.context import PORTRAIT_HEAD
    from harness.portrait import MAX_WORDS, slice_text
    long = " ".join(["слово"] * 300)
    reply = REPLY.replace("A ferryman who owes everyone a little and trusts nobody with the oar.", long)
    reply = reply.replace("Never begs, never names who pays him for the letters.", long)
    reply = reply.replace("Lines of about 8 words; numbers first; «ти» only to friends.", long)
    reply = reply.replace("Answers what is asked, names the fare first, keeps the oar between them.", long)
    p = short_portrait(spec(), None, lambda m: reply)
    assert p is not None and len(p.never.split()) <= 30 and len(p.core.split()) <= 40
    budget = MAX_WORDS - len(PORTRAIT_HEAD.split())
    for st in p.stances:
        text = slice_text(p, st, p.leaks[0] if p.leaks else None, budget)
        assert len(text.split()) <= budget and p.never in text, st.id
        assert all(x in text for x in st.examples) and p.leaks[0] in text


def test_last_resort_cut_keeps_never_and_drops_the_leak_first():
    from harness.portrait import parse_portrait, slice_text
    p = load_world_portraits("witcher")["velerad"]
    st = p.stances[0]
    text = slice_text(p, st, "LEAKLINE one two", 60)
    assert p.never in text and "LEAKLINE" not in text and len(text.split()) <= 60
    tight = slice_text(p, st, None, len(p.never.split()) + 5)
    assert p.never in tight


def test_null_and_blank_fields_skip_the_item_not_the_portrait():
    more = REPLY.replace("switches:", """  - id: extra
    rung: [close]
    does: Shares the bench.
    sounds: Quiet.
switches:""").replace("hidden:", """  - id: broken
    trigger:
    warmth: 0.1
    trust: 0.1
  - id: fourth
    trigger: Did the player share bread?
    warmth: 0.1
    trust: 0.1
hidden:""")
    bad = more.replace("    does: Quiet, rough tenderness; brings food without a word.\n", "    does:\n")
    p = short_portrait(spec(), None, lambda m: bad)
    assert p is not None
    assert [st.id for st in p.stances] == ["wary", "easy", "extra"]
    assert len(p.switches) == 4 and all("None" not in st.does for st in p.stances)


def test_too_few_usable_items_is_a_failure_with_a_reason():
    bad = REPLY.replace("    does: Quiet, rough tenderness; brings food without a word.\n",
                        "    does:\n")
    why = []
    assert short_portrait(spec(), None, lambda m: bad, on_fail=why.append) is None
    assert why and "too thin" in why[0]
