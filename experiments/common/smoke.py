import sys; sys.path.insert(0, "experiments")
from common.llm import chat
for m in ["anthropic/claude-sonnet-5.5","google/gemma-3-4b-it","mistralai/ministral-8b-2512"]:
    r=chat(m,[{"role":"user","content":"Скажи 'привіт' одним словом."}],exp="smoke",max_tokens=50)
    print(m,repr(r["text"]),r["cost"])
