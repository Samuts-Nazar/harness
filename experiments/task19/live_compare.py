"""Task 19 live comparison, usable on the old and the new code alike (it only uses what both have):
a 15-turn session of the inn campaign, per-turn seconds to the first word and to the end of the text,
the slow lane (new code only), prompt tokens, cached tokens and cost from the API's own usage.

    PYTHONPATH=<checkout> python experiments/task19/live_compare.py <label> [turns] [budget]

Writes $SESSION_OUT/<label>.json (default: a temp folder). Paid, cheap models only; capped.
"""
from __future__ import annotations

import faulthandler
import json
import os
import pathlib
import sys
import tempfile
import time

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))  # the checkout this file is in
from dotenv import load_dotenv  # noqa: E402

load_dotenv(".env")
load_dotenv("/home/cock/projects/harness/.env")  # a worktree or an export has no .env of its own
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness.policy import Spend  # noqa: E402

TURNS = [
    "Я струшую дощ із плаща, сідаю до столу й питаю Горста, чого він від мене хоче.",
    "Я дивлюсь на Ельзу й питаю її, що вона знає про млин.",
    "Я кладу руку на меч і кажу: спершу розкажіть мені все, потім говоритимемо про гроші.",
    "Я питаю Горста, скільки він готовий заплатити наперед.",
    "Я мовчки розглядаю кошіль і чекаю, що скаже Ельза.",
    "Я кажу Ельзі, що прийду на млин до світанку, але сам.",
    "Я питаю Горста, чи бачив він, хто саме знайшов мертвих хлопців.",
    "Я встаю з-за столу й підходжу до вікна, дивлюсь на греблю.",
    "Я розповідаю їм, що в Каер Морені навчають відьмаків розпізнавати такі сліди.",
    "Я питаю Ельзу, чи згадувала вона про Трісс Мерігольд, чародійку, яка проїздила тут.",
    "Я кажу Горсту, що гроші підуть наперед, або я не піду на млин взагалі.",
    "Я замовляю в корчмаря кухоль пива й чекаю на відповідь Горста.",
    "Я питаю обох, чи не бачили вони чужинців у Брідках цієї осені.",
    "Я піднімаюсь, беру меч і кажу, що йду на млин зараз, поки не стемніло.",
    "Я прошу Ельзу провести мене до греблі, а Горста — залишитись у корчмі.",
]

USAGE = {"prompt": 0, "cached": 0, "written": 0, "calls": 0}
_orig_add = Spend.add


def _add(self, usage):  # type: ignore[no-untyped-def]
    u = usage or {}
    det = u.get("prompt_tokens_details") or {}
    USAGE["prompt"] += int(u.get("prompt_tokens") or 0)
    USAGE["cached"] += int(det.get("cached_tokens") or 0)
    USAGE["written"] += int(det.get("cache_write_tokens") or 0)
    USAGE["calls"] += 1
    return _orig_add(self, u)


Spend.add = _add  # type: ignore[method-assign]


def main() -> None:
    faulthandler.dump_traceback_later(float(os.environ.get("DUMP_S", "90")), repeat=True)
    label = sys.argv[1]
    n = int(sys.argv[2]) if len(sys.argv) > 2 else 15
    budget = float(sys.argv[3]) if len(sys.argv) > 3 else 0.15
    stack = live_stack(budget)
    root = tempfile.mkdtemp(prefix=f"cmp-{label}-")
    game = Game(lambda new: open_campaign(stack, root=root, new=new, data_file=root + "/none"), pace=0.0)
    rows = []
    t_all = time.monotonic()
    for i, text in enumerate(TURNS[:n], 1):
        t0 = time.monotonic()
        game.start_turn(text)
        # the player "reads" for a moment, then types the next input (the slow lane runs meanwhile)
        deadline = time.monotonic() + 240
        while game.phase != "idle" and time.monotonic() < deadline:
            time.sleep(0.02)
        ready = round(time.monotonic() - t0, 2)             # until the player has everything to read
        game.wait_idle(240)
        done = round(time.monotonic() - t0, 2)               # until the turn is fully settled
        d = game.debug
        err = next((e for e in game.events_after(0) if e["type"] in ("error", "retract")), None)
        tm = d.get("timing", {})
        rows.append({"turn": i, "first_word_s": tm.get("first_word_s"), "ready_s": ready,
                     "settled_s": done, "slow_s": tm.get("slow_s"), "waited_s": tm.get("waited_s"),
                     "cost": d.get("cost"), "error": err and err.get("message"),
                     "speakers": [e["who"] for e in game.events_after(0) if e["type"] == "speaker"]})
        print(rows[-1], flush=True)
        part = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.gettempdir())) / f"{label}.partial.json"
        part.write_text(json.dumps({"rows": rows, "usage": USAGE}, ensure_ascii=False))
        if i < n:
            time.sleep(float(os.environ.get("READ_S", "0")))   # reading time before the next input
    import collections
    rec = game.camp.recorder
    roles = collections.Counter(c["role"].split(":")[0] for c in rec.calls)
    roles_s = collections.defaultdict(float)
    for c in rec.calls:
        roles_s[c["role"].split(":")[0]] += c["seconds"]
    tags = collections.Counter(j["tag"] for j in game.eng.judgments.entries)
    notes = collections.Counter(n["kind"] for n in game.eng.devlog)
    print("provider calls by role", dict(roles), {k: round(v, 1) for k, v in roles_s.items()})
    print("judgments by tag", dict(tags))
    print("devlog", dict(notes))
    out = {"label": label, "roles": roles, "tags": tags, "notes": notes, "rows": rows, "usage": USAGE, "spend": stack.spend.total,  # type: ignore[union-attr]
           "wall_s": round(time.monotonic() - t_all, 1),
           "cache_hit_rate": round(USAGE["cached"] / USAGE["prompt"], 3) if USAGE["prompt"] else None}
    p = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.mkdtemp())) / f"{label}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    ok = [r for r in rows if not r["error"]]
    f = [r["first_word_s"] for r in ok if r["first_word_s"] is not None]
    rd = [r["ready_s"] for r in ok]
    print(f"\n{label}: turns {len(ok)}/{n}  first word avg {sum(f) / max(len(f), 1):.1f}s  "
          f"ready avg {sum(rd) / max(len(rd), 1):.1f}s  settled avg "
          f"{sum(r['settled_s'] for r in ok) / max(len(ok), 1):.1f}s  prompt tokens {USAGE['prompt']} "
          f"cached {USAGE['cached']} ({out['cache_hit_rate']})  cost ${out['spend']:.4f}")
    print("saved", p)


if __name__ == "__main__":
    main()
