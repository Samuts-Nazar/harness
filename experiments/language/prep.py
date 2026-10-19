"""Blind packets: shuffle per item across model x variant x sample, label, write key separately."""
import json, random, re
from pathlib import Path
from . import prompts_lang as L
from experiments.bakeoff import prompts as P

HERE = Path(__file__).parent
rng = random.Random(10)
key = {}
(HERE / "packets").mkdir(exist_ok=True)
for s in ("narrator", "npc"):
    rows = [json.loads(l) for l in open(HERE / "raw" / f"{s}.jsonl")]
    ids = list(L.NARR if s == "narrator" else L.NPCS)
    md = [f"# {s} packet (blind)\n"]
    for iid in ids:
        it = (L.NARR if s == "narrator" else L.NPCS)[iid]
        rs = [r for r in rows if r["id"] == iid]
        rng.shuffle(rs)
        md.append(f"\n## {iid}\n")
        if s == "narrator":
            md.append(f"Scene: {it['location']}; present: {', '.join(P.nm(c) for c in it['present'])}\n"
                      f"Player: {it['player']}\nCampaign: {it['campaign']}\nState: {it['state']}\nRecent: {it['recent']}\nNotes: {it['notes']}\n")
        else:
            md.append(f"NPC: {P.nm(it['npc'])} - {P.PROFILES[it['npc']]}\nKnows: {it['knows']}\n"
                      f"Noticed: {it.get('noticed')}; attitudes: {it.get('attitudes')}\nRecent: {it['recent']}\n"
                      f"GOLD: {it['gold']}\nFORBIDDEN: {it['forbidden']}\n")
        for n, r in enumerate(rs):
            lab = chr(65 + n)
            key[f"{s}/{iid}/{lab}"] = dict(model=r["model"], variant=r["variant"], sample=r["sample"])
            md.append(f"\n### {lab}\n{r['text'].strip()}\n")
    (HERE / "packets" / f"{s}.md").write_text("\n".join(md))

# extractor: render parsed facts
rows = [json.loads(l) for l in open(HERE / "raw" / "extract.jsonl")]
ex = {i["id"]: i for i in json.loads((HERE.parent / "bakeoff" / "testset" / "extract.json").read_text())}
md = ["# extract packet (blind)\n"]
for iid, it in ex.items():
    rs = [r for r in rows if r["id"] == iid]
    rng.shuffle(rs)
    md.append(f"\n## {iid}\nPassage: {it['segments']}\nState: {it['state']}\nGOLD facts: {it['gold_facts']}\nGOLD state: {it['gold_state']}\n")
    for n, r in enumerate(rs):
        lab = chr(65 + n)
        key[f"extract/{iid}/{lab}"] = dict(model=r["model"], variant=r["variant"], sample=r["sample"])
        txt = r["text"].strip()
        try:
            m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", txt, re.S)
            d = json.loads(m.group(1) if m else txt)
            txt = "FACTS:\n" + "\n".join(f"  - {f.get('content')}" for f in d.get("new_facts", []))
            txt += "\nCHANGES:\n" + "\n".join(f"  - {c.get('character')}/{c.get('category')}/{c.get('op')}: {c.get('item')}" for c in d.get("state_changes", []))
        except Exception as e:
            txt = f"[INVALID JSON] {txt[:200]}"
        md.append(f"\n### {lab}\n{txt}\n")
(HERE / "packets" / "extract.md").write_text("\n".join(md))
(HERE / "raw" / "blind_key.json").write_text(json.dumps(key, ensure_ascii=False, indent=0))
print(len(key))
