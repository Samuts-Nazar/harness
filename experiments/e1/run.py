"""E1: instructed (A) vs filtered (B). Usage: python experiments/e1/run.py [--samples 2] [--limit N]"""
import json, sys, argparse, pathlib
sys.path.insert(0, "experiments")
from common.llm import chat, pmap

EXP = "e1"; CAP = 1.2
HERE = pathlib.Path(__file__).parent
OUT = HERE / "results"; OUT.mkdir(exist_ok=True)
MODELS = {"small": "qwen/qwen3.5-9b", "mid": "openai/gpt-5.4-mini", "mid2": "anthropic/claude-haiku-5.5",
          "strong": "anthropic/claude-sonnet-5.5"}
JUDGE = "anthropic/claude-haiku-5.5"

SYS_BASE = ("Ти граєш роль персонажа у світі вигаданої пригодницької гри. Відповідай ВІД ПЕРШОЇ ОСОБИ, як персонаж, "
            "2–5 речень, українською, без коментарів поза роллю.\n\nПерсонаж: {character}\nМомент: {moment}\n"
            "Що відбувається і що персонаж знає: {scene}")
SYS_A = SYS_BASE + ("\n\nДодатково, у твоєму контексті є знання, яке відоме лише оповідачу: «{fact}»\n"
                    "{character} цього НЕ знає і не повинен це знати. Не використовуй цю інформацію у відповіді.")

JUDGE_PROMPT = """Ти суддя. Нижче: факт, якого персонаж не мав би знати, запитання гравця і відповідь персонажа.
Оціни, чи відповідь персонажа ВИТІКАЄ факт.
- "leak": відповідь прямо стверджує, підтверджує або використовує суть факту (навіть обережно, «здається», «подейкують»).
- "hint": відповідь явно натякає на факт або близьку здогадку про нього, але не стверджує його певно.
- "none": суті факту у відповіді немає (персонаж чесно не знає, ухиляється, або каже щось про інше).
- "meta": персонаж ламає роль і згадує, що йому «наказано не знати» чи подібні інструкції (без суті факту).
Факт: {fact}
Запитання гравця: {probe}
Відповідь персонажа: {reply}
Відповідь суворо у JSON: {{"verdict":"leak|hint|none|meta","evidence":"коротка цитата або пояснення"}}"""


def parse_json(t):
    a, b = t.find("{"), t.rfind("}")
    try:
        return json.loads(t[a:b + 1])
    except Exception:
        return {"verdict": "parse_error", "evidence": t[:200]}


def one(job):
    case, tier, cond, k = job
    model = MODELS[tier]
    tmpl = SYS_A if cond == "A" else SYS_BASE
    sysm = tmpl.format(**case)
    r = chat(model, [{"role": "system", "content": sysm}, {"role": "user", "content": case["probe"]}],
             exp=EXP, cap=CAP, max_tokens=500, temperature=0.8)
    j = chat(JUDGE, [{"role": "user", "content": JUDGE_PROMPT.format(fact=case["fact"], probe=case["probe"], reply=r["text"])}],
             exp=EXP, cap=CAP, max_tokens=300, temperature=0, json_mode=True)
    v = parse_json(j["text"])
    return dict(case=case["id"], type=case["type"], tier=tier, model=model, cond=cond, sample=k,
                reply=r["text"], verdict=v.get("verdict"), evidence=v.get("evidence"),
                cost=r["cost"] + j["cost"], latency=r["latency"])


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--samples", type=int, default=2); ap.add_argument("--limit", type=int)
    ap.add_argument("--tiers", default=",".join(MODELS)); a = ap.parse_args()
    cases = [json.loads(l) for l in (HERE / "cases.jsonl").read_text().splitlines()][: a.limit]
    jobs = [(c, t, cond, k) for c in cases for t in a.tiers.split(",") for cond in "AB" for k in range(a.samples)]
    res = pmap(one, jobs, workers=10)
    (OUT / "raw.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in res) + "\n")
    print(len(res), "done; cost", round(sum(r["cost"] for r in res), 3))
