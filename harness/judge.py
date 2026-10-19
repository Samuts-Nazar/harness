"""Typed judgments: yes/no, choice, score. No text generation.

Backends behind one interface (`Judge.ask`, which takes a *batch* of questions about one state):
- `JevJudge`    — TypeSafe Jev via OpenRouter (`POST /api/alpha/decisions`).
- `LLMJudge`    — a cheap allowed LLM answering the same questions as JSON.
- `EscalatingJudge` — Jev first; if its probability is below the threshold the same question goes
  to the LLM and the LLM's answer is used. Tags in `direct_tags` (relationship magnitude) skip Jev.
- `FakeJudge` / `StubJudge` — deterministic, for tests and the offline demo.
`LoggingJudge` records every judgment for the debug view.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import httpx

from .policy import Spend, check_model
from .providers import Provider

YES_NO, CHOICE, SCORE = "yes_no", "choice", "score"
ESCALATE_BELOW = 0.8
DIRECT_TAGS = frozenset({"relationship_magnitude"})  # Jev was weak here: LLM directly
JEV_URL = "https://openrouter.ai/api/alpha/decisions"


class JudgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Question:
    kind: str
    text: str
    options: Mapping[str, str] = field(default_factory=dict)  # choice: option -> description
    lo: float = 0.0  # score: value of the first legend entry
    legend: tuple[str, ...] = ()  # score: labels, evenly spaced from lo
    tag: str = ""  # what the question is for ("salience", "unknown_claim", ...)


@dataclass(frozen=True)
class Judgment:
    answer: bool | str | float
    probabilities: dict[str, float] = field(default_factory=dict)
    probability: float = 1.0  # probability of the answer itself
    escalated: bool = False
    backend: str = ""


def yes_no_q(text: str, tag: str = "") -> Question:
    return Question(YES_NO, text, tag=tag)


def choice_q(text: str, options: Mapping[str, str] | Sequence[str], tag: str = "") -> Question:
    opts = dict(options) if isinstance(options, Mapping) else {o: o for o in options}
    return Question(CHOICE, text, options=opts, tag=tag)


def score_q(text: str, lo: float = 0.0, hi: float = 1.0, legend: Sequence[str] = (),
            tag: str = "") -> Question:
    if not legend:
        n = int(hi - lo) + 1
        legend = tuple(str(int(lo) + i) for i in range(max(n, 2)))
    return Question(SCORE, text, lo=lo, legend=tuple(legend), tag=tag)


class Judge:
    """Interface. Subclasses implement `ask`; the single-question helpers are built on it."""

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        raise NotImplementedError

    def yes_no(self, question: str, context: str = "", *, tag: str = "") -> Judgment:
        return self.ask([context] if context else [], {"q": yes_no_q(question, tag)})["q"]

    def choice(self, question: str, options: Mapping[str, str] | Sequence[str], context: str = "",
               *, tag: str = "") -> Judgment:
        return self.ask([context] if context else [], {"q": choice_q(question, options, tag)})["q"]

    def score(self, question: str, context: str = "", lo: float = 0.0, hi: float = 1.0, *,
              tag: str = "") -> Judgment:
        return self.ask([context] if context else [], {"q": score_q(question, lo, hi, tag=tag)})["q"]


# -- Jev --------------------------------------------------------------------------------------
def _jev_question(q: Question) -> dict[str, Any]:
    if q.kind == YES_NO:
        return {"type": "noul", "instructions": q.text}
    if q.kind == CHOICE:
        return {"type": "choice", "criteria": dict(q.options), "instructions": q.text}
    return {"type": "score", "criteria": list(q.legend), "instructions": q.text}


def _jev_judgment(q: Question, a: Mapping[str, Any]) -> Judgment:
    try:
        if q.kind == YES_NO:
            p = float(a["noul"])
            return Judgment(p >= 0.5, {"yes": p, "no": 1 - p}, max(p, 1 - p), backend="jev")
        probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
        if q.kind == CHOICE:
            ch = a["choice"]
            return Judgment(ch, probs, probs.get(ch, 1.0), backend="jev")
        return Judgment(q.lo + float(a["score"]), probs, max(probs.values(), default=1.0),
                        backend="jev")
    except (KeyError, TypeError, ValueError) as e:
        raise JudgeError(f"unexpected Jev answer {a!r}: {e}") from e


class JevJudge(Judge):
    """Several questions about the same state go out as ONE call."""

    def __init__(self, api_key: str, model: str = "typesafe/jev-1.14", *,
                 client: httpx.Client | None = None, url: str = JEV_URL,
                 timeout: float = 60.0, spend: Spend | None = None) -> None:
        check_model(model)
        self.model, self.url = model, url
        self.spend = spend or Spend()
        self._headers = {"Authorization": f"Bearer {api_key}"}
        self._client = client or httpx.Client(timeout=timeout)
        self.calls = 0

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        body = {
            "model": self.model,
            "state": list(state) or ["(no additional context)"],
            "questions": {n: _jev_question(q) for n, q in questions.items()},
        }
        self.calls += 1
        self.spend.check()
        try:
            r = self._client.post(self.url, headers=self._headers, json=body)
            r.raise_for_status()
            j = r.json()
            self.spend.add(j.get("usage"))
            answers = j["answers"]
        except (httpx.HTTPError, KeyError, ValueError) as e:
            raise JudgeError(f"Jev call failed: {e}") from e
        try:
            return {n: _jev_judgment(q, answers[n]) for n, q in questions.items()}
        except KeyError as e:
            raise JudgeError(f"Jev answer missing {e}") from e


# -- LLM --------------------------------------------------------------------------------------
class LLMJudge(Judge):
    """A cheap allowed LLM answering typed questions as JSON (one call per batch)."""

    SYSTEM = "You are a module of a game engine that makes narrow judgments. Answer JSON only."

    def __init__(self, provider: Provider, model: str) -> None:
        self.provider, self.model = provider, model

    @staticmethod
    def _spec(q: Question) -> str:
        if q.kind == YES_NO:
            return f'{q.text}\n  answer: {{"answer": "yes"|"no", "p_yes": 0..1}}'
        if q.kind == CHOICE:
            opts = "; ".join(f"{k}: {v}" for k, v in q.options.items())
            return (f'{q.text}\n  options: {opts}\n  answer: {{"answer": <option>, '
                    '"probabilities": {<option>: 0..1}}')
        legend = "; ".join(f"{q.lo + i:g} = {lab}" for i, lab in enumerate(q.legend))
        return f'{q.text}\n  scale: {legend}\n  answer: {{"answer": <number from the scale>}}'

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        qs = "\n".join(f"[{n}] {self._spec(q)}" for n, q in questions.items())
        prompt = (
            "State:\n" + "\n".join(f"- {s}" for s in state) + "\n\nQuestions:\n" + qs +
            '\n\nReply with one JSON object: {"<question name>": <its answer object>, ...}'
        )
        raw = ""
        for attempt in range(2):  # one retry with a stricter instruction, like a strict matcher
            raw = self.provider.complete(
                self.model, [{"role": "system", "content": self.SYSTEM},
                             {"role": "user", "content": prompt + (
                                 "\nJSON object only: no prose, no code fences, every question "
                                 "name present." if attempt else "")}])
            m = re.search(r"\{.*\}", raw, re.DOTALL)
            try:
                data = json.loads(m.group(0)) if m else None
                data = {k.strip().strip("[]").strip(): v for k, v in data.items()}  # "[name]" too
                return {n: self._parse(q, data[n]) for n, q in questions.items()}
            except (TypeError, KeyError, ValueError, AttributeError):
                continue
        raise JudgeError(f"unparseable LLM judgment: {raw[:200]!r}")

    @staticmethod
    def _parse(q: Question, a: Mapping[str, Any]) -> Judgment:
        if q.kind == YES_NO:
            yes = str(a["answer"]).lower().startswith("y")
            p = a.get("p_yes")
            p = float(p) if isinstance(p, (int, float)) else (1.0 if yes else 0.0)
            return Judgment(yes, {"yes": p, "no": 1 - p}, p if yes else 1 - p, backend="llm")
        if q.kind == CHOICE:
            ch = a["answer"]
            if ch not in q.options:
                raise ValueError(f"{ch!r} is not an option")
            probs = {k: float(v) for k, v in (a.get("probabilities") or {}).items()}
            return Judgment(ch, probs, probs.get(ch, 1.0), backend="llm")
        v = float(a["answer"])
        return Judgment(min(max(v, q.lo), q.lo + len(q.legend) - 1), backend="llm")


# -- escalation -------------------------------------------------------------------------------
class EscalatingJudge(Judge):
    def __init__(self, primary: Judge, fallback: Judge, *, threshold: float = ESCALATE_BELOW,
                 direct_tags: frozenset[str] = DIRECT_TAGS) -> None:
        self.primary, self.fallback = primary, fallback
        self.threshold, self.direct_tags = threshold, direct_tags

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        out: dict[str, Judgment] = {}
        direct = {n: q for n, q in questions.items() if q.tag in self.direct_tags}
        first = {n: q for n, q in questions.items() if n not in direct}
        redo = dict(direct)
        jev_answers: dict[str, Judgment] = {}
        if first:
            try:
                jev_answers = self.primary.ask(state, first)
            except JudgeError:
                redo.update(first)  # primary down: everything goes to the LLM
            for n, j in jev_answers.items():
                if j.probability < self.threshold:
                    redo[n] = first[n]
                else:
                    out[n] = j
        if redo:
            cause = ""
            try:
                answers = self.fallback.ask(state, redo)
            except JudgeError as e:
                answers, cause = {}, f" (LLM: {e})"
            for n, j in answers.items():
                out[n] = Judgment(j.answer, j.probabilities, j.probability, True, j.backend)
            for n in redo:
                if n not in out:  # LLM failed too: keep Jev's low-confidence answer if any
                    if n not in jev_answers:
                        raise JudgeError(f"no backend could answer {n!r}{cause}")
                    out[n] = jev_answers[n]
        return out


# -- log --------------------------------------------------------------------------------------
class JudgmentLog:
    """Every judgment: question, answer, probability, escalated or not. For the debug view."""

    def __init__(self, path: Path | None = None) -> None:
        self.entries: list[dict[str, Any]] = []
        self.path = path

    def record(self, tag: str, question: str, j: Judgment) -> None:
        e = {"tag": tag, "question": question, "answer": j.answer,
             "probability": round(j.probability, 4), "escalated": j.escalated,
             "backend": j.backend}
        self.entries.append(e)
        if self.path is not None:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a") as f:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")


class LoggingJudge(Judge):
    def __init__(self, inner: Judge, log: JudgmentLog) -> None:
        self.inner, self.log = inner, log

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        out = self.inner.ask(state, questions)
        for n, j in out.items():
            self.log.record(questions[n].tag or n, questions[n].text, j)
        return out


# -- fakes ------------------------------------------------------------------------------------
Rule = Callable[[Question, Sequence[str]], Any]


class FakeJudge(Judge):
    """Deterministic. `rules` maps a tag to a fixed answer or a callable(question, state).
    Unlisted tags: no / first option / lowest score. Every ask is recorded in `asked`."""

    def __init__(self, rules: Mapping[str, Any] | None = None, *, yes: bool = False) -> None:
        self.rules = dict(rules or {})
        self.yes = yes
        self.asked: list[tuple[Sequence[str], dict[str, Question]]] = []

    def ask(self, state: Sequence[str], questions: Mapping[str, Question]) -> dict[str, Judgment]:
        self.asked.append((list(state), dict(questions)))
        out: dict[str, Judgment] = {}
        for n, q in questions.items():
            rule = self.rules.get(q.tag)
            if callable(rule):
                rule = rule(q, state)
            if isinstance(rule, list):  # scripted sequence: one answer per question, last repeats
                rule = rule.pop(0) if len(rule) > 1 else rule[0]
            out[n] = self._make(q, rule)
        return out

    def _make(self, q: Question, a: Any) -> Judgment:
        if q.kind == YES_NO:
            yes = self.yes if a is None else bool(a)
            return Judgment(yes, {"yes": float(yes), "no": float(not yes)}, 1.0, backend="fake")
        if q.kind == CHOICE:
            opts = list(q.options)
            ans = opts[0] if a is None else a
            return Judgment(ans, {o: float(o == ans) for o in opts}, 1.0, backend="fake")
        hi = q.lo + len(q.legend) - 1
        return Judgment((q.lo + hi) / 2 if a is None else float(a), backend="fake")


def default_fake_judge() -> FakeJudge:
    """Offline default: no leaks, no speech, not salient, neutral attitudes."""
    return FakeJudge({"attitude_direction": "neutral", "relationship_magnitude": 0})


class StubJudge(FakeJudge):
    """Old name: answers yes (or no) to everything, first option, midpoint."""

    def __init__(self, yes: bool = True) -> None:
        super().__init__(yes=yes)
