"""Run text models on narrator / npc / extractor sets. Raw outputs -> raw/text_<model>.jsonl.

    nix develop --command python -m experiments.bakeoff.run_text [--models a,b] [--sets narrator,npc,extract]
"""
import argparse, json, time
from pathlib import Path
from experiments.common import llm
from . import prompts

HERE = Path(__file__).parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)
EXP = "task7"
CAP = 0.85  # shared guard for all task-7 spend (budget is < 1 USD)
MODELS = ["deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3-flash", "qwen/qwen3.8-omni-flash",
          "openai/gpt-6-luna", "google/gemini-3.5-flash-lite", "cohere/command-a-plus"]
SETS = {"narrator": ("narrator.json", prompts.narrator, 1200),
        "npc": ("npc.json", prompts.npc, 500),
        "extract": ("extract.json", prompts.extractor, 1200)}


def call(model, messages, max_tokens):
    """reasoning disabled; if the model refuses, retry with low effort and headroom."""
    t = time.time()
    try:
        r = llm.chat(model, messages, exp=EXP, cap=CAP, max_tokens=max_tokens)
        mode = "no-reasoning"
    except RuntimeError as e:
        if "easoning" not in str(e) and "400" not in str(e):
            raise
        r = llm.chat(model, messages, exp=EXP, cap=CAP, max_tokens=max_tokens + 2500,
                     reasoning={"effort": "low"})
        mode = "effort-low"
    return r, mode


def one(model, setname, it):
    fn, render, mt = SETS[setname]
    try:
        r, mode = call(model, render(it), mt)
        return dict(model=model, set=setname, id=it["id"], text=r["text"], cost=r["cost"],
                    latency=round(r["latency"], 2), tokens=r["usage"].get("completion_tokens"),
                    in_tokens=r["usage"].get("prompt_tokens"), mode=mode)
    except Exception as e:  # keep going; the failure is a result too
        return dict(model=model, set=setname, id=it["id"], text="", error=str(e)[:300], cost=0, latency=0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(MODELS))
    ap.add_argument("--sets", default="narrator,npc,extract")
    a = ap.parse_args()
    for model in a.models.split(","):
        out = RAW / f"text_{model.replace('/', '__')}.jsonl"
        done = {(r["set"], r["id"]) for r in map(json.loads, out.read_text().splitlines())
                if not r.get("error")} if out.exists() else set()
        jobs = []
        for s in a.sets.split(","):
            for it in json.loads((HERE / "testset" / SETS[s][0]).read_text()):
                if (s, it["id"]) not in done:
                    jobs.append((s, it))
        res = llm.pmap(lambda j: one(model, *j), jobs, workers=6)
        with out.open("a") as f:
            for r in res:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        errs = [r for r in res if r.get("error")]
        print(model, len(res), "calls, cost", round(sum(r["cost"] for r in res), 4), "errors", len(errs),
              errs[:1])


if __name__ == "__main__":
    main()
