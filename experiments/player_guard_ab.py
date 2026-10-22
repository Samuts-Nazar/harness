"""A/B live check: the narrator with the old prompt and no post-check (A) vs the new rule and the
player guard (B). Narrator only (Engine._narrate), a temp campaign, ten tempting inputs.

  nix develop --command python experiments/player_guard_ab.py OUT.json

Prints raw (before guard) and final text per input; the violations are graded by reading them.
"""
from __future__ import annotations

import json
import sys

from app.stacks import live_stack
from harness import context, pipeline
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine
from harness.player_guard import flag_player_acts, split_sentences, strip_player_quotes

INPUTS = [
    "Іду на ринок.",
    "Виходжу на вулицю.",
    "Входжу й кажу: «Пані чародійко, мені сказали, що ви можете допомогти.»",
    "Кажу: «Добрий вечір.»",
    "Підходжу до столу.",
    "Сідаю.",
    "Питаю корчмаря: «Скільки коштує ніч?»",
    "Іду до річки.",
    "Відчиняю двері й кажу: «Є хто вдома?»",
    "Чекаю до ранку.",
]
PROFILES = [
    CharacterProfile(PLAYER, "Мирослав", "Мандрівник."),
    CharacterProfile("innkeeper", "Корчмар", "Похмурий корчмар."),
    CharacterProfile("witch", "Чародійка", "Стара чародійка."),
]


def run(arm: str, stack) -> list[dict]:
    old_rule = context.PLAYER_CHARACTER_RULE
    if arm == "A":
        context.PLAYER_CHARACTER_RULE = ""
        pipeline.PLAYER_CHARACTER_RULE = ""
    eng = Engine(stack.provider, PROFILES, Scene("корчма «Під Лисом»", (PLAYER, "innkeeper"), time=0),
                 models=stack.models, judge=stack.judge, narration="prose",
                 output_language="Ukrainian", record_language=None)
    if arm == "A":
        eng._start_player_act_check = lambda *a, **k: None  # type: ignore[method-assign]
        pipeline.strip_player_quotes = lambda t, p: (t, [])
    raw: list[str] = []
    inner = eng._complete_text
    eng._complete_text = lambda role, m: raw.append(inner(role, m)) or raw[-1]  # type: ignore
    rows = []
    for text in INPUTS:
        raw.clear()
        out = eng._narrate(text)
        first = eng._prose_of(raw[0]) if raw else ""
        stripped, quotes = strip_player_quotes(first, text)
        flagged = [s.strip() for i, s in enumerate(split_sentences(stripped))
                   if i in flag_player_acts(split_sentences(stripped), "Мирослав")]
        rows.append({"arm": arm, "input": text, "raw": first, "final": out.description,
                     "raw_quotes_of_player": quotes, "raw_flagged": flagged,
                     "dropped": [n for n in eng.devlog if n["kind"] == "narrator_player_action_dropped"]})
        eng.devlog.clear()
    context.PLAYER_CHARACTER_RULE = old_rule
    pipeline.PLAYER_CHARACTER_RULE = old_rule
    pipeline.strip_player_quotes = strip_player_quotes
    return rows


if __name__ == "__main__":
    stack = live_stack(0.09)
    rows = run("A", stack) + run("B", stack)
    json.dump(rows, open(sys.argv[1], "w"), ensure_ascii=False, indent=1)
    print("spent", stack.spend.total if hasattr(stack.spend, "total") else stack.spend)
