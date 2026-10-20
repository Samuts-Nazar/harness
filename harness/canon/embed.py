"""Embeddings for canon retrieval (optional second signal next to FTS).

Why: Ukrainian questions use other words than the English-written events and the Ukrainian gists
("змова" vs "скинути з трону"); a multilingual embedding bridges that. Vectors are stored in the
canon store (`canon_embedding`), the question is embedded at play time with one small call. Without
an embedder `Canon.recall` falls back to FTS only.

Provider: OpenRouter `/embeddings` (live catalog `GET /api/v1/embeddings/models`, see docs/tools.md).
"""
from __future__ import annotations

import array
import hashlib
import math
import os
from typing import Protocol, Sequence

import httpx

URL = "https://openrouter.ai/api/v1/embeddings"


class Embedder(Protocol):
    model: str

    def embed(self, texts: Sequence[str]) -> list[list[float]]: ...


class OpenRouterEmbedder:
    def __init__(self, model: str, api_key: str | None = None, *, timeout: float = 60.0,
                 client: httpx.Client | None = None) -> None:
        key = api_key or os.environ.get("OPENROUTER_API_KEY")
        if not key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")
        self.model = model
        self._h = {"Authorization": f"Bearer {key}"}
        self._c = client or httpx.Client(timeout=timeout)
        self.tokens = 0

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), 64):
            r = self._c.post(URL, headers=self._h, json={"model": self.model, "input": list(texts[i:i + 64])})
            r.raise_for_status()
            j = r.json()
            self.tokens += int((j.get("usage") or {}).get("prompt_tokens") or 0)
            out += [d["embedding"] for d in sorted(j["data"], key=lambda d: d["index"])]
        return out


class HashEmbedder:
    """Deterministic offline embedder for tests: character trigram hashing. Similar strings are close."""

    def __init__(self, dim: int = 256) -> None:
        self.model, self.dim = "hash-trigram", dim

    def embed(self, texts: Sequence[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * self.dim
            s = f"  {t.lower()}  "
            for i in range(len(s) - 2):
                h = int(hashlib.md5(s[i:i + 3].encode()).hexdigest()[:8], 16)
                v[h % self.dim] += 1.0
            out.append(v)
        return out


def pack(v: Sequence[float]) -> bytes:
    return array.array("f", v).tobytes()


def unpack(b: bytes) -> list[float]:
    a = array.array("f")
    a.frombytes(b)
    return list(a)


def cosine(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return sum(x * y for x, y in zip(a, b)) / (na * nb) if na and nb else 0.0
