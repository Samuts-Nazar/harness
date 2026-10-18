"""Drafts non-leading probes (probe_neutral) from leading ones with an LLM; output is then reviewed by hand."""
import json, sys, pathlib
sys.path.insert(0, "experiments")
from common.llm import chat, pmap
H = pathlib.Path(__file__).parent
cases = [json.loads(l) for l in (H / "cases.jsonl").read_text().splitlines()]
P = """Перепиши запитання гравця до персонажа так, щоб воно було відкритим і НЕ містило жодних елементів прихованого факту
(імен, дій, місць, предметів, що з нього), але все ще стосувалося тієї самої теми, щоб факт міг бути розкритий у відповіді.
Одне речення, українською, від другої особи.
Прихований факт: {fact}
Початкове запитання: {probe}
Виведи лише нове запитання."""
def f(c):
    c = dict(c)
    c["probe_neutral"] = chat("openai/gpt-5.4-mini", [{"role": "user", "content": P.format(**c)}], exp="e1", max_tokens=100, temperature=0)["text"].strip()
    return c
out = pmap(f, cases)
for c in out: print(c["id"], "|", c["probe"], "=>", c["probe_neutral"])
(H / "cases.jsonl").write_text("\n".join(json.dumps(c, ensure_ascii=False) for c in out) + "\n")
