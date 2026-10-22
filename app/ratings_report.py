"""Per model and role: how the player rated the lines (👍 / 👎) and why.

    nix develop --command python -m app.ratings_report [campaigns_dir]

Reads every `ratings.jsonl` under the folder (default: the app's campaigns folder) and prints a
plain table: count up, count down, % down, then the notes. Speakers are shown only by their
masked label, never by a real character id.
"""
from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

from .campaigns import CAMPAIGNS


def load(root: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in sorted(Path(root).glob("*/ratings.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            if isinstance(rec, dict) and rec.get("rating") in ("up", "down"):
                rec.setdefault("campaign", path.parent.name)
                out.append(rec)
    return out


def report(recs: list[dict[str, Any]]) -> str:
    if not recs:
        return "Оцінок ще немає."
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for r in recs:
        groups[(str(r.get("model", "?")), str(r.get("role", "?")))].append(r)
    rows = [("model", "role", "up", "down", "% down")]
    for (model, role), rs in sorted(groups.items()):
        up = sum(r["rating"] == "up" for r in rs)
        down = len(rs) - up
        rows.append((model, role, str(up), str(down), f"{100 * down / len(rs):.0f}%"))
    widths = [max(len(r[i]) for r in rows) for i in range(5)]
    lines = ["  ".join(c.ljust(w) if i < 2 else c.rjust(w)
                       for i, (c, w) in enumerate(zip(r, widths))) for r in rows]
    notes = [r for r in recs if str(r.get("note", "")).strip()]
    if notes:
        lines += ["", "Notes:"]
        for (model, role), rs in sorted(groups.items()):
            for r in rs:
                if str(r.get("note", "")).strip():
                    who = f" [{r['label']}]" if r.get("label") else ""
                    lines.append(f"- {model} / {role} / {r['rating']}{who}: "
                                 f"{str(r['note']).strip()}")
    return "\n".join(lines)


def main(argv: list[str]) -> None:
    root = Path(argv[0]) if argv else CAMPAIGNS
    print(report(load(root)))


if __name__ == "__main__":
    main(sys.argv[1:])
