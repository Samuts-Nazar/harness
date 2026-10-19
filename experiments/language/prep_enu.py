"""Blind packets for the third variant (English context + Ukrainian proper nouns). Models shuffled together."""
import json, random
from pathlib import Path
from . import prompts_lang as L
from experiments.bakeoff import prompts as P

HERE = Path(__file__).parent
key = {}
for s, seed in (("narrator", 12), ("npc", 11)):
    rng = random.Random(seed)
    rows = [json.loads(l) for l in open(HERE / "raw" / f"{s}_enu.jsonl")]
    items = L.NARR if s == "narrator" else L.NPCS
    md = [f"# {s} packet (blind, third variant)\n"]
    for iid, it in items.items():
        rs = [r for r in rows if r["id"] == iid]
        rng.shuffle(rs)
        if s == "npc":
            md.append(f"\n## {iid}\nNPC: {P.nm(it['npc'])}\nKnows: {it['knows']}\nNoticed: {it.get('noticed')}; attitudes: {it.get('attitudes')}\nRecent: {it['recent']}\nGOLD: {it['gold']}\nFORBIDDEN: {it['forbidden']}\n")
        else:
            md.append(f"\n## {iid}\nScene: {it['location']}; present: {', '.join(P.nm(c) for c in it['present'])}\nPlayer: {it['player']}\n")
        for n, r in enumerate(rs):
            lab = chr(65 + n)
            key[f"{s}/{iid}/{lab}"] = dict(model=r["model"], variant="enu", sample=r["sample"])
            md.append(f"\n### {lab}\n{r['text'].strip()}\n")
    (HERE / "packets" / f"{s}_enu.md").write_text("\n".join(md))
(HERE / "raw" / "blind_key_enu.json").write_text(json.dumps(key, ensure_ascii=False, indent=0))
print(len(key))
