"""Total task-7 spend: ledger (chat calls) + hosted-decider calls (their usage.cost, recorded in raw/decide_*.jsonl).
Calls not recorded anywhere (npc_check / timing decider calls, probes) are estimated from the mean d1-ultra cost."""
import glob, json
ledger = sum(r["cost"] for r in map(json.loads, open("experiments/results/spend.jsonl")) if r["exp"] == "task7")
hosted = 0.0
for f in glob.glob("experiments/bakeoff/raw/decide_*.jsonl"):
    for l in open(f):
        r = json.loads(l)
        if r["model"] in ("typesafe/jev-1.14", "perplexity/pplx-decider-v1.2", "perplexity/pplx-decider-flash-v1.2", "liquid/d1-ultra"):
            hosted += r["cost"]
n_unrec = 408 - 0 + 8 * 3  # npc_check systemone calls (jev/pplx/d1 x2 variants) + timing runs
est_unrec = n_unrec * 0.000012  # upper bound: Jev 1.14 mean cost per call
print(f"ledger chat calls: {ledger:.4f}\nhosted deciders (60-judgment runs): {hosted:.4f}\n"
      f"unrecorded decider calls (npc_check, timing): <= {est_unrec:.4f}\nTOTAL <= {ledger + hosted + est_unrec:.4f}")
