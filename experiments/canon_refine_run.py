"""Run the pilot-2 refinement on the task-13 deepseek v2 store. Output store: campaigns/canon/pilot_v3.db.

    PYTHONPATH=. python3 experiments/canon_refine_run.py
"""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from harness.canon import chunk, timeline
from harness.canon.ingest import BOOK_FIRST, BOOK_LAST, CHAPTERS, TokenSpend
from harness.canon.refine import Refiner
from harness.glossary import Glossary
from harness.providers import OpenRouterProvider

load_dotenv(".env")
RAW = Path("campaigns/canon/raw_v3")
spend = TokenSpend(cap=0.25)
prov = OpenRouterProvider(spend=spend, timeout=300)
paras = chunk.read_arc("data/witcher_books.txt", BOOK_FIRST, BOOK_LAST, CHAPTERS)
scenes = timeline.parse_scenes({"scenes": json.loads((RAW / "timeline_final.json").read_text())})
for s, d in zip(scenes, json.loads((RAW / "timeline_final.json").read_text())):
    s.flags = d.get("flags", [])
model = sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4.1-flash-1017"
r = Refiner(prov, model, "campaigns/canon/pilot_deepseek2g.db", "campaigns/canon/pilot_v3.db", paras, scenes,
            raw_dir=RAW, glossary=Glossary.for_world("witcher"))
rep = r.run()
rep["cost_usd"] = round(spend.total, 5)
dropped = rep.pop("dropped")
print(json.dumps(rep, ensure_ascii=False))
print(len(dropped), "dropped")
for d in dropped[:30]:
    print(d)
