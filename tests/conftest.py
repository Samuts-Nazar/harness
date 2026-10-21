import json

import pytest

from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import FakeProvider

PROFILES = [
    CharacterProfile(PLAYER, "Geralt", "A witcher."),
    CharacterProfile("innkeeper", "Innkeeper", "Gruff innkeeper."),
    CharacterProfile("bard", "Dandelion", "A cheerful bard."),
    CharacterProfile("spy", "Spy", "Hidden in the next room."),
]


def diff(*facts: dict, changes: tuple = ()) -> str:
    return json.dumps({"new_facts": list(facts), "state_changes": list(changes)})


def fact(content, source, notability=0.5):
    """An extractor fact. Knowers are not part of the schema: code computes perception."""
    return {"content": content, "source": source, "notability": notability}


def change(character, category, op, item, source, observable=True):
    return {"character": character, "category": category, "op": op, "item": item,
            "observable": observable, "source": source}


def narr(description="N.", actions=(), speakers=()):
    return json.dumps({"description": description, "observable_actions": list(actions),
                       "speakers": list(speakers)})


def _wrap(script):
    """Plain-text narrator replies in a script become `{"description": ...}` JSON."""
    out = dict(script)
    out["narrator"] = [n if isinstance(n, Exception) or n.lstrip().startswith("{") else narr(n) for n in script.get("narrator", [])]
    return out


def make_engine(script, present=(PLAYER, "innkeeper", "bard"), outside=(), **kw):
    provider = FakeProvider(script=_wrap(script))
    scene = Scene("Inn", tuple(present), time=0, outside=tuple(outside))
    kw.setdefault("narration", "json")  # these tests script the task 3 JSON narrator
    kw.setdefault("record_language", None)
    eng = Engine(provider, PROFILES, scene, models=ModelConfig(), **kw)
    return eng, provider


@pytest.fixture(autouse=True)
def price_catalog():
    """Prices come from a fixture, never from the network."""
    from pathlib import Path

    from harness import policy

    policy.set_catalog(json.loads((Path(__file__).parent / "fixtures" / "catalog.json").read_text()))
    yield
    policy.set_catalog(None)


# Modules whose fake judges script the task 12 director ("director_first" / "director_also",
# at most MAX_SPEAKERS). They are the classic-mode regression suite: run unchanged with
# `dialogue="classic"` as the engine default (living dialogue, task LD-4). Every other module runs
# with the real default, "living"; tests/test_exchange.py covers the living exchange loop.
CLASSIC_DIRECTOR_MODULES = {
    "test_prose", "test_task19_turn", "test_glossary_repetition", "test_style", "test_decisions",
    "test_eval_sessions",
}


@pytest.fixture(autouse=True)
def classic_director_default(request, monkeypatch):
    if request.module.__name__ in CLASSIC_DIRECTOR_MODULES:
        monkeypatch.setitem(Engine.__init__.__kwdefaults__, "dialogue", "classic")
    yield
