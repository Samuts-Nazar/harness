"""Run decision models on the 60 judgments. Sequential (clean per-call latency).
Raw -> raw/decide_<model>.jsonl with p_yes per item and language condition.

    nix develop --command python -m experiments.bakeoff.run_decide [--models ...]
"""
import argparse, json, os, re, time
from pathlib import Path
import httpx
from dotenv import load_dotenv
from experiments.common import llm

load_dotenv()
HERE = Path(__file__).parent
RAW = HERE / "raw"
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
URL = "https://openrouter.ai/api/v1/systemone"
LAYA = "http://127.0.0.1:8765/v1/systemone"
HOSTED = ["typesafe/jev-1.14", "perplexity/pplx-decider-flash-v1.2", "perplexity/pplx-decider-v1.2",
          "liquid/d1-ultra"]
LAYA_M = {"laya/english": "english", "laya/multilingual": "multilingual"}
CHAT = ["elorian/glimpse"]


def conditions(it):
    if it["lang_mode"] == "both":
        return [("en", it["en"]), ("uk", it["uk"])]
    return [("mixed", it["en"])]


def decide_http(model, state, q):
    body = {"model": model, "state": state, "questions": {"q": {"type": "noul", "instructions": q}}}
    for i in range(6):  # 429s happen on the flash model: back off, measure only the successful call
        t = time.time()
        r = httpx.post(URL, headers=H, json=body, timeout=60)
        lat = time.time() - t
        if r.status_code != 429:
            break
        time.sleep(2 * (i + 1))
    r.raise_for_status()
    j = r.json()
    return float(j["answers"]["q"]["noul"]), lat, float(j.get("usage", {}).get("cost") or 0), j.get("usage", {})


def decide_laya(name, state, q):
    body = {"model": LAYA_M[name], "state": state, "questions": {"q": {"type": "noul", "instructions": q}}}
    t = time.time()
    r = httpx.post(LAYA, json=body, timeout=120)
    lat = time.time() - t
    r.raise_for_status()
    j = r.json()
    return float(j["answers"]["q"]["noul"]), lat, 0.0, j.get("usage", {})


def decide_chat(model, state, q):
    prompt = ("State:\n" + "\n".join(f"- {s}" for s in state) + f"\n\nQuestion: {q}\n\n"
              'Reply with JSON only: {"answer": "yes"|"no", "p_yes": number 0..1}')
    r = llm.chat(model, [{"role": "system", "content": "You are a module of a game engine that makes narrow judgments. Answer JSON only."},
                         {"role": "user", "content": prompt}], exp="task7", cap=0.85, max_tokens=200, temperature=0)
    m = re.search(r"\{.*\}", r["text"], re.S)
    try:
        d = json.loads(m.group(0))
        yes = str(d["answer"]).lower().startswith("y")
        p = float(d["p_yes"]) if isinstance(d.get("p_yes"), (int, float)) else (1.0 if yes else 0.0)
        # some models report the confidence in their answer instead of P(yes): trust the answer field
        # (the engine's LLMJudge does too) and flip an inconsistent p_yes
        if (yes and p < 0.5) or (not yes and p > 0.5):
            p = 1 - p
    except Exception:
        p = None
    return p, r["latency"], r["cost"], r["usage"]


def run(model, items):
    out = RAW / f"decide_{model.replace('/', '__')}.jsonl"
    rows = []
    for it in items:
        for cond, c in conditions(it):
            try:
                if model in HOSTED:
                    p, lat, cost, u = decide_http(model, c["state"], c["q"])
                elif model in LAYA_M:
                    p, lat, cost, u = decide_laya(model, c["state"], c["q"])
                else:
                    p, lat, cost, u = decide_chat(model, c["state"], c["q"])
                err = None
            except Exception as e:
                p, lat, cost, u, err = None, 0, 0, {}, str(e)[:200]
            rows.append(dict(model=model, id=it["id"], type=it["type"], cond=cond, gold=it["gold"], p_yes=p,
                             latency=round(lat, 3), cost=cost,
                             in_tokens=u.get("input_tokens") or u.get("prompt_tokens"), error=err))
    out.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n")
    ok = [r for r in rows if r["p_yes"] is not None]
    acc = sum((r["p_yes"] >= 0.5) == r["gold"] for r in ok) / max(len(ok), 1)
    print(model, len(rows), "calls", "errors", len(rows) - len(ok), "acc", round(acc, 3),
          "cost", round(sum(r["cost"] for r in rows), 5))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=",".join(HOSTED + list(LAYA_M) + CHAT))
    a = ap.parse_args()
    items = json.loads((HERE / "testset" / "judgments.json").read_text())
    for m in a.models.split(","):
        run(m, items)


if __name__ == "__main__":
    main()
