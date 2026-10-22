"""LLM provider interface, OpenRouter implementation and a scripted fake."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Protocol

import httpx

from .policy import MODEL_TEMPERATURE, Spend, check_model
from .retry import RETRY_STATUS, backoff_delay, send_with_retry

Messages = list[dict[str, str]]


class ProviderError(RuntimeError):
    """A call failed for good (after retries): the engine may switch to the role's fallback model."""


class Provider(Protocol):
    def complete(self, model: str, messages: Messages) -> str: ...
    def stream(self, model: str, messages: Messages) -> Iterator[str]: ...


def _chunk_error(j: dict) -> str | None:  # type: ignore[type-arg]
    """An error reported inside a 200 response or stream chunk, or None."""
    if j.get("error"):
        e = j["error"]
        return str(e.get("message", e)) if isinstance(e, dict) else str(e)
    for c in j.get("choices") or []:
        if c.get("finish_reason") == "error":
            return "finish_reason=error"
    return None


class OpenRouterProvider:
    URL = "https://openrouter.ai/api/v1/chat/completions"
    # Safe to call from several threads at once (httpx.Client and Spend are thread-safe), so the
    # engine may run independent calls of one turn in parallel.
    parallel_ok = True

    def __init__(self, api_key: str | None = None, timeout: float = 120.0,
                 spend: Spend | None = None, *, client: httpx.Client | None = None,
                 retries: int = 4, backoff: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep,
                 session_id: str | None = None) -> None:
        """`session_id`: OpenRouter sticky routing (up to 256 characters; the same session goes
        to the same provider endpoint for about ten idle minutes, so the prompt cache is hit)."""
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {key}"}
        self._client = client or httpx.Client(timeout=timeout)
        self.spend = spend or Spend()
        self.retries, self.backoff, self._sleep = retries, backoff, sleep
        self.session_id = session_id[:256] if session_id else None

    def _post(self, body: dict) -> httpx.Response:  # type: ignore[type-arg]
        return send_with_retry(
            lambda: self._client.post(self.URL, headers=self._headers, json=body),
            retries=self.retries, base=self.backoff, sleep=self._sleep)

    def complete(self, model: str, messages: Messages) -> str:
        check_model(model)  # cheap models only, enforced here
        self.spend.check()
        body: dict = {"model": model, "messages": messages,  # type: ignore[type-arg]
                      "reasoning": {"enabled": False}}  # short outputs; no hidden thinking tokens
        if model in MODEL_TEMPERATURE:
            body["temperature"] = MODEL_TEMPERATURE[model]
        if self.session_id:
            body["session_id"] = self.session_id
        try:
            r = self._post(body)
            if r.status_code == 400:  # a model that insists on reasoning: retry with defaults
                body.pop("reasoning")
                r = self._post(body)
            r.raise_for_status()
            j = r.json()
        except (httpx.HTTPError, ValueError) as e:
            raise ProviderError(f"{model}: {e}") from e
        self.spend.add(j.get("usage"))  # usage is returned on every response
        if (err := _chunk_error(j)) is not None:
            raise ProviderError(f"{model}: {err}")
        return j["choices"][0]["message"]["content"] or ""

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        check_model(model)
        self.spend.check()
        body = {"model": model, "messages": messages, "stream": True}
        if model in MODEL_TEMPERATURE:
            body["temperature"] = MODEL_TEMPERATURE[model]
        if self.session_id:
            body["session_id"] = self.session_id
        resp = None
        try:
            for attempt in range(self.retries + 1):
                req = self._client.build_request("POST", self.URL, headers=self._headers, json=body)
                try:
                    resp = self._client.send(req, stream=True)
                except httpx.TransportError:
                    if attempt == self.retries:
                        raise
                    self._sleep(backoff_delay(attempt, self.backoff))
                    continue
                if resp.status_code in RETRY_STATUS and attempt < self.retries:
                    delay = backoff_delay(attempt, self.backoff, resp.headers.get("retry-after"))
                    resp.close()
                    self._sleep(delay)
                    continue
                break
            assert resp is not None
            resp.raise_for_status()
            usage = None
            for line in resp.iter_lines():
                if not line.startswith("data:"):  # also skips ": OPENROUTER PROCESSING" comments
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    j = json.loads(data)
                except json.JSONDecodeError:
                    continue
                if (err := _chunk_error(j)) is not None:  # mid-stream error under HTTP 200
                    raise ProviderError(f"{model}: {err}")
                if j.get("usage"):  # the final chunk carries usage
                    usage = j["usage"]
                choices = j.get("choices") or []
                delta = (choices[0].get("delta") or {}).get("content") if choices else None
                if delta:
                    yield delta
            self.spend.add(usage)
        except httpx.HTTPError as e:
            raise ProviderError(f"{model}: {e}") from e
        finally:
            if resp is not None:
                resp.close()


@dataclass
class FakeProvider:
    """Scripted provider for tests/demo.

    `script` maps a model name to the queue of responses it will return in order.
    Every request is recorded in `calls` so tests can inspect exact contexts.
    """

    script: dict[str, list[str]] = field(default_factory=dict)
    chunk_size: int = 4
    calls: list[tuple[str, Messages]] = field(default_factory=list)
    # False (default): the engine calls the provider one call at a time, so a shared script queue
    # is consumed in a fixed order. Set True only for providers that are safe under threads.
    parallel_ok: bool = False
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def _next(self, model: str, messages: Messages) -> str:
        """A script entry may be an Exception instance: it is raised instead of returned."""
        with self._lock:
            self.calls.append((model, messages))
            queue = self.script.get(model)
            if not queue:
                raise RuntimeError(f"FakeProvider: script for {model!r} is exhausted")
            item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def complete(self, model: str, messages: Messages) -> str:
        return self._next(model, messages)

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        text = self._next(model, messages)
        for i in range(0, len(text), self.chunk_size):
            yield text[i : i + self.chunk_size]
