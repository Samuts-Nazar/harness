"""Per-call metering of the live stack (task 6). Logs role, model, tokens, cost, latency.

Nothing here touches engine code: it subclasses the OpenRouter provider, wraps the Jev HTTP client
and tags calls by wrapping Engine methods. Prompt texts are NOT logged (only sizes).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import httpx

from harness.policy import check_model
from harness.providers import OpenRouterProvider

STATE = {"turn": 0, "role": "setup"}
LOG: list[dict] = []
LOG_PATH: Path | None = None


def record(**kw) -> None:
    e = {"turn": STATE["turn"], **kw}
    LOG.append(e)
    if LOG_PATH:
        with LOG_PATH.open("a") as f:
            f.write(json.dumps(e) + "\n")


class MeteredProvider(OpenRouterProvider):
    def complete(self, model, messages):
        check_model(model)
        self.spend.check()
        body = {"model": model, "messages": messages, "usage": {"include": True},
                "reasoning": {"enabled": False}}
        t = time.perf_counter()
        r = httpx.post(self.URL, headers=self._headers, json=body, timeout=self._timeout)
        if r.status_code == 400:
            body.pop("reasoning")
            r = httpx.post(self.URL, headers=self._headers, json=body, timeout=self._timeout)
        lat = time.perf_counter() - t
        r.raise_for_status()
        j = r.json()
        u = j.get("usage") or {}
        self.spend.add(u)
        record(role=STATE["role"], model=model, input_tokens=u.get("prompt_tokens"),
               output_tokens=u.get("completion_tokens"), cost=float(u.get("cost") or 0),
               latency=round(lat, 3))
        return j["choices"][0]["message"]["content"] or ""


class MeteredClient(httpx.Client):
    """Used for the Jev endpoint."""

    def post(self, url, **kw):
        t = time.perf_counter()
        r = super().post(url, **kw)
        lat = time.perf_counter() - t
        try:
            j = r.json()
            u = j.get("usage") or {}
            model = kw.get("json", {}).get("model")
            record(role="jev", model=model, input_tokens=u.get("prompt_tokens") or u.get("input_tokens"),
                   output_tokens=u.get("completion_tokens") or u.get("output_tokens"),
                   cost=float(u.get("cost") or 0), latency=round(lat, 3),
                   n_questions=len(kw.get("json", {}).get("questions", {})), usage_raw=u)
        except ValueError:
            pass
        return r


def tag(obj, name: str, role: str) -> None:
    """Wrap obj.<name> so provider calls inside it are attributed to `role`."""
    inner = getattr(obj, name)

    def wrapped(*a, **k):
        prev = STATE["role"]
        STATE["role"] = role
        try:
            return inner(*a, **k)
        finally:
            STATE["role"] = prev

    setattr(obj, name, wrapped)
