import json, glob, statistics as st
from collections import defaultdict

rows = []
for f in sorted(glob.glob("experiments/bakeoff/raw/decide_*.jsonl")):
    rows += [json.loads(l) for l in open(f)]
models = sorted({r["model"] for r in rows})
out = {}


def stats(rs):
    rs = [r for r in rs if r["p_yes"] is not None]
    if not rs:
        return None
    ok = [(r["p_yes"] >= 0.5) == r["gold"] for r in rs]
    conf = [max(r["p_yes"], 1 - r["p_yes"]) for r in rs]
    brier = st.mean((r["p_yes"] - float(r["gold"])) ** 2 for r in rs)
    hi = [o for o, c in zip(ok, conf) if c >= 0.8]
    lo = [o for o, c in zip(ok, conf) if c < 0.8]
    # ECE with 5 equal-width confidence bins over [0.5, 1]
    bins = defaultdict(list)
    for o, c in zip(ok, conf):
        bins[min(int((c - 0.5) / 0.1), 4)].append((o, c))
    ece = sum(len(b) / len(rs) * abs(st.mean(o for o, _ in b) - st.mean(c for _, c in b)) for b in bins.values())
    return dict(n=len(rs), acc=round(st.mean(ok), 3), brier=round(brier, 3), ece=round(ece, 3),
                esc=round(len(lo) / len(rs), 3), acc_hi=round(st.mean(hi), 3) if hi else None,
                acc_lo=round(st.mean(lo), 3) if lo else None,
                lat=round(st.mean(r["latency"] for r in rs), 3),
                lat_p95=round(sorted(r["latency"] for r in rs)[int(0.95 * (len(rs) - 1))], 3),
                cost1k=round(1000 * st.mean(r["cost"] for r in rs), 4))


for m in models:
    mr = [r for r in rows if r["model"] == m]
    d = dict(all=stats(mr))
    for c in ("en", "uk", "mixed"):
        d[c] = stats([r for r in mr if r["cond"] == c])
    for t in sorted({r["type"] for r in mr}):
        d["type:" + t] = stats([r for r in mr if r["type"] == t])
    # EN vs UK on the same items
    both = [r for r in mr if r["cond"] in ("en", "uk")]
    out[m] = d
json.dump(out, open("reports/bakeoff/decide_metrics.json", "w"), indent=1, ensure_ascii=False)
print(f"{'model':38s} {'acc':>5} {'en':>5} {'uk':>5} {'mix':>5} {'brier':>6} {'ece':>5} {'<0.8':>5} {'hi':>5} {'lo':>5} {'lat':>6} {'$/1k':>7}")
for m, d in out.items():
    a = d["all"]
    print(f"{m:38s} {a['acc']:5.3f} {d['en']['acc']:5.3f} {d['uk']['acc']:5.3f} {d['mixed']['acc']:5.3f} "
          f"{a['brier']:6.3f} {a['ece']:5.3f} {a['esc']:5.3f} {a['acc_hi'] or 0:5.3f} {a['acc_lo'] or 0:5.3f} {a['lat']:6.3f} {a['cost1k']:7.4f}")
print()
types = sorted({k[5:] for k in out[models[0]] if k.startswith("type:")})
print(f"{'model':38s} " + " ".join(f"{t[:8]:>8}" for t in types))
for m, d in out.items():
    print(f"{m:38s} " + " ".join(f"{d['type:'+t]['acc']:8.3f}" for t in types))
