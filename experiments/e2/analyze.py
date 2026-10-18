import json, pathlib, collections, statistics as st
H = pathlib.Path(__file__).parent
R = [json.loads(l) for l in (H / "results/raw.jsonl").read_text().splitlines()]
out = []
def correct(r): return r["pred"] == r["label"]
systems = list(dict.fromkeys(r["system"] for r in R))
def brier(rows):  # binary types only: p_yes vs label
    v = [(r["p_yes"] - (1 if r["label"] == "yes" else 0)) ** 2 for r in rows if r.get("p_yes") is not None]
    return sum(v) / len(v) if v else float("nan")
def ece(rows, bins=3):
    rr = [r for r in rows if r.get("p") is not None and r["pred"] is not None]
    if not rr: return float("nan")
    tot = 0
    for b in range(bins):
        lo, hi = 0.5 + b * 0.5 / bins, 0.5 + (b + 1) * 0.5 / bins
        sel = [r for r in rr if lo <= r["p"] < hi or (b == bins - 1 and r["p"] == 1.0)]
        if sel: tot += len(sel) * abs(sum(r["p"] for r in sel) / len(sel) - sum(correct(r) for r in sel) / len(sel))
    return tot / len(rr)
types = ["contradiction", "relationship", "salience", "uncertainty"]
out.append("| system | overall acc | " + " | ".join(types) + " | acc (non-unsure) | Brier (binary) | ECE (3 bins) | p50 latency s | p95 latency s | $ / 1000 judgments | unparsed |")
out.append("|" + "---|" * (len(types) + 9))
for s in systems:
    rows = [r for r in R if r["system"] == s]
    acc = lambda rs: sum(correct(r) for r in rs) / len(rs) if rs else float("nan")
    lat = sorted(r["latency"] for r in rows if r["latency"])
    cost = sum(r["cost"] for r in rows) / len(rows) * 1000
    bin_rows = [r for r in rows if r["type"] != "relationship"]
    out.append(f"| {s} | {acc(rows):.2f} | " + " | ".join(f"{acc([r for r in rows if r['type']==t]):.2f}" for t in types) +
               f" | {acc([r for r in rows if not r['unsure']]):.2f} | {brier(bin_rows):.3f} | {ece(rows):.3f} | {st.median(lat):.2f} | {lat[int(.95*(len(lat)-1))]:.2f} | {cost:.3f} | {sum(r['pred'] is None for r in rows)} |")
# relationship magnitude MAE
out.append("\nRelationship magnitude MAE (0-3 scale):")
for s in systems:
    rr = [r for r in R if r["system"] == s and r["type"] == "relationship" and isinstance(r.get("mag"), (int, float))]
    out.append(f"- {s}: {sum(abs(round(r['mag']) - r['magnitude']) for r in rr)/len(rr):.2f} (n={len(rr)})")
# rep consistency
out.append("\nRepeat-run disagreement (same item, 2 runs):")
for s in systems:
    g = collections.defaultdict(list)
    for r in R:
        if r["system"] == s: g[r["item"]].append(r["pred"])
    out.append(f"- {s}: {sum(len(set(v))>1 for v in g.values())}/{len(g)} items changed")
# per-item errors for Jev 1.14 and for best LLM
out.append("\nItems wrong for each system (item ids, rep 0):")
for s in systems:
    w = [r["item"] for r in R if r["system"] == s and r["rep"] == 0 and not correct(r)]
    out.append(f"- {s}: {', '.join(w)}")
# bins of confidence vs correct
out.append("\nConfidence calibration (all items; p = prob of predicted class):")
for s in systems:
    rr = [r for r in R if r["system"] == s and r.get("p") is not None and r["pred"] is not None]
    cells = []
    for lo, hi in ((0.5, .8), (.8, .95), (.95, 1.01)):
        sel = [r for r in rr if lo <= r["p"] < hi]
        cells.append(f"[{lo:.2f},{min(hi,1):.2f}): n={len(sel)} acc={sum(correct(r) for r in sel)/len(sel):.2f}" if sel else f"[{lo:.2f},{min(hi,1):.2f}): n=0")
    out.append(f"- {s}: " + "; ".join(cells))
(H / "results/summary.md").write_text("\n".join(out)); print("\n".join(out))
