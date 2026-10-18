"""Scripted demo scene. Fake provider by default; OpenRouter if OPENROUTER_API_KEY is set.

    nix develop --command python -m harness.demo
"""
from __future__ import annotations

import json
import os

from dotenv import load_dotenv

from .models import PLAYER, CharacterProfile, Scene, format_time
from .pipeline import Engine, ModelConfig
from .providers import FakeProvider, OpenRouterProvider, Provider
from .streaming import InterruptHandle

PROFILES = [
    CharacterProfile(PLAYER, "Geralt", "A witcher."),
    CharacterProfile("innkeeper", "Innkeeper", "A gruff innkeeper who fears monsters."),
    CharacterProfile("bard", "Dandelion", "A cheerful, talkative bard."),
]


def _facts(*items: tuple[str, str, list[tuple[str, str]], float]) -> str:
    return json.dumps({"new_facts": [
        {"content": c, "source": s,
         "knowers": [{"character": ch, "how": h} for ch, h in ks], "notability": n}
        for c, s, ks, n in items]})


def fake_provider() -> FakeProvider:
    return FakeProvider(script={
        "narrator": [
            "Rain drums on the roof of the inn as Geralt shakes water from his cloak.",
            "The fire pops. The bard leans closer, grinning.",
        ],
        "npc": [
            "A witcher! Last night something howled by the old mill and I have not slept since.",
            "Oh, I know that story, and it ends with the miller's daughter vanishing.",
        ],
        "extractor": [
            _facts(("Something howled by the old mill last night", "innkeeper",
                    [("innkeeper", "witnessed"), (PLAYER, "heard")], 0.6)),
            _facts(("Dandelion says he knows a story about the old mill", "bard",
                    [("bard", "witnessed"), (PLAYER, "heard")], 0.4)),
            _facts(),
        ],
    })


def build_provider() -> tuple[Provider, ModelConfig, bool]:
    load_dotenv()
    if os.environ.get("OPENROUTER_API_KEY"):
        m = os.environ.get("HARNESS_MODEL", "anthropic/claude-sonnet-4.5")
        return OpenRouterProvider(), ModelConfig(m, m, m), True
    return fake_provider(), ModelConfig(), False


def main() -> None:
    provider, models, live = build_provider()
    print(f"[provider: {'OpenRouter' if live else 'fake'}]\n")
    eng = Engine(provider, PROFILES, Scene("Roadside inn", (PLAYER, "innkeeper", "bard"), 18 * 60),
                 models=models)
    eng.facts.add_canon("Witchers hunt monsters for coin.", knowers=[("innkeeper", "told")])

    print(f"== {format_time(eng.scene.time)} ==")
    print("> Geralt: I need a room and a hot meal.")
    r = eng.turn("I need a room and a hot meal.", speakers=["innkeeper"])
    print(r.narration)
    print("Innkeeper:", end=" ")
    for u in r.utterances:
        print(u.payload["text"])

    print("\n> Geralt: What is the bard saying?  (live interrupt after 5 words)")
    h = InterruptHandle()
    n = 0

    def cut_after_5(npc: str, w: str) -> None:
        nonlocal n
        n += 1
        print(w, end=" ", flush=True)
        if n == 5:
            h.request()

    print("Dandelion:", end=" ")
    r = eng.turn("What does the bard say?", speakers=["bard"], handle=h, on_word=cut_after_5)
    print("\n[narration]", r.narration)
    print("[interrupted:", r.interrupted, "]")
    print("[Dandelion's private intent:]",
          [e.payload["text"] for e in eng.intents.pending("bard")])

    print("\n-- dev view: facts known to the Innkeeper vs. the Bard --")
    for who in ("innkeeper", "bard"):
        print(f"{who}:")
        for f in eng.facts.visible_to(who, eng.scene.time):
            print("  -", f.content)


if __name__ == "__main__":
    main()
