"""False-reject / detection rate of the NPC output check ("unknown_claim") on the graded NPC lines.

Context format copied from Engine._unknown_claim. Lines with fmt failures (stage directions, reasoning
leaks) are excluded: clean_npc_line / format retries handle those, not the check.
Variants: v0 = engine question verbatim; v1 = revised question (narrower, lists what to ignore).
"""
import json, os, sys, time
from pathlib import Path
import httpx
from dotenv import load_dotenv
from harness.narrator import clean_npc_line
from . import prompts

load_dotenv()
HERE = Path(__file__).parent
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
URL = "https://openrouter.ai/api/v1/systemone"
Q0 = ("Does the line assert a fact about the world or other people that this "
      "character had no channel to learn from what they know? Ignore greetings, "
      "questions, opinions and general common sense.")
Q1 = ("Does the line state, as a fact, something specific about the world or other people (a name, "
      "place, event, number, cause or plan) that is NOT in the character's knowledge, the recent "
      "conversation or what they just noticed? Do NOT count: greetings, questions, opinions, "
      "feelings, advice, threats, insults, jokes, vague hearsay ('they say'), plausible common "
      "sense, or the character's own manner of speech.")
MODELS = ["liquid/d1-ultra", "perplexity/pplx-decider-v1.2", "typesafe/jev-1.14"]
key = json.loads((HERE / "raw/blind_key.json").read_text())
grades = {}
for f in ["grades_npc_1.json", "grades_npc_2.json"]:
    grades.update({k: v for k, v in json.loads((HERE / f).read_text()).items() if not k.startswith("_")})
rows = {}
for f in (HERE / "raw").glob("text_*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        rows[(r["set"], r["id"], r["model"])] = r
items = {i["id"]: i for i in json.loads((HERE / "testset/npc.json").read_text())}


def context(it, line):
    nm = prompts.nm
    known = [f"- {t} (heard from {nm(s)})" if s else f"- {t}" for t, s in it["knows"]]
    known += [f"- (just noticed) {t}" for t in it.get("noticed") or []]
    seen = [f"{nm(c)}: {t}" for c, t in it["recent"]]
    return (f"Character: {nm(it['npc'])}\nWhat the character knows:\n" + ("\n".join(known + seen) or "- (nothing)")
            + f"\nLine: {line}")


def ask(model, state, q):
    body = {"model": model, "state": [state], "questions": {"q": {"type": "noul", "instructions": q}}}
    for i in range(6):
        t = time.time()
        r = httpx.post(URL, headers=H, json=body, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(2 * (i + 1))
    r.raise_for_status()
    return r.json()["answers"]["q"]["noul"], time.time() - t


def main():
    out = []
    for k, g in grades.items():
        if g["fmt"]:
            continue
        s, iid, lab = k.split("/")
        it = items[iid]
        line = clean_npc_line(rows[(s, iid, key[k])]["text"])
        for m in MODELS:
            for vname, q in (("v0", Q0), ("v1", Q1)):
                p, lat = ask(m, context(it, line), q)
                out.append(dict(id=k, text_model=key[k], leak=g["leak"], check_model=m, variant=vname, p=p, lat=round(lat, 3)))
    (HERE / "raw/npc_check.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n")
    print(len(out), "checks")


if __name__ == "__main__":
    main()
