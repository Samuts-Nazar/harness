"""Task 21A probe client (throwaway experiment code). Decision points live in campaigns/21A/ (git-ignored,
book-derived), never in git. Own ledger with a hard cap so the probe cannot exceed its budget."""
import json
import os
import random
import re
import threading
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv("/home/cock/projects/harness/.env")
_H = {"Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"]}
DATA = ROOT / "campaigns" / "21A"
LEDGER = DATA / "ledger.jsonl"
CAP = 0.28  # USD, hard stop (brief: 0.30)
_lock = threading.Lock()
LETTERS = "ABCDEFGH"


def spent() -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(json.loads(x)["cost"] for x in LEDGER.read_text().splitlines())


def _post(url, body, kind, model):
    if spent() >= CAP:
        raise RuntimeError(f"budget cap {CAP} reached")
    last = None
    for i in range(5):
        t = time.time()
        try:
            r = httpx.post(url, headers=_H, json=body, timeout=120)
            if r.status_code == 200 and "error" not in r.json():
                j = r.json()
                u = j.get("usage") or {}
                cost = float(u.get("cost") or 0)
                with _lock, LEDGER.open("a") as f:
                    f.write(json.dumps({"kind": kind, "model": model, "cost": cost,
                                        "lat": round(time.time() - t, 2)}) + "\n")
                return j
            last = f"{r.status_code} {r.text[:300]}"
            if r.status_code in (400, 401, 402, 403, 404):
                break
        except httpx.HTTPError as e:
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"{model}: {last}")


def decide(model, state_lines, question, options):
    """options: list of texts (order matters). Returns {option_text: prob}."""
    body = {"model": model, "state": state_lines,
            "questions": {"q": {"type": "choice", "criteria": {o: o for o in options},
                                "instructions": question}}}
    j = _post("https://openrouter.ai/api/v1/systemone", body, "decide", model)
    a = j["answers"]["q"]
    return {k: float(v) for k, v in (a.get("probabilities") or {}).items()}, a.get("choice")


def chat(model, system, user, max_tokens=400, temperature=1.0):
    body = {"model": model, "max_tokens": max_tokens, "temperature": temperature,
            "usage": {"include": True}, "reasoning": {"enabled": False},
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}]}
    j = _post("https://openrouter.ai/api/v1/chat/completions", body, "chat", model)
    return j["choices"][0]["message"].get("content") or ""


def orders(n_opts, k, seed):
    """k option orders: identity, reverse, then seeded shuffles (positions are permuted, labels re-assigned)."""
    base = list(range(n_opts))
    out = [base, base[::-1]]
    rng = random.Random(seed)
    while len(out) < k:
        p = base[:]
        rng.shuffle(p)
        out.append(p)
    return out[:k]


def parse_letter(text, n):
    m = re.search(r"\b([A-%s])\b" % LETTERS[n - 1], text.strip().upper())
    return LETTERS.index(m.group(1)) if m else None


def parse_json_dist(text, n):
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    out = [0.0] * n
    for k, v in d.items():
        k = k.strip().upper()[:1]
        if k in LETTERS[:n]:
            try:
                out[LETTERS.index(k)] = float(v)
            except (TypeError, ValueError):
                pass
    s = sum(out)
    return [x / s for x in out] if s > 0 else None
