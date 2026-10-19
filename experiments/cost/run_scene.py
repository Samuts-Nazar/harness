"""Live cost demo: 12 scripted player turns, a two-NPC exchange, second-hand knowledge.

    nix develop --command python -m experiments.cost.run_scene [--budget 0.35]
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path

from dotenv import load_dotenv

from harness.demo import PROFILES
from harness.judge import EscalatingJudge, JevJudge, LLMJudge
from harness.models import EQUIPMENT, INJURY, PLAYER, Scene
from harness.pipeline import Engine, ExtractionRejected, ModelConfig
from harness.policy import (
    DEFAULT_EXTRACTOR, DEFAULT_JEV, DEFAULT_JUDGE_LLM, DEFAULT_NARRATOR, DEFAULT_NPC, Spend,
)
from harness.state import StateChange

from . import meter

# (player input, forced speakers or None = narrator decides, note)
TURNS = [
    ("I step inside, shake the rain off my cloak and ask for a room.", None, ""),
    ("I ask the innkeeper what has been going on around here lately.", None, ""),
    ("I ask him how long the animals have been dying.", None, ""),
    ("I turn to the bard and ask what he knows about the old mill.", None, ""),
    ("I ask both of them together: who was the miller's daughter, and who saw her last?",
     ["innkeeper", "bard"], "two-NPC dialogue"),
    ("I ask the bard what the innkeeper just said about the howling.", ["bard"],
     "second-hand: bard heard it from the innkeeper"),
    ("I tell them I killed a drowner at the river crossing this afternoon, and show the claw.",
     None, ""),
    ("I ask the innkeeper whether he trusts what the bard says about the mill.", ["innkeeper"], ""),
    ("I ask the bard if he has heard anything about a witcher named Vesemir.", ["bard"],
     "unlearnable: should be refused/unknown"),
    ("I put a few coins on the bar and ask the innkeeper to send word to the village elder.",
     None, ""),
    ("I ask the bard to play something quiet while I clean my sword.", None, ""),
    ("I ask the innkeeper who else stayed here this week.", ["innkeeper"], ""),
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=float, default=0.35)
    ap.add_argument("--out", default="reports/cost/calls.jsonl")
    ap.add_argument("--narrator", default=DEFAULT_NARRATOR)
    ap.add_argument("--npc", default=DEFAULT_NPC)
    ap.add_argument("--extractor", default=DEFAULT_EXTRACTOR)
    a = ap.parse_args()
    load_dotenv()
    key = os.environ["OPENROUTER_API_KEY"]
    out = Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("")
    meter.LOG_PATH = out

    spend = Spend(a.budget)
    provider = meter.MeteredProvider(key, spend=spend)
    models = ModelConfig(a.narrator, a.npc, a.extractor, DEFAULT_JUDGE_LLM)
    llm_judge = LLMJudge(provider, models.judge)
    meter.tag(llm_judge, "ask", "judge_llm")
    judge = EscalatingJudge(JevJudge(key, DEFAULT_JEV, client=meter.MeteredClient(timeout=60),
                                     spend=spend), llm_judge)
    eng = Engine(provider, PROFILES, Scene("Roadside inn", ("innkeeper", "bard"), 18 * 60),
                 models=models, judge=judge, campaign_dir=Path("campaigns/cost-demo"))
    meter.tag(eng, "_narrate", "narrator")
    meter.tag(eng, "_npc_line", "npc")
    meter.tag(eng, "_extract", "extractor")
    meter.tag(eng, "_assess_attitudes", "attitude_judge")
    meter.tag(eng, "_observe", "salience_judge")

    eng.facts.add_canon("Witchers hunt monsters for coin.", knowers=[("innkeeper", "told")])
    eng.facts.add_canon(
        "For three nights running, sheep and a dog east of the village were found torn apart.",
        knowers=[("innkeeper", "told"), ("bard", "told")])
    eng.facts.add_canon(
        "The old mill east of the village stands empty since the miller's daughter vanished.",
        knowers=[("bard", "told"), ("innkeeper", "told")])
    # second-hand from the start: the bard only heard this from the innkeeper
    eng.facts.add_canon(
        "The miller's daughter was last seen walking toward the mill with a lantern at dusk.",
        knowers=[("innkeeper", "witnessed"), ("bard", "told", "innkeeper")])
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "a bloody drawn sword", True))
    eng.apply_state_change(StateChange(PLAYER, INJURY, "add", "an old scar under his shirt", False))
    eng.enter_scene(PLAYER)

    transcript = []
    for i, (text, speakers, note) in enumerate(TURNS, 1):
        meter.STATE["turn"] = i
        try:
            r = eng.turn(text, speakers)
        except ExtractionRejected as e:  # engine rolled the turn back; its calls were still paid
            transcript.append({"turn": i, "note": f"FAILED: ExtractionRejected: {e}", "player": text,
                               "narration": "", "lines": []})
            continue
        transcript.append({"turn": i, "note": note, "player": text, "narration": r.narration,
                           "lines": [(u.payload["speaker"], u.payload["text"]) for u in r.utterances]})
    meter.STATE["turn"] = 0
    import json
    (out.parent / "transcript.json").write_text(json.dumps(transcript, ensure_ascii=False, indent=1))
    (out.parent / "devlog.json").write_text(json.dumps(
        [d for d in eng.devlog], ensure_ascii=False, indent=1, default=str))
    print(f"spend ${spend.total:.4f} over {spend.calls} calls; log {out}")


if __name__ == "__main__":
    main()
