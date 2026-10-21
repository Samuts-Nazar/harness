"""Build the A/B page data (task LD-8, regenerated in Task 12) from the saved live-check units:
the same player input answered by the classic engine and by the living engine, a whole short
exchange per side (narration if any, then the lines). Pairs: the first 5 turns of inn session A
and of session B. The two sides come from separate runs (same scripted input, histories may
differ). Which side is which is shuffled with a fixed seed and written to
reports/dialogue/ab_key.json (not shown).

A pair is dropped when either side shows a detected glitch (`glitches`): letters of another
script, a line that opens with a speaker prefix or with the speaker's own name or description
(the page puts the name before the line), or another character's script line inside a line.

    python -m experiments.dialogue.make_ab
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from harness.style import foreign_runs

REPO = Path(__file__).resolve().parents[2]
LD = Path("/home/cock/projects/harness/campaigns/ld")
NAMES = {"horst": "Горст", "elza": "Ельза"}
PER_SESSION = 5
_PREFIX = re.compile(r"^\s*[\w'’ ]{2,40}:\s")


def _lines(turn: dict) -> list[tuple[str, str]]:
    if turn["exchange"]:  # living: lines in order; a gesture is an action; silence is nothing
        return [(npc, text) for kind, npc, text in turn["exchange"] if kind == "line"]
    return [(s, t) for s, t in turn["utterances"]]


def side(turn: dict) -> str:
    parts = [turn["narration"].strip()] if turn["narration"].strip() else []
    if turn["exchange"]:
        for kind, npc, text in turn["exchange"]:
            if kind == "line":
                parts.append(f"{NAMES.get(npc, npc)}: {text}")
            elif kind == "gesture":
                parts.append(text)
    else:
        parts += [f"{NAMES.get(s, s)}: {t}" for s, t in turn["utterances"]]
    return "\n\n".join(parts) or "(тиша)"


def glitches(turn: dict, looks: dict[str, str]) -> list[str]:
    """What would show as a glitch on the page; [] for a clean side."""
    out = [f"script: {r}" for r in foreign_runs(side(turn), "Ukrainian")]
    for npc, text in _lines(turn):
        t = text.strip().lstrip("—– ").lower()
        own = [NAMES.get(npc, npc).lower()[:4], looks.get(npc, "").lower()]
        if _PREFIX.match(text):
            out.append(f"prefix: {text[:40]}")
        elif any(o and t.startswith(o) for o in own) and not text.strip()[:1] in "—–":
            out.append(f"opens with own name/label: {text[:40]}")
        for other in NAMES.values():
            if re.search(rf"(?:^|\n)\s*{other}\s*:", text):
                out.append(f"script line for {other}")
    return out


def main() -> None:
    from app.campaigns import ELZA_LOOK, HORST_LOOK
    looks = {"horst": HORST_LOOK, "elza": ELZA_LOOK}
    rng = random.Random(20261021)
    pairs, key, dropped = [], [], []
    for sess in ("A", "B"):
        liv = json.loads((LD / f"session_{sess}_living.json").read_text(encoding="utf-8"))["turns"]
        cla = json.loads((LD / f"session_{sess}_classic.json").read_text(encoding="utf-8"))["turns"]
        for i in range(PER_SESSION):
            living_is_a = rng.random() < 0.5  # drawn for every pair, so the shuffle is stable
            bad = glitches(liv[i], looks) + glitches(cla[i], looks)
            if bad:
                dropped.append({"session": sess, "turn": i + 1, "why": bad})
                continue
            a, b = (side(liv[i]), side(cla[i])) if living_is_a else (side(cla[i]), side(liv[i]))
            pairs.append({"who": "", "player": liv[i]["player"], "a": a, "b": b})
            key.append({"pair": len(pairs), "session": sess, "turn": i + 1,
                        "A": "living" if living_is_a else "classic",
                        "B": "classic" if living_is_a else "living"})
    (REPO / "app/static/ab_data.js").write_text(
        "window.AB_PAIRS = " + json.dumps(pairs, ensure_ascii=False, indent=1) + ";\n", encoding="utf-8")
    out = REPO / "reports/dialogue/ab_key.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(key, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"{len(pairs)} pairs; living on side A in {sum(k['A'] == 'living' for k in key)}; "
          f"dropped {len(dropped)}")
    for d in dropped:
        print("dropped:", json.dumps(d, ensure_ascii=False))


if __name__ == "__main__":
    main()
