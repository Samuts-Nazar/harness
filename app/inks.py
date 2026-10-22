"""Character tokens and inks: the client keys everything on an opaque, stable per-campaign token
(never the internal id or a name it may not know), and each token has an ink colour that the
player can change. Inks are stored per campaign in `inks.json` next to the database."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Mapping, Sequence

# Eight inks readable on the dark paper page (all at least about 7:1 against #15110e).
PALETTE: tuple[str, ...] = (
    "#e8a87c",  # amber
    "#8fb8e8",  # blue
    "#a8d49a",  # green
    "#e89ab8",  # rose
    "#c8a8f0",  # violet
    "#e8d27c",  # gold
    "#7cd4cc",  # teal
    "#e8887c",  # coral
)
INK_RE = re.compile(r"^#[0-9a-fA-F]{6}$")


def token_for(campaign_seed: str, character_id: str) -> str:
    """A stable 8-character opaque token for a character in one campaign."""
    h = hashlib.sha256(f"{campaign_seed}|{character_id}".encode()).hexdigest()
    return h[:8]


def assign_ink(present_tokens: Sequence[str], inks: Mapping[str, str],
               recency: Sequence[str]) -> str:
    """The ink for a token that has none: a colour no present token uses, else the colour of the
    colour whose latest user was active least recently (`recency`: oldest first, most recent last;
    a token missing from it counts as the least recent)."""
    coloured = [t for t in present_tokens if t in inks]
    used = {inks[t] for t in coloured}
    for c in PALETTE:
        if c not in used:
            return c
    rank = {t: i for i, t in enumerate(recency)}
    # a colour is as recent as its most recent user, so a shared colour is not picked again
    latest: dict[str, int] = {}
    for t in coloured:
        latest[inks[t]] = max(latest.get(inks[t], -1), rank.get(t, -1))
    return min(latest, key=lambda c: latest[c])


class InkBook:
    """token -> ink, persisted in a small json file (None path: in memory only)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.inks: dict[str, str] = {}
        if path is not None and path.exists():
            try:
                self.inks = {str(k): str(v) for k, v in json.loads(path.read_text()).items()}
            except (OSError, ValueError):
                self.inks = {}

    def set(self, tok: str, ink: str) -> None:
        self.inks[tok] = ink
        if self.path is not None:
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.inks, ensure_ascii=False))
            tmp.replace(self.path)
