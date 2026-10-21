import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA  # noqa: E402

pts = json.load(open(DATA / "points.json"))
longest = 0
ranks = []
for p in pts:
    ls = [len(o.split()) for o in p["options"]]
    b = ls[p["book"]]
    longest += b == max(ls)
    ranks.append(sorted(ls, reverse=True).index(b) + 1)
    print(p["id"], "book words", b, "all", ls)
print("book option is the longest in", longest, "of", len(pts), "points; mean length rank", sum(ranks) / len(ranks))
