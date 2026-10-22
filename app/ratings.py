"""The player's ratings of world lines (👍 / 👎), kept app-side next to the campaign.

`ratings.jsonl` in the campaign folder: one JSON record per rated line (rating a line again
replaces its record). It is not an engine event: it never touches the world, the event log or the
database. The records carry only the masked label and an opaque speaker token, never a real id.
`app/ratings_report.py` reads these files.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

KINDS = ("narr", "npc", "npc_act")
ROLE_OF = {"narr": "narrator", "npc": "npc", "npc_act": "gesture"}
NOTE_MAX = 2000


class RatingBook:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self._lock = threading.Lock()
        self._mem: list[dict[str, Any]] = []  # a campaign without a folder keeps them in memory

    def _read(self) -> list[dict[str, Any]]:
        if self.path is None:
            return list(self._mem)
        out: list[dict[str, Any]] = []
        try:
            for line in self.path.read_text(encoding="utf-8").splitlines():
                try:
                    rec = json.loads(line)
                except ValueError:
                    continue
                if isinstance(rec, dict):
                    out.append(rec)
        except OSError:
            pass
        return out

    def all(self) -> list[dict[str, Any]]:
        with self._lock:
            return self._read()

    def marks(self) -> dict[str, str]:
        """event id (as text) -> "up" | "down"."""
        return {str(r["event"]): r["rating"] for r in self.all() if "event" in r}

    def put(self, rec: dict[str, Any]) -> None:
        """Store the record; an earlier one for the same line is replaced."""
        with self._lock:
            recs = [r for r in self._read() if r.get("event") != rec["event"]] + [rec]
            if self.path is None:
                self._mem = recs
                return
            tmp = self.path.with_suffix(".jsonl.tmp")
            tmp.write_text("".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs),
                           encoding="utf-8")
            os.replace(tmp, self.path)
