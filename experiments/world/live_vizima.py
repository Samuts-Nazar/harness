"""Task 17 live check (paid, cheap models, budget 0.30 USD): a scripted player in Vizima.

    nix develop --command python experiments/world/live_vizima.py [budget]

A miracle in the tavern, leave for the lake shore, wait until morning, go to the market and talk
to the cloth seller. Prints what happened, then the world report (who knows what, which version,
what the authorities did) and the cost and latency of the world steps per in-world hour and day.
Writes the full result to $SESSION_OUT/vizima.json (default: a temp folder).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
load_dotenv("/home/cock/projects/harness/.env")  # a worktree has no .env of its own
from app.campaigns import Recorder  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness.glossary import Glossary  # noqa: E402
from harness.models import NARRATION, PLAYER, UTTERANCE  # noqa: E402
from harness.style import Style  # noqa: E402
from harness.world import pilot  # noqa: E402
from harness.world.world import World  # noqa: E402

TURNS = [
    "*Підношу руку над столом, і все пиво в корчмі, у кухлях і в діжці, на очах у всіх стає "
    "кров'ю. Мої очі спалахують жовтим.* Ось ваше пиво, люди. Пийте.",
    "*Невимушено виходжу з корчми й іду до берега озера.*",
    "*Сідаю на камінь біля води й чекаю до ранку.*",
    "*Підводжусь і йду на ринок.*",
    "Добрий ранок. Скажи, красуне, що нового в місті?",
]

TIMED: dict[str, list[tuple[float, float, int]]] = {}  # name -> [(seconds, cost, in-world minutes)]


def instrument(world: World, spend) -> None:  # type: ignore[no-untyped-def]
    depth = {"n": 0}

    def wrap(name: str) -> None:
        orig = getattr(world, name)

        def inner(*a, **kw):  # type: ignore[no-untyped-def]
            if depth["n"]:
                return orig(*a, **kw)
            depth["n"] += 1
            t0, c0, m0 = time.monotonic(), spend.total, world.now
            try:
                return orig(*a, **kw)
            finally:
                depth["n"] -= 1
                TIMED.setdefault(name, []).append(
                    (time.monotonic() - t0, spend.total - c0, world.now - m0))
        setattr(world, name, inner)

    for n in ("tick", "refresh_place", "interpret"):
        wrap(n)


def clock(t: int) -> str:
    d, r = divmod(t, 1440)
    return f"день {d + 1}, {r // 60:02d}:{r % 60:02d}"


def main() -> None:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 0.30
    stack = live_stack(budget)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    eng, world = pilot.build(rec, stack.judge, stack.models, style=Style.load("witcher"),
                             record_language="English", output_language="Ukrainian",
                             glossary=Glossary.for_world("witcher"))
    instrument(world, stack.spend)
    out: dict = {"turns": []}
    print(f"start: {clock(eng.scene.time)}, {eng.scene.location}")
    for i, text in enumerate(TURNS, 1):
        c0, t0, k0 = stack.spend.total, time.monotonic(), len(rec.calls)
        mark = max(e.id for e in eng.log.active())
        wt = world.play(text)
        print(f"\n== ход {i}: {text}\n   -> {clock(eng.scene.time)}, {eng.scene.location}"
              f" (план: {wt.plan.move}/{wt.plan.wait}/{wt.plan.duration}; "
              f"подорож/очікування {wt.waited} хв; стоп: {wt.interrupted_by})"
              f"  ${stack.spend.total - c0:.4f}  {time.monotonic() - t0:.1f} с")
        for e in eng.log.active([NARRATION, UTTERANCE]):
            if e.id > mark:
                who = e.payload.get("speaker")
                print(f"   [{eng.ctx.label(PLAYER, who) if who else 'оповідач'}] {e.payload['text'][:420]}")
        out["turns"].append({"text": text, "time": eng.scene.time, "place": eng.scene.location,
                             "plan": vars(wt.plan), "waited": wt.waited,
                             "cost": stack.spend.total - c0, "calls": len(rec.calls) - k0,
                             "report": world.report(mark)})
    rep = world.report(0)
    out["final_report"] = rep
    print("\n=========== СВІТ ===========")
    for n in rep["news"]:
        print(f"\nНовина #{n['id']} (гучність {n['notability']}): {n['text'][:160]}")
        for v in n["versions"]:
            print(f"  - {v['holder']} [{v['operator']}, {v['hops']} пер., від {v['source']}, "
                  f"{clock(v['at'])}, {v['stance']}]: {v['text'][:200]}")
        for h in n["heard_by"]:
            print(f"  * почув(ла) {h['person']} через {h['via']} ({clock(h['at'])})")
    print("\nВлада:")
    for r in rep["reactions"]:
        print(f"  - {clock(r['at'])} {r['authority']}: {r['kind']}: {r['text']}")
    for a in rep["arrivals"]:
        print(f"  - прибули {clock(a['at'])}: {a['text']}")
    print("\nПоза сценою:")
    for o in rep["offscreen"]:
        print(f"  - {clock(o['at'])} {o['character']}: {o['what']} ({o['place']})")
    print("\nХто що знає про подію (з бази):")
    for cid in ("innkeeper", "brann", "vatsko", "myrra", "sergeant", "col_town", "col_guard",
                "col_velerad", "col_king"):
        items = [f for f in eng.facts.visible_to(cid, eng.scene.time, store="campaign")
                 if any(w in f.content.lower() for w in ("blood", "beer", "кров", "пиво", "demon",
                                                         "демон", "report", "sent", "ordered"))]
        print(f"  {cid}: " + (" | ".join(
            f"{f.content[:110]} ({next(k for k in f.knowers if k.character == cid).how}"
            f"{', від ' + str(next(k for k in f.knowers if k.character == cid).source) if next(k for k in f.knowers if k.character == cid).source else ''})"
            for f in items) or "нічого"))

    print("\nНитки (відкриті):")
    for t in rep["threads"]:
        print(f"  - #{t['thread']} гучність {t['notability']} {t['participants']}: {t['text'][:100]}")
    # a skip of three days: what the cheap sim costs per in-world day once the news is processed
    c0, t0, m0 = stack.spend.total, time.monotonic(), eng.scene.time
    sk = world.skip_days(3)
    idle = {"minutes": eng.scene.time - m0, "cost": stack.spend.total - c0,
            "seconds": time.monotonic() - t0, "stopped": sk["stopped"]}
    print(f"\nпропуск днів: {idle['minutes']} хв ({idle['minutes'] / 1440:.1f} д), "
          f"${idle['cost']:.4f}, {idle['seconds']:.1f} с, зупинка: {idle['stopped']}")
    for e in sk["summaries"]:
        print("  підсумок:", e.payload["text"])
    out["skip"] = idle
    summary = {}
    for name, rows in TIMED.items():
        mins = sum(r[2] for r in rows)
        summary[name] = {"calls": len(rows), "seconds": sum(r[0] for r in rows),
                         "cost": sum(r[1] for r in rows), "in_world_minutes": mins}
        print(f"{name}: {len(rows)} викл., {summary[name]['seconds']:.1f} с, "
              f"${summary[name]['cost']:.4f}, {mins} хв світу")
    out["timed"] = summary
    out["timed_rows"] = TIMED
    print("\nкроки світу (c, $, хв світу):")
    for name, rows in TIMED.items():
        for sec, cost, mins in rows:
            print(f"  {name}: {sec:.1f} с, ${cost:.5f}, {mins} хв")
    out["spend"] = stack.spend.total
    out["calls_by_role"] = {}
    for c in rec.calls:
        r = out["calls_by_role"].setdefault(c["role"], {"n": 0, "cost": 0.0, "seconds": 0.0})
        r["n"] += 1
        r["cost"] += c["cost"]
        r["seconds"] += c["seconds"]
    print(f"\nвитрачено: ${stack.spend.total:.4f}")
    path = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.mkdtemp())) / "vizima.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print("saved", path)
    eng.close()


if __name__ == "__main__":
    main()
