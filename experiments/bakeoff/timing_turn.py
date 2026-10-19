"""Seconds per turn with the recommended stack: sequential vs parallel (real calls).

A turn: narrator -> speech check -> [NPC line -> NPC check] x2 speakers -> extractor -> 2 salience judges.
Parallel plan: after the narrator, the speech check, both NPC chains and the extractor-on-narration run
concurrently; the extractor on NPC lines and the judges follow (the NPC-line extractor needs the lines).
Prints per-step latency and wall-clock per plan; display-critical path = time until the first NPC line can be shown.
"""
import json, os, statistics as st, sys, time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import httpx
from dotenv import load_dotenv
from experiments.common import llm
from harness.narrator import clean_npc_line
from . import prompts
from .npc_check import Q0, context, items as npc_items

load_dotenv()
HERE = Path(__file__).parent
TEXT = sys.argv[1] if len(sys.argv) > 1 else "openai/gpt-6-luna"
DEC = sys.argv[2] if len(sys.argv) > 2 else "liquid/d1-ultra"
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
narr = {i["id"]: i for i in json.loads((HERE / "testset/narrator.json").read_text())}
ext = {i["id"]: i for i in json.loads((HERE / "testset/extract.json").read_text())}


def timed(fn, *a):
    t = time.perf_counter()
    r = fn(*a)
    return r, time.perf_counter() - t


def chat(messages, mt):
    return llm.chat(TEXT, messages, exp="task7", cap=0.9, max_tokens=mt)["text"]


def decide(state, q):
    body = {"model": DEC, "state": [state], "questions": {"q": {"type": "noul", "instructions": q}}}
    for i in range(6):
        r = httpx.post("https://openrouter.ai/api/v1/systemone", headers=H, json=body, timeout=60)
        if r.status_code != 429:
            break
        time.sleep(1 + i)
    r.raise_for_status()
    return r.json()["answers"]["q"]["noul"]


def npc_chain(it):
    t = {}
    line, t["npc"] = timed(lambda: clean_npc_line(chat(prompts.npc(it), 500)))
    _, t["check"] = timed(decide, context(it, line), Q0)
    return t


def turn(plan, n):
    t = {}
    nit = narr[n]
    text, t["narrator"] = timed(chat, prompts.narrator(nit), 1200)
    npcs = [npc_items["c01"], npc_items["c06"]]
    exi = ext["e06"]
    if plan == "seq":
        t0 = time.perf_counter()
        _, t["speech_check"] = timed(decide, "Player character: Ragnar\nText: " + text[:600], "Does the text state what a character other than the player character says aloud?")
        chains = [npc_chain(i) for i in npcs]
        first_line = time.perf_counter() - t0
        _, t["extract"] = timed(lambda: chat(prompts.extractor(exi), 1200))
        _, t["judges"] = timed(lambda: [decide("Observer: Triss\nRagnar carries a bloody sack.", "Would the observer react?") for _ in range(2)])
        total = sum(t.values()) + sum(c["npc"] + c["check"] for c in chains) - 0
        wall = t["narrator"] + t["speech_check"] + sum(c["npc"] + c["check"] for c in chains) + t["extract"] + t["judges"]
        display = t["narrator"] + t["speech_check"] + chains[0]["npc"] + chains[0]["check"]
        return dict(wall=wall, display=display)
    t0 = time.perf_counter()
    with ThreadPoolExecutor(6) as ex:
        f_sp = ex.submit(timed, decide, "Player character: Ragnar\nText: " + text[:600], "Does the text state what a character other than the player character says aloud?")
        f_ch = [ex.submit(npc_chain, i) for i in npcs]
        f_ex = ex.submit(timed, lambda: chat(prompts.extractor(exi), 1200))
        sp = f_sp.result()[1]
        chains = [f.result() for f in f_ch]
        f_ex.result()
        # second wave: extractor over NPC lines + salience judges in parallel
        f2 = [ex.submit(timed, lambda: chat(prompts.extractor(exi), 1200))] + [
            ex.submit(timed, decide, "Observer: Triss\nRagnar carries a bloody sack.", "Would the observer react?") for _ in range(2)]
        for f in f2:
            f.result()
    wall = t["narrator"] + (time.perf_counter() - t0)
    display = t["narrator"] + max(sp, chains[0]["npc"] + chains[0]["check"])
    return dict(wall=wall, display=display)


def main():
    res = {"seq": [], "par": []}
    scenes = ["n01", "n05", "n06", "n09"]
    for rep, n in enumerate(scenes):
        for plan in ("seq", "par"):
            r = turn(plan, n)
            res[plan].append(r)
            print(plan, n, {k: round(v, 2) for k, v in r.items()}, flush=True)
    summary = {p: {k: round(st.mean(x[k] for x in v), 2) for k in ("wall", "display")} for p, v in res.items()}
    print(TEXT, DEC, summary)
    (HERE / "raw/timing.json").write_text(json.dumps(dict(text=TEXT, decider=DEC, runs=res, summary=summary), indent=1))


if __name__ == "__main__":
    main()
