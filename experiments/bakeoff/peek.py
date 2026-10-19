import json, sys
for f in sys.argv[1:]:
    rows = [json.loads(l) for l in open(f"experiments/bakeoff/raw/decide_{f}.jsonl")]
    errs = [r for r in rows if r["error"]]
    print(f, len(errs), errs[0]["error"] if errs else "", sorted({r["type"] for r in errs}))
    print([round(r["p_yes"], 2) for r in rows if r["p_yes"] is not None][:40])
