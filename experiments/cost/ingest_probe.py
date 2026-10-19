"""Measure structured ingestion of one chapter of the books (Ukrainian). Stats only are saved:
tokens, cost, latency, counts. The model outputs are NOT written anywhere (books are not committed).

    nix develop --command python -m experiments.cost.ingest_probe
"""
from __future__ import annotations

import json
import os
import re
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

from harness.policy import check_model

BOOKS = Path("data/witcher_books.txt")
START, END = 15520, 16260  # lines of "Розділ 1" (first book part) up to the next "Розділ"
MODELS = ["anthropic/claude-haiku-5.5", "deepseek/deepseek-v4-flash", "qwen/qwen3.5-9b"]
CHUNK_CHARS = 6000
SYSTEM = (
    "You extract structured story knowledge from a Ukrainian fantasy novel passage. Reply with JSON "
    "only: {\"events\": [{\"what\": str, \"who\": [names], \"where\": str|null, "
    "\"witnesses\": [names], \"reactions\": [{\"who\": str, \"reaction\": str}], "
    "\"notability\": 0..1}]}. Write values in Ukrainian. Include only things the passage states.")


def chunks(text: str, size: int) -> list[str]:
    out, cur = [], ""
    for para in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(para) > size:
            out.append(cur)
            cur = ""
        cur += para + "\n\n"
    if cur.strip():
        out.append(cur)
    return out


def call(key: str, model: str, text: str) -> dict:
    check_model(model)
    body = {"model": model, "usage": {"include": True}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": SYSTEM}, {"role": "user", "content": text}]}
    t = time.perf_counter()
    for _ in range(2):
        r = httpx.post("https://openrouter.ai/api/v1/chat/completions",
                       headers={"Authorization": f"Bearer {key}"}, json=body, timeout=180)
        if r.status_code == 400 and "reasoning" in body:
            body.pop("reasoning")
            continue
        break
    lat = time.perf_counter() - t
    r.raise_for_status()
    j = r.json()
    u = j.get("usage") or {}
    content = j["choices"][0]["message"]["content"] or ""
    m = re.search(r"\{.*\}", content, re.DOTALL)
    try:
        events = json.loads(m.group(0))["events"] if m else None
    except (ValueError, KeyError):
        events = None
    return {"in": u.get("prompt_tokens"), "out": u.get("completion_tokens"),
            "cost": float(u.get("cost") or 0), "latency": round(lat, 2),
            "valid_json": events is not None, "n_events": len(events) if events else 0}


def main() -> None:
    load_dotenv()
    key = os.environ["OPENROUTER_API_KEY"]
    text = "".join(BOOKS.read_text(encoding="utf-8").splitlines(keepends=True)[START:END])
    cs = chunks(text, CHUNK_CHARS)
    res = {"chapter_chars": len(text), "chunks": len(cs), "models": {}}
    for model in MODELS:
        rows = [call(key, model, c) for c in cs]
        res["models"][model] = {
            "rows": rows,
            "in": sum(r["in"] for r in rows), "out": sum(r["out"] for r in rows),
            "cost": sum(r["cost"] for r in rows), "latency_sum": sum(r["latency"] for r in rows),
            "valid": sum(r["valid_json"] for r in rows), "events": sum(r["n_events"] for r in rows),
        }
        m = res["models"][model]
        print(model, {k: v for k, v in m.items() if k != "rows"}, flush=True)
    Path("reports/cost/ingest_probe.json").write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
