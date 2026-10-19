"""Print the rendered prompts of one situation: python -m experiments.style.show i1 old|new|ex"""
import sys

from experiments.style import scenes as S
from harness.style import Style

ex, pl = Style.load("witcher"), Style.load("witcher", exemplars=False)
m = {"horst": "Крутить шапку; торгується, повторюючи цифру.", "elza": "Говорить коротко, з перцем."}
iid, v = sys.argv[1], sys.argv[2]
msgs = (S.npc_messages(iid, v, m, ex, pl) if iid[0] != "n" or iid[1] == "0" else
        S.narrator_messages(iid, v, ex, pl))
print("chars", sum(len(x["content"]) for x in msgs))
for x in msgs:
    print(f"[{x['role']}]\n{x['content']}\n")
