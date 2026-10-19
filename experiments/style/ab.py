"""Build the blind A/B set: per situation the best old output against the best new output (by the
blind grades: Sapkowski + liveliness + Ukrainian, no leak, no acting for others, no glitch).
The page gets only the shuffled texts; the key goes to reports/style/ab_key.json.

    PYTHONPATH=. python -m experiments.style.ab
"""
import json
import random
import re
from pathlib import Path

from experiments.style import scenes as S

RAW = Path(__file__).parent / "raw"
REPO = Path(__file__).resolve().parents[2]
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
BAD = re.compile(r"[一-鿿԰-֏]|\b[A-Za-z]{4,}\b")

best: dict[tuple[str, str], tuple[float, dict]] = {}
for rid, g in G.items():
    k = KEY[rid]
    r = ROWS[(k["id"], k["variant"], k["model"], k["sample"])]
    if g[4] or g[5] or not g[3] or BAD.search(r["text"]) or len(r["text"].split()) > 140:
        continue
    kind = "old" if k["variant"] == "old" else "new"
    score = g[0] + g[1] + g[2] + (0.5 if k["model"].endswith("luna") else 0)
    cur = best.get((k["id"], kind))
    if cur is None or score > cur[0]:
        best[(k["id"], kind)] = (score, {**k, "text": r["text"]})

rng = random.Random(1015)
pairs, key = [], []
for sid in S.npc_ids():
    old, new = best[(sid, "old")][1], best[(sid, "new")][1]
    flip = rng.random() < 0.5
    a, b = (new, old) if flip else (old, new)
    npc = S.INN[sid][0] if sid in S.INN else S.NPC_SET[sid]["npc"]
    last = S.INN[sid][1][-1][1] if sid in S.INN else S.NPC_SET[sid]["recent"][-1][1]
    who = {"horst": "Горст", "elza": "Ельза"}.get(npc) or S.PROF["names"].get(npc, npc)
    pairs.append({"who": who, "player": last, "a": a["text"], "b": b["text"]})
    key.append({"situation": sid, "A": "new" if flip else "old", "B": "old" if flip else "new",
                "new_variant": new["variant"], "new_model": new["model"], "old_model": old["model"]})
rng.shuffle(order := list(range(len(pairs))))
pairs, key = [pairs[i] for i in order], [key[i] for i in order]
out = REPO / "app" / "static" / "ab_data.js"
out.write_text("window.AB_PAIRS = " + json.dumps(pairs, ensure_ascii=False, indent=1) + ";\n",
               encoding="utf-8")
(REPO / "reports" / "style").mkdir(parents=True, exist_ok=True)
(REPO / "reports" / "style" / "ab_key.json").write_text(
    json.dumps(key, ensure_ascii=False, indent=1), encoding="utf-8")
print(len(pairs), "pairs")
for p, k in zip(pairs, key):
    print(k["situation"], k["A"], k["new_variant"], k["new_model"], "|", p["a"][:70].replace("\n", " "),
          "||", p["b"][:70].replace("\n", " "))
