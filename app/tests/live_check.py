"""Live check (costs a little): 3 Ukrainian turns through the real Game session, no pacing, so the
numbers are engine latency. Prints seconds to first word and per turn, calls, cost.

    nix develop --command python app/tests/live_check.py
"""
from __future__ import annotations

import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import live_stack  # noqa: E402

TURNS = [
    "Я струшую дощ із плаща, сідаю до столу й питаю Горста, чого він від мене хоче.",
    "Я дивлюсь на Ельзу й питаю її, що вона знає про млин.",
    "Я кладу руку на меч і кажу: спершу розкажіть мені все, потім говоритимемо про гроші.",
]


def main() -> None:
    stack = live_stack(budget=0.25)
    root = tempfile.mkdtemp(prefix='live-check-')
    game = Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0)
    for i, text in enumerate(TURNS, 1):
        game.start_turn(text)
        game.wait_idle(180)
        d = game.debug
        err = next((e for e in game.events_after(0) if e["type"] == "error"), None)
        print(f"\n--- turn {i}: first word {d['timing']['first_word_s']} s, total "
              f"{d['timing']['total_s']} s, cost ${d['cost']:.4f}, error={err and err['message']}")
        for c in d["calls"]:
            print(f"    {c['role']:<18} {c['model']:<36} {c['seconds']:>5} s  ${c['cost']:.5f}")
        print(f"    judgments: {len(d['judgments'])}  notes: {[n['kind'] for n in d['notes']]}")
        for t in game.transcript[-3:]:
            print(f"    [{t['kind']}{':' + t['name'] if 'name' in t else ''}] {t['text'][:220]}")
    print(f"\ntotal spend ${stack.spend.total:.4f} over {stack.spend.calls} paid calls")  # type: ignore[union-attr]
    print("panel:", game.panel())


if __name__ == "__main__":
    main()
