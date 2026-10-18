"""E2: Jev vs LLM-with-JSON on narrow judgments. Usage: python experiments/e2/run.py [--reps 2]"""
import json, sys, argparse, pathlib, time
sys.path.insert(0, "experiments")
from common.llm import chat, jev, pmap

EXP = "e2"; CAP = 0.6
HERE = pathlib.Path(__file__).parent
OUT = HERE / "results"; OUT.mkdir(exist_ok=True)
JEV = ["typesafe/jev-1.14", "typesafe/jev-1.13"]
LLMS = ["google/gemini-3.1-flash-lite", "qwen/qwen3.5-9b", "openai/gpt-5.4-mini", "anthropic/claude-haiku-5.5",
        "anthropic/claude-sonnet-5.5"]
REL = {"worse": "ставлення стало гіршим", "unchanged": "ставлення не змінилося", "better": "ставлення стало кращим"}
MAG = ["немає змін", "незначна зміна", "помітна зміна", "велика зміна"]


def describe(it):
    i = it["input"]; t = it["type"]
    if t == "contradiction":
        return [f"Канонічний факт: {i['canon']}", f"Уривок: {i['passage']}"], "Чи суперечить уривок канонічному факту?"
    if t == "relationship":
        return [f"Персонаж: {i['npc']}", f"Сцена: {i['scene']}"], f"Як змінилося ставлення персонажа {i['npc']} до гравця Рагнара внаслідок цієї сцени?"
    if t == "salience":
        return [f"Персонаж: {i['npc']}", f"Подія: {i['event']}"], "Чи помітив би цей персонаж цю подію або чи переймався б нею?"
    return [f"Дія в грі: {i['action']}"], "Чи справді невизначений результат цієї дії (тобто він може вийти по-різному)?"


def run_jev(model, it):
    state, q = describe(it)
    if it["type"] == "relationship":
        qs = {"direction": {"type": "choice", "criteria": REL, "instructions": q},
              "magnitude": {"type": "score", "criteria": MAG, "instructions": "Наскільки велика ця зміна ставлення?"}}
    else:
        qs = {"a": {"type": "noul", "instructions": q}}
    r = jev(model, state, qs, exp=EXP, cap=CAP)
    a = r["answers"]
    if it["type"] == "relationship":
        pr = a["direction"]["probabilities"]; pred = a["direction"]["choice"]
        return dict(pred=pred, p=pr.get(pred), probs=pr, mag=a["magnitude"]["score"], cost=r["cost"], latency=r["latency"])
    p = a["a"]["noul"]
    return dict(pred="yes" if p >= 0.5 else "no", p=p if p >= .5 else 1 - p, p_yes=p, cost=r["cost"], latency=r["latency"])


SYS = "Ти модуль ігрового рушія, що виносить вузькі судження. Відповідай лише JSON."


def llm_prompt(it):
    state, q = describe(it)
    ctx = "\n".join(state)
    if it["type"] == "relationship":
        return (f"{ctx}\n\nПитання: {q}\nВідповідь JSON: "
                '{"direction":"worse|unchanged|better","p_worse":0..1,"p_unchanged":0..1,"p_better":0..1,'
                '"magnitude":0|1|2|3}\n(magnitude: 0 немає змін, 1 незначна, 2 помітна, 3 велика; ймовірності в сумі 1)')
    return f'{ctx}\n\nПитання: {q}\nВідповідь JSON: {{"answer":"yes|no","p_yes":0..1}} (p_yes — твоя ймовірність, що правильна відповідь «yes»)'


def parse(t):
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def run_llm(model, it):
    r = chat(model, [{"role": "system", "content": SYS}, {"role": "user", "content": llm_prompt(it)}],
             exp=EXP, cap=CAP, max_tokens=300, temperature=0, json_mode=True)
    try:
        j = parse(r["text"])
    except Exception:
        return dict(pred=None, p=None, cost=r["cost"], latency=r["latency"], raw=r["text"][:200])
    if it["type"] == "relationship":
        pr = {k: j.get("p_" + k) for k in REL}
        return dict(pred=j.get("direction"), p=pr.get(j.get("direction")), probs=pr, mag=j.get("magnitude"), cost=r["cost"], latency=r["latency"])
    p = j.get("p_yes")
    pred = j.get("answer")
    return dict(pred=pred, p=(p if pred == "yes" else 1 - p) if isinstance(p, (int, float)) else None,
                p_yes=p, cost=r["cost"], latency=r["latency"])


def job(x):
    sysname, it, rep = x
    try:
        res = (run_jev if sysname.startswith("typesafe") else run_llm)(sysname, it)
    except Exception as e:
        res = dict(pred=None, error=str(e)[:200], cost=0, latency=None)
    return dict(system=sysname, item=it["id"], type=it["type"], label=it["label"], magnitude=it["magnitude"],
                unsure=it["unsure"], rep=rep, **res)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--reps", type=int, default=2); a = ap.parse_args()
    items = [json.loads(l) for l in (HERE / "items.jsonl").read_text().splitlines()]
    jobs = [(s, it, r) for s in JEV + LLMS for it in items for r in range(a.reps)]
    res = pmap(job, jobs, workers=6)
    (OUT / "raw.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n")
    print(len(res), "done; cost", round(sum(r["cost"] for r in res), 3), "errors", sum(1 for r in res if r["pred"] is None))
