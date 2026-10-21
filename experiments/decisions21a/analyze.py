"""Aggregate raw.jsonl: per method, how often the book option / the typical option wins, and how spread the choice is.
Run: nix develop --command python experiments/decisions21a/analyze.py [--per-point]"""
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA  # noqa: E402

pts = {p["id"]: p for p in json.load(open(DATA / "points.json"))}
raw = defaultdict(dict)
for line in open(DATA / "raw.jsonl"):
    r = json.loads(line)
    raw[r["method"]][r["id"]] = r["rows"]


def mean_dist(rows):
    ds = [x["dist"] for x in rows if sum(x["dist"]) > 0]
    if not ds:
        return None, 0
    n = len(ds[0])
    return [sum(d[i] for d in ds) / len(ds) for i in range(n)], len(ds)


def ent(d):
    h = -sum(x * math.log(x) for x in d if x > 0)
    return h / math.log(len(d))


def pick_entropy(rows):
    """spread of the individual picks (argmax of each row) across samples/orders, normalised."""
    n = len(rows[0]["dist"])
    c = [0] * n
    for x in rows:
        if sum(x["dist"]) > 0:
            c[max(range(n), key=lambda i: x["dist"][i])] += 1
    t = sum(c) or 1
    return ent([x / t for x in c]), sum(1 for x in c if x)


out = []
per_point = "--per-point" in sys.argv
for m, byid in raw.items():
    if m == "open":
        continue
    pb, top_b, pt, top_t, H, Hp, uniq, fails, kb = [], 0, [], 0, [], [], [], 0, 0
    for pid, rows in byid.items():
        p = pts[pid]
        md, n = mean_dist(rows)
        fails += len(rows) - n
        if md is None:
            continue
        kb += 1
        b, t = p["book"], p["typical"]
        pb.append(md[b]); pt.append(md[t])
        top = max(range(len(md)), key=lambda i: md[i])
        top_b += top == b
        top_t += top == t
        H.append(ent(md))
        e, u = pick_entropy(rows)
        Hp.append(e); uniq.append(u)
        if per_point:
            print(m, pid, "book %.2f typical %.2f top=%d(book=%d)" % (md[b], md[t], top, b))
    k = len(pb)
    base = sum(1 / len(pts[i]["options"]) for i in byid) / len(byid)
    out.append((m, k, sum(pb) / k, top_b, sum(pt) / k, top_t, sum(H) / k, sum(Hp) / k, sum(uniq) / k, fails, base))

print("%-42s %2s %7s %6s %7s %6s %6s %6s %5s %5s" % ("method", "n", "P(book)", "top=bk", "P(typ)", "top=ty", "H_mean", "H_pick", "uniq", "fail"))
for m, k, pb, tb, pt, tt, H, Hp, u, f, base in out:
    print("%-42s %2d %7.3f %6d %7.3f %6d %6.2f %6.2f %5.1f %5d" % (m, k, pb, tb, pt, tt, H, Hp, u, f))
print("uniform baseline P(book) = %.3f" % out[0][10])
