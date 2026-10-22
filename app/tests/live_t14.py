"""Task 14 live check (paid, cheap models): 10 turns of the inn scene, once with the old NPC
context ("what you have said before": the last 10 own lines in full) and once with the new one
("already said in this scene", short, plus the points those lines made).

    nix develop --command python app/tests/live_t14.py old|new [turns] [budget]

Prints each NPC line and, per line, the overlap of its content words with the same NPC's earlier
lines (share of its content-word stems already used: a rough measure of "same advice in new
words"; the repetition metric of the engine only sees surface repeats), plus the engine's own
repetition score. Reading the transcript is the real judgement.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness import context  # noqa: E402
from harness.models import UTTERANCE  # noqa: E402,F401

TURNS = [
    "Я струшую дощ із плаща, сідаю до столу й питаю Горста, чого він від мене хоче.",
    "Я питаю Ельзу, що вона знає про млин.",
    "Я питаю Горста ще раз: що мені треба знати про той млин, перш ніж іти туди?",
    "Я кажу: порадьте мені, як підготуватись до ночі на млині.",
    "Що ви ще можете мені сказати про те, що там виє?",
    "Я питаю Ельзу, чи варто мені йти туди сьогодні.",
    "Я питаю Горста, на що мені розраховувати, якщо піду.",
    "Я кажу, що не поспішаю, й прошу ще раз пояснити, чого саме вони бояться.",
    "Є ще щось, що мені варто знати перед тим, як я вирішу?",
    "Я питаю обох: що б ви зробили на моєму місці?",
]


def old_already_said(self, character, mem, viewer):  # the task 12 rendering, for the baseline
    own = [e for e in self.log.active([UTTERANCE]) if e.payload.get("speaker") == character][-10:]
    return ["What you have said before:\n" + "\n".join(f"- {e.payload['text']}" for e in own)] if own else []


def stems(text: str) -> set[str]:
    return {w[:5] for w in re.findall(r"[а-яіїєґ']{4,}", text.lower())}


def main() -> None:
    mode = sys.argv[1] if len(sys.argv) > 1 else "new"
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 0.10
    if mode == "old":
        context.ContextBuilder._already_said = old_already_said  # type: ignore[method-assign]
    stack = live_stack(budget)
    root = tempfile.mkdtemp(prefix=f"live-t14-{mode}-")
    game = Game(lambda new: open_campaign(stack, root=root, new=new, data_file=root + "/none"),
                pace=0.0)
    prior: dict[str, set[str]] = {}
    overlaps: list[float] = []
    reps: list[float] = []
    for i, text in enumerate(TURNS[:n], 1):
        before = len(game.transcript)
        game.start_turn(text)
        game.wait_idle(240)
        err = next((e for e in game.events_after(0) if e["type"] == "error"), None)
        r = (game.debug.get("repetition") or {}).get("score")
        reps.append(r if r is not None else 0.0)
        print(f"\n== turn {i}: {text}  (rep {r}, cost ${game.debug['cost']:.4f}, err {err and err['message']})")
        for t in game.transcript[before:]:  # this turn's lines only
            if t["kind"] == "npc":
                s = stems(t["text"])
                seen = prior.setdefault(t["tok"], set())
                ov = len(s & seen) / len(s) if s else 0.0
                overlaps.append(ov)
                seen |= s
                print(f"  [{t['name']}] overlap={ov:.2f}  {t['text']}")
            elif t["kind"] == "narr":
                print(f"  (narration) {t['text'][:160]}")
    print(f"\nMODE {mode}: mean overlap with own earlier lines {sum(overlaps) / max(len(overlaps), 1):.3f} "
          f"over {len(overlaps)} lines; mean engine repetition {sum(reps) / max(len(reps), 1):.3f}; "
          f"spend ${stack.spend.total:.4f}")  # type: ignore[union-attr]
    out = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.mkdtemp())) / f"t14_{mode}.json"
    out.write_text(json.dumps({"overlaps": overlaps, "transcript": game.transcript}, ensure_ascii=False,
                              indent=1))
    print("saved", out)


if __name__ == "__main__":
    main()
