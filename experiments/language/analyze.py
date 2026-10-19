"""Join blind grades with the key (read only now) and print tables. Writes results.json."""
import json, random, re, statistics as st
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
key = json.loads((HERE / "raw" / "blind_key.json").read_text())
SHORT = {"openai/gpt-6-luna": "luna", "deepseek/deepseek-v4.1-flash-1017": "deepseek"}
rng = random.Random(1)


def read(f):
    rows = []
    for l in (HERE / f).read_text().splitlines():
        if l.strip() and not l.startswith("#"):
            rows.append(l.split())
    return rows


def rec(setname, iid, lab):
    k = key[f"{setname}/{iid}/{lab}"]
    return SHORT[k["model"]], k["variant"]


def boot(diffs, n=4000):
    """95% bootstrap CI of the mean of per-item diffs (items are the resampling unit)."""
    m = [st.mean(rng.choices(diffs, k=len(diffs))) for _ in range(n)]
    m.sort()
    return m[int(.025 * n)], m[int(.975 * n)]


out = {}
# ---------- NPC ----------
npc = defaultdict(list)  # (model,variant) -> list of dict
for r in read("grades_npc.txt"):
    iid, lab, uk, ic, leak = r[:5]
    flags = r[5:]
    m, v = rec("npc", iid, lab)
    npc[(m, v)].append(dict(id=iid, uk=int(uk), ic=int(ic), leak=int(leak), ru="ru" in flags, en="en" in flags, x="x" in flags))
narr = defaultdict(list)
for r in read("grades_narr.txt"):
    iid, lab, uk = r[:3]
    flags = r[3:]
    m, v = rec("narrator", iid, lab)
    narr[(m, v)].append(dict(id=iid, uk=int(uk), pc="pc" in flags, en="en" in flags, ru="ru" in flags))


key_enu = json.loads((HERE / "raw" / "blind_key_enu.json").read_text())
for r in read("grades_npc_enu.txt"):
    iid, lab, uk, ic, leak = r[:5]
    flags = r[5:]
    k = key_enu[f"npc/{iid}/{lab}"]
    npc[(SHORT[k["model"]], "enu")].append(dict(id=iid, uk=int(uk), ic=int(ic), leak=int(leak), ru="ru" in flags, en="en" in flags, x="x" in flags))
for r in read("grades_narr_enu.txt"):
    iid, lab, uk = r[:3]
    flags = r[3:]
    k = key_enu[f"narrator/{iid}/{lab}"]
    narr[(SHORT[k["model"]], "enu")].append(dict(id=iid, uk=int(uk), pc="pc" in flags, en="en" in flags, ru="ru" in flags, inv="inv" in flags))
for d in (narr,):
    for kk, xs in d.items():
        for x in xs:
            x.setdefault("inv", False)


def paired(d, model, field, a_v="uk", b_v="en"):
    """per-item mean(en) - mean(uk), then mean and bootstrap CI over items."""
    ids = sorted({x["id"] for x in d[(model, a_v)]})
    diffs = []
    for i in ids:
        a = [float(x[field]) for x in d[(model, a_v)] if x["id"] == i]
        b = [float(x[field]) for x in d[(model, b_v)] if x["id"] == i]
        diffs.append(st.mean(b) - st.mean(a))
    lo, hi = boot(diffs)
    better = sum(x > 0 for x in diffs); worse = sum(x < 0 for x in diffs)
    return st.mean(diffs), lo, hi, better, worse, len(diffs)


def table(d, fields, title):
    print(f"\n### {title}")
    res = {}
    for model in ("luna", "deepseek"):
        for v in ("uk", "en", "enu"):
            xs = d[(model, v)]
            row = {f: round(st.mean(float(x[f]) for x in xs), 3) for f in fields}
            row["n"] = len(xs)
            res[f"{model}/{v}"] = row
            print(model, v, row)
        for (a_v, b_v) in (("uk", "en"), ("uk", "enu"), ("en", "enu")):
            for f in fields:
                dm, lo, hi, b, w, n = paired(d, model, f, a_v, b_v)
                res[f"{model}/diff_{b_v}-{a_v}_{f}"] = dict(mean=round(dm, 3), lo=round(lo, 3), hi=round(hi, 3), higher=b, lower=w, items=n)
                print(f"  {model} {f}: {b_v}-{a_v} = {dm:+.3f} (95% CI {lo:+.3f}..{hi:+.3f}); items higher {b}, lower {w}, of {n}")
    # pooled over both models, per-item means
    for v in ("uk", "en", "enu"):
        res[f"pooled/{v}"] = {f: round(st.mean(float(x[f]) for m in ("luna", "deepseek") for x in d[(m, v)]), 3) for f in fields}
        print("pooled", v, res[f"pooled/{v}"])
    return res


