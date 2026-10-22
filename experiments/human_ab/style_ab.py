"""Old vs new style prompts on round-2 moments w0 (Yennefer, narrator then NPC) and w3 (sergeant).

OLD prompts = style sheet and NARR_CORE/NPC_CORE as of the commit before the plain-words change
(git rev OLD_REV); NEW = the working tree. 3 models x 2 moments x 2 versions x 2 samples. Raw output
goes to experiments/human_ab/raw/style_ab.jsonl (the version label is in the row; the user grades
blind, so this script builds no page). Detector counts are printed at the end.

    PYTHONPATH=. nix develop --command python -m experiments.human_ab.style_ab
"""
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/home/cock/projects/harness/.env")  # the worktree has no .env of its own

from experiments.common import llm  # noqa: E402
from experiments.human_ab import run2  # noqa: E402
from harness import style as S  # noqa: E402
from harness.stylehits import style_hits  # noqa: E402

OLD_REV = "2e5bc45"
OUT = Path(__file__).parent / "raw" / "style_ab.jsonl"
EXP, CAP = "style_ab", 0.12
MODELS = ["xiaomi/mimo-v2.6-flash", "z-ai/glm-5.3-flash", "xiaomi/mimo-v2.6-pro"]
MOMENTS = ["w0", "w3"]
SAMPLES = 2

OLD_NARR_CORE = (
    "You write the narration of a role-playing game in the manner of Sapkowski's Witcher books "
    "in Ukrainian: an ironic, worldly narrator who knows a little more than the hero and says it "
    "flatly. Concrete, ugly, specific detail (smell, dirt, the weight of a coin, a dog "
    "scratching), earthy comparisons, short flat sentences for danger and longer ones for "
    "crowds. Show the hero's alertness by what he watches. No stock atmosphere (ominous, "
    "palpable silence, a chill down the spine, the air grew heavy), no summarising of feelings, "
    "no moralising. Scenes move: someone does something, someone reacts. The characters' own "
    "small gestures while they speak are written with their lines by their own calls: narrate "
    "the scene, what the hero perceives and what happens around, not how somebody delivers a line.")
OLD_NPC_TAIL = ("it. A line is a move in a bargain or a quarrel, not information handed over. No summary of "
                "the situation, no neat closing offer, no polite filler, no stock phrases of fiction.")


def old_sheet() -> dict[str, str]:
    md = subprocess.run(["git", "show", f"{OLD_REV}:worlds/witcher/style.md"], capture_output=True,
                        text=True, check=True).stdout
    return S._sections(md)


def old_npc_core() -> str:
    # the new core has the same text up to the plain-words addition
    new = S.NPC_CORE
    cut = new.index(" Talk in plain words")
    return new[:cut]


def set_version(version: str) -> None:
    if version == "old":
        run2.STYLE = S.Style(old_sheet(), exemplars=False)
        S.NARR_CORE, S.NPC_CORE = OLD_NARR_CORE, old_npc_core()
    else:
        run2.STYLE = S.Style.load("witcher", exemplars=False)
        S.NARR_CORE, S.NPC_CORE = NEW_NARR_CORE, NEW_NPC_CORE


NEW_NARR_CORE, NEW_NPC_CORE = S.NARR_CORE, S.NPC_CORE


def main() -> None:
    rows = []
    for version in ("old", "new"):
        set_version(version)
        jobs = [(m, mod, s) for m in MOMENTS for mod in MODELS for s in range(SAMPLES)]

        def one(job, version=version):
            mid, mod, s = job
            try:
                r = run2.run_moment(mid, mod, run2.MODELS[mod], exp=EXP, cap=CAP)
            except Exception as e:  # noqa: BLE001
                return dict(id=mid, model=mod, sample=s, version=version, text="", error=str(e)[:200], cost=0.0)
            return dict(id=mid, model=mod, sample=s, version=version, **r)
        rows += llm.pmap(one, jobs, workers=6)
    with OUT.open("w") as f:
        for r in rows:
            r["hits"] = [(h.kind, h.text) for h in style_hits(r["text"])] if r.get("text") else []
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    tot, n, cost = Counter(), Counter(), 0.0
    for r in rows:
        cost += r.get("cost") or 0
        if r.get("text"):
            tot[(r["model"], r["version"])] += len(r["hits"])
            n[(r["model"], r["version"])] += 1
    for mod in MODELS:
        print(mod, {v: f"{tot[(mod, v)]} hits / {n[(mod, v)]} texts" for v in ("old", "new")})
    print("all", {v: sum(c for (m, vv), c in tot.items() if vv == v) for v in ("old", "new")},
          "errors", sum(1 for r in rows if r.get("error")), "cost", round(cost, 4), file=sys.stdout)


if __name__ == "__main__":
    main()
