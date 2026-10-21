"""Task 22: "writes like a person" bake-off, graded by the user.

6 moments (4 NPC from experiments/style, 2 narration of Vizima situation A) x candidates, one sample each,
the engine's own prompts (style sheet on, no book exemplars: `Style.load("witcher")` as app/vizima.py does).
Raw output: experiments/human_ab/raw/out.jsonl (resumable). Builds the page data and the key.

    PYTHONPATH=. nix develop --command python -m experiments.human_ab.run [--build-only]

Spend cap 0.20 USD through the ledger of experiments/common/llm.py (experiment name "task22").
"""
import json
import os
import re
import random
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/home/cock/projects/harness/.env")  # the key lives in the main checkout
os.environ.setdefault("OPENROUTER_API_KEY", "")

from experiments.common import llm  # noqa: E402
from experiments.style import scenes as S  # noqa: E402
from harness.style import Style  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)
OUT = RAW / "out.jsonl"
EXP, CAP = "task22", 0.19

BASE = "openai/gpt-6-luna"
# Catalog of 2026-10-22 (created field), price USD per M input/output; see docs/tools.md.
CANDIDATES = [
    "xiaomi/mimo-v2.6-pro",
    "z-ai/glm-5.3",
    "deepseek/deepseek-v4.1-flash-1017",
    "qwen/qwen3.8-27b",
    "cohere/command-a-plus",
    "bytedance-seed/seed-2-1-turbo",
    "xiaomi/mimo-v2.6-flash",
]
MODELS = [BASE, *CANDIDATES]

# id -> (kind, title, situation shown to the user, the player's line)
MOMENTS = {
    "i1": ("npc", "Горст відкриває розмову",
           "Корчма. Двоє селян, Горст і Ельза, сіли навпроти тебе: їм щось потрібно від відьмака.",
           "Сідайте. Я слухаю вас."),
    "i3": ("npc", "Горст торгується",
           "Той самий стіл. Горст уже виклав, що від тебе хоче, і назвав п'ятдесят оренів.",
           "П'ятдесят оренів за двох мертвих хлопців і те, що виє? Ні. Сто п'ятдесят."),
    "c07": ("npc", "Роше на лісовій дорозі",
            "Лісова дорога, день. Роше, темерський розвідник, знає про Нільфгаард лише чутки від купців.",
            "Що ти знаєш про наміри Нільфгаарда?"),
    "c08": ("npc", "Марта на хуторі",
            "Хутір біля лісу, вечір. Вовки виють третю ніч. У незнайомця жовті очі й срібний меч; Марта не знає його імені.",
            "Добрий вечір. Ти знаєш, хто я?"),
    "v1": ("narr", "Візім: заходиш до корчми",
           "Корчма «Під Лисом», вечір третього дня. Ти демон без обмежень, у корчмі вартовий і п'яний візник.",
           "Сідаю за стійку й замовляю пива."),
    "v2": ("narr", "Візім: пиво стає кров'ю",
           "Та сама корчма, трохи згодом.",
           "*Підношу руку над столом, і все пиво в кухлях стає кров'ю. Мої очі спалахують жовтим.* "
           "Це моя відповідь тим, хто бреше."),
}



def glitch(text: str) -> str | None:
    t = text.strip()
    if not t:
        return "empty"
    if len(t.split()) < 3:
        return "too short"
    if re.search(r"[一-鿿぀-ヿ가-힯԰-֏֐-׿؀-ۿऀ-ॿ]", t):
        return "foreign script"
    if re.search(r"[ыэъёЫЭЪЁ]", t):
        return "russian letters"
    if re.search(r"\b[A-Za-z]{4,}\b", t):
        return "latin words"
    if re.search(r"</?think|<\|", t):
        return "markup"
    if len(t.split()) > 330:
        return "too long"
    if t[-1] not in ".!?…»\")*—-":
        return "cut off"
    return None


