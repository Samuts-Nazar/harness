"""LLM provider interface, OpenRouter and local-server implementations and a scripted fake."""
from __future__ import annotations

import json
import os
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Iterator, Protocol

import httpx

from .decisions import full_role
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


def _sse_deltas(resp: httpx.Response, model: str,
                usage: list[dict]) -> Iterator[str]:  # type: ignore[type-arg]
    """The content deltas of an OpenAI-style SSE stream; a chunk's `usage` is appended to `usage`.
    A mid-stream error under HTTP 200 raises ProviderError."""
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
        if (err := _chunk_error(j)) is not None:
            raise ProviderError(f"{model}: {err}")
        if j.get("usage"):  # the final chunk carries usage
            usage.append(j["usage"])
        choices = j.get("choices") or []
        delta = (choices[0].get("delta") or {}).get("content") if choices else None
        if delta:
            yield delta


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
            usage: list[dict] = []  # type: ignore[type-arg]
            yield from _sse_deltas(resp, model, usage)
            self.spend.add(usage[-1] if usage else None)
        except httpx.HTTPError as e:
            raise ProviderError(f"{model}: {e}") from e
        finally:
            if resp is not None:
                resp.close()


LOCAL_URL = "http://127.0.0.1:8090/v1/chat/completions"
CREATIVE_ROLES = ("narrator", "npc", "assistant", "world: rumour")
CREATIVE_TEMPERATURE = 0.8  # as in the bake-off that chose the creative models (task 22)
LOCAL_TEMPERATURE = 0.3  # narrow calls (judge, extractor, reader, looks): steadier JSON


class LocalProvider:
    """A local OpenAI-compatible server (llama.cpp `llama-server`, docs/local-llm.md): the same
    interface as OpenRouterProvider, no key, no price check (`check_model` is never called: it
    costs nothing; `spend` stays at 0), no OpenRouter-only fields (`reasoning`, `session_id`).

    `slots`: the server's parallel slots (`--parallel 2`). At most that many requests are in
    flight at once, from any thread (the engine's pool, translations, suggestions); the others
    wait here instead of piling up in the server. With that bound the engine may run the
    independent calls of a turn in parallel (`parallel_ok`)."""

    parallel_ok = True

    def __init__(self, url: str = LOCAL_URL, *, timeout: float = 120.0, slots: int = 2,
                 spend: Spend | None = None, client: httpx.Client | None = None,
                 retries: int = 2, backoff: float = 1.0,
                 sleep: Callable[[float], None] = time.sleep) -> None:
        """`timeout`: seconds to wait for an answer (the read timeout). The engine does not
        abandon local calls (the local stack has no fast-lane timeout), so this is what bounds
        how long a call holds a slot. `retries`: only for a refused connection or a 5xx status;
        a timeout or a connection dropped mid-answer is never retried (it would hold the slot
        again for as long)."""
        self.url, self.timeout = url, timeout
        self._client = client or httpx.Client(timeout=httpx.Timeout(timeout, connect=5.0))
        self.spend = spend or Spend()
        self.retries, self.backoff, self._sleep = retries, backoff, sleep
        self._slots = threading.BoundedSemaphore(max(1, slots))

    def _body(self, model: str, messages: Messages, stream: bool = False) -> dict:  # type: ignore[type-arg]
        body: dict = {"model": model, "messages": messages}  # type: ignore[type-arg]
        role = full_role(messages)
        body["temperature"] = MODEL_TEMPERATURE.get(model, CREATIVE_TEMPERATURE if role.startswith(
            CREATIVE_ROLES) else LOCAL_TEMPERATURE)
        if stream:
            body["stream"] = True
        return body

    def _fail(self, model: str, e: Exception) -> ProviderError:
        if isinstance(e, (httpx.ConnectError, httpx.ConnectTimeout)):
            return ProviderError(
                f"{model}: the local model server at {self.url} is not answering ({e}). "
                "Start it with the command in docs/local-llm.md.")
        if isinstance(e, httpx.TimeoutException):
            return ProviderError(f"{model} ({self.url}): no answer in {self.timeout:g} s ({e})")
        if isinstance(e, httpx.TransportError):
            return ProviderError(f"{model} ({self.url}): the connection broke mid-answer ({e})")
        return ProviderError(f"{model} ({self.url}): {e}")

    def _send(self, req_fn: Callable[[], httpx.Response]) -> httpx.Response:
        """Retry a refused connection or a 5xx status with backoff; anything else is final."""
        for attempt in range(self.retries + 1):
            try:
                r = req_fn()
            except (httpx.ConnectError, httpx.ConnectTimeout):
                if attempt == self.retries:
                    raise
                self._sleep(backoff_delay(attempt, self.backoff))
                continue
            if r.status_code in RETRY_STATUS and attempt < self.retries:
                r.close()
                self._sleep(backoff_delay(attempt, self.backoff))
                continue
            return r
        raise AssertionError("unreachable")

    def complete(self, model: str, messages: Messages) -> str:
        body = self._body(model, messages)
        with self._slots:
            try:
                r = self._send(lambda: self._client.post(self.url, json=body))
                r.raise_for_status()
                j = r.json()
            except (httpx.HTTPError, ValueError) as e:
                raise self._fail(model, e) from e
        if (err := _chunk_error(j)) is not None:
            raise ProviderError(f"{model}: {err}")
        try:
            out = j["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError) as e:
            raise ProviderError(f"{model} ({self.url}): no choices in the answer {str(j)[:200]!r}") from e
        self.spend.add(None)  # counts the call; the cost is 0
        return out

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        body = self._body(model, messages, stream=True)
        with self._slots:
            resp = None
            try:
                resp = self._send(lambda: self._client.send(
                    self._client.build_request("POST", self.url, json=body), stream=True))
                resp.raise_for_status()
                yield from _sse_deltas(resp, model, [])
                self.spend.add(None)
            except httpx.HTTPError as e:
                raise self._fail(model, e) from e
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
