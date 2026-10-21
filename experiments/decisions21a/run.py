"""Task 21A: does the decision layer pick the book-like option or the typical one?
Usage: python experiments/decisions21a/run.py METHOD [--points p01,p02] [--n 5]
Methods:
  dec:<model>[+state]   hosted decider, 3 option orders, mean probability per option
  llm[+state]           closed-list pick by the chat LLM, n samples, shuffled order each
  vs[+state]            verbalized sampling: the LLM writes a probability distribution over options
  open                  the LLM lists 6 things the character might do (no options given); graded by hand
Raw rows go to campaigns/21A/raw.jsonl (git-ignored)."""
import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, LETTERS, chat, decide, orders, parse_json_dist, parse_letter  # noqa: E402

LLM = "openai/gpt-6-luna"
SYS = ("You decide what a character in a novel does next. The setting is Andrzej Sapkowski's Witcher world "
       "(the book 'The Last Wish'). Stay true to this specific person in this specific moment.")


ANON = [("Geralt", "Arvid"), ("Foltest", "Hadrian"), ("Velerad", "Brenn"), ("Ostrit", "Tavish"),
        ("Vizima", "Carrowmere"), ("Rivian", "Dunmarker"), ("Rivia", "Dunmark"), ("witchers", "monster-hunters"),
        ("witcher", "monster-hunter"), ("strzyga", "ghoul-girl"), ("orens", "crowns"), ("Adda", "Mira"),
        ("Signs", "charms"), ("Sign", "charm"), ("Under the Fox", "The Sign of the Hare")]


def transform(p, flags):
    """+anon: rename names and world words (defeats recall of the book); +noscene: options only."""
    p = json.loads(json.dumps(p))
    if "anon" in flags:
        def an(t):
            for a, b in ANON:
                t = t.replace(a, b)
            return t
        for k in ("actor", "situation", "state"):
            p[k] = an(p[k])
        p["options"] = [an(o) for o in p["options"]]
    if "noscene" in flags:
        p["situation"] = "A character in a medieval fantasy novel faces a decision."
        p["state"] = ""
        p["actor"] = "the character"
    return p


def scene(p, with_state):
    s = f"Scene: {p['situation']}"
    if with_state:
        s += f"\nCharacter: {p['state']}"
    return s


def run_dec(p, model, with_state, k=3):
    rows = []
    for oi, order in enumerate(orders(len(p["options"]), k, seed=int(p["id"][1:]))):
        opts = [p["options"][i] for i in order]
        state = [p["situation"]] + ([p["state"]] if with_state else [])
        probs, _ = decide(model, state, f"What does {p['actor']} do next?", opts)
        dist = [probs.get(p["options"][i], 0.0) for i in range(len(p["options"]))]
        s = sum(dist) or 1
        rows.append({"dist": [x / s for x in dist], "order": oi})
    return rows


def run_llm(p, with_state, n):
    rows = []
    for si, order in enumerate(orders(len(p["options"]), n, seed=17 + int(p["id"][1:]))):
        opts = [p["options"][i] for i in order]
        lst = "\n".join(f"{LETTERS[j]}. {o}" for j, o in enumerate(opts))
        user = (f"{scene(p, with_state)}\n\nWhat does {p['actor']} do next?\n{lst}\n\n"
                "Answer with the single letter of the option only.")
        out = chat(LLM, SYS, user, max_tokens=8)
        j = parse_letter(out, len(opts))
        dist = [0.0] * len(opts)
        if j is not None:
            dist[order[j]] = 1.0
        rows.append({"dist": dist, "raw": out.strip()[:20], "ok": j is not None})
    return rows


def run_vs(p, with_state, n):
    rows = []
    for si, order in enumerate(orders(len(p["options"]), n, seed=91 + int(p["id"][1:]))):
        opts = [p["options"][i] for i in order]
        lst = "\n".join(f"{LETTERS[j]}. {o}" for j, o in enumerate(opts))
        user = (f"{scene(p, with_state)}\n\nWhat does {p['actor']} do next?\n{lst}\n\n"
                "Imagine many different tellings of this moment by the author. Give the probability of each "
                "option being what happens, as a JSON object mapping letter to probability (sum 1), nothing else.")
        out = chat(LLM, SYS, user, max_tokens=120)
        d = parse_json_dist(out, len(opts))
        dist = [0.0] * len(opts)
        if d:
            for j, v in enumerate(d):
                dist[order[j]] = v
        rows.append({"dist": dist, "ok": d is not None})
    return rows


def run_open(p, n):
    rows = []
    for i in range(n):
        user = (f"Scene: {p['situation']}\n\nList six different things {p['actor']} might do or say next, "
                "from the most expected to the least expected but still entirely in character. One line each, "
                "numbered 1-6, no commentary.")
        rows.append({"text": chat(LLM, SYS, user, max_tokens=300)})
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("method")
    ap.add_argument("--points")
    ap.add_argument("--n", type=int, default=5)
    a = ap.parse_args()
    pts = json.load(open(DATA / ("points_eq.json" if "+eq" in a.method else "points.json")))
    if a.points:
        keep = set(a.points.split(","))
        pts = [p for p in pts if p["id"] in keep]
    m = a.method
    flags = set(m.split("+")[1:])
    base = m.split("+")[0]
    with_state = "state" in flags
    pts = [transform(p, flags) for p in pts]

    def one(p):
        if base.startswith("dec:"):
            return run_dec(p, base[4:], with_state)
        if base == "llm":
            return run_llm(p, with_state, a.n)
        if base == "vs":
            return run_vs(p, with_state, a.n)
        if base == "open":
            return run_open(p, a.n)
        raise SystemExit("unknown method")

    with ThreadPoolExecutor(4) as ex:
        results = list(ex.map(one, pts))
    with (DATA / "raw.jsonl").open("a") as f:
        for p, rows in zip(pts, results):
            f.write(json.dumps({"method": m, "id": p["id"], "rows": rows}, ensure_ascii=False) + "\n")
    print(m, "done", len(pts), "points")


main()
