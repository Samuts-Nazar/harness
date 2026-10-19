"""Retry with exponential backoff for HTTP calls (OpenRouter chat and the decision endpoint)."""
from __future__ import annotations

import random
import time
from typing import Callable

import httpx

RETRY_STATUS = frozenset({429, 500, 502, 503, 504, 520, 522, 524, 529})


def backoff_delay(attempt: int, base: float, retry_after: str | None = None,
                  cap: float = 30.0) -> float:
    """base * 2^attempt with a little jitter; a numeric Retry-After header wins if longer."""
    d = base * (2 ** attempt)
    d += random.uniform(0, d / 4)
    if retry_after:
        try:
            d = max(d, float(retry_after))
        except ValueError:
            pass
    return min(d, cap)


def send_with_retry(send: Callable[[], httpx.Response], *, retries: int = 4, base: float = 1.0,
                    sleep: Callable[[float], None] = time.sleep) -> httpx.Response:
    """Call `send` until the status is not 429/5xx and no transport error occurs; at most
    `retries` extra attempts. Returns the last response (the caller raises on an error status);
    re-raises the last transport error."""
    for attempt in range(retries + 1):
        try:
            r = send()
        except (httpx.TransportError, httpx.TimeoutException):
            if attempt == retries:
                raise
            sleep(backoff_delay(attempt, base))
            continue
        if r.status_code not in RETRY_STATUS or attempt == retries:
            return r
        sleep(backoff_delay(attempt, base, r.headers.get("retry-after")))
    raise AssertionError("unreachable")
