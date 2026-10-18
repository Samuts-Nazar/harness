"""Minimal OpenRouter client with per-experiment spend ledger (throwaway experiment code)."""
import json, os, threading, time
from pathlib import Path
import httpx
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")
_KEY = os.environ["OPENROUTER_API_KEY"]
_H = {"Authorization": f"Bearer {_KEY}"}
LEDGER = ROOT / "experiments" / "results" / "spend.jsonl"
LEDGER.parent.mkdir(parents=True, exist_ok=True)
_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


def spent(experiment: str) -> float:
    if not LEDGER.exists():
        return 0.0
    return sum(r["cost"] for r in map(json.loads, LEDGER.read_text().splitlines()) if r["exp"] == experiment)


def _record(exp, kind, model, cost, latency):
    with _lock, LEDGER.open("a") as f:
        f.write(json.dumps({"exp": exp, "kind": kind, "model": model, "cost": cost, "latency": latency}) + "\n")


def _post(url, body, exp, kind, cap, retries=4):
    if cap is not None and spent(exp) >= cap:
        raise BudgetExceeded(f"{exp} spent {spent(exp):.3f} >= cap {cap}")
    last = None
    for i in range(retries):
        t = time.time()
        try:
            r = httpx.post(url, headers=_H, json=body, timeout=180)
            lat = time.time() - t
            if r.status_code == 200 and "error" not in r.json():
                return r.json(), lat
            last = f"{r.status_code} {r.text[:300]}"
            if r.status_code in (400, 401, 402, 403, 404):
                break
        except httpx.HTTPError as e:
            last = repr(e)
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"request failed: {last}")


def chat(model, messages, *, exp, cap=None, max_tokens=800, temperature=0.7, json_mode=False,
         reasoning={"enabled": False}):
    """Returns dict(text, cost, latency, usage). Reasoning is disabled by default; models where it is
    mandatory (e.g. claude-sonnet-5.5) fall back to effort=low with extra token headroom."""
    body = {"model": model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature,
            "usage": {"include": True}}
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if reasoning is not None:
        body["reasoning"] = reasoning
    try:
        j, lat = _post("https://openrouter.ai/api/v1/chat/completions", body, exp, "chat", cap)
    except RuntimeError as e:
        if "Reasoning is mandatory" not in str(e):
            raise
        body["reasoning"] = {"effort": "low"}
        body["max_tokens"] = max_tokens + 3000
        body.pop("temperature", None)
        j, lat = _post("https://openrouter.ai/api/v1/chat/completions", body, exp, "chat", cap)
    u = j.get("usage", {})
    cost = float(u.get("cost") or 0)
    _record(exp, "chat", model, cost, lat)
    msg = j["choices"][0]["message"]
    return {"text": msg.get("content") or "", "cost": cost, "latency": lat, "usage": u}


def jev(model, state, questions, *, exp, cap=None):
    """Jev decisions endpoint. Returns dict(answers, cost, latency)."""
    body = {"model": model, "state": state, "questions": questions}
    j, lat = _post("https://openrouter.ai/api/alpha/decisions", body, exp, "jev", cap)
    cost = float(j.get("usage", {}).get("cost") or 0)
    _record(exp, "jev", model, cost, lat)
    return {"answers": j["answers"], "cost": cost, "latency": lat, "usage": j.get("usage", {})}


def pmap(fn, items, workers=8):
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(workers) as ex:
        return list(ex.map(fn, items))
