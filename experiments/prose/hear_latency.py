"""Latency cost of NPCs hearing each other: 2-speaker turns, hear_each_other True vs False, live,
pace 0 (so the time of a speaker's first word is the time its line was ready).

    nix develop --command python -m experiments.prose.hear_latency [turns_per_mode]
"""
import statistics as st
import sys
import tempfile
import time

from app.campaigns import open_campaign
from app.stacks import live_stack

PLAYER_LINES = [
    "Я кажу обом: хтось із вас бреше про те, що виє на млині.",
    "Я питаю, хто з вас першим почув виття.",
    "Я кладу на стіл дві монети й питаю, кому вірити.",
    "Я питаю, чому ви обоє боїтесь млина.",
    "Я кажу, що піду на млин сам, і дивлюсь на вас обох.",
    "Я питаю обох, що вони бачили біля греблі.",
]


def run(hear: bool, n: int):
    stack = live_stack(0.15)
    camp = open_campaign(stack, root=tempfile.mkdtemp(), new=True)
    eng = camp.engine
    eng.hear_each_other = hear
    rows = []
    for text in PLAYER_LINES[:n]:
        t0 = time.monotonic()
        marks = {}

        def on_word(who, w):
            marks.setdefault(who, round(time.monotonic() - t0, 2))

        eng.turn(text, speakers=["horst", "elza"], on_word=on_word)
        rows.append((marks.get("horst"), marks.get("elza"), round(time.monotonic() - t0, 2)))
    return rows, stack.spend.total


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 4
    for hear in (False, True):
        rows, cost = run(hear, n)
        print("hear_each_other", hear, "cost", round(cost, 4))
        for r in rows:
            print("   first speaker ready %ss, second ready %ss, turn total %ss" % r)
        print("   mean: first %.1f, second %.1f, total %.1f" % tuple(
            st.mean(r[i] for r in rows if r[i] is not None) for i in range(3)))
