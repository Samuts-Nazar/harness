"""Blind packet: shuffled narrator outputs (JSON variant shows the description only), key kept apart."""
import json
import random
from pathlib import Path

HERE = Path(__file__).parent
rows = [json.loads(x) for x in (HERE / "raw" / "narr.jsonl").read_text().splitlines()]
random.Random(12).shuffle(rows)
key, lines = {}, []
for i, r in enumerate(rows, 1):
    t = r["text"].strip()
    if r["variant"] == "json":
        try:
            t = json.loads(t.strip("`").removeprefix("json").strip())["description"]
        except Exception:  # noqa: BLE001
            pass
    key[i] = [r["id"], r["variant"], r["sample"]]
    lines.append(f"### {i} [{r['id']}]\n{t}\n")
(HERE / "raw" / "blind_key.json").write_text(json.dumps(key))
(HERE / "raw" / "packet.txt").write_text("\n".join(lines))
print(len(rows))
