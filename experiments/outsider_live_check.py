"""Live check (outsider plan 1, task 10): the generic Ellander package on `ellander_road`, 3 turns,
real cheap models over OpenRouter, hard cap $0.10. Checks: the latent Source is in the engine but
not on the player's panel; Yennefer's magic sense on entry; reading an INVENTED inline text on the
laptop (the «Прочитано» block, `read: <item id>` records, the clock, nobody else gains them); the
closed backpack; first-word latency, cost, and the canon deferral of the temple scenes.

    OUTSIDER_ENV=/home/cock/projects/harness/.env OUTSIDER_BE=/path/to/be.db \
        nix develop --command python experiments/outsider_live_check.py OUT_DIR

The key is loaded with python-dotenv and never printed. OUT_DIR gets raw JSON (it may hold canon
records: keep it out of git).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
load_dotenv(os.environ.get("OUTSIDER_ENV", ROOT / ".env"))
for k in ("HARNESS_CANON_DB", "HARNESS_CANON_DB_BE"):
    os.environ.pop(k, None)

from app import newgame  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from harness.canon.play import what_knows  # noqa: E402
from harness.models import PLAYER  # noqa: E402

BE = os.environ.get("OUTSIDER_BE", str(ROOT / "campaigns/canon/be.db"))
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/outsider_live")
OUT.mkdir(parents=True, exist_ok=True)
CAP = 0.10

# an invented text (not the saga): notes for a board game the character was designing
LAMP = ("Мої нотатки до настільної гри «Скляна лампа» (вигадка, чернетка).\n"
        "Дух лампи звуть Ормаз. Він живе в мідній лампі з вузьким носиком.\n"
        "Прокидається, якщо лампу потерти тричі проти годинникової стрілки.\n"
        "Бажань не виконує: на кожне запитання відповідає загадкою.\n"
        "Боїться солоної води: від неї гасне на цілу добу.\n"
        "Світить зеленим, коли поруч хтось бреше.")

TURNS = [
    "Підводжуся з землі, обтрушую коліна й кажу жінці: «Вибачте... Де я? Здається, я заблукав».",
    "Знімаю рюкзак, розстібаю його, дістаю ноутбук і відкриваю свої нотатки про духа лампи.",
    "Питаю її: «Чому ви так на мене дивитеся? Щось зі мною не так?»",
]


def package():
    d = yaml.safe_load((ROOT / "app/tests/fixtures/outsider_ellander.yaml").read_text("utf-8"))
    for it in d["player"]["inventory"]:
        if it["name"] == "ноутбук":
            it["notes"] = "робочий ноутбук, без пароля для власника"
            it["content"] = LAMP
    return newgame.parse(yaml.safe_dump(d, allow_unicode=True, sort_keys=False))


def ids(eng):
    yen = [c for c, p in eng.profiles.items() if "Йеннефер" in (p.name or "")]
    return yen[0] if yen else None


def player_state(eng):
    return [{"cat": el.category, "item": el.item, "id": el.id, "loc": el.location,
             "aware": el.aware, "channel": el.channel, "observable": el.observable,
             "open": el.open} for el in eng.live.snapshot().get(PLAYER, {}).values()]


def knows(eng, who):
    return what_knows(eng, who) if who else []


def snap(game, label, extra=None):
    eng = game.eng
    yen = ids(eng)
    s = {"label": label, "clock": game.clock(), "scene_time": eng.scene.time,
         "spend": round(game.camp.spend.total, 6), "panel": game.panel(),
         "player_state": player_state(eng), "yennefer": yen,
         "yen_knows": knows(eng, yen), "player_knows": knows(eng, PLAYER),
         "devlog_kinds": [n.get("kind") for n in eng.devlog],
         "canon_log": [{"type": e.type, "t": e.game_time, "p": e.payload}
                       for e in eng.log.active(["canon_deferred", "canon_retired"])],
         **(extra or {})}
    (OUT / f"{label}.json").write_text(json.dumps(s, ensure_ascii=False, indent=1, default=str))
    return s


def main():
    stack = live_stack(CAP)
    pkg = package()
    t0 = time.monotonic()
    game = Game(lambda new: newgame.open_package(stack, pkg, root=OUT / "campaigns",
                                                 canon_db=BE), pace=0.0, suggestions=False)
    print("start built in", round(time.monotonic() - t0, 1), "s; spend", round(stack.spend.total, 5))
    snap(game, "t0", {"judgments": game.eng.judgments.entries, "notes": game.eng.devlog,
                      "intro": game.camp.intro})
    for i, text in enumerate(TURNS, 1):
        if stack.spend.total >= CAP * 0.85:
            print("stop: close to the cap"); break
        try:
            game.start_turn(text)
            time.sleep(0.5)
            end = time.monotonic() + 240
            while game.phase != "idle" and time.monotonic() < end:
                time.sleep(0.2)
            game.wait_idle(240)
        except Exception as e:  # report, never retry
            print(f"turn {i} failed:", type(e).__name__, str(e)[:200])
            break
        evs = game.events_after(0)
        dbg = getattr(game, "debug", {}) or {}
        snap(game, f"t{i}", {"text": text, "events": evs, "debug": dbg,
                             "transcript": game.state()["transcript"]})
        print(f"turn {i}: first word {dbg.get('timing', {}).get('first_word_s')} s, "
              f"total {dbg.get('timing', {}).get('total_s')} s, cost {dbg.get('cost')}, "
              f"error {dbg.get('error')}")
    print("spend total", round(stack.spend.total, 5), "calls", stack.spend.calls)


if __name__ == "__main__":
    main()
