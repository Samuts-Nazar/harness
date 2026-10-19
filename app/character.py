"""The player character's looks, derived once from the local character file (task 14).

The inn scene used to seed only a sword and a scar, so nobody reacted to the character's eyes or
claws. One cheap call reads the file (`data/Ragnar.md`, local, never committed) and returns what a
stranger sees at first sight (observable) and what is true but not visible (hidden), plus a short
phrase to call the person by until their name is known. The result is cached beside the campaigns
(`traits-<hash>.json`, derived facts only, git-ignored with the rest of `campaigns/`) so a new
campaign does not pay for the call again.

Nothing here quotes the file: the model is asked for short noun phrases, and only those are kept.
"""
from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from harness.models import APPEARANCE, CLOTHING, EQUIPMENT, INJURY, INVENTORY, INTERNAL
from harness.providers import Provider

SYSTEM = "You read a character sheet and describe how the character looks to others."
CATEGORIES = (APPEARANCE, CLOTHING, EQUIPMENT, INVENTORY, INJURY, INTERNAL)
MAX_FILE = 120_000  # characters sent (the whole of a long chronicle fits a cheap long-context model)
MAX_OBSERVABLE, MAX_HIDDEN, MAX_ITEM = 8, 6, 80
VERSION = "1"

PROMPT = (
    "From the character file below, list how the character is seen and what is true of them. Use "
    "only what the file states (as of the latest age it describes); invent nothing.\n"
    "- \"observable\": what a stranger sees at first sight in a tavern: eyes, skin, hair, build, "
    "marks on the face or hands, claws, clothing, weapons and gear carried openly.\n"
    "- \"hidden\": true of the body or belongings but not visible at first sight (scars under "
    "clothes, hidden items, mutations that show only in some conditions).\n"
    "- \"label\": a phrase of at most 7 words, in Ukrainian, that describes this person to someone "
    "who does not know their name (no name in it, only what is visible).\n"
    "Answer with JSON only:\n"
    '{"label": str, "observable": [{"category": "appearance"|"clothing"|"equipment"|"inventory"|'
    '"injury", "item": str}], "hidden": [{"category": "appearance"|"clothing"|"equipment"|'
    '"inventory"|"injury"|"internal", "item": str}]}\n'
    f"Items are short English noun phrases (at most 8 words), e.g. \"golden eyes\", \"steel sword "
    f"on the belt\"; names of people and places stay in Ukrainian. At most {MAX_OBSERVABLE} "
    f"observable and {MAX_HIDDEN} hidden items. \"appearance\" is for body features (eyes, hair, "
    "skin, claws, build, marks).\n\nCharacter file:\n")


@dataclass
class Traits:
    label: str = ""
    observable: list[tuple[str, str]] = field(default_factory=list)  # (category, item)
    hidden: list[tuple[str, str]] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return {"label": self.label,
                "observable": [{"category": c, "item": i} for c, i in self.observable],
                "hidden": [{"category": c, "item": i} for c, i in self.hidden]}


def parse_traits(raw: str) -> Traits:
    """The model's answer, validated: unknown categories and over-long items are dropped,
    duplicates removed, the lists capped. Raises ValueError if it is not a JSON object."""
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        text = m.group(1)
    a, b = text.find("{"), text.rfind("}")
    data = json.loads(text[a: b + 1] if a >= 0 and b >= 0 else text)
    if not isinstance(data, dict):
        raise ValueError("not an object")

    def clean(items: Any, cap: int) -> list[tuple[str, str]]:
        out: list[tuple[str, str]] = []
        for it in items if isinstance(items, list) else []:
            if not isinstance(it, dict):
                continue
            cat, item = it.get("category"), it.get("item")
            if cat not in CATEGORIES or not isinstance(item, str):
                continue
            item = item.strip()
            if item and len(item) <= MAX_ITEM and (cat, item) not in out:
                out.append((cat, item))
        return out[:cap]

    label = data.get("label")
    label = label.strip().rstrip(".") if isinstance(label, str) and len(label) <= 80 else ""
    hidden = clean(data.get("hidden"), MAX_HIDDEN)
    seen = set(clean(data.get("observable"), MAX_OBSERVABLE))
    return Traits(label, [x for x in clean(data.get("observable"), MAX_OBSERVABLE)],
                  [x for x in hidden if x not in seen])


def derive_traits(provider: Provider, model: str, path: Path, cache_dir: Path | None = None
                  ) -> Traits | None:
    """The character's traits from the file at `path`, or None (no file, or the call failed: the
    scene then keeps its plain seeds). The cache is keyed by the file's content."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    key = hashlib.sha1((VERSION + PROMPT + text).encode("utf-8")).hexdigest()[:16]
    cache = cache_dir / f"traits-{key}.json" if cache_dir else None
    try:
        if cache is not None and cache.exists():
            return parse_traits(cache.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    try:
        raw = provider.complete(model, [{"role": "system", "content": SYSTEM},
                                        {"role": "user", "content": PROMPT + text[:MAX_FILE]}])
        traits = parse_traits(raw)
    except Exception:  # noqa: BLE001 - a setup nicety: the scene keeps its plain seeds
        return None
    if cache is not None:
        try:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(traits.to_json(), ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
    return traits
