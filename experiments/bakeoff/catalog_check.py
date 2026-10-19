"""List mandated candidates and cheap alternatives from the saved catalog snapshot."""
import json, re, sys
d = json.load(open("experiments/bakeoff/catalog_2026-10-19.json"))["data"]
ids = {m["id"]: m for m in d}
want = ['deepseek/deepseek-v4.1-flash-1017', 'z-ai/glm-5.3-flash', 'qwen/qwen3.8-omni-flash',
        'elorian/glimpse', 'perplexity/pplx-decider-flash-v1.2', 'perplexity/pplx-decider-v1.2',
        'liquid/d1-ultra', 'typesafe/jev-1.14', '~perplexity/pplx-decider-latest']
print(len(d), "models")
for w in want:
    m = ids.get(w)
    if m:
        p = m["pricing"]
        print(w, p.get("prompt"), p.get("completion"), m.get("context_length"),
              m.get("architecture", {}).get("modality"), m.get("canonical_slug"))
    else:
        print(w, "MISSING")
for m in d:
    if re.search(r"decider|glimpse|/d1|jev|laya", m["id"]):
        print("~", m["id"], m["pricing"].get("prompt"), m["pricing"].get("completion"))
