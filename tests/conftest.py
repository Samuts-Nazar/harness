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
    out["narrator"] = [n if n.lstrip().startswith("{") else narr(n) for n in script.get("narrator", [])]
    return out


def make_engine(script, present=(PLAYER, "innkeeper", "bard"), outside=(), **kw):
    provider = FakeProvider(script=_wrap(script))
    scene = Scene("Inn", tuple(present), time=0, outside=tuple(outside))
    eng = Engine(provider, PROFILES, scene, models=ModelConfig(), **kw)
    return eng, provider
