"""LLM provider interface, OpenRouter implementation and a scripted fake."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Iterator, Protocol

import httpx

from .policy import Spend, check_model

Messages = list[dict[str, str]]


class Provider(Protocol):
    def complete(self, model: str, messages: Messages) -> str: ...
    def stream(self, model: str, messages: Messages) -> Iterator[str]: ...


class OpenRouterProvider:
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, api_key: str | None = None, timeout: float = 120.0,
                 spend: Spend | None = None) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self._headers = {"Authorization": f"Bearer {key}"}
        self._timeout = timeout
        self.spend = spend or Spend()

    def complete(self, model: str, messages: Messages) -> str:
        check_model(model)  # cheap models only, enforced here
        self.spend.check()
        body = {"model": model, "messages": messages, "usage": {"include": True},
                "reasoning": {"enabled": False}}  # short outputs; no hidden thinking tokens
        r = httpx.post(self.URL, headers=self._headers, json=body, timeout=self._timeout)
        if r.status_code == 400:  # a model that insists on reasoning: retry with defaults
            body.pop("reasoning")
            r = httpx.post(self.URL, headers=self._headers, json=body, timeout=self._timeout)
        r.raise_for_status()
        j = r.json()
        self.spend.add(j.get("usage"))
        return j["choices"][0]["message"]["content"] or ""

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        check_model(model)
        self.spend.check()
        with httpx.stream(
            "POST",
            self.URL,
            headers=self._headers,
            json={"model": model, "messages": messages, "stream": True},
            timeout=self._timeout,
        ) as r:
            r.raise_for_status()
            for line in r.iter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    return
                try:
                    delta = json.loads(data)["choices"][0]["delta"].get("content")
                except (json.JSONDecodeError, KeyError, IndexError):
                    continue
                if delta:
                    yield delta


@dataclass
class FakeProvider:
    """Scripted provider for tests/demo.

    `script` maps a model name to the queue of responses it will return in order.
    Every request is recorded in `calls` so tests can inspect exact contexts.
    """

    script: dict[str, list[str]] = field(default_factory=dict)
    chunk_size: int = 4
    calls: list[tuple[str, Messages]] = field(default_factory=list)

    def _next(self, model: str, messages: Messages) -> str:
        self.calls.append((model, messages))
        queue = self.script.get(model)
        if not queue:
            raise RuntimeError(f"FakeProvider: script for {model!r} is exhausted")
        return queue.pop(0)

    def complete(self, model: str, messages: Messages) -> str:
        return self._next(model, messages)

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        text = self._next(model, messages)
        for i in range(0, len(text), self.chunk_size):
            yield text[i : i + self.chunk_size]