out["npc"] = table(npc, ["uk", "ic", "leak", "ru", "en", "x"], "NPC lines (12 situations x 3 samples per cell)")
out["narrator"] = table(narr, ["uk", "pc", "en", "ru", "inv"], "Narrator (9 scenes x 3 samples per cell)")

# ---------- extractor ----------
ext = defaultdict(list)
gold = {i["id"]: i for i in json.loads((HERE.parent / "bakeoff" / "testset" / "extract.json").read_text())}
raws = {}
for l in (HERE / "raw" / "extract.jsonl").read_text().splitlines():
    r = json.loads(l)
    raws[(r["id"], r["variant"], r["sample"])] = r


def lang_of(text):
    try:
        mm = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text.strip(), re.S)
        d = json.loads(mm.group(1) if mm else text)
        facts = " ".join(f.get("content", "") for f in d.get("new_facts", []))
    except Exception:
        return None, False
    cyr = len(re.findall(r"[а-яіїєґА-ЯІЇЄҐ]", facts)); lat = len(re.findall(r"[A-Za-z]", facts))
    return ("uk" if cyr > lat else "en"), True


for r in read("grades_extract.txt"):
    iid, lab, tp, nf, w, s, sw = r[0], r[1], *map(int, r[2:7])
    k = key[f"extract/{iid}/{lab}"]
    raw = raws[(iid, k["variant"], k["sample"])]
    lang, valid = lang_of(raw["text"])
    g = gold[iid]
    ext[k["variant"]].append(dict(id=iid, tp=tp, nf=nf, w=w, st=s, sw=sw, gf=len(g["gold_facts"]), gs=len(g["gold_state"]),
                                  lang=lang, valid=valid))
print("\n### Extractor (deepseek-v4.1-flash-1017, 10 passages x 3 samples = 30 per variant on the key; 6 graded per passage)")
res = {}
for v in ("uk", "en"):
    xs = ext[v]
    rf = sum(x["tp"] for x in xs) / sum(x["gf"] for x in xs)
    rs = sum(x["st"] for x in xs) / sum(x["gs"] for x in xs)
    rec_all = sum(x["tp"] + x["st"] for x in xs) / sum(x["gf"] + x["gs"] for x in xs)
    prec = 1 - sum(x["w"] for x in xs) / sum(x["nf"] for x in xs)
    nstate = sum(x["st"] + x["sw"] for x in xs)
    bad = sum(x["sw"] for x in xs) / max(1, nstate)
    langc = sum(x["lang"] == ("uk" if v == "uk" else "en") for x in xs) / len(xs)
    valid = sum(x["valid"] for x in xs) / len(xs)
    res[v] = dict(n=len(xs), fact_recall=round(rf, 3), state_recall=round(rs, 3), recall_all=round(rec_all, 3),
                  precision=round(prec, 3), bad_state_ops=round(bad, 3), asked_language_followed=round(langc, 3), valid_json=round(valid, 3),
                  lang_counts={l: sum(x["lang"] == l for x in xs) for l in ("uk", "en", None)})
    print(v, res[v])
# per passage paired recall diff
ids = sorted(gold)
diffs = []
for i in ids:
    def rr(v):
        xs = [x for x in ext[v] if x["id"] == i]
        return sum(x["tp"] + x["st"] for x in xs) / (len(xs) * (len(gold[i]["gold_facts"]) + len(gold[i]["gold_state"])))
    diffs.append(rr("en") - rr("uk"))
lo, hi = boot(diffs)
res["recall_diff_en_minus_uk"] = dict(mean=round(st.mean(diffs), 3), lo=round(lo, 3), hi=round(hi, 3))
print("recall en-uk per-passage mean", round(st.mean(diffs), 3), "CI", round(lo, 3), round(hi, 3))
out["extract"] = res
(HERE / "results.json").write_text(json.dumps(out, indent=1, ensure_ascii=False))
