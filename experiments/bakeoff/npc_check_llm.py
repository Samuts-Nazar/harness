"""Same NPC-check experiment with gpt-6-luna as an LLM judge (JSON answer), appended to raw/npc_check.jsonl."""
import json, re
from experiments.common import llm
from . import npc_check as nc

MODEL = "openai/gpt-6-luna"


def ask(state, q):
    prompt = ("State:\n- " + state.replace("\n", "\n  ") + f"\n\nQuestion: {q}\n\n"
              'Reply with JSON only: {"answer": "yes"|"no", "p_yes": number 0..1}')
    r = llm.chat(MODEL, [{"role": "system", "content": "You are a module of a game engine that makes narrow judgments. Answer JSON only."},
                         {"role": "user", "content": prompt}], exp="task7", cap=0.9, max_tokens=200, temperature=0)
    d = json.loads(re.search(r"\{.*\}", r["text"], re.S).group(0))
    yes = str(d["answer"]).lower().startswith("y")
    p = float(d.get("p_yes", 1.0 if yes else 0.0))
    if (yes and p < 0.5) or (not yes and p > 0.5):
        p = 1 - p
    return p, r["latency"]


out = []
for k, g in nc.grades.items():
    if g["fmt"]:
        continue
    s, iid, lab = k.split("/")
    line = nc.clean_npc_line(nc.rows[(s, iid, nc.key[k])]["text"])
    for vname, q in (("v0", nc.Q0), ("v1", nc.Q1)):
        p, lat = ask(nc.context(nc.items[iid], line), q)
        out.append(dict(id=k, text_model=nc.key[k], leak=g["leak"], check_model=MODEL, variant=vname, p=p, lat=round(lat, 3)))
with (nc.HERE / "raw/npc_check.jsonl").open("a") as f:
    f.write("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n")
print(len(out))
