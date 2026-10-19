"""Language of state-change items per extractor variant (mixing check)."""
import json, re
from pathlib import Path
rows = [json.loads(l) for l in open(Path(__file__).parent / "raw" / "extract.jsonl")]
for v in ("uk", "en"):
    cyr = lat = 0
    for r in rows:
        if r["variant"] != v:
            continue
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", r["text"].strip(), re.S)
        d = json.loads(m.group(1) if m else r["text"])
        for c in d.get("state_changes", []):
            t = c.get("item", "")
            if re.search(r"[а-яіїєґ]", t, re.I):
                cyr += 1
            else:
                lat += 1
    print(v, "state items cyrillic", cyr, "latin", lat)
