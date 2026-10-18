"""E3: state extraction from a narrated turn. Usage: python experiments/e3/run.py [--models a,b]"""
import json, sys, argparse, pathlib
sys.path.insert(0, "experiments")
from common.llm import chat, pmap

EXP = "e3"; CAP = 0.85
HERE = pathlib.Path(__file__).parent
OUT = HERE / "results"; OUT.mkdir(exist_ok=True)
DATA = HERE.parents[1] / "data"
MODELS = ["google/gemma-3-4b-it", "mistralai/ministral-8b-2512", "qwen/qwen3.5-9b", "deepseek/deepseek-v4-flash",
          "google/gemini-3.1-flash-lite", "anthropic/claude-haiku-5.5", "anthropic/claude-sonnet-5.5"]
MATCHER = "anthropic/claude-haiku-5.5"

SYS = """Ти модуль-екстрактор ігрового рушія. Тобі дають уривок оповіді. Виведи JSON-диф змін стану світу, ЛИШЕ на основі того,
що прямо сказано або однозначно випливає з уривка. Нічого не вигадуй. Схема:
{"facts":[{"text":"нова подія/факт одним реченням","where":"місце або null","witnesses":["хто це бачив/чув"],"notability":"low|medium|high"}],
 "inventory":[{"who":"...","item":"...","change":"gain|lose"}],
 "injuries":[{"who":"...","desc":"..."}],
 "relationships":[{"a":"...","b":"...","delta":"better|worse"}]}
notability: low — тихо, помітили лише присутні; medium — помітна подія; high — гучна, про неї знатимуть далеко.
witnesses — лише ті, хто присутній у сцені й міг це побачити чи почути. Порожні списки допустимі. Відповідай лише JSON."""


def passage_text(p):
    L = (DATA / p["src"]).read_text(encoding="utf-8").split("\n")
    return "\n".join(l for l in L[p["lines"][0] - 1:p["lines"][1]] if l.strip())


def parse(t):
    a, b = t.find("{"), t.rfind("}")
    return json.loads(t[a:b + 1])


def extract(job):
    p, model = job
    user = f"Контекст сцени: {p['header']}\n\nУривок:\n{passage_text(p)}"
    r = chat(model, [{"role": "system", "content": SYS}, {"role": "user", "content": user}], exp=EXP, cap=CAP,
             max_tokens=1500, temperature=0, json_mode=True)
    try:
        pred = parse(r["text"]); ok = True
    except Exception:
        pred, ok = {"facts": [], "inventory": [], "injuries": [], "relationships": []}, False
    for k in ("facts", "inventory", "injuries", "relationships"):
        if not isinstance(pred.get(k), list): pred[k] = []
    return dict(passage=p["id"], model=model, valid_json=ok, pred=pred, cost=r["cost"], latency=r["latency"], raw=None if ok else r["text"][:300])


MP = """Ти оцінюєш екстракцію змін стану. Є уривок, ЕТАЛОН (ручна розмітка) і ПРОГНОЗ моделі. Зіставляй за змістом, не за словами.
Уривок:
{text}

ЕТАЛОН: {gold}
ПРОГНОЗ: {pred}

Поверни JSON:
{{"facts":[{{"pred_index":i,"gold_index":j|null,"supported":true|false,"witnesses":"same|superset|subset|partial|different|na"}}],
 "inventory":{{"tp":n,"fp":n,"fn":n}},"injuries":{{"tp":n,"fp":n,"fn":n}},"relationships":{{"tp":n,"fp":n,"fn":n}}}}
Правила:
- Для кожного прогнозного факту (поле i) — gold_index = поле i еталонного факту, який він передає за змістом (кожен еталонний факт можна зіставити лише з одним прогнозним; якщо кілька — найкращий, решта gold_index=null).
- supported: чи підтверджується прогнозний факт уривком (true), чи це вигадка/не випливає з тексту (false). Для зіставлених — true.
- witnesses (лише для зіставлених; інакше "na"): порівняй список свідків прогнозу з еталоном (імена-синоніми й псевдоніми з контексту сцени рахуй однаковими): same — однакові; superset — прогноз додає зайвих; subset — пропускає частину; partial — перетин, але розбіжності в обидва боки; different — немає перетину.
- inventory/injuries/relationships: tp — прогнозні записи, що відповідають еталонним за змістом; fp — прогнозні записи без відповідника в еталоні; fn — еталонні записи, яких немає в прогнозі.
Лише JSON."""


def score(rec, passages):
    p = passages[rec["passage"]]
    pred = {"facts": [dict(i=i, **f) if isinstance(f, dict) else {"i": i, "text": str(f)} for i, f in enumerate(rec["pred"]["facts"])],
            "inventory": rec["pred"]["inventory"], "injuries": rec["pred"]["injuries"], "relationships": rec["pred"]["relationships"]}
    gold = dict(p["gold"], facts=[dict(i=i, **f) for i, f in enumerate(p["gold"]["facts"])])
    prompt = MP.format(text=passage_text(p), gold=json.dumps(gold, ensure_ascii=False), pred=json.dumps(pred, ensure_ascii=False))
    cost = 0; s = None; raw = None
    for attempt in range(3):
        j = chat(MATCHER, [{"role": "user", "content": prompt + ("\n\nВІДПОВІДАЙ ЛИШЕ ВАЛІДНИМ JSON, БЕЗ ЖОДНОГО ТЕКСТУ ПОЗА ЖОДНИМ ОБ'ЄКТОМ." if attempt else "")}], exp=EXP, cap=CAP, max_tokens=2500, temperature=0, json_mode=True)
        cost += j["cost"]
        try:
            s = parse(j["text"]); break
        except Exception:
            raw = j["text"][:300]
    return dict(rec, score=s, match_cost=cost, match_raw=raw)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--models", default=",".join(MODELS)); a = ap.parse_args()
    passages = [json.loads(l) for l in (HERE / "passages.jsonl").read_text().splitlines()]
    pm = {p["id"]: p for p in passages}
    ex = pmap(extract, [(p, m) for p in passages for m in a.models.split(",")], workers=8)
    sc = pmap(lambda r: score(r, pm), ex, workers=8)
    (OUT / "raw.jsonl").write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in sc) + "\n")
    print(len(sc), "done; extract cost", round(sum(r["cost"] for r in sc), 3), "match cost", round(sum(r["match_cost"] for r in sc), 3),
          "unscored", sum(r["score"] is None for r in sc), "invalid json", sum(not r["valid_json"] for r in sc))
