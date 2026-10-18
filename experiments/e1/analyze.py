import json, pathlib, collections, math, random
H = pathlib.Path(__file__).parent
R = [json.loads(l) for l in (H / "results" / (__import__("sys").argv[1] if len(__import__("sys").argv)>1 else "raw_leading.jsonl")).read_text().splitlines()]
def rate(rows, f):
    n = len(rows); k = sum(1 for r in rows if f(r)); return k, n
def wilson(k, n, z=1.96):
    if n == 0: return (0, 0)
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (max(0, (c - w) / d), min(1, (c + w) / d))
strict = lambda r: r["verdict"] == "leak"
lenient = lambda r: r["verdict"] in ("leak", "hint")
out = []
def table(title, groupf, rows):
    out.append(f"\n**{title}**\n\n| group | A leak | A leak+hint | B leak | B leak+hint | n per cond |\n|---|---|---|---|---|---|")
    g = collections.defaultdict(list)
    for r in rows: g[groupf(r)].append(r)
    for k in sorted(g):
        A = [r for r in g[k] if r["cond"] == "A"]; B = [r for r in g[k] if r["cond"] == "B"]
        cells = []
        for rows_, f in ((A, strict), (A, lenient), (B, strict), (B, lenient)):
            kk, n = rate(rows_, f); lo, hi = wilson(kk, n); cells.append(f"{kk}/{n} = {kk/n:.0%} [{lo:.0%}–{hi:.0%}]")
        out.append(f"| {k} | " + " | ".join(cells) + f" | {len(A)} |")
table("All", lambda r: "all", R)
table("By model tier", lambda r: f"{r['tier']} ({r['model']})", R)
table("By case type", lambda r: r["type"], R)
table("Canon cases only, by tier", lambda r: r["tier"], [r for r in R if r["type"] != "invented"])
table("Invented (no pretraining confound), by tier", lambda r: r["tier"], [r for r in R if r["type"] == "invented"])
# paired by (case,tier,sample): A leak & B no leak etc
pairs = collections.defaultdict(dict)
for r in R: pairs[(r["case"], r["tier"], r["sample"])][r["cond"]] = r
a_only = sum(1 for p in pairs.values() if strict(p["A"]) and not strict(p["B"]))
b_only = sum(1 for p in pairs.values() if strict(p["B"]) and not strict(p["A"]))
both = sum(1 for p in pairs.values() if strict(p["A"]) and strict(p["B"]))
out.append(f"\nPaired (strict leak): A-only {a_only}, B-only {b_only}, both {both}, pairs {len(pairs)}")
out.append(f"Verdict counts: {dict(collections.Counter((r['cond'], r['verdict']) for r in R))}")
out.append(f"Cost total: ${sum(r['cost'] for r in R):.3f}; mean narrator latency {sum(r['latency'] for r in R)/len(R):.1f}s")
(H / "results" / ("summary_" + (__import__("sys").argv[1] if len(__import__("sys").argv)>1 else "raw_leading.jsonl").replace(".jsonl", ".md"))).write_text("\n".join(out)); print("\n".join(out))
