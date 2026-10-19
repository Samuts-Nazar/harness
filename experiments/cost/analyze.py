"""Per-turn tables and extrapolations from the call logs (reports/cost/**/calls.jsonl)."""
import json, collections, statistics, sys
from pathlib import Path

ROLES = ["narrator", "npc", "extractor", "jev", "judge_llm"]

def load(p): return [json.loads(l) for l in Path(p).read_text().splitlines()]

def per_turn(L):
    t = collections.defaultdict(lambda: collections.defaultdict(list))
    for c in L: t[c["turn"]][c["role"]].append(c)
    return t

def summarize(name, p):
    L = load(p); T = per_turn(L)
    turns = [k for k in T if k > 0]
    setup = sum(c["cost"] for c in T.get(0, {}).get("jev", []) + sum((v for v in T.get(0, {}).values()), []) ) if False else sum(c["cost"] for v in T.get(0, {}).values() for c in v)
    print(f"\n### {name}  ({len(turns)} turns with calls; setup cost ${setup:.5f})")
    print("| turn | calls n/np/ex/jev/jllm | in tok | out tok | cost $ | latency s (sum of calls) |")
    print("|--|--|--|--|--|--|")
    costs, lats, ins, outs, ncalls = [], [], [], [], []
    for k in sorted(turns):
        cs = [c for v in T[k].values() for c in v]
        cnt = "/".join(str(len(T[k].get(r, []))) for r in ROLES)
        ci, co = sum(c["input_tokens"] for c in cs), sum(c["output_tokens"] for c in cs)
        cc, cl = sum(c["cost"] for c in cs), sum(c["latency"] for c in cs)
        costs.append(cc); lats.append(cl); ins.append(ci); outs.append(co); ncalls.append(len(cs))
        print(f"| {k} | {cnt} | {ci} | {co} | {cc:.5f} | {cl:.1f} |")
    n = len(costs)
    print(f"| mean | {statistics.mean(ncalls):.1f} calls | {statistics.mean(ins):.0f} | {statistics.mean(outs):.0f} | {statistics.mean(costs):.5f} | {statistics.mean(lats):.1f} |")
    byrole = collections.defaultdict(lambda: [0, 0.0, 0, 0, 0.0])
    for c in L:
        if c["turn"] == 0: continue
        r = byrole[c["role"]]; r[0] += 1; r[1] += c["cost"]; r[2] += c["input_tokens"]; r[3] += c["output_tokens"]; r[4] += c["latency"]
    print("\n| role | calls | cost $ | $/call | in tok/call | out tok/call | s/call |\n|--|--|--|--|--|--|--|")
    for r, (n_, c_, i_, o_, l_) in sorted(byrole.items()):
        print(f"| {r} | {n_} | {c_:.5f} | {c_/n_:.6f} | {i_/n_:.0f} | {o_/n_:.0f} | {l_/n_:.2f} |")
    return dict(mean_turn=statistics.mean(costs), total=sum(costs) + setup, setup=setup,
                byrole={r: dict(n=v[0], cost=v[1], per_call=v[1]/v[0]) for r, v in byrole.items()})

if __name__ == "__main__":
    out = {}
    for name, p in [("main (deepseek-v4-flash narrator+NPC, haiku extractor)", "reports/cost/calls.jsonl"),
                    ("haiku (haiku narrator+NPC+extractor)", "reports/cost/variants/haiku/calls.jsonl"),
                    ("lite (gemini-3.1-flash-lite narrator+NPC+extractor)", "reports/cost/variants/lite/calls.jsonl")]:
        out[name] = summarize(name, p)
    Path("reports/cost/scene_summary.json").write_text(json.dumps(out, indent=1))
