"""Join blind grades with the key; tables by variant and model. Also mechanical metrics:
assistant-isms (code), beat presence, Ukrainian glitches (non-Cyrillic/Latin runs), length."""
import json
import re
import statistics as st
from collections import defaultdict
from pathlib import Path

from harness.style import assistant_isms, split_npc_output

RAW = Path(__file__).parent / "raw"
KEY = json.loads((RAW / "key_npc.json").read_text())
ROWS = {}
for l in (RAW / "npc.jsonl").read_text().splitlines():
    r = json.loads(l)
    ROWS[(r["id"], r["variant"], r["model"], r["sample"])] = r
G = {}
for f in sorted(RAW.glob("grades_npc_*.txt")):
    for line in f.read_text().split("\n"):
        if line.strip():
            p = line.split()
            G[p[0]] = [int(x) for x in p[1:]]
assert len(G) == len(KEY), (len(G), len(KEY))

FOREIGN = re.compile(r"[一-鿿԰-֏]|\b[A-Za-z]{4,}\b")


def table(by):
    agg = defaultdict(lambda: defaultdict(list))
    for rid, g in G.items():
        k = KEY[rid]
        r = ROWS[(k["id"], k["variant"], k["model"], k["sample"])]
        keyv = by(k)
        a = agg[keyv]
        a["S"].append(g[0]); a["L"].append(g[1]); a["U"].append(g[2])
        a["C"].append(g[3]); a["K"].append(g[4]); a["A"].append(g[5])
        a["ism"].append(1 if assistant_isms(r["text"]) else 0)
        a["glitch"].append(1 if FOREIGN.search(r["text"]) else 0)
        a["beats"].append(1 if split_npc_output(r["text"]).beats else 0)
        a["words"].append(len(r["text"].split()))
        a["cost"].append(r["cost"]); a["lat"].append(r["latency"]); a["tin"].append(r["tokens_in"])
    return agg


def show(title, agg):
    print(f"\n{title}\n{'key':42s} n   S    L    U    inchar leak  acts  ism  glitch beats words cost$   lat  tin")
    for k in sorted(agg):
        a = agg[k]
        m = lambda x: st.mean(a[x])
        print(f"{str(k):42s} {len(a['S']):3d} {m('S'):.2f} {m('L'):.2f} {m('U'):.2f} {m('C'):.2f}   {m('K'):.2f}  {m('A'):.2f}  {m('ism'):.2f} {m('glitch'):.2f}   {m('beats'):.2f}  {m('words'):4.0f} {m('cost'):.5f} {m('lat'):4.1f} {m('tin'):.0f}")


show("by variant", table(lambda k: k["variant"]))
show("by model x variant", table(lambda k: (k["model"].split("/")[1], k["variant"])))
show("by situation x variant", table(lambda k: (k["id"], k["variant"])))
