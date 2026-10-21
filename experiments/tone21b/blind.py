"""Shuffle probe outputs into a blind packet (labels A.. per moment) and a key. Usage: blind.py IN.json OUTDIR"""
import json
import random
import sys

res = json.load(open(sys.argv[1]))
out = sys.argv[2]
rnd = random.Random(2110)
key, lines = {}, []
for mid in ["i1", "i3", "c07", "c11", "c08"]:
    rows = [r for r in res if r["id"] == mid and r["text"]]
    rnd.shuffle(rows)
    lines.append(f"## moment {mid}\n")
    for n, r in enumerate(rows):
        lab = "ABCDEFGHIJKL"[n]
        key[f"{mid}/{lab}"] = f"{r['v']}.{r['k']}"
        lines.append(f"### {mid}/{lab}\n{r['text']}\n")
open(out + "/packet.md", "w").write("\n".join(lines))
json.dump(key, open(out + "/key.json", "w"), indent=1)
print(len(key))
