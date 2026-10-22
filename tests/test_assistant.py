"""Turn assistant: the context is the player character's view; parsing; the decision count."""
from harness import assistant
from harness.decisions import count_since
from harness.models import PLAYER
from test_names import HORST, make


def prompt_of(prov) -> str:
    return "\n".join(m["content"] for m in prov.calls[-1][1]) if isinstance(prov.calls[-1], tuple) \
        else str(prov.calls[-1])


class Spy:
    """Wraps a provider and records every prompt."""
    def __init__(self, inner):
        self.inner, self.prompts, self.models = inner, [], []

    def complete(self, model, messages):
        self.prompts.append("\n".join(m["content"] for m in messages))
        self.models.append(model)
        return "*оглядається*\n1. Що вам потрібно?\n- «Я слухаю»\n*оглядається*"

    def stream(self, model, messages):
        yield self.complete(model, messages)


def test_suggest_sees_only_player_view():
    eng, _ = make({})
    eng.facts.add_canon("The player knows the road to Брідки is flooded.", knowers=[(PLAYER, "told")])
    eng.facts.add_canon("Горст hides a ZXQ-SECRET key under the floor.", knowers=[("horst", "told")])
    eng.facts.add_canon("Ельза fears QQV-DEEPFEAR of the mill.", knowers=[("elza", "told")])
    spy = Spy(eng.provider)
    eng.provider = spy
    out = assistant.suggest(eng, 3)
    text = spy.prompts[-1]
    assert "road to Брідки is flooded" in text
    assert "ZXQ-SECRET" not in text and "QQV-DEEPFEAR" not in text
    assert "Горст" not in text and "Ельза" not in text, "names the player has not learned"
    assert HORST in text, "seen by appearance instead"
    assert out == ["*оглядається*", "Що вам потрібно?", "Я слухаю"], "bullets, quotes, repeats out"


def test_suggest_counts_as_an_assistant_call_and_writes_nothing():
    eng, _ = make({})
    spy = Spy(eng.provider)
    eng.provider = spy
    before_events = len(eng.log.active())
    mark = len(eng.llm_calls)
    assistant.suggest(eng, 3)
    assert len(eng.log.active()) == before_events, "drafts are not part of the log"
    assert eng.assistant_calls == ["assistant"]
    assert count_since(eng, 0, 0, mark).llm_calls_by_role == {}, "never inside a turn's counts"
    assert eng.devlog == [] or all(n["kind"] != "model_fallback" for n in eng.devlog)


def test_prompt_forbids_feelings_and_outcomes():
    eng, _ = make({})
    spy = Spy(eng.provider)
    eng.provider = spy
    assistant.suggest(eng, 3)
    text = spy.prompts[-1]
    assert "Never feelings" in text and "Never outcomes" in text
    assert "*відчуває страх*" in text and "feels" in text  # the unknown name is masked, fine
    assert "*вбиває Горста*" in assistant.SYSTEM


def test_assistant_call_after_the_marks_does_not_change_the_turn_decisions():
    eng, _ = make({})
    spy = Spy(eng.provider)
    eng.provider = spy
    marks = (len(eng.judgments.entries), len(eng.llm_calls), len(eng.devlog))
    assistant.suggest(eng, 3)  # lands after the next turn took its marks
    d = count_since(eng, 0, *marks[:2], marks[2])
    assert d.total == 0 and d.llm_calls_by_role == {}


def test_avoid_is_in_the_prompt_and_filtered_from_the_answer():
    eng, _ = make({})
    spy = Spy(eng.provider)
    eng.provider = spy
    out = assistant.suggest(eng, 3, avoid=["*оглядається*"])
    assert "- *оглядається*" in spy.prompts[-1]
    assert "*оглядається*" not in out and out


def test_content_limits_reach_the_assistant_prompt():
    """Final review, finding 7: the campaign's content limits are in the assistant's SYSTEM."""
    eng, _ = make({})
    eng.ctx.limits = "No gore. ZQ-LIMIT-MARK."
    spy = Spy(eng.provider)
    eng.provider = spy
    ctx = assistant.context(eng)
    assert "ZQ-LIMIT-MARK" in ctx.system
    assistant.ask(eng, ctx, 3)
    assert "ZQ-LIMIT-MARK" in spy.prompts[-1]


class NamingSpy(Spy):
    def complete(self, model, messages):
        self.prompts.append("\n".join(m["content"] for m in messages))
        return "Горсте, налий ще.\n*киває Горстові*\nЩо скажете?"


def test_suggestions_mask_names_the_player_character_does_not_know():
    """Finding 7: a suggestion naming an unlearned character is masked like the feed, with the
    known snapshot taken when the context was rendered (ask runs on a thread of its own)."""
    eng, _ = make({})
    eng.provider = NamingSpy(eng.provider)
    ctx = assistant.context(eng)
    assert ctx.known is not None and "horst" not in ctx.known
    out = assistant.ask(eng, ctx, 3)
    assert out and not any("Горст" in s for s in out), out
    assert any(HORST.lower() in s.lower() for s in out), out


class VeleradSpy:
    def __init__(self, inner):
        self.inner = inner

    def complete(self, model, messages):
        return "Скажи, а що ти знаєш про Велерада?\n*оглядається*\nЩо скажете?"


def test_suggestions_drop_a_character_name_the_context_never_gave():
    """Smoke 2026-10-22: the model knows the books and offered «що ти знаєш про Велерада?». That
    character has no appearance, so the name mask does not hide him; but his name was nowhere in
    what the player character knows, so a line that says it is dropped."""
    from harness.models import CharacterProfile
    eng, _ = make({})
    eng.profiles["velerad"] = CharacterProfile("velerad", "Велерад", "Радник короля.")
    eng.provider = VeleradSpy(eng.provider)
    out = assistant.ask(eng, assistant.context(eng), 3)
    assert out == ["*оглядається*", "Що скажете?"]
    # a name the context did give stays
    eng.facts.add_canon("The player was told that Велерад keeps the city order.",
                        knowers=[(PLAYER, "told")])
    assert any("Велерада" in s for s in assistant.ask(eng, assistant.context(eng), 3))
