"""Task 15 style bake-off. Resumable; raw output in experiments/style/raw/.

    PYTHONPATH=. nix develop --command python -m experiments.style.run --models a,b --samples 3 [--narr]

Spend is capped (task budget 0.60 USD) through the ledger of experiments/common/llm.py.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv("/home/cock/projects/harness/.env")  # the key lives in the main checkout
os.environ.setdefault("OPENROUTER_API_KEY", "")

from experiments.common import llm  # noqa: E402
from experiments.style import scenes as S  # noqa: E402
from harness.models import CharacterProfile  # noqa: E402
from harness.style import Style, manner_messages, parse_manner  # noqa: E402

RAW = Path(__file__).parent / "raw"
RAW.mkdir(exist_ok=True)
EXP = "task15"
ONLY: list[str] = []
MANNER_MODEL = "openai/gpt-6-luna"


def manners() -> dict[str, str]:
    f = RAW / "manners.json"
    if f.exists():
        return json.loads(f.read_text())
    out = {}
    plain = Style.load("witcher", exemplars=False)
    cases = {"horst": S.inn_engine("i1")[0], "elza": S.inn_engine("i1")[0]}
    profs = {k: v.profiles[k] for k, v in cases.items()}
    for iid in S.TASK7:
        eng, npc = S.task7_engine(iid)
        profs[npc] = eng.profiles[npc]
    for npc, prof in profs.items():
        r = llm.chat(MANNER_MODEL, manner_messages(prof, plain), exp=EXP, cap=0.6, max_tokens=500)
        out[npc] = parse_manner(r["text"])
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1))
    return out


def run(kind: str, models: list[str], samples: int, variants: list[str]) -> None:
    mans = manners()
    ex, plain = Style.load("witcher", exemplars=True), Style.load("witcher", exemplars=False)
    out = RAW / f"{kind}.jsonl"
    done = set()
    if out.exists():
        for r in map(json.loads, out.read_text().splitlines()):
            done.add((r["id"], r["variant"], r["model"], r["sample"]))
    ids = S.npc_ids() if kind == "npc" else list(S.NARR)
    if ONLY:
        ids = [i for i in ids if i in ONLY]
    jobs = [(i, v, m, k) for i in ids for v in variants for m in models for k in range(samples)
            if (i, v, m, k) not in done]
    print(len(jobs), "jobs", file=sys.stderr)

    def one(job):
        i, v, m, k = job
        msgs = (S.npc_messages(i, v, mans, ex, plain) if kind == "npc"
                else S.narrator_messages(i, v, ex, plain))
        try:
            r = llm.chat(m, msgs, exp=EXP, cap=0.58, max_tokens=700 if kind == "npc" else 900,
                         temperature=0.8)
        except Exception as e:  # noqa: BLE001
            return dict(id=i, variant=v, model=m, sample=k, text="", error=str(e)[:200])
        u = r["usage"]
        return dict(id=i, variant=v, model=m, sample=k, text=r["text"].strip(), cost=r["cost"],
                    latency=round(r["latency"], 2), tokens_in=u.get("prompt_tokens"),
                    tokens_out=u.get("completion_tokens"))

    res = llm.pmap(one, jobs, workers=8)
    with out.open("a") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    errs = [r for r in res if r.get("error")]
    print(kind, "done", len(res), "errors", len(errs), errs[:2], "spent", round(llm.spent(EXP), 4))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", required=True)
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--variants", default="old,new,ex")
    ap.add_argument("--narr", action="store_true")
    ap.add_argument("--ids", default="")
    a = ap.parse_args()
    ONLY.extend([x for x in a.ids.split(",") if x])
    run("narr" if a.narr else "npc", a.models.split(","), a.samples, a.variants.split(","))
