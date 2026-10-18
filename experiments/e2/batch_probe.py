"""Does batching several typed questions about one state into a single Jev call cut latency/cost? (5 reps)"""
import sys, statistics as st
sys.path.insert(0, "experiments")
from common.llm import jev
state = ["Персонаж: Весемір", "Подія: Рагнар вночі вийшов за ворота без дозволу, а вранці повернувся з пораненою рукою."]
Q = {"salience": {"type": "noul", "instructions": "Чи помітив би цей персонаж цю подію або переймався б нею?"},
     "uncertain": {"type": "noul", "instructions": "Чи справді невизначено, як Весемір відреагує?"},
     "rel": {"type": "choice", "criteria": {"worse": "ставлення гірше", "unchanged": "без змін", "better": "краще"}, "instructions": "Як змінилося ставлення Весеміра до Рагнара?"},
     "contradiction": {"type": "noul", "instructions": "Чи суперечить ця подія тому, що Каер Морхен — фортеця в горах?"}}
single = [sum(jev("typesafe/jev-1.14", state, {k: v}, exp="e2")["latency"] for k, v in Q.items()) for _ in range(5)]
batch = [jev("typesafe/jev-1.14", state, Q, exp="e2")["latency"] for _ in range(5)]
c1 = sum(jev("typesafe/jev-1.14", state, {k: v}, exp="e2")["cost"] for k, v in Q.items()); c2 = jev("typesafe/jev-1.14", state, Q, exp="e2")
print("4 separate calls: p50 total latency %.2fs, cost $%.6f" % (st.median(single), c1))
print("1 batched call:   p50 latency %.2fs, cost $%.6f" % (st.median(batch), c2["cost"]))
print({k: (v.get("noul") if "noul" in v else v.get("choice")) for k, v in c2["answers"].items()})
