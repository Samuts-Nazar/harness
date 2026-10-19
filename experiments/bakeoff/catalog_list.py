"""Cheap, non-Anthropic, text-output chat models from the snapshot, newest first."""
import json, datetime
d = json.load(open("experiments/bakeoff/catalog_2026-10-19.json"))["data"]
rows = []
for m in d:
    try:
        pi = float(m["pricing"]["prompt"]) * 1e6
        po = float(m["pricing"]["completion"]) * 1e6
    except Exception:
        continue
    if pi < 0 or "anthropic" in m["id"]:
        continue
    if "text" not in (m.get("architecture", {}).get("output_modalities") or ["text"]):
        continue
    if (pi <= 0.6 and po <= 2.5) or m["id"].endswith(":free"):
        rows.append((m.get("created", 0), m["id"], pi, po, m.get("context_length")))
rows.sort(reverse=True)
for c, i, pi, po, ctx in rows[:70]:
    print(datetime.date.fromtimestamp(c), f"{i:55s} {pi:6.3f} {po:6.3f} {ctx}")
