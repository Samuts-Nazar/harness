"""Make options equal in length and specificity: luna rewrites each option list blind (does not know the book option).
Writes campaigns/21A/points_eq.json. Run: nix develop --command python experiments/decisions21a/equalize.py"""
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from common import DATA, chat  # noqa: E402

pts = json.load(open(DATA / "points.json"))
for p in pts:
    lst = "\n".join(f"{i + 1}. {o}" for i, o in enumerate(p["options"]))
    user = ("Rewrite each of these alternative actions as one plain clause of 7 to 9 words, same order, same meaning, "
            "no added detail, no adjectives of tone, no explanations. Keep every option equally dry and equally "
            f"specific.\n\n{lst}\n\nReturn exactly {len(p['options'])} numbered lines.")
    out = chat("openai/gpt-6-luna", "You edit lists of options neutrally.", user, max_tokens=300, temperature=0.2)
    new = [re.sub(r"^\s*\d+[.)]\s*", "", x).strip() for x in out.strip().splitlines() if x.strip()]
    assert len(new) == len(p["options"]), (p["id"], out)
    p["options"] = new
json.dump(pts, open(DATA / "points_eq.json", "w"), ensure_ascii=False, indent=1)
longest = sum(len(p["options"][p["book"]].split()) == max(len(o.split()) for o in p["options"]) for p in pts)
print("book longest in", longest, "of", len(pts))
