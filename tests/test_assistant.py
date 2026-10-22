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
    assert count_since(eng, 0, 0, mark).llm_calls_by_role == {"assistant": 1}


def test_avoid_is_in_the_prompt_and_filtered_from_the_answer():
    eng, _ = make({})
    spy = Spy(eng.provider)
    eng.provider = spy
    out = assistant.suggest(eng, 3, avoid=["*оглядається*"])
    assert "- *оглядається*" in spy.prompts[-1]
    assert "*оглядається*" not in out and out
