"""Scripted demo scene. Fake provider and fake judge by default: no network, no `.env`.

    nix develop --command python -m harness.demo            # offline, deterministic
    nix develop --command python -m harness.demo --live     # real cheap models (costs a little)

`--live` loads `.env` (OPENROUTER_API_KEY, never printed) and uses the allowed cheap models:
extractor, narrator, NPC lines and the escalation LLM are separately configurable; judgments go
to Jev first and escalate to the LLM below probability 0.8. A spend cap stops runaway costs.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .judge import EscalatingJudge, FakeJudge, Judge, JevJudge, LLMJudge
from .models import EQUIPMENT, INJURY, PLAYER, CharacterProfile, Scene, format_time
from .pipeline import Engine, ModelConfig
from .policy import (
    DEFAULT_EXTRACTOR, DEFAULT_JEV, DEFAULT_JUDGE_LLM, DEFAULT_NARRATOR, DEFAULT_NPC, Spend,
)
from .providers import FakeProvider, OpenRouterProvider, Provider
from .state import StateChange
from .streaming import InterruptHandle

PROFILES = [
    CharacterProfile(PLAYER, "Geralt", "A witcher."),
    CharacterProfile("innkeeper", "Innkeeper", "A gruff innkeeper who fears monsters."),
    CharacterProfile("bard", "Dandelion", "A cheerful, talkative bard."),
]

TURNS = [  # (player input, live-interrupt after N words or None)
    ("I step inside, shake the rain off my cloak and ask for a room.", None),
    ("I ask the innkeeper what has been going on around here lately.", None),
    ("I turn to the bard and ask what he knows about the old mill.", 5),
]


def _diff(facts=(), changes=()) -> str:
    return json.dumps({"new_facts": [
        {"content": c, "source": s, "notability": n} for c, s, n in facts],
        "state_changes": list(changes)})


def _narr(description, actions=(), speakers=()) -> str:
    return json.dumps({"description": description, "observable_actions": list(actions),
                       "speakers": list(speakers)})


def fake_stack() -> tuple[Provider, Judge, ModelConfig]:
    """Offline script. It deliberately includes a narrator that writes NPC speech and an NPC line
    that claims something the NPC could not know, so the rejection paths are visible."""
    provider = FakeProvider(script={
        "narrator": [
            _narr('Rain drums on the roof. The innkeeper mutters, "A witcher, gods help us."',
                  ["Geralt shakes the rain from his cloak"], ["innkeeper"]),  # speech: rejected
            _narr("Rain drums on the roof. The innkeeper eyes the blood on the blade.",
                  ["Geralt shakes the rain from his cloak"], ["innkeeper"]),
            _narr("The fire pops; the innkeeper wipes a mug and lowers his voice.",
                  ["The innkeeper glances at the cellar door"], ["innkeeper"]),
            _narr("The bard leans closer, grinning.",
                  ["Dandelion tunes his lute", "Geralt sheathes his sword"], ["bard"]),
        ],
        "npc": [
            "Ciri was seen at Kaer Morhen, everyone knows that.",  # unlearnable claim: regenerated
            "A witcher, with a drawn sword! I want no blood spilled in here.",
            "Something howled by the old mill last night and I have not slept since.",
            "Oh, I know that story, and it ends with the miller's daughter vanishing.",
        ],
        "extractor": [
            _diff([("The innkeeper does not want blood spilled in his inn", "innkeeper", 0.5)]),
            _diff([("Something howled by the old mill last night", "innkeeper", 0.6)]),
            _diff([("Dandelion says the old mill story ends with a vanished girl", "bard", 0.4)],
                  [{"character": PLAYER, "category": "equipment", "op": "remove",
                    "item": "a bloody drawn sword", "observable": True, "source": "action1"}]),
        ],
    })
    judge = FakeJudge({
        "narrator_speech": True,
        "unknown_claim": lambda q, st: "Ciri" in st[0].rsplit("Line:", 1)[1],
        "salience": lambda q, st: "Innkeeper" in q.text,
        "attitude_direction": "negative",
        "relationship_magnitude": 2,
    })
    return provider, judge, ModelConfig("narrator", "npc", "extractor", "judge")


def live_stack(a: argparse.Namespace) -> tuple[Provider, Judge, ModelConfig, Spend]:
    from dotenv import load_dotenv

    load_dotenv()  # network and secrets only with --live
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("--live needs OPENROUTER_API_KEY (env or .env)")
    spend = Spend(a.budget)
    provider = OpenRouterProvider(key, spend=spend)
    models = ModelConfig(a.narrator_model, a.npc_model, a.extractor_model, a.judge_model)
    judge = EscalatingJudge(JevJudge(key, a.jev_model, spend=spend),
                            LLMJudge(provider, models.judge))
    return provider, judge, models, spend


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--live", action="store_true", help="use the network (OpenRouter + Jev)")
    ap.add_argument("--narrator-model", default=DEFAULT_NARRATOR)
    ap.add_argument("--npc-model", default=DEFAULT_NPC)
    ap.add_argument("--extractor-model", default=DEFAULT_EXTRACTOR)
    ap.add_argument("--judge-model", default=DEFAULT_JUDGE_LLM, help="LLM for judge escalation")
    ap.add_argument("--jev-model", default=DEFAULT_JEV)
    ap.add_argument("--budget", type=float, default=0.25, help="USD cap for a live run")
    ap.add_argument("--campaign-dir", default="campaigns/demo")
    a = ap.parse_args(argv)

    spend = None
    if a.live:
        provider, judge, models, spend = live_stack(a)
    else:
        provider, judge, models = fake_stack()
    print(f"[mode: {'LIVE' if a.live else 'offline (fake provider, fake judge)'}]")

    camp = Path(a.campaign_dir)
    # the demo starts fresh; the log is in memory, so stale memory files would only confuse
    eng = Engine(provider, PROFILES, Scene("Roadside inn", ("innkeeper", "bard"), 18 * 60),
                 models=models, judge=judge, campaign_dir=camp)
    eng.facts.add_canon("Witchers hunt monsters for coin.", knowers=[("innkeeper", "told")])

    # Geralt arrives with a bloody drawn sword (observable) and an old scar (hidden)
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "a bloody drawn sword", True))
    eng.apply_state_change(StateChange(PLAYER, INJURY, "add", "an old scar under his shirt", False))
    print(f"\n== {format_time(eng.scene.time)}: Geralt walks in ==")
    eng.enter_scene(PLAYER)

    for text, cut in TURNS:
        print(f"\n> Geralt: {text}")
        h = InterruptHandle() if cut else None
        n = 0

        def on_word(npc: str, w: str) -> None:
            nonlocal n
            n += 1
            print(w, end=" ", flush=True)
            if cut and n == cut and h is not None:
                h.request()

        r = _run_turn(eng, text, h, on_word)
        print(f"\n[narration] {r.narration}")
        for act in r.actions:
            print(f"[action]    {act}")
        if r.interrupted:
            print("[interrupted; private intent:]",
                  [e.payload["text"] for e in eng.intents.pending("bard")])

    print("\n-- dev view: what each character knows (and from whom) --")
    for who in ("innkeeper", "bard", PLAYER):
        print(f"{who}:")
        for it in eng.deriver.derive(who, eng.scene.time).knows:
            src = f"  <- {it.knower.source}" if it.knower.source else ""
            print(f"  - {it.fact.content} [{it.knower.how}{src}]")
    print("\n-- dev view: engine notes (rejections, fallbacks) --")
    for note in eng.devlog:
        print(" ", {k: (v[:60] + '…' if isinstance(v, str) and len(v) > 60 else v)
                     for k, v in note.items()})
    print("\n-- dev view: judgments (tag, answer, probability, escalated) --")
    for j in eng.judgments.entries:
        print(f"  {j['tag']:<20} {str(j['answer']):<9} p={j['probability']:<5} "
              f"escalated={j['escalated']} [{j['backend']}]")
    print(f"\nmemory files: {camp / 'memory'}  (git-ignored)")
    if spend is not None:
        print(f"API spend this run: ${spend.total:.4f} over {spend.calls} calls")


def _run_turn(eng: Engine, text: str, h: InterruptHandle | None, on_word):  # type: ignore[no-untyped-def]
    print("Speech:", end=" ")
    return eng.turn(text, handle=h, on_word=on_word)


if __name__ == "__main__":
    main()
