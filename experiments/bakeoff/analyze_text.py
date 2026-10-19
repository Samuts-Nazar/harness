"""Unblind the grades and aggregate per model and role. Writes reports/bakeoff/text_metrics.json."""
import glob, json, re, statistics as st
from collections import defaultdict
from pathlib import Path
from harness.narrator import NarrationError, has_quotes, has_speaker_line, parse_narration
from harness.extractor import DiffValidationError, parse_diff

HERE = Path(__file__).parent
key = json.loads((HERE / "raw/blind_key.json").read_text())
grades = {}
for f in ["grades_narrator.json", "grades_npc_1.json", "grades_npc_2.json", "grades_extract.json"]:
    grades.update({k: v for k, v in json.loads((HERE / f).read_text()).items() if not k.startswith("_")})
rows = {}
for f in glob.glob(str(HERE / "raw/text_*.jsonl")):
    for l in open(f):
        r = json.loads(l)
        rows[(r["set"], r["id"], r["model"])] = r
names = {"narrator": [], "npc": [], "extract": []}
M = defaultdict(lambda: defaultdict(list))
for k, g in grades.items():
    s, iid, lab = k.split("/")
    model = key[k]
    r = rows[(s, iid, model)]
    M[model][s + "_lat"].append(r["latency"]); M[model][s + "_cost"].append(r["cost"])
    M[model][s + "_tok"].append(r.get("tokens") or 0)
    if s == "narrator":
        try:
            out = parse_narration(r["text"]); ok = 1
        except NarrationError:
            out, ok = None, 0
        M[model]["n_valid"].append(ok)
        M[model]["n_uk"].append(g["uk"]); M[model]["n_pv"].append(g["pv"]); M[model]["n_cf"].append(g["cf"])
        speech = 0
        if out:
            txt = "\n".join(out.texts())
            speech = int(has_quotes(txt) or has_speaker_line(txt, ["Весемір", "Ламберт", "Тріс", "Ескель", "Койон"]))
        M[model]["n_speech"].append(speech)
        M[model]["n_lang0"].append(int(g["uk"] <= 1))
    elif s == "npc":
        M[model]["c_uk"].append(g["uk"]); M[model]["c_ic"].append(g["ic"])
        M[model]["c_leak"].append(g["leak"]); M[model]["c_fmt"].append(g["fmt"])
        M[model]["c_usable"].append(int(g["uk"] >= 2 and not g["fmt"]))
    else:
        M[model]["e_valid"].append(g["valid"]); M[model]["e_uk"].append(int(g["lang"] == "uk"))
        for f in ("tp", "nf", "w", "st", "sw"):
            M[model]["e_" + f].append(g[f])
gold_f = {i["id"]: len(i["gold_facts"]) for i in json.loads((HERE / "testset/extract.json").read_text())}
gold_s = {i["id"]: len(i["gold_state"]) for i in json.loads((HERE / "testset/extract.json").read_text())}
for model in M:
    ids = [k.split("/")[1] for k, g in grades.items() if k.startswith("extract/") and key[k] == model]
    M[model]["e_gold"] = [gold_f[i] for i in ids]
    M[model]["e_goldst"] = [gold_s[i] for i in ids]

TURNS_PER_HOUR = 40
out = {}
for model, d in sorted(M.items()):
    m = lambda x: round(st.mean(d[x]), 3) if d[x] else None
    tp, nf, w, gold = sum(d["e_tp"]), sum(d["e_nf"]), sum(d["e_w"]), sum(d["e_gold"])
    r = dict(
        narr_valid=m("n_valid"), narr_uk=m("n_uk"), narr_lang_fail=round(sum(d["n_lang0"]) / 9, 3),
        narr_player_voice=round(sum(d["n_pv"]) / 9, 3), narr_canon_err=round(sum(d["n_cf"]) / 9, 3),
        narr_npc_speech=round(sum(d["n_speech"]) / 9, 3),
        npc_uk=m("c_uk"), npc_ic=m("c_ic"), npc_leak=round(sum(d["c_leak"]) / 12, 3),
        npc_fmt_fail=round(sum(d["c_fmt"]) / 12, 3), npc_usable=round(sum(d["c_usable"]) / 12, 3),
        ext_valid=round(sum(d["e_valid"]) / 10, 3), ext_uk=round(sum(d["e_uk"]) / 10, 3),
        ext_recall=round(tp / gold, 3), ext_precision=round((nf - w) / nf, 3) if nf else 0,
        ext_state_recall=round(sum(d["e_st"]) / max(sum(d["e_goldst"]), 1), 3),
        ext_state_bad=round(sum(d["e_sw"]) / max(sum(d["e_sw"]) + sum(d["e_st"]), 1), 3),
        lat_narr=round(st.mean(d["narrator_lat"]), 2), lat_npc=round(st.mean(d["npc_lat"]), 2),
        lat_ext=round(st.mean(d["extract_lat"]), 2),
        cost_narr=round(st.mean(d["narrator_cost"]), 6), cost_npc=round(st.mean(d["npc_cost"]), 6),
        cost_ext=round(st.mean(d["extract_cost"]), 6),
    )
    # a turn = 1 narrator + 1.5 NPC lines + 1 extractor (assumption); cost/hour at 40 turns/hour
    r["cost_per_turn"] = round(r["cost_narr"] + 1.5 * r["cost_npc"] + r["cost_ext"], 6)
    r["cost_per_hour"] = round(r["cost_per_turn"] * TURNS_PER_HOUR, 4)
    out[model] = r
(HERE.parents[1] / "reports/bakeoff/text_metrics.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
cols = list(next(iter(out.values())))
for model, r in out.items():
    print(model)
    print("  ", {k: r[k] for k in cols[:6]})
    print("  ", {k: r[k] for k in cols[6:11]})
    print("  ", {k: r[k] for k in cols[11:19]})
    print("  ", {k: r[k] for k in cols[19:]})
