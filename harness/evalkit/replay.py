"""Record and replay of provider calls and typed judgments (task 19, 18A: about fifty lines).

A cassette is a JSONL file. Line 1 is a header (scenario, turns, model names, seed). Then one line
per call, keyed by a hash of what was asked:
- `c`  a text completion: key = hash(model, messages), `out` the reply (or `err` the failure);
- `j`  a typed judgment batch: key = hash(state, questions), `out` the answers.
Replay answers by key (a queue per key, so a retry gets the next recorded answer), thread-safe, so
the parallel turn replays too. A call with no recorded answer is a miss: `strict` raises
`ReplayMiss` (the prompt changed: this is the regression signal), otherwise the next unused
recording of the same kind and model is used and the miss is counted.

By default prompts are NOT stored, only hashes, so a cassette made with the local character file or
the book exemplars in the prompt holds no source text. `keep_prompts=True` stores them (for a
debugging session on your own machine; never commit that).
"""
from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import Any, Iterator, Mapping, Sequence

from ..judge import Judge, Judgment, Question
from ..providers import Messages, ProviderError


class ReplayMiss(RuntimeError):
    pass


def _h(*parts: Any) -> str:
    return hashlib.sha1(json.dumps(parts, ensure_ascii=False, sort_keys=True,
                                   default=str).encode()).hexdigest()


def key_complete(model: str, messages: Messages) -> str:
    return _h("c", model, messages)


def _qdict(q: Question) -> dict[str, Any]:
    return {"kind": q.kind, "text": q.text, "options": dict(q.options), "lo": q.lo,
            "legend": list(q.legend), "tag": q.tag}


def key_judge(state: Sequence[str], questions: Mapping[str, Question]) -> str:
    return _h("j", list(state), {n: _qdict(q) for n, q in questions.items()})


def _jdict(j: Judgment) -> dict[str, Any]:
    return {"answer": j.answer, "probabilities": j.probabilities, "probability": j.probability,
            "escalated": j.escalated, "backend": j.backend}


def _judgment(d: Mapping[str, Any]) -> Judgment:
    return Judgment(d["answer"], dict(d.get("probabilities") or {}), float(d.get("probability", 1.0)),
                    bool(d.get("escalated")), str(d.get("backend", "")))


class Cassette:
    """Append-only JSONL writer (thread-safe)."""

    def __init__(self, path: str | Path, header: Mapping[str, Any] | None = None) -> None:
        self.path = Path(path)
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if header is not None:
            self.path.write_text(json.dumps({"k": "h", **header}, ensure_ascii=False) + "\n",
                                 encoding="utf-8")

    def write(self, rec: Mapping[str, Any]) -> None:
        with self._lock, self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def load(path: str | Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    lines = [json.loads(x) for x in Path(path).read_text(encoding="utf-8").splitlines() if x.strip()]
    if not lines or lines[0].get("k") != "h":
        raise ValueError(f"{path}: not a cassette (no header)")
    return lines[0], lines[1:]


class RecordingProvider:
    def __init__(self, inner: Any, cassette: Cassette, *, keep_prompts: bool = False) -> None:
        self.inner, self.cassette, self.keep = inner, cassette, keep_prompts
        self.parallel_ok = bool(getattr(inner, "parallel_ok", False))
        self.spend = getattr(inner, "spend", None)

    def complete(self, model: str, messages: Messages) -> str:
        t0 = time.monotonic()
        rec: dict[str, Any] = {"k": "c", "model": model, "key": key_complete(model, messages)}
        if self.keep:
            rec["messages"] = messages
        try:
            out = self.inner.complete(model, messages)
        except Exception as e:  # noqa: BLE001 - recorded, then raised again
            rec.update(err=type(e).__name__ + ": " + str(e)[:200], s=round(time.monotonic() - t0, 3))
            self.cassette.write(rec)
            raise
        rec.update(out=out, s=round(time.monotonic() - t0, 3))
        self.cassette.write(rec)
        return out

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        yield self.complete(model, messages)


class ReplayProvider:
    parallel_ok = True

    def __init__(self, path: str | Path, *, strict: bool = True) -> None:
        self.header, recs = load(path)
        self.strict = strict
        self._lock = threading.Lock()
        self._by_key: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self._by_model: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self.misses: list[dict[str, Any]] = []
        self.calls = 0
        for r in recs:
            if r["k"] == "c":
                self._by_key[r["key"]].append(r)
                self._by_model[r["model"]].append(r)

    def complete(self, model: str, messages: Messages) -> str:
        key = key_complete(model, messages)
        with self._lock:
            self.calls += 1
            q = self._by_key.get(key)
            if q:
                r = q.popleft()
                self._by_model[model].remove(r)
            elif self.strict:
                self.misses.append({"model": model, "head": messages[-1]["content"][:160]})
                raise ReplayMiss(f"no recording for a {model} call (the prompt changed): "
                                 f"{messages[-1]['content'][:120]!r}")
            else:
                pool = self._by_model.get(model)
                if not pool:
                    self.misses.append({"model": model, "head": messages[-1]["content"][:160]})
                    raise ReplayMiss(f"no recording left for {model}")
                r = pool.popleft()
                self._by_key[r["key"]].remove(r)
                self.misses.append({"model": model, "head": messages[-1]["content"][:160],
                                    "used": "next in order"})
        if "err" in r:
            raise ProviderError(r["err"])
        return str(r["out"])

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        yield self.complete(model, messages)


class RecordingJudge(Judge):
    def __init__(self, inner: Judge, cassette: Cassette) -> None:
        self.inner, self.cassette = inner, cassette

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        got = self.inner.ask(state, questions)
        self.cassette.write({"k": "j", "key": key_judge(state, questions),
                             "tags": sorted({q.tag for q in questions.values()}),
                             "out": {n: _jdict(j) for n, j in got.items()}})
        return got


class ReplayJudge(Judge):
    def __init__(self, path: str | Path, *, strict: bool = True) -> None:
        _, recs = load(path)
        self.strict = strict
        self._lock = threading.Lock()
        self._by_key: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
        self._all: deque[dict[str, Any]] = deque()
        self.misses: list[dict[str, Any]] = []
        for r in recs:
            if r["k"] == "j":
                self._by_key[r["key"]].append(r)
                self._all.append(r)

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        key = key_judge(state, questions)
        tags = sorted({q.tag for q in questions.values()})
        with self._lock:
            q = self._by_key.get(key)
            if q:
                r = q.popleft()
                self._all.remove(r)
            elif self.strict:
                self.misses.append({"tags": tags})
                raise ReplayMiss(f"no recorded judgment for {tags} (the question changed)")
            else:
                same = next((x for x in self._all if x["tags"] == tags), None)
                if same is None:
                    self.misses.append({"tags": tags})
                    raise ReplayMiss(f"no recorded judgment left for {tags}")
                r = same
                self._all.remove(r)
                self._by_key[r["key"]].remove(r)
                self.misses.append({"tags": tags, "used": "next of the same tags"})
        out = {n: _judgment(d) for n, d in r["out"].items()}
        return {n: out.get(n) or next(iter(out.values())) for n in questions}
