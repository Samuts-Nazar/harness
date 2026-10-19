"""Compact blind view of narrator outputs: python -m experiments.language.show_narr [packet.md] n01 n02"""
import json, re, sys
from pathlib import Path
args = sys.argv[1:]
packet = args.pop(0) if args and args[0].endswith(".md") else "narrator.md"
txt = (Path(__file__).parent / "packets" / packet).read_text()
for iid in args:
    sec = re.search(rf"## {iid}\n(.*?)(?=\n## n|\Z)", txt, re.S).group(1)
    head, *outs = re.split(r"\n### ", sec)
    print("##", iid, head.strip()[:300])
    for o in outs:
        lab, body = o.split("\n", 1)
        body = body.strip()
        try:
            m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", body, re.S)
            d = json.loads(m.group(1) if m else body)
            print(f"[{lab}] {d.get('description')}\n   ACT: {' | '.join(d.get('observable_actions', []))}  SPK: {d.get('speakers')}")
        except Exception:
            print(f"[{lab}] RAW: {body[:700]}")
