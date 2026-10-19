"""Blind packets for the Claude Code agent to grade, and automatic format checks.

Writes packets/{narrator,npc,extract}.md (no model names) and raw/blind_key.json (label -> model).
Automatic checks (format validity, quote heuristics, JSON keys) are computed in analyze_text.py.
"""
import glob, json, random
from pathlib import Path
from . import prompts

HERE = Path(__file__).parent
rows = []
for f in sorted(glob.glob(str(HERE / "raw" / "text_*.jsonl"))):
    rows += [json.loads(l) for l in open(f)]
items = {s: {i["id"]: i for i in json.loads((HERE / "testset" / f"{s}.json").read_text())}
         for s in ("narrator", "npc", "extract")}
rng = random.Random(7)
key = {}
(HERE / "packets").mkdir(exist_ok=True)
for s in ("narrator", "npc", "extract"):
    md = [f"# {s} packet (blind)\n"]
    for iid, it in items[s].items():
        rs = [r for r in rows if r["set"] == s and r["id"] == iid]
        rng.shuffle(rs)
        md.append(f"\n## {iid}\n")
        if s == "narrator":
            md.append(f"Scene: {it['location']}; present: {', '.join(prompts.nm(c) for c in it['present'])}\n"
                      f"Player: {it['player']}\nCampaign: {it['campaign']}\nRecent: {it['recent']}\nNotes: {it['notes']}\n")
        elif s == "npc":
            md.append(f"NPC: {prompts.nm(it['npc'])} — {prompts.PROFILES[it['npc']]}\nKnows: {it['knows']}\n"
                      f"Noticed: {it.get('noticed')}; attitudes: {it.get('attitudes')}\nRecent: {it['recent']}\n"
                      f"GOLD: {it['gold']}\nFORBIDDEN: {it['forbidden']}\n")
        else:
            md.append("Passage:\n" + "\n".join(f"[{k}] {t}" for k, t in it["segments"]) +
                      f"\nCurrent state: {it['state']}\nGOLD facts: {it['gold_facts']}\nGOLD state: {it['gold_state']}\n")
        for lab, r in zip("ABCDEFG", rs):
            key[f"{s}/{iid}/{lab}"] = r["model"]
            txt = r["text"].strip()
            if s == "extract":
                try:
                    import re
                    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", txt, re.S)
                    d = json.loads(m.group(1) if m else txt)
                    txt = "FACTS:\n" + "\n".join(f"  - ({f.get('notability')}) {f.get('content')}" for f in d.get("new_facts", []))
                    txt += "\nCHANGES:\n" + "\n".join(f"  - {c.get('character')}/{c.get('category')}/{c.get('op')}: {c.get('item')} (obs={c.get('observable')})" for c in d.get("state_changes", []))
                except Exception as e:
                    txt = f"[INVALID JSON: {e}] {txt[:300]}"
            md.append(f"\n### {lab}\n{txt}\n")
    (HERE / "packets" / f"{s}.md").write_text("\n".join(md))
(HERE / "raw" / "blind_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=0))
print(len(key), "labelled outputs")
