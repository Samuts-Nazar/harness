"""Task 10 runner. Raw outputs -> experiments/language/raw/<set>.jsonl (resumable).

    nix develop --command python -m experiments.language.run [--sets narrator,npc,extract] [--samples 3]
"""
import argparse, json, time
from pathlib import Path
from experiments.common import llm
from experiments.bakeoff import prompts as P
from . import prompts_lang as L

HERE = Path(__file__).parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)
EXP = "task10"
CAP = 0.45
MODELS = ["openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash-1017"]
EXTRACT_MODEL = "deepseek/deepseek-v4.1-flash-1017"
TS = HERE.parent / "bakeoff" / "testset"


def call(model, msgs, mt):
    try:
        return llm.chat(model, msgs, exp=EXP, cap=CAP, max_tokens=mt)
    except RuntimeError as e:
        if "easoning" not in str(e) and "400" not in str(e):
            raise
        return llm.chat(model, msgs, exp=EXP, cap=CAP, max_tokens=mt + 2500, reasoning={"effort": "low"})


def job(j):
    s, model, iid, v, k = j
    if s == "narrator":
        msgs, mt = L.narrator(iid, v), 1200
    elif s == "npc":
        msgs, mt = L.npc(iid, v), 500
    else:
        msgs, mt = L.extractor(EX[iid], v), 1200
    try:
        r = call(model, msgs, mt)
        return dict(set=s, model=model, id=iid, variant=v, sample=k, text=r["text"], cost=r["cost"],
                    in_tokens=r["usage"].get("prompt_tokens"))
    except Exception as e:
        return dict(set=s, model=model, id=iid, variant=v, sample=k, text="", error=str(e)[:300], cost=0)


EX = {i["id"]: i for i in json.loads((TS / "extract.json").read_text())}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--sets", default="narrator,npc,extract")
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--variants", default="uk,en")
    ap.add_argument("--suffix", default="")
    a = ap.parse_args()
    for s in a.sets.split(","):
        out = RAW / f"{s}{a.suffix}.jsonl"
        done = {(r["model"], r["id"], r["variant"], r["sample"]) for r in map(json.loads, out.read_text().splitlines())
                if not r.get("error")} if out.exists() else set()
        ids = {"narrator": list(L.NARR), "npc": list(L.NPCS), "extract": list(EX)}[s]
        models = [EXTRACT_MODEL] if s == "extract" else MODELS
        jobs = [(s, m, i, v, k) for m in models for i in ids for v in a.variants.split(",") for k in range(a.samples)
                if (m, i, v, k) not in done]
        res = llm.pmap(job, jobs, workers=8)
        with out.open("a") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        errs = [r for r in res if r.get("error")]
        print(s, len(res), "calls, cost", round(sum(r["cost"] for r in res), 4), "errors", len(errs), errs[:1])
    print("task10 spent", round(llm.spent(EXP), 4))
