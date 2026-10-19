"""Probe which endpoint each decision model answers on, with a trivial question."""
import json, os, sys, time
import httpx
from dotenv import load_dotenv
load_dotenv()
H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
models = sys.argv[1:] or ["typesafe/jev-1.14", "perplexity/pplx-decider-v1.2",
                          "perplexity/pplx-decider-flash-v1.2", "liquid/d1-ultra", "elorian/glimpse"]
for m in models:
    body = {"model": m, "state": ["Ragnar drew his sword in the hall."],
            "questions": {"a": {"type": "noul", "instructions": "Did Ragnar draw a weapon?"}}}
    for url in ("https://openrouter.ai/api/v1/systemone", "https://openrouter.ai/api/alpha/decisions"):
        t = time.time()
        r = httpx.post(url, headers=H, json=body, timeout=60)
        print(m, url.split("/api/")[1], r.status_code, round(time.time() - t, 2), r.text[:400].replace("\n", " "))
