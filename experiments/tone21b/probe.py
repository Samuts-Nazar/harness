"""Task 21B tone probe: same 5 NPC moments as experiments/style, several ways of asking, blind-graded by the agent.

Variants (V0 is read from experiments/style/raw/npc.jsonl, no cost):
  V0 luna, task 15 'ex' prompt (rule list + exemplars), one live sample at temperature 0.8
  V1 luna, document frame (no rule list; book-page frame, exemplars, scene note, line to continue)
  V2 gemma-4-31b-it, document frame, temperature 1.0, min_p 0.05
  V3 mistral-nemo, document frame, temperature 0.9, min_p 0.05
  V4 gemma-4-31b-it rewrite of the V0 line (editor pass with exemplars)
Book exemplars come from data/ at runtime and live in the prompts; outputs are written outside the repo.
Spend cap 0.30 USD, own ledger.
Run: PYTHONPATH=. nix develop --command python -m experiments.tone21b.probe OUT.json LEDGER.jsonl MSGS.json
"""
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
from dotenv import load_dotenv

load_dotenv(".env")
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
CAP = 0.30
LEDGER = sys.argv[2]
MSGS = sys.argv[3]
lock = threading.Lock()
EXSEP = ("Take only the rhythm, the dryness and the manner. The people, places and events in them are "
         "not in your scene; use none of their names, facts or phrases.")


def spent():
    try:
        return sum(json.loads(line)["cost"] for line in open(LEDGER))
    except FileNotFoundError:
        return 0.0


def chat(model, messages, **kw):
    if spent() >= CAP:
        raise RuntimeError("cap")
    body = {"model": model, "messages": messages, "max_tokens": 600, **kw}
    for i in range(4):
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions", headers=H, json=body, timeout=180)
        if r.status_code == 200 and "error" not in r.json():
            j = r.json()
            c = float(j.get("usage", {}).get("cost") or 0)
            with lock, open(LEDGER, "a") as f:
                f.write(json.dumps({"model": model, "cost": c}) + "\n")
            return (j["choices"][0]["message"].get("content") or "").strip(), c
        if r.status_code in (400, 401, 402, 403, 404):
            raise RuntimeError(r.text[:300])
        time.sleep(2 * (i + 1))
    raise RuntimeError("failed")


def exemplars(msgs):
    return msgs[1]["content"].split(EXSEP)[1].split("Recent conversation:")[0].strip()


def doc_prompt(msgs):
    """Re-frame the task 15 messages as a book page to continue, without the rule list."""
    u = msgs[1]["content"]
    name = re.search(r"Write (.+?)'s next turn", u).group(1)
    know = u.split("What you know:")[1].split("Location:")[0].strip()
    loc = re.search(r"Location: (.*)", u).group(1)
    recent = u.split("Recent conversation:")[1].split("Write ")[0].strip()
    manner = msgs[0]["content"].split("You write a living person")[0].strip()
    return (f"Український переклад роману про відьмака. Уривки.\n\n{exemplars(msgs)}\n\n* * *\n\n"
            f"[Далі сцена, якої в книжці немає. Місце: {loc}. {name} знає тільки це:\n{know}\n"
            f"Більше він нічого не знає й не вигадує нових фактів, імен чи подій.\n"
            f"Про героя: {manner}]\n\n{recent}\n\n"
            f"Допиши наступний уривок цього перекладу: відповідь {name} з його дрібним жестом (третьою особою). "
            f"Пиши так, як пише перекладач книжки, українською. Лише текст уривка, без пояснень.")


def main(out):
    msgs = json.load(open(MSGS))
    ids = ["i1", "i3", "c07", "c11", "c08"]
    v0 = {}
    for i in ids:  # V0 live, so that run A and run B use the same settings
        v0[i], _ = chat("openai/gpt-6-luna", msgs[i], temperature=0.8, reasoning={"enabled": False})
    jobs = []
    for i in ids:
        jobs.append((i, "V0", 0, None))
        jobs.append((i, "V1", 0, ("openai/gpt-6-luna", {"reasoning": {"enabled": False}, "temperature": 1.0})))
        for k in range(2):
            jobs.append((i, "V2", k, ("google/gemma-4-31b-it",
                                      {"temperature": 1.0, "min_p": 0.05, "reasoning": {"enabled": False}})))
            jobs.append((i, "V3", k, ("mistralai/mistral-nemo", {"temperature": 0.9, "min_p": 0.05})))
        jobs.append((i, "V4", 0, ("google/gemma-4-31b-it", {"temperature": 0.8, "reasoning": {"enabled": False}})))

    def one(j):
        i, v, k, spec = j
        if v == "V0":
            return dict(id=i, v=v, k=k, text=v0[i], cost=0)
        try:
            if v == "V4":
                p = (f"Нижче уривки з українського перекладу книжок про відьмака, а потім чернетка репліки персонажа.\n\n"
                     f"{exemplars(msgs[i])}\n\n* * *\n\nЧернетка:\n{v0[i]}\n\n"
                     "Перепиши чернетку так, як її написав би перекладач цих книжок: ті самі факти й та сама дія, без нових фактів. "
                     "Прибери все, що звучить як повідомлення чи кальки з англійської, іноземні слова, акуратні висновки. "
                     "Лише переписаний текст.")
                m = [{"role": "user", "content": p}]
            else:
                m = [{"role": "user", "content": doc_prompt(msgs[i])}]
            t, c = chat(spec[0], m, **spec[1])
            return dict(id=i, v=v, k=k, text=t, cost=c)
        except Exception as e:  # noqa: BLE001
            return dict(id=i, v=v, k=k, text="", cost=0, error=str(e)[:200])

    with ThreadPoolExecutor(6) as ex:
        res = list(ex.map(one, jobs))
    json.dump(res, open(out, "w"), ensure_ascii=False, indent=1)
    print(len(res), "errors", [r for r in res if r.get("error")][:3], "spent", round(spent(), 4))


if __name__ == "__main__":
    main(sys.argv[1])
