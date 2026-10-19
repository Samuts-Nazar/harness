"""Build the v3 scene timeline (two readers + code check + arbiter) for the pilot arc; cache raw replies."""
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

from harness.canon import chunk, timeline
from harness.canon.ingest import BOOK_FIRST, BOOK_LAST, CHAPTERS, TokenSpend
from harness.providers import OpenRouterProvider

load_dotenv(".env")
RAW = Path("campaigns/canon/raw_v3")
RAW.mkdir(parents=True, exist_ok=True)
cache_path = RAW / "timeline_cache.json"
cache = json.loads(cache_path.read_text()) if cache_path.exists() else {}
spend = TokenSpend(cap=0.1)
prov = OpenRouterProvider(spend=spend, timeout=300)
paras = chunk.read_arc("data/witcher_books.txt", BOOK_FIRST, BOOK_LAST, CHAPTERS)
try:
    scenes, rep = timeline.build(prov, ("deepseek/deepseek-v4.1-flash-1017", "openai/gpt-6-luna"),
                                 sys.argv[1] if len(sys.argv) > 1 else "deepseek/deepseek-v4.1-flash-1017", paras, cache=cache)
finally:
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=1))
(RAW / "timeline_final.json").write_text(json.dumps([s.as_dict() for s in scenes], ensure_ascii=False, indent=1))
for s in scenes:
    print(s.from_line, s.to_line, s.day_lo, s.day_hi, s.part, s.place, s.flags)
print(json.dumps(rep, ensure_ascii=False, indent=1))
print("spend", spend.total, spend.calls)
