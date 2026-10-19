"""Extrapolations behind reports/cost/SUMMARY.md. Inputs are measured per-call costs."""
import json
S = json.load(open("reports/cost/scene_summary.json"))
P = json.load(open("reports/cost/ingest_probe.json"))
print("per hour of play ($) at 30 / 60 turns")
for k, v in S.items():
    print(f"  {k[:28]:28s} per turn {v['mean_turn']:.5f}  30t {30*v['mean_turn']:.3f}  60t {60*v['mean_turn']:.3f}")
JEV_TICK = 1200 * 0.042e-6        # Jev ~$0.042 per M input tokens (fit on 72 calls); 1200-token batched tick
ESC = 0.25 * 0.000114             # 25% of ticks escalate one Haiku judgment call (measured $0.000114/call)
a = JEV_TICK + ESC
SUM_DS = 0.000119                 # measured DeepSeek-v4-flash NPC call (1710 in / 186 out)
SUM_HK = 1500 * 0.1e-6 + 200 * 0.5e-6   # Haiku list price, 1500 in / 200 out
b_ds, b_hk = a + SUM_DS, a + SUM_HK
CATCH_HK = 3000 * 0.1e-6 + 400 * 0.5e-6
CATCH_DS = 3000 * 0.091e-6 + 400 * 0.182e-6
print(f"\nagent-day: a={a:.6f} b_ds={b_ds:.6f} b_hk={b_hk:.6f}  catchup haiku={CATCH_HK:.6f} ds={CATCH_DS:.6f}")
for n in (10, 50, 200):
    print(f"N={n}: a={n*a:.4f} b_ds={n*b_ds:.4f} b_hk={n*b_hk:.4f}")
for m in (3, 10):
    print(f"c: {m} meetings/day haiku={m*CATCH_HK:.4f} ds={m*CATCH_DS:.4f}")
total_chars = 4_998_019
f = total_chars / P["chapter_chars"]
print(f"\ningestion scale x{f:.2f} (chars {total_chars} / chapter {P['chapter_chars']})")
for m, v in P["models"].items():
    print(f"{m}: chapter in={v['in']} out={v['out']} ${v['cost']:.4f} t={v['latency_sum']:.0f}s valid={v['valid']}/13 events={v['events']}"
          f" | book in={v['in']*f/1e6:.2f}M out={v['out']*f/1e6:.2f}M ${v['cost']*f:.2f} seq={v['latency_sum']*f/3600:.1f}h par8={v['latency_sum']*f/3600/8*60:.0f}min")
