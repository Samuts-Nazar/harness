import json, pathlib, collections, math
H = pathlib.Path(__file__).parent / "results"
R = [json.loads(l) for l in (H / "raw_neutral_adj.jsonl").read_text().splitlines()]
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); w = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return max(0, (c - w) / d), min(1, (c + w) / d)
def cell(rows, f):
    k = sum(1 for r in rows if f(r)); n = len(rows); lo, hi = wilson(k, n); return f"{k}/{n} = {k/n:.0%} [{lo:.0%}–{hi:.0%}]"
conf = lambda r: r["verdict"] == "leak" and r["verdict2"] == "leak"           # both judges: leak
anyl = lambda r: r["verdict"] == "leak" or r["verdict2"] == "leak"
either = lambda r: r["verdict2"] in ("leak", "hint")                         # strong judge: leak or hint
out = ["| group | A: both judges leak | B: both judges leak | A: strong judge leak+hint | B: strong judge leak+hint | n/cond |", "|---|---|---|---|---|---|"]
def row(name, rows):
    A = [r for r in rows if r["cond"] == "A"]; B = [r for r in rows if r["cond"] == "B"]
    out.append(f"| {name} | {cell(A, conf)} | {cell(B, conf)} | {cell(A, either)} | {cell(B, either)} | {len(A)} |")
row("all", R)
for t in ("small", "mid", "mid2", "strong"): row(f"tier {t}", [r for r in R if r["tier"] == t])
for t in ("secret", "elsewhere", "future", "invented"): row(f"type {t}", [r for r in R if r["type"] == t])
row("canon only (no invented)", [r for r in R if r["type"] != "invented"])
pairs = collections.defaultdict(dict)
for r in R: pairs[(r["case"], r["tier"])][r["cond"]] = r
out.append(f"\nPaired (both-judge leak): A-only {sum(conf(p['A']) and not conf(p['B']) for p in pairs.values())}, B-only {sum(conf(p['B']) and not conf(p['A']) for p in pairs.values())}, both {sum(conf(p['A']) and conf(p['B']) for p in pairs.values())}, of {len(pairs)} pairs")
(H / "summary_neutral_adj.md").write_text("\n".join(out)); print("\n".join(out))
# list A-cond rows confirmed
for r in R:
    if r["cond"] == "A" and conf(r): print("A-leak:", r["case"], r["tier"], r["reply"][:200].replace("\n", " "))
