"""Task 19 live evaluation (paid, cheap models, capped): play 22 turns of the Vizima campaign (no canon
store, so the session replays offline), record a cassette, replay it offline, run the automatic
checks and print everything a person needs to grade a sample by hand.

    PYTHONPATH=. python experiments/task19/live_eval.py [budget]

Writes $SESSION_OUT/vizima_live.jsonl (the cassette: hashes and replies only), report.json and the
transcript. Do not commit them.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from dotenv import load_dotenv  # noqa: E402

load_dotenv("/home/cock/projects/harness/.env")
from app.stacks import live_stack  # noqa: E402
from harness.evalkit import session  # noqa: E402
from harness.models import PLAYER, UTTERANCE  # noqa: E402

TURNS = [
    "Сідаю за стійку й замовляю пива.",
    "Питаю вартового, як його звати і давно він на службі.",
    "Кажу вартовому: я дам тобі талер, якщо до ранку ти нікому не скажеш, що бачив мене тут.",
    "Питаю візника, чи їздить він до озера і чи не візьме мене завтра.",
    "*Беру візника за руку й дивлюсь йому в очі.* Домовились?",
    "*Підношу руку над столом, і все пиво в кухлях стає кров'ю. Мої очі спалахують жовтим.* Це моя відповідь тим, хто бреше.",
    "Питаю вартового, що він тепер збирається робити.",
    "Кажу візнику, що завтра на світанку чекаю його біля брами, і що дам йому два талери.",
    "*Виходжу з корчми й іду на ринок.*",
    "Питаю торговку, що нового в місті.",
    "Питаю її, чи знає вона вартового з корчми «Під Лисом».",
    "Кажу їй, що це я вчора обернув пиво на кров, і що не збираюся ховатися.",
    "*Іду до кордегардії й питаю сержанта, чи шукають когось.*",
    "Кажу сержантові, що вартовий із корчми обіцяв мені мовчати за талер, і що я його не звинувачую.",
    "Питаю сержанта, що він знає про мою домовленість із візником.",
    "*Виходжу й іду на ринок.*",
    "Питаю торговку, що вона пам'ятає з нашої розмови.",
    "*Іду до брами.*",
    "Питаю когось із людей біля брами, чи не бачили вони візника з корчми.",
    "Кажу, що чекаю на нього, і сідаю біля брами.",
    "Питаю, скільки я обіцяв візнику за дорогу.",
    "Питаю, чи пам'ятає хтось, кому я обіцяв талер.",
]


def main() -> None:
    budget = float(sys.argv[1]) if len(sys.argv) > 1 else 0.25
    out = pathlib.Path(os.environ.get("SESSION_OUT", tempfile.mkdtemp()))
    out.mkdir(parents=True, exist_ok=True)
    stack = live_stack(budget)
    cas = out / "vizima_live.jsonl"
    game, rows = session.record(stack, TURNS, cas)
    print(f"recorded {len(rows)} turns, spend ${stack.spend.total:.4f}")  # type: ignore[union-attr]
    for r in rows:
        print(r)
    reports = session.check(game, min_gap=20)
    print(session.summary(reports))
    (out / "report.json").write_text(session.to_json(reports))
    (out / "transcript.json").write_text(json.dumps(game.transcript, ensure_ascii=False, indent=1))
    eng = game.eng
    lines = [(e.id, eng.profiles[e.payload["speaker"]].name, e.payload["text"])
             for e in eng.log.active([UTTERANCE]) if e.payload.get("speaker") not in (PLAYER, None)]
    (out / "npc_lines.json").write_text(json.dumps(lines, ensure_ascii=False, indent=1))
    # the offline replay of what was just played
    g2, info = session.replay(cas)
    print(f"replay: same story {info['same_story']}, misses {len(info['misses'])}")
    print("spend total", round(stack.spend.total, 4))  # type: ignore[union-attr]


if __name__ == "__main__":
    main()
