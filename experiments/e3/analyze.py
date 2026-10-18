import json, pathlib, collections, statistics as st
H = pathlib.Path(__file__).parent
R = [json.loads(l) for l in (H / "results/raw.jsonl").read_text().splitlines()]
P = {json.loads(l)["id"]: json.loads(l) for l in (H / "passages.jsonl").read_text().splitlines()}
models = list(dict.fromkeys(r["model"] for r in R))
WS = {"same": 1.0, "superset": .5, "subset": .5, "partial": .5, "different": 0.0}
def f1(p, r): return 2 * p * r / (p + r) if p + r else 0.0
out = ["| model | JSON ok | fact recall | fact precision | fact F1 | hallucinated facts (% of predicted) | witness exact | witness graded | inv F1 | injury F1 | rel F1 | pred facts / passage | $ / 100 turns | p50 latency s |", "|" + "---|" * 14]
detail = {}
for m in models:
    rows = [r for r in R if r["model"] == m]
    sc = [r for r in rows if r["score"]]
    nG = sum(len(P[r["passage"]]["gold"]["facts"]) for r in sc)
    cov = npred = match = unsup = 0; wsum = wex = wn = 0
    cat = {k: [0, 0, 0] for k in ("inventory", "injuries", "relationships")}
    for r in sc:
        fl = r["score"].get("facts", []) or []
        gi = set(); 
        npred += len(r["pred"]["facts"])
        for f in fl:
            if f.get("gold_index") is not None and f["gold_index"] not in gi:
                gi.add(f["gold_index"]); match += 1
                w = f.get("witnesses"); wn += 1; wsum += WS.get(w, 0); wex += (w == "same")
            elif f.get("supported") is False:
                unsup += 1
        cov += len(gi)
        for k in cat:
            d = r["score"].get(k) or {}
            for i, key in enumerate(("tp", "fp", "fn")): cat[k][i] += int(d.get(key, 0) or 0)
    rec = cov / nG; prec = match / npred if npred else 0
    cf = lambda k: f1(cat[k][0] / (cat[k][0] + cat[k][1]) if cat[k][0] + cat[k][1] else 0, cat[k][0] / (cat[k][0] + cat[k][2]) if cat[k][0] + cat[k][2] else 0)
    cost = sum(r["cost"] for r in rows) / len(rows) * 100
    lat = st.median(r["latency"] for r in rows)
    out.append(f"| {m} | {sum(r['valid_json'] for r in rows)}/{len(rows)} | {rec:.2f} | {prec:.2f} | {f1(prec, rec):.2f} | {unsup/npred:.1%} | {wex/wn:.2f} | {wsum/wn:.2f} | {cf('inventory'):.2f} | {cf('injuries'):.2f} | {cf('relationships'):.2f} | {npred/len(sc):.1f} | {cost:.3f} | {lat:.1f} |")
    detail[m] = dict(cat=cat, unscored=len(rows) - len(sc), nG=nG, cov=cov, npred=npred, match=match, unsup=unsup)
out.append("\nGold totals: facts %d, inventory %d, injuries %d, relationships %d, passages %d" % (
    sum(len(p["gold"]["facts"]) for p in P.values()), sum(len(p["gold"]["inventory"]) for p in P.values()),
    sum(len(p["gold"]["injuries"]) for p in P.values()), sum(len(p["gold"]["relationships"]) for p in P.values()), len(P)))
out.append("\nRaw category counts (tp, fp, fn) and unscored:")
for m, d in detail.items(): out.append(f"- {m}: {d['cat']}, unscored {d['unscored']}")
# recall per passage for hardest
out.append("\nPer-passage fact recall averaged over models (lowest 6):")
pr = collections.defaultdict(list)
for r in R:
    if r["score"]:
        g = {f.get("gold_index") for f in r["score"].get("facts", []) if f.get("gold_index") is not None}
        pr[r["passage"]].append(len(g) / len(P[r["passage"]]["gold"]["facts"]))
for k, v in sorted(pr.items(), key=lambda kv: sum(kv[1]) / len(kv[1]))[:6]: out.append(f"- {k}: {sum(v)/len(v):.2f}")
(H / "results/summary.md").write_text("\n".join(out)); print("\n".join(out))
