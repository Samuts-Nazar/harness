"""Narrator bake-off: blind grades joined with the key."""
import json
import statistics as st
from collections import defaultdict
from pathlib import Path

RAW = Path(__file__).parent / "raw"
KEY = json.loads((RAW / "key_narr.json").read_text())
ROWS = {}
for l in (RAW / "narr.jsonl").read_text().splitlines():
    r = json.loads(l)
    ROWS[(r["id"], r["variant"], r["model"], r["sample"])] = r
G = {}
for f in sorted(RAW.glob("grades_narr_*.txt")):
    for line in f.read_text().split("\n"):
        if line.strip():
            p = line.split()
            G[p[0]] = [int(x) for x in p[1:]]
agg = defaultdict(lambda: defaultdict(list))
for rid, g in G.items():
    k = KEY[rid]
    r = ROWS[(k["id"], k["variant"], k["model"], k["sample"])]
    for key in (k["variant"], (k["model"].split("/")[1], k["variant"])):
        a = agg[key]
        a["S"].append(g[0]); a["U"].append(g[1]); a["P"].append(g[2])
        a["words"].append(len(r["text"].split())); a["cost"].append(r["cost"])
        a["lat"].append(r["latency"]); a["tin"].append(r["tokens_in"])
print("n graded", len(G), "of", len(KEY))
for k in sorted(agg, key=str):
    a = agg[k]
    m = lambda x: st.mean(a[x])
    print(f"{str(k):32s} n={len(a['S']):2d} S={m('S'):.2f} U={m('U'):.2f} decides_player={m('P'):.2f} "
          f"words={m('words'):.0f} cost={m('cost'):.5f} lat={m('lat'):.1f} tin={m('tin'):.0f}")
