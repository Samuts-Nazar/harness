"""Character tokens and inks: the client keys everything on an opaque, stable per-campaign token
(never the internal id or a name it may not know), and each token has an ink colour that the
player can change. Inks are stored per campaign in `inks.json` next to the database."""
from __future__ import annotations

import hashlib
import json
import re
import os
import secrets
import tempfile
import threading
from pathlib import Path
from typing import Mapping, Sequence

# Eight inks readable on the dark paper page: each at least 6.5:1 against the page (--paper,
# #231d18 in style.css) and at least 5:1 on a selected line (--paper3, #3a2e23); a test in
# app/tests/test_app_cast.py recomputes this from style.css.
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
    """A stable 8-character opaque token for a character in one campaign. `campaign_seed` is the
    campaign's random salt (see `InkBook.salt`), so a token cannot be guessed back to an id."""
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
    """token -> ink, persisted in a small json file, plus the campaign's random token salt in a
    file beside it (None path: in memory only). `set` only marks the book dirty; `flush` writes,
    so the streaming path never does file I/O under the game's lock. `lock` guards `inks` (a
    request thread sets an ink while a turn's thread assigns new ones); flushes are serialised
    and each writes its own temporary file."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.lock = threading.RLock()
        self._write = threading.Lock()
        self.inks: dict[str, str] = {}
        self.dirty = False
        self.salt = ""
        salt_file = path.with_name("token_salt.txt") if path is not None else None
        if path is not None and path.exists():
            try:
                self.inks = {str(k): str(v) for k, v in json.loads(path.read_text()).items()}
            except (OSError, ValueError):
                self.inks = {}
        if salt_file is not None and salt_file.exists():
            self.salt = salt_file.read_text().strip()
        if not self.salt:
            self.salt = secrets.token_hex(16)
            if salt_file is not None:
                salt_file.write_text(self.salt)

    def set(self, tok: str, ink: str) -> None:
        with self.lock:
            self.inks[tok] = ink
            self.dirty = True

    def get(self, tok: str) -> str | None:
        with self.lock:
            return self.inks.get(tok)

    def flush(self) -> None:
        if self.path is None:
            return
        with self._write:  # one writer at a time; a set during the write marks it dirty again
            with self.lock:
                if not self.dirty:
                    return
                self.dirty = False
                data = json.dumps(dict(self.inks), ensure_ascii=False)
            fd, tmp = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp",
                                       dir=self.path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(data)
                os.replace(tmp, self.path)
            except BaseException:
                with self.lock:
                    self.dirty = True
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
