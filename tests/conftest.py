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


def diff(*facts: dict) -> str:
    return json.dumps({"new_facts": list(facts)})


def fact(content, source, knowers, notability=0.5):
    return {
        "content": content,
        "source": source,
        "knowers": [{"character": c, "how": h} for c, h in knowers],
        "notability": notability,
    }


def make_engine(script, present=(PLAYER, "innkeeper", "bard"), **kw):
    provider = FakeProvider(script=script)
    scene = Scene("Inn", tuple(present), time=0)
    eng = Engine(provider, PROFILES, scene, models=ModelConfig(), **kw)
    return eng, provider
