"""Print the saved first-run report of each pilot model (cost, tokens, counts, dropped items by reason)."""
import json
from collections import Counter

BASE = "/home/cock/projects/harness/campaigns/canon"
for m in ("deepseek", "luna", "qwen", "deepseek2", "luna2"):
    r = json.load(open(f"{BASE}/raw_{m}/report.json"))
    d = r.pop("dropped")
    print(m, r)
    print("  dropped:", len(d), dict(Counter(x["why"] for x in d)))
