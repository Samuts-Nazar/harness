"""Task 12: JSON narrator vs prose narrator on the task 7 narrator set (luna, 3 samples, EN+UKNAMES
context as the engine now renders it), plus the cost of the scene director on the prose outputs.

    nix develop --command python -m experiments.prose.run [--samples 3]

Raw output: experiments/prose/raw/{narr,director}.jsonl (resumable). Spend is capped.
"""
import argparse
import json
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from dotenv import load_dotenv

from experiments.language import prompts_lang as L
from harness.director import actions_messages, decide_speakers, parse_actions
from harness.glossary import Glossary
from harness.judge import DecisionJudge
from harness.policy import DEFAULT_JUDGE_FIRST, DEFAULT_EXTRACTOR, DEFAULT_NARRATOR, Spend
from harness.providers import OpenRouterProvider

HERE = Path(__file__).parent
RAW = HERE / "raw"
RAW.mkdir(exist_ok=True)
G = Glossary.for_world("witcher")

PROSE = ("Write the narration as plain prose and nothing else: no JSON, no lists, no headings, no "
         "markup. Its length and shape follow the moment (a glance can be a sentence, a crisis "
         "several paragraphs); do not settle into a fixed pattern. Never write speech for anyone "
         "but the player: NPC lines are produced separately. Do not decide what the player "
         "character says, does or feels beyond what the player gave.\nWrite in Ukrainian.")


def prose_messages(iid):
    msgs = L.narrator(iid, "enu")
    u = msgs[1]["content"]
    a = u.index("Narrate what happens next.") + len("Narrate what happens next.")
    b = u.index("Never write speech for anyone but the player: NPC lines are produced separately.")
    b += len("Never write speech for anyone but the player: NPC lines are produced separately.")
    msgs[1] = dict(msgs[1], content=u[:a] + "\n\n" + PROSE + u[b:])
    return msgs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", type=int, default=3)
    ap.add_argument("--cap", type=float, default=0.12)
    a = ap.parse_args()
    load_dotenv()
    key = os.environ["OPENROUTER_API_KEY"]
    spend = Spend(a.cap)
    prov = OpenRouterProvider(key, spend=spend)
    judge = DecisionJudge(key, DEFAULT_JUDGE_FIRST, spend=spend)

    def narr(job):
        iid, variant, k = job
        msgs = L.narrator(iid, "enu") if variant == "json" else prose_messages(iid)
        t = time.monotonic()
        try:
            text = prov.complete(DEFAULT_NARRATOR, msgs)
        except Exception as e:  # noqa: BLE001
            return dict(id=iid, variant=variant, sample=k, text="", error=str(e)[:200])
        return dict(id=iid, variant=variant, sample=k, text=text, seconds=round(time.monotonic() - t, 2))

    jobs = [(i, v, k) for i in L.NARR for v in ("json", "prose") for k in range(a.samples)]
    out = RAW / "narr.jsonl"
    done = {(r["id"], r["variant"], r["sample"]) for r in map(json.loads, out.read_text().splitlines())
            if not r.get("error")} if out.exists() else set()
    with ThreadPoolExecutor(8) as ex:
        res = list(ex.map(narr, [j for j in jobs if j not in done]))
    with out.open("a") as f:
        for r in res:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print("narrator calls", len(res), "errors", sum(1 for r in res if r.get("error")),
          "spend", round(spend.total, 4))

    # director on the prose outputs (sequential, to time each step on its own)
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    prose = [r for r in rows if r["variant"] == "prose" and not r.get("error") and r["sample"] == 0]
    dout = RAW / "director.jsonl"
    dres = []
    for r in prose:
        it = L.NARR[r["id"]]
        npcs = {c: L.P.NAMES.get(c, c) for c in it["present"] if c != "player"}
        text = G.apply(r["text"])
        state = [f"Location: {it['location']}", f"The player does/says: {it['player']}",
                 f"Narration: {text}"]
        t = time.monotonic()
        try:
            spk = decide_speakers(judge, state, npcs) if npcs else []
        except Exception as e:  # noqa: BLE001
            spk = f"ERROR {e}"
        t_spk = time.monotonic() - t
        t = time.monotonic()
        raw = prov.complete(DEFAULT_EXTRACTOR, actions_messages(
            text, names=list(npcs.values()), language="English", glossary_line=G.prompt_line(text)))
        t_act = time.monotonic() - t
        dres.append(dict(id=r["id"], speakers=spk, actions=parse_actions(raw),
                         t_decider=round(t_spk, 2), t_actions=round(t_act, 2),
                         expected=it.get("notes", "")))
    dout.write_text("\n".join(json.dumps(d, ensure_ascii=False) for d in dres))
    print("director rows", len(dres), "spend", round(spend.total, 4))


if __name__ == "__main__":
    main()
