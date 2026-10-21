"""Task 19: how often does the engine's own claim-check judge agree with a hand grading?

Replays the recorded live Vizima session offline (no cost), then asks the live judge (first-line
decider, LLM escalation) the engine's own "does this line assert something the character had no
channel to learn" question for every NPC line, with the character's knowledge as the context, and
compares it with the grading below (made by the Claude Code agent reading the whole session, not by
an API model).

    PYTHONPATH=. python experiments/task19/judge_agreement.py <cassette.jsonl>
"""
from __future__ import annotations

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/cock/projects/harness/.env")
from app.stacks import live_stack  # noqa: E402
from harness.evalkit import session  # noqa: E402
from harness.evalkit.checks import Labelled, agreement  # noqa: E402
from harness.models import PLAYER, UTTERANCE  # noqa: E402
from harness.pipeline import UNKNOWN_CLAIM_Q  # noqa: E402

# event id of the NPC line -> True if the line states something its speaker had no channel to learn.
# 171: the cloth seller says the guard "lies under the table now"; she was never in the tavern and
# nobody told her. Every other line is a reaction to what the character saw, was told, or ordinary
# background of their trade.
LEAK = {171}


def main() -> None:
    game, info = session.replay(sys.argv[1])
    assert info["same_story"] and not info["misses"]
    eng = game.eng
    items = []
    for e in eng.log.active([UTTERANCE]):
        who = e.payload.get("speaker")
        if who in (None, PLAYER) or who not in eng.profiles:
            continue
        view = eng.ctx.character_view(who, eng.scene)
        items.append(Labelled(str(e.id), view.check_prefix() + e.payload["text"], UNKNOWN_CLAIM_Q,
                              e.id in LEAK))
    stack = live_stack(0.10)
    res = agreement(stack.judge, items, tag="unknown_claim")
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}))
    print("disagreements:", [r for r in res["rows"] if r["got"] != r["expected"]])
    print("spend", round(stack.spend.total, 4))  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
