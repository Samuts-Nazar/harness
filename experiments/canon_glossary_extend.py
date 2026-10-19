"""Tidy the glossary JSON: a variant must not also be a legitimate oblique case of the same entry, and
common nouns (items, terms, creatures, descriptive places) are marked `proper: false` so they are not
swapped inside English record text."""
import json

P = "harness/canon/glossary_witcher_arc1.json"
d = json.load(open(P))
COMMON = {"char:princess", "place:old-palace", "place:new-palace", "place:crypt"}
for e in d["entries"]:
    e["variants"] = [v for v in e["variants"] if v not in e["cases"] and v != e["canonical"]]
    e["proper"] = not (e["type"] in ("item", "term", "creature") or e["id"] in COMMON)
json.dump(d, open(P, "w"), ensure_ascii=False, indent=1)
print(len(d["entries"]), sum(1 for e in d["entries"] if e["proper"]))
