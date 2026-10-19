"""Model and spending policy (docs/decisions.md): paid API calls use cheap models only.

Enforced in code, not by convention: the OpenRouter client and the Jev client refuse any model
that is not on the allowlist. Extra cheap models can be added with HARNESS_EXTRA_ALLOWED
(comma-separated) — never Sonnet-, Opus- or GPT-5.x-full-class models.
"""
from __future__ import annotations

import os

ALLOWED_MODELS = frozenset({
    "typesafe/jev-1.13",
    "typesafe/jev-1.14",
    "anthropic/claude-haiku-5.5",
    "google/gemini-3.1-flash-lite",
    "deepseek/deepseek-v4-flash",
    "qwen/qwen3.5-9b",
})
FORBIDDEN_MARKERS = ("sonnet", "opus", "gpt-5", "gpt-4", "gemini-3.1-pro", "fable")

DEFAULT_EXTRACTOR = "anthropic/claude-haiku-5.5"
DEFAULT_NARRATOR = "deepseek/deepseek-v4-flash"
DEFAULT_NPC = "deepseek/deepseek-v4-flash"
DEFAULT_JUDGE_LLM = "anthropic/claude-haiku-5.5"  # escalation target (E2: best cheap accuracy)
DEFAULT_JEV = "typesafe/jev-1.14"


class ModelNotAllowed(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


def allowed_models() -> frozenset[str]:
    extra = {m.strip() for m in os.environ.get("HARNESS_EXTRA_ALLOWED", "").split(",") if m.strip()}
    bad = [m for m in extra if any(x in m.lower() for x in FORBIDDEN_MARKERS)]
    if bad:
        raise ModelNotAllowed(f"never allowed over the API: {bad}")
    return ALLOWED_MODELS | extra


def check_model(model: str) -> None:
    if model not in allowed_models():
        raise ModelNotAllowed(
            f"{model!r} is not on the cheap-model allowlist (see harness/policy.py)")


class Spend:
    """Running total of what the API reported (`usage.cost`), with a hard cap."""

    def __init__(self, cap: float | None = None) -> None:
        self.total, self.cap, self.calls = 0.0, cap, 0

    def check(self) -> None:
        if self.cap is not None and self.total >= self.cap:
            raise BudgetExceeded(f"spent ${self.total:.4f} >= cap ${self.cap:.2f}")

    def add(self, usage: dict | None) -> None:  # type: ignore[type-arg]
        self.calls += 1
        self.total += float((usage or {}).get("cost") or 0)