def vizima_narrator(player_input: str) -> list[dict[str, str]]:
    from app.stacks import fake_stack
    from app.vizima import INTRO, open_vizima
    from harness.models import NARRATION
    c = open_vizima(fake_stack(), root=tempfile.mkdtemp(), new=True, canon_db=False)
    eng = c.engine
    eng.ctx.narration = "prose"
    eng._event(NARRATION, [], {"text": INTRO}, witnesses=[])
    return eng.ctx.narrator(eng.scene, player_input)


def messages(mid: str) -> list[dict[str, str]]:
    kind = MOMENTS[mid][0]
    if kind == "npc":
        mans = json.loads((Path(S.__file__).parent / "raw" / "manners.json").read_text())
        plain = Style.load("witcher", exemplars=False)
        return S.npc_messages(mid, "plain", mans, plain, plain)
    return vizima_narrator(MOMENTS[mid][3])


def run(workers: int = 6) -> None:
    done = set()
    if OUT.exists():
        done = {(r["id"], r["model"]) for r in map(json.loads, OUT.read_text().splitlines())}
    msgs = {m: messages(m) for m in MOMENTS}
    jobs = [(m, mod) for m in MOMENTS for mod in MODELS if (m, mod) not in done]
    print(len(jobs), "jobs", file=sys.stderr)

    def one(job):
        mid, mod = job
        try:
            r = llm.chat(mod, msgs[mid], exp=EXP, cap=CAP, temperature=0.8,
                         max_tokens=700 if MOMENTS[mid][0] == "npc" else 900)
        except Exception as e:  # noqa: BLE001
            return dict(id=mid, model=mod, text="", error=str(e)[:200], cost=0.0, latency=0.0)
        return dict(id=mid, model=mod, text=r["text"].strip(), cost=r["cost"],
                    latency=round(r["latency"], 2), tokens_out=r["usage"].get("completion_tokens"))

    res = llm.pmap(one, jobs, workers=workers)
    with OUT.open("a") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def build(seed: int = 22) -> None:
    rows = [json.loads(l) for l in OUT.read_text().splitlines()]
    rnd = random.Random(seed)
    data, key, stats = [], {}, {m: dict(n=0, glitch=[], cost=0.0, lat=[]) for m in MODELS}
    for mid, (kind, title, situ, player) in MOMENTS.items():
        items = []
        for r in (x for x in rows if x["id"] == mid):
            st = stats[r["model"]]
            st["cost"] += r["cost"]
            if r.get("latency"):
                st["lat"].append(r["latency"])
            bad = "error" if r.get("error") else glitch(r["text"])
            if bad:
                st["glitch"].append(f"{mid}: {bad}")
                continue
            st["n"] += 1
            items.append(r)
        rnd.shuffle(items)
        letters = "ABCDEFGHIJKLMNOP"
        data.append(dict(id=mid, kind=kind, title=title, situation=situ, player=player,
                         texts=[dict(label=letters[i], text=r["text"]) for i, r in enumerate(items)]))
        key[mid] = {letters[i]: r["model"] for i, r in enumerate(items)}
    (REPO / "app/static/human_ab_data.js").write_text(
        "// generated by experiments/human_ab/run.py; the key is in reports/human_ab/key.json (not served)\n"
        "window.HUMAN_AB = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    kd = REPO / "reports/human_ab"
    kd.mkdir(parents=True, exist_ok=True)
    (kd / "key.json").write_text(json.dumps(key, ensure_ascii=False, indent=1))
    print(f"{'model':40s} texts glitches cost  mean_latency_s")
    for m, st in stats.items():
        lat = sum(st["lat"]) / len(st["lat"]) if st["lat"] else 0
        print(f"{m:40s} {st['n']:3d} {len(st['glitch']):3d} {st['cost']:.4f} {lat:5.1f}  {st['glitch']}")
    print("total", round(sum(s["cost"] for s in stats.values()), 4))


if __name__ == "__main__":
    if "--build-only" not in sys.argv:
        run()
    build()
