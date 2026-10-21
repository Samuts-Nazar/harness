import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA  # noqa: E402

pts = {p["id"]: p for p in json.load(open(DATA / "points.json"))}
for line in open(DATA / "raw.jsonl"):
    r = json.loads(line)
    if r["method"] != "open":
        continue
    p = pts[r["id"]]
    print("###", r["id"], "BOOK:", p["options"][p["book"]][:90])
    for i, row in enumerate(r["rows"][:int(sys.argv[1]) if len(sys.argv) > 1 else 5]):
        print(f"-- list {i + 1}")
        for ln in row["text"].strip().splitlines():
            print("  ", ln[:110])
