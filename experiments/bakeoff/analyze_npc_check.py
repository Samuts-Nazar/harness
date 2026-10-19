import json
from collections import defaultdict
rows = [json.loads(l) for l in open("experiments/bakeoff/raw/npc_check.jsonl")]
res = {}
print("lines graded clean:", sum(1 for r in rows if r["check_model"] == "liquid/d1-ultra" and r["variant"] == "v0" and not r["leak"]),
      "leaky:", sum(1 for r in rows if r["check_model"] == "liquid/d1-ultra" and r["variant"] == "v0" and r["leak"]))
print(f"{'checker':32s} {'var':3s} {'thr':>4s} {'false-rej':>10s} {'detect':>7s}")
for m in sorted({r["check_model"] for r in rows}):
    for v in ("v0", "v1"):
        rs = [r for r in rows if r["check_model"] == m and r["variant"] == v]
        clean = [r for r in rs if not r["leak"]]
        leaky = [r for r in rs if r["leak"]]
        for t in (0.5, 0.7, 0.9, 0.97):
            fr = sum(r["p"] >= t for r in clean) / len(clean)
            dt = sum(r["p"] >= t for r in leaky) / len(leaky)
            res[f"{m}|{v}|{t}"] = (round(fr, 3), round(dt, 3), len(clean), len(leaky))
            print(f"{m:32s} {v:3s} {t:4.2f} {fr:10.3f} {dt:7.3f}")
json.dump(res, open("reports/bakeoff/npc_check_metrics.json", "w"), indent=1)
# which clean lines were rejected most often by v0 at 0.5 (all checkers)
cnt = defaultdict(int)
for r in rows:
    if r["variant"] == "v0" and not r["leak"] and r["p"] >= 0.5:
        cnt[r["id"]] += 1
print(sorted(cnt.items(), key=lambda x: -x[1])[:15])
