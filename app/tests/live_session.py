"""15-turn live session (costs a little): latency, repetition and name consistency per turn.

    nix develop --command python app/tests/live_session.py [turns] [budget]

Prints a table, writes the transcript and per-turn data to a JSON file under the scratch folder
given by $SESSION_OUT (default: a temp folder).
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness.glossary import Glossary  # noqa: E402
from harness.models import ACTION, NARRATION, UTTERANCE  # noqa: E402

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


def main() -> None:
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 15
    budget = float(sys.argv[2]) if len(sys.argv) > 2 else 0.30
    stack = live_stack(budget)
    root = tempfile.mkdtemp(prefix="live-session-")
    game = Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0)
    rows = []
    for i, text in enumerate(TURNS[:n], 1):
        game.start_turn(text)
        game.wait_idle(240)
        err = next((e for e in game.events_after(game.turn_start_seq) if e["type"] == "error"), None)
        d = game.debug
        spk = [e["tok"] for e in game.events_after(game.turn_start_seq) if e["type"] == "speaker"]
        npc_s = [c["seconds"] for c in d["calls"] if c["role"].startswith("npc")]
        row = {"turn": i, "error": err and err["message"], "speakers": spk,
               "first_word_s": d["timing"]["first_word_s"], "total_s": d["timing"]["total_s"],
               "cost": d["cost"], "calls": [(c["role"], c["model"], c["seconds"]) for c in d["calls"]],
               "npc_call_s": npc_s, "repetition": d.get("repetition"), "names": d.get("names"),
               "notes": [n_["kind"] for n_ in d["notes"]]}
        rows.append(row)
        r = row["repetition"] or {}
        nm = row["names"] or {}
        print(f"t{i:02d} speakers={spk} first={row['first_word_s']}s total={row['total_s']}s "
              f"cost=${row['cost']:.4f} rep={r.get('score')} (ng {r.get('ngram')}, op {r.get('opening')}, "
              f"sh {r.get('shape')}) fixed={len(nm.get('fixed', []))} near={nm.get('near_misses')} "
              f"err={row['error']}")
        for t in game.transcript[-3:]:
            print(f"      [{t['kind']}{':' + t['label'] if 'label' in t else ''}] {t['text'][:200]}")
    # name consistency over everything stored and shown
    g = Glossary.for_world("witcher")
    eng = game.eng
    shown = [t["text"] for t in game.transcript if t["kind"] in ("narr", "npc")]
    records = [f.content for f in eng.facts.all_campaign(10**9)]
    records += [it for el in eng.live.snapshot().values() for (_c, it) in el]
    records += [e.payload["text"] for e in eng.log.active([ACTION])]
    stats = {"shown_texts": len(shown), "records": len(records),
             "variants_left_in_shown": [f.form for t in shown for f in g.variants_in(t)],
             "variants_left_in_records": [f.form for t in records for f in g.variants_in(t)],
             "near_misses_shown": [m for t in shown for m in g.near_misses(t)],
             "near_misses_records": [m for t in records for m in g.near_misses(t)],
             "canonical_forms_shown": sum(g.canonical_count(t) for t in shown),
             "canonical_forms_records": sum(g.canonical_count(t) for t in records),
             "fixed_by_code": [f for r in rows for f in (r["names"] or {}).get("fixed", [])]}
    print("\nNAMES", json.dumps({k: v for k, v in stats.items() if k != "fixed_by_code"},
                               ensure_ascii=False))
    print("fixed by code:", [(f["where"], f["form"], f["canonical"]) for f in stats["fixed_by_code"]])
    print(f"total spend ${stack.spend.total:.4f} over {stack.spend.calls} paid calls")  # type: ignore[union-attr]
    out = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.mkdtemp())) / "session.json"
    out.write_text(json.dumps({"rows": rows, "stats": stats, "transcript": game.transcript,
                               "records": records}, ensure_ascii=False, indent=1))
    print("saved", out)


if __name__ == "__main__":
    main()
