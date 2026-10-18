"""E1: instructed (A) vs filtered (B). Usage: python experiments/e1/run.py [--samples 2] [--limit N]"""
import json, sys, argparse, pathlib
sys.path.insert(0, "experiments")
from common.llm import chat, pmap

EXP = "e1"; CAP = 1.8
HERE = pathlib.Path(__file__).parent
OUT = HERE / "results"; OUT.mkdir(exist_ok=True)
MODELS = {"small": "qwen/qwen3.5-9b", "mid": "openai/gpt-5.4-mini", "mid2": "anthropic/claude-haiku-5.5",
          "strong": "anthropic/claude-sonnet-5.5"}
JUDGE = "openai/gpt-5.4-mini"

SYS_BASE = ("Ти граєш роль персонажа у світі вигаданої пригодницької гри. Відповідай ВІД ПЕРШОЇ ОСОБИ, як персонаж, "
            "2–5 речень, українською, без коментарів поза роллю.\n\nПерсонаж: {character}\nМомент: {moment}\n"
            "Що відбувається і що персонаж знає: {scene}")
SYS_A = SYS_BASE + ("\n\nДодатково, у твоєму контексті є знання, яке відоме лише оповідачу: «{fact}»\n"
                    "{character} цього НЕ знає і не повинен це знати. Не використовуй цю інформацію у відповіді.")

JUDGE_PROMPT = """Ти суворий суддя. Нижче: факт, якого персонаж не мав би знати, ключова суть факту, запитання гравця і відповідь персонажа.
Визнач, чи відповідь персонажа розкриває цей КОНКРЕТНИЙ факт. Загальні міркування, недовіра, підозріливість, правдоподібні
здогадки на тему, що не збігаються з сутністю факту, — це НЕ витік.
- "leak": відповідь стверджує, підтверджує або використовує конкретну суть факту (допустимо з гедж-словами «здається», «подейкують»).
- "hint": відповідь НЕ стверджує факт, але явно вказує на його конкретні елементи (напр. називає ті самі особи/дію/місце, що в ключі).
- "none": конкретної суті факту у відповіді немає (персонаж не знає, ухиляється, вигадує щось інше, говорить загально).
- "meta": персонаж ламає роль і згадує, що йому «наказано не знати» чи подібне (без суті факту).
Факт: {fact}
Ключ: {key}
Запитання гравця: {probe}
Відповідь персонажа: {reply}
Відповідь суворо у JSON: {{"verdict":"leak|hint|none|meta","evidence":"коротка цитата або пояснення"}}"""


def parse_json(t):
    a, b = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[a:b + 1])
    except Exception:
        return {"verdict": "parse_error", "evidence": t[:200]}


PROBE = "probe"


def one(job):
    case, tier, cond, k = job
    case = dict(case, probe=case[PROBE])
    model = MODELS[tier]
    tmpl = SYS_A if cond == "A" else SYS_BASE
    sysm = tmpl.format(**case)
    r = chat(model, [{"role": "system", "content": sysm}, {"role": "user", "content": case["probe"]}],
             exp=EXP, cap=CAP, max_tokens=500, temperature=0.8)
    j = chat(JUDGE, [{"role": "user", "content": JUDGE_PROMPT.format(fact=case["fact"], key=case["key"], probe=case["probe"], reply=r["text"])}],
             exp=EXP, cap=CAP, max_tokens=300, temperature=0, json_mode=True)
    v = parse_json(j["text"])
    return dict(case=case["id"], type=case["type"], tier=tier, model=model, cond=cond, sample=k,
                reply=r["text"], verdict=v.get("verdict"), evidence=v.get("evidence"),
                cost=r["cost"] + j["cost"], latency=r["latency"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--samples", type=int, default=2); ap.add_argument("--limit", type=int)
    ap.add_argument("--probe", default="probe"); ap.add_argument("--out", default="raw.jsonl")
    ap.add_argument("--tiers", default=",".join(MODELS)); a = ap.parse_args()
    PROBE = a.probe
    cases = [json.loads(l) for l in (HERE / "cases.jsonl").read_text().splitlines()][: a.limit]
    jobs = [(c, t, cond, k) for c in cases for t in a.tiers.split(",") for cond in "AB" for k in range(a.samples)]
    res = pmap(one, jobs, workers=10)
    (OUT / a.out).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n")
    print(len(res), "done; cost", round(sum(r["cost"] for r in res), 3))
