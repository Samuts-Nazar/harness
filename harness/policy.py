"""Model and spending policy (docs/decisions.md): paid API calls use cheap models only.

The rule, enforced in code by the OpenRouter client and the decision client:
- a chat model is allowed when its live OpenRouter price is at most 0.60 USD input and 2.50 USD
  output per million tokens, it is not Anthropic, and it is not on the small deny list;
- decision models (served on the decision endpoint, absent from the chat catalog) are allowed
  by an explicit list.
Prices come from the OpenRouter catalog, fetched once and cached on disk with a date (refreshed
when older than a day). If the price cannot be verified, the model is refused (fail closed).
Tests install a fixture catalog with `set_catalog`; they never touch the network.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path
from typing import Any, Callable, Mapping

import httpx

MAX_INPUT_PER_M = 0.60
MAX_OUTPUT_PER_M = 2.50
CATALOG_URL = "https://openrouter.ai/api/v1/models"
CACHE_MAX_AGE = 24 * 3600

DECISION_MODELS = frozenset({
    "liquid/d1-ultra",
    "perplexity/pplx-decider-v1.2",
    "perplexity/pplx-decider-flash-v1.2",
    "typesafe/jev-1.13",
    "typesafe/jev-1.14",
})
# Routers and aliases: the model actually served (and its price) is chosen by someone else.
DENY = frozenset({
    "openrouter/auto", "openrouter/auto-beta", "openrouter/fusion", "openrouter/pareto-code",
    "openrouter/bodybuilder",
})
ANTHROPIC_MARKERS = ("anthropic/", "claude")

# Defaults per role (docs/tools.md, Models) and the fallback from another vendor.
DEFAULT_NARRATOR = "xiaomi/mimo-v2.6-flash"  # 2026-10-22: user chose speed (pro gave 10-23 s to first word); flash graded 3.6 vs pro 4.0
DEFAULT_NPC = "xiaomi/mimo-v2.6-flash"  # second in that grading; faster for many short lines
DEFAULT_EXTRACTOR = "deepseek/deepseek-v4.1-flash-1017"
DEFAULT_JUDGE_FIRST = "liquid/d1-ultra"
DEFAULT_JUDGE_LLM = "openai/gpt-6-luna"  # escalation target
DEFAULT_READER = "inclusionai/ling-3.1-flash"  # term expansion and reader (docs/tools.md, 2026-10-26)
FALLBACKS = {
    "narrator": "deepseek/deepseek-v4.1-flash-1017",
    "npc": "deepseek/deepseek-v4.1-flash-1017",
    "extractor": "qwen/qwen3.8-omni-flash",
    "judge_first": "perplexity/pplx-decider-v1.2",
    "judge_llm": "deepseek/deepseek-v4.1-flash-1017",
    "reader": "xiaomi/mimo-v2.6-flash",
}
# Sampling temperature per model, as used in the bake-off that chose it (task 22: 0.8). Models
# not listed get the provider's default.
MODEL_TEMPERATURE = {"xiaomi/mimo-v2.6-pro": 0.8, "xiaomi/mimo-v2.6-flash": 0.8}
DEFAULT_JEV = DEFAULT_JUDGE_FIRST  # old name: the first-pass decision model


class ModelNotAllowed(RuntimeError):
    pass


class BudgetExceeded(RuntimeError):
    pass


Prices = Mapping[str, tuple[float, float]]  # model -> (input, output) USD per million tokens


def parse_catalog(data: Mapping[str, Any]) -> dict[str, tuple[float, float]]:
    """Worst-case price per model: the base price or any surcharge tier, whichever is higher.
    Negative prices (variable, router-style) are kept as negative so they are refused."""
    out: dict[str, tuple[float, float]] = {}
    for m in data.get("data", []):
        pr = m.get("pricing") or {}
        try:
            tiers = [pr] + list(pr.get("overrides") or [])
            pin = max(float(t["prompt"]) for t in tiers if "prompt" in t)
            pout = max(float(t["completion"]) for t in tiers if "completion" in t)
        except (KeyError, TypeError, ValueError):
            continue
        low = min(float(pr.get("prompt", 0)), float(pr.get("completion", 0)))
        out[m["id"]] = (-1.0, -1.0) if low < 0 else (pin * 1e6, pout * 1e6)
    return out


def cache_path() -> Path:
    root = os.environ.get("HARNESS_CACHE_DIR")
    return Path(root) / "openrouter_models.json" if root else (
        Path(__file__).resolve().parents[1] / ".cache" / "openrouter_models.json")


def load_catalog(*, path: Path | None = None, fetch: Callable[[], Mapping[str, Any]] | None = None,
                 now: Callable[[], float] = time.time) -> dict[str, tuple[float, float]]:
    """Prices from the disk cache when it is younger than a day, else fetched and re-cached.
    A failed fetch falls back to an older cache; with no cache at all it raises."""
    path = path or cache_path()
    cached: dict[str, Any] | None = None
    try:
        cached = json.loads(path.read_text())
    except (OSError, ValueError):
        pass
    if cached and now() - float(cached.get("fetched_at", 0)) < CACHE_MAX_AGE:
        return parse_catalog(cached["catalog"])
    try:
        fresh = (fetch or _fetch_catalog)()
    except Exception as e:  # noqa: BLE001 - any failure means "use what we have"
        if cached:
            return parse_catalog(cached["catalog"])
        raise ModelNotAllowed(f"cannot verify model prices (catalog fetch failed: {e})") from e
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"fetched_at": now(),
                                    "date": time.strftime("%Y-%m-%d", time.gmtime(now())),
                                    "catalog": fresh}))
    except OSError:
        pass  # an unwritable cache only costs a refetch next time
    return parse_catalog(fresh)


def _fetch_catalog() -> Mapping[str, Any]:
    r = httpx.get(CATALOG_URL, timeout=30)
    r.raise_for_status()
    return r.json()  # type: ignore[no-any-return]


_lock = threading.Lock()
_prices: Prices | None = None


def set_catalog(table: Prices | Mapping[str, Any] | None) -> None:
    """Install a price table (tests) or, with None, forget it so it is loaded again.
    Accepts either {model: (in, out)} or a raw catalog JSON with a "data" list."""
    global _prices
    with _lock:
        if table is not None and "data" in table:
            table = parse_catalog(table)  # type: ignore[arg-type]
        _prices = table  # type: ignore[assignment]


def prices() -> Prices:
    global _prices
    with _lock:
        if _prices is None:
            _prices = load_catalog()
        return _prices


def deny_list() -> frozenset[str]:
    extra = {m.strip() for m in os.environ.get("HARNESS_DENY", "").split(",") if m.strip()}
    return DENY | extra


def check_model(model: str) -> None:
    """Raise ModelNotAllowed unless `model` may be called over the API."""
    if model in deny_list():
        raise ModelNotAllowed(f"{model!r} is on the deny list")
    if model in DECISION_MODELS:
        return
    if any(m in model.lower() for m in ANTHROPIC_MARKERS):
        raise ModelNotAllowed(f"{model!r}: no Anthropic models in the engine")
    got = prices().get(model)
    if got is None:
        raise ModelNotAllowed(f"{model!r} is not in the OpenRouter catalog (price unknown)")
    pin, pout = got
    if pin < 0 or pout < 0:
        raise ModelNotAllowed(f"{model!r} has variable pricing")
    if pin > MAX_INPUT_PER_M or pout > MAX_OUTPUT_PER_M:
        raise ModelNotAllowed(
            f"{model!r} costs ${pin:g}/${pout:g} per M tokens; limit "
            f"${MAX_INPUT_PER_M:g}/${MAX_OUTPUT_PER_M:g}")


def check_decision_model(model: str) -> None:
    """The decision endpoint serves only the explicit list of decision models."""
    check_model(model)
    if model not in DECISION_MODELS:
        raise ModelNotAllowed(f"{model!r} is not a decision model (see DECISION_MODELS)")


class Spend:
    """Running total of what the API reported (`usage.cost`), with a hard cap. Thread-safe."""

    def __init__(self, cap: float | None = None) -> None:
        self.total, self.cap, self.calls = 0.0, cap, 0
        # prompt-cache numbers reported by OpenRouter (usage.prompt_tokens_details)
        self.prompt_tokens = self.cached_tokens = self.cache_write_tokens = 0
        self._lock = threading.Lock()

    def check(self) -> None:
        if self.cap is not None and self.total >= self.cap:
            raise BudgetExceeded(f"spent ${self.total:.4f} >= cap ${self.cap:.2f}")

    def add(self, usage: dict | None) -> None:  # type: ignore[type-arg]
        with self._lock:
            self.calls += 1
            self.total += float((usage or {}).get("cost") or 0)
            u = usage or {}
            det = u.get("prompt_tokens_details") or {}
            self.prompt_tokens += int(u.get("prompt_tokens") or 0)
            self.cached_tokens += int(det.get("cached_tokens") or 0)
            self.cache_write_tokens += int(det.get("cache_write_tokens") or 0)

    def cache_hit_rate(self) -> float:
        """Share of prompt tokens that were read from the provider's cache."""
        with self._lock:
            return self.cached_tokens / self.prompt_tokens if self.prompt_tokens else 0.0
