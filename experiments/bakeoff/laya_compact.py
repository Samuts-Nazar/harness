"""Laya on the engine's real NPC-check state (Ukrainian lines): token counts, truncation, accuracy; plus EN-vs-UK
paired comparison for all decision models on the 36 'both' judgments."""
import json, glob, statistics as st
import httpx
from . import npc_check as nc

rows = {}
for m in ("english", "multilingual"):
    res = []
    toks, trunc = [], 0
    for k, g in nc.grades.items():
        if g["fmt"]:
            continue
        s, iid, lab = k.split("/")
        line = nc.clean_npc_line(nc.rows[(s, iid, nc.key[k])]["text"])
        body = {"model": m, "state": [nc.context(nc.items[iid], line)],
                "questions": {"q": {"type": "noul", "instructions": nc.Q0}}}
        j = httpx.post("http://127.0.0.1:8765/v1/systemone", json=body, timeout=120).json()
        p = j["answers"]["q"]["noul"]
        u = j["usage"]
        toks.append(u["state_tokens"] + u["input_tokens"] - u["state_tokens"]); trunc += int(u["truncated"] or u["state_tokens_dropped"] > 0)
        res.append(((p >= 0.5) == bool(g["leak"]), p, g["leak"]))
    acc = st.mean(r[0] for r in res)
    print(m, "n", len(res), "acc", round(acc, 3), "leak-rate", round(st.mean(r[2] for r in res), 3),
          "mean input tokens", round(st.mean(toks)), "max", max(toks), "truncated", trunc,
          "flag-rate", round(st.mean(r[1] >= 0.5 for r in res), 3))

# EN vs UK paired
dec = {}
for f in glob.glob("experiments/bakeoff/raw/decide_*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r["cond"] in ("en", "uk") and r["p_yes"] is not None:
            dec.setdefault(r["model"], {}).setdefault(r["id"], {})[r["cond"]] = (r["p_yes"] >= 0.5) == r["gold"]
tot = {"en_only": 0, "uk_only": 0, "both": 0, "neither": 0}
for m, d in sorted(dec.items()):
    c = {"en_only": 0, "uk_only": 0, "both": 0, "neither": 0}
    for i, v in d.items():
        c["both" if v["en"] and v["uk"] else "en_only" if v["en"] else "uk_only" if v["uk"] else "neither"] += 1
    for k in c:
        tot[k] += c[k]
    n = sum(c.values())
    print(f"{m:36s} EN {100*(c['both']+c['en_only'])/n:5.1f}%  UK {100*(c['both']+c['uk_only'])/n:5.1f}%  EN-only-right {c['en_only']}  UK-only-right {c['uk_only']}")
print("pooled (excluding laya):", tot)
