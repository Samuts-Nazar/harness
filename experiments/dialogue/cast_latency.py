"""Seconds to the first word on the Vizima campaign (the app default) with the scene cast review on
and off (final review of the living-dialogue branch): 5 scripted turns each, live models.

    python -m experiments.dialogue.cast_latency

Raw results go to /home/cock/projects/harness/campaigns/ld/cast_latency.json (git-ignored). The
key is read from the .env by absolute path and never printed. Spend cap 0.06 USD for both runs.
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ABS = Path("/home/cock/projects/harness")
OUT = ABS / "campaigns" / "ld"
CANON = ABS / "campaigns" / "canon" / "pilot_v3.db"
CAP = 0.06
TURNS = [
    "Підходжу до стійки й замовляю пива.",
    "Що чути в місті, господарю?",
    "*Сідаю за вільний стіл біля вікна й роззираюся.*",
    "Гей, стражнику, що там сталося за палацовим муром?",
    "А про білоголового чужинця що кажуть?",
]


def run(cast_on: bool, stack) -> dict:
    from app.vizima import open_vizima
    camp = open_vizima(stack, root=OUT / "vizima", new=True, canon_db=CANON,
                       name=f"lat-{'on' if cast_on else 'off'}-{int(time.time())}")
    eng, world = camp.engine, camp.world
    if not cast_on:
        eng.scene_cast = None
    rows = []
    for text in TURNS:
        t0 = time.monotonic()
        first: list[float] = []

        def mark(*_a) -> None:
            if not first:
                first.append(time.monotonic() - t0)

        cost0 = stack.spend.total
        dev0 = len(eng.devlog)
        r = world.play(text, defer_slow=True, on_word=lambda n, w: mark(),
                       on_narration=lambda s: mark() if s.strip() else None).result
        fast = time.monotonic() - t0
        eng.settle()
        notes = [n["kind"] for n in eng.devlog[dev0:]]
        rows.append({"player": text, "first_word_s": round(first[0], 2) if first else None,
                     "fast_s": round(fast, 2), "lines": len(r.utterances),
                     "narrated": bool(r.narration.strip()),
                     "cast_notes": {k: notes.count(k) for k in set(notes) if k.startswith("scene_cast")
                                    or k.startswith("narrator_absent")},
                     "present": len(eng.scene.present), "cost": round(stack.spend.total - cost0, 5)})
        print(f"[cast {'on' if cast_on else 'off'}] {rows[-1]}", flush=True)
    eng.close()
    fw = [r["first_word_s"] for r in rows if r["first_word_s"] is not None]
    return {"cast": cast_on, "turns": rows,
            "first_word_median_s": statistics.median(fw) if fw else None,
            "first_word_mean_s": round(statistics.mean(fw), 2) if fw else None,
            "first_word_max_s": max(fw) if fw else None,
            "present_start_end": [rows[0]["present"], rows[-1]["present"]]}


def main(argv: list[str]) -> int:
    from dotenv import load_dotenv
    load_dotenv(ABS / ".env")
    from app.stacks import live_stack
    stack = live_stack(CAP)
    out = [run(True, stack), run(False, stack)]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cast_latency.json").write_text(json.dumps(out, ensure_ascii=False, indent=1),
                                           encoding="utf-8")
    for o in out:
        print(json.dumps({k: v for k, v in o.items() if k != "turns"}))
    print(f"spend USD: {stack.spend.total:.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
