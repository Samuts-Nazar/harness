"""Detector hits per model over round-2 texts (out2.jsonl and the page data via key2.json)."""
import json
from collections import Counter, defaultdict
from pathlib import Path

from harness.stylehits import style_hits

ROOT = Path(__file__).resolve().parents[2]
rows = [json.loads(l) for l in (ROOT / "experiments/human_ab/raw/out2.jsonl").read_text().splitlines()]
per, kinds, n = Counter(), defaultdict(Counter), Counter()
for r in rows:
    if not r.get("text"):
        continue
    h = style_hits(r["text"])
    per[r["model"]] += len(h)
    n[r["model"]] += 1
    for x in h:
        kinds[r["model"]][x.kind] += 1
print("out2.jsonl")
for m in per:
    print(f"  {m:32s} texts={n[m]:2d} hits={per[m]:2d} per_text={per[m]/n[m]:.2f} {dict(kinds[m])}")

js = (ROOT / "app/static/human_ab2_data.js").read_text()
data = json.loads(js[js.index("window.HUMAN_AB") + len("window.HUMAN_AB ="):].strip().rstrip(";"))
key = json.loads((ROOT / "reports/human_ab/key2.json").read_text())
per2, n2 = Counter(), Counter()
for mom in data:
    for t in mom["texts"]:
        m = key[mom["id"]][t["label"]]["model"]
        per2[m] += len(style_hits(t["text"]))
        n2[m] += 1
print("human_ab2_data.js via key2.json")
for m in per2:
    print(f"  {m:32s} texts={n2[m]:2d} hits={per2[m]:2d} per_text={per2[m]/n2[m]:.2f}")
