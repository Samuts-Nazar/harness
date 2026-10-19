"""Join blind grades with the key; variety = how similar the 3 samples of one item are (trigram
overlap and shared first two words), by variant."""
import json
import re
from collections import defaultdict
from itertools import combinations
from pathlib import Path

from harness.repetition import trigrams, words

HERE = Path(__file__).parent
key = json.loads((HERE / "raw" / "blind_key.json").read_text())
# id: (Ukrainian quality 1-5, flags)  S = NPC speech in the text, P = decides/embellishes the
# player character's acts, R = calque or wrong form, N = Latin or mangled name
G = """1 5;2 4 S;3 5;4 5;5 4 P;6 4;7 4 S;8 4 S;9 5;10 4;11 4;12 4;13 5;14 4;15 4;16 4;17 4;18 4;19 4;20 5;
21 4;22 4;23 4;24 4;25 4;26 4;27 4;28 5;29 4;30 4;31 4;32 5;33 4 P;34 4;35 5;36 5;37 4;38 4 S;39 4;40 4;
41 4;42 4;43 5;44 4;45 5;46 3 R;47 4;48 4;49 5;50 5;51 4;52 4;53 5;54 4"""
grades = {}
for part in re.split(r"[;\n]+", G):
    t = part.split()
    if t:
        grades[t[0]] = (int(t[1]), t[2:] )
raws = {}
for x in (HERE / "raw" / "narr.jsonl").read_text().splitlines():
    r = json.loads(x)
    t = r["text"]
    if r["variant"] == "json":
        try:
            t = json.loads(t.strip("`").removeprefix("json").strip())["description"]
        except Exception:  # noqa: BLE001
            pass
    raws[(r["id"], r["variant"], r["sample"])] = t

by = defaultdict(list)
for k, (iid, var, s) in key.items():
    q, fl = grades[k]
    by[var].append((iid, q, fl))
print("variant  n  Ukrainian  speech  decides-player  calque  names")
for var, rows in by.items():
    n = len(rows)
    print(f"{var:7} {n:3} {sum(q for _, q, _ in rows) / n:.2f}   "
          f"{sum('S' in f for *_, f in rows)}/{n}  {sum('P' in f for *_, f in rows)}/{n}  "
          f"{sum('R' in f for *_, f in rows)}/{n}  {sum('N' in f for *_, f in rows)}/{n}")

# per-item paired difference prose - json (mean over samples), bootstrap
import random
items = sorted({v[0] for v in key.values()})
d = []
for it in items:
    a = [grades[k][0] for k, v in key.items() if v[0] == it and v[1] == "prose"]
    b = [grades[k][0] for k, v in key.items() if v[0] == it and v[1] == "json"]
    d.append(sum(a) / len(a) - sum(b) / len(b))
rng = random.Random(1)
bs = sorted(sum(rng.choice(d) for _ in d) / len(d) for _ in range(5000))
print("quality prose - json: %.2f (95%% CI %.2f..%.2f)" % (sum(d) / len(d), bs[125], bs[4875]))

sim = defaultdict(list)
for var in ("json", "prose"):
    for it in items:
        txt = [raws[(it, var, s)] for s in range(3)]
        for a, b in combinations(txt, 2):
            ta, tb = set(trigrams(words(a))), set(trigrams(words(b)))
            oa = {tuple(words(s)[:2]) for s in re.split(r"(?<=[.!?])\s+", a) if words(s)}
            ob = {tuple(words(s)[:2]) for s in re.split(r"(?<=[.!?])\s+", b) if words(s)}
            sim[var].append((len(ta & tb) / max(1, min(len(ta), len(tb))),
                             len(oa & ob) / max(1, min(len(oa), len(ob)))))
for var, v in sim.items():
    print(var, "between-sample overlap: trigram %.3f, opening %.3f" % (
        sum(a for a, _ in v) / len(v), sum(b for _, b in v) / len(v)))
firsts = defaultdict(list)
for var in ("json", "prose"):
    lens = [len(words(raws[(it, var, s)])) for it in items for s in range(3)]
    print(var, "mean words", round(sum(lens) / len(lens), 1))
