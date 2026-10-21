"""Task 21B leak probe: claim-splitting check on the 68 graded NPC lines of task 7 (25 leaks, 43 clean).

One luna call per line: list the specific factual claims in the line and mark each SUPPORTED or UNSUPPORTED by the
character's knowledge, the recent talk, or plain common sense. Line flagged when any claim is UNSUPPORTED.
Run: PYTHONPATH=. nix develop --command python -m experiments.tone21b.leak_probe OUT.json LEDGER.jsonl
"""
import json
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import httpx
from dotenv import load_dotenv

load_dotenv(".env")
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
LEDGER = sys.argv[2]
BK = Path("experiments/bakeoff")
from experiments.bakeoff import prompts  # noqa: E402

PROMPT = """You check one line spoken by a character in a fantasy story for invented facts.

{ctx}

Step 1: list every specific factual claim the line makes about the world or other people (a name, place, event, number, cause, plan, past or present happening). Skip greetings, questions, opinions, feelings, threats, jokes, vague hearsay ("they say") and the character's manner.
Step 2: for each claim write SUPPORTED if it follows from what the character knows, the recent conversation or plain common sense of their trade; otherwise UNSUPPORTED (the character had no way to know it, or it is an invented specific).
Answer one claim per line as: SUPPORTED|UNSUPPORTED - short claim. If there are no claims write: NONE."""


def context(it, line):
    nm = prompts.nm
    known = [f"- {t} (heard from {nm(s)})" if s else f"- {t}" for t, s in it["knows"]]
    known += [f"- (just noticed) {t}" for t in it.get("noticed") or []]
    seen = [f"{nm(c)}: {t}" for c, t in it["recent"]]
    return (f"Character: {nm(it['npc'])}\nWhat the character knows:\n" + ("\n".join(known + seen) or "- (nothing)")
            + f"\n\nLine spoken by the character:\n{line}")


def spent():
    try:
        return sum(json.loads(x)["cost"] for x in open(LEDGER))
    except FileNotFoundError:
        return 0.0


def call(model, content):
    if spent() >= 0.15:
        raise RuntimeError("cap")
    body = {"model": model, "messages": [{"role": "user", "content": content}], "max_tokens": 500,
            "temperature": 0, "reasoning": {"enabled": False}}
    for i in range(4):
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers=H, json=body, timeout=120)
        if r.status_code == 200 and "error" not in r.json():
            j = r.json()
            c = float(j.get("usage", {}).get("cost") or 0)
            with open(LEDGER, "a") as f:
                f.write(json.dumps({"model": model, "cost": c}) + "\n")
            return j["choices"][0]["message"].get("content") or "", c
        time.sleep(2 * (i + 1))
    raise RuntimeError("failed")


def main(out):
    from harness.narrator import clean_npc_line
    key = json.loads((BK / "raw/blind_key.json").read_text())
    grades = {}
    for f in ["grades_npc_1.json", "grades_npc_2.json"]:
        grades.update({k: v for k, v in json.loads((BK / f).read_text()).items() if not k.startswith("_")})
    rows = {}
    for f in (BK / "raw").glob("text_*.jsonl"):
        for line in open(f):
            r = json.loads(line)
            rows[(r["set"], r["id"], r["model"])] = r
    items = {i["id"]: i for i in json.loads((BK / "testset/npc.json").read_text())}
    jobs = []
    for k, g in grades.items():
        if g["fmt"]:
            continue
        s, iid, lab = k.split("/")
        jobs.append((k, g["leak"], iid, clean_npc_line(rows[(s, iid, key[k])]["text"])))

    def one(j):
        k, leak, iid, line = j
        t, c = call("openai/gpt-6-luna", PROMPT.format(ctx=context(items[iid], line)))
        uns = [x for x in t.splitlines() if x.strip().upper().startswith("UNSUPPORTED")]
        return dict(id=k, leak=leak, flagged=bool(uns), unsupported=uns, raw=t, cost=c)

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, jobs))
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    tp = sum(r["leak"] and r["flagged"] for r in res)
    fp = sum((not r["leak"]) and r["flagged"] for r in res)
    P = sum(r["leak"] for r in res)
    N = len(res) - P
    print(len(res), "leaks caught", tp, "/", P, "false rejects", fp, "/", N, "spent", round(spent(), 4))


if __name__ == "__main__":
    main(sys.argv[1])
