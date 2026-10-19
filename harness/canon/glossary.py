"""Canonical-name glossary: replace variant spellings (Latin transliterations, wrong spellings) by the
canonical Ukrainian form. Format: harness/canon/glossary_witcher_arc1.json (entries with `canonical`,
`variants`, `cases`). Applied in code to record text after ingestion and, in play, to rendered context.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

DEFAULT = Path(__file__).with_name("glossary_witcher_arc1.json")


class Glossary:
    def __init__(self, data: dict[str, Any]) -> None:
        self.entries = data["entries"]
        pairs: list[tuple[str, str]] = []
        for e in self.entries:
            if not e.get("proper", True):
                continue   # common nouns are not swapped inside English text; kept for Ukrainian-side checks
            gen = e.get("cases", [""])[0] if e.get("cases") else e["canonical"]
            for v in e.get("variants", []):
                if re.search(r"[A-Za-z]", v) or v != e["canonical"]:
                    pairs.append((v + "'s", gen))        # Latin possessive: Foltest's -> genitive
                    pairs.append((v, e["canonical"]))
        # longest variant first so "Geralt of Rivia" wins over "Geralt"
        self._pairs = sorted(set(pairs), key=lambda p: -len(p[0]))
        self._re = [(re.compile(r"(?<!\w)" + re.escape(v) + r"(?!\w)"), c) for v, c in self._pairs if v != c]

    @classmethod
    def load(cls, path: str | Path = DEFAULT) -> "Glossary":
        return cls(json.loads(Path(path).read_text(encoding="utf-8")))

    def apply(self, text: str) -> str:
        for rx, canon in self._re:
            text = rx.sub(canon, text)
        return text

    def canonical_names(self) -> list[str]:
        return [e["canonical"] for e in self.entries]
