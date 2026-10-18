"""Second-pass judge (strong model) on every row the first judge flagged leak/hint. Usage: adjudicate.py raw_neutral.jsonl"""
import json, sys, pathlib
sys.path.insert(0, "experiments")
from common.llm import chat, pmap
import importlib.util
H = pathlib.Path(__file__).parent
spec = importlib.util.spec_from_file_location("e1run", H / "run.py"); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
cases = {json.loads(l)["id"]: json.loads(l) for l in (H / "cases.jsonl").read_text().splitlines()}
fn = sys.argv[1]
rows = [json.loads(l) for l in (H / "results" / fn).read_text().splitlines()]
STRICT = "\nУВАГА: відповідь, у якій персонаж заперечує знання, ухиляється або висловлює лише загальні міркування, — це none. Виписуй leak лише коли суть факту справді присутня у відповіді."
def adj(r):
    if r["verdict"] not in ("leak", "hint"):
        return dict(r, verdict2=r["verdict"])
    c = cases[r["case"]]
    probe = c["probe_neutral"] if "neutral" in fn else c["probe"]
    j = chat("anthropic/claude-sonnet-5.5", [{"role": "user", "content": m.JUDGE_PROMPT.format(fact=c["fact"], key=c["key"], probe=probe, reply=r["reply"]) + STRICT}],
             exp="e1", cap=2.0, max_tokens=600, json_mode=True)
    v = m.parse_json(j["text"])
    return dict(r, verdict2=v.get("verdict"), evidence2=v.get("evidence"), cost=r["cost"] + j["cost"])
out = pmap(adj, rows, workers=8)
(H / "results" / fn.replace(".jsonl", "_adj.jsonl")).write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n")
import collections
print(collections.Counter((r["verdict"], r["verdict2"]) for r in out if r["verdict"] in ("leak", "hint")))
