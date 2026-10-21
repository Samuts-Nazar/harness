"""Build the A/B page data (task LD-8) from the saved live-check units: the same player input
answered by the classic engine and by the living engine, a whole short exchange per side
(narration if any, then the lines). Pairs: the first 5 turns of inn session A and of session B.
The two sides come from separate runs (same scripted input, histories may differ). Which side is
which is shuffled with a fixed seed and written to reports/dialogue/ab_key.json (not shown).

    python -m experiments.dialogue.make_ab
"""
from __future__ import annotations

import json
import random
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
LD = Path("/home/cock/projects/harness/campaigns/ld")
NAMES = {"horst": "Горст", "elza": "Ельза"}
PER_SESSION = 5


def side(turn: dict) -> str:
    parts = [turn["narration"].strip()] if turn["narration"].strip() else []
    if turn["exchange"]:  # living: lines in order; a gesture is an action; silence is nothing
        for kind, npc, text in turn["exchange"]:
            if kind == "line":
                parts.append(f"{NAMES.get(npc, npc)}: {text}")
            elif kind == "gesture":
                parts.append(text)
    else:
        parts += [f"{NAMES.get(s, s)}: {t}" for s, t in turn["utterances"]]
    return "\n\n".join(parts) or "(тиша)"


def main() -> None:
    rng = random.Random(20261021)
    pairs, key = [], []
    for sess in ("A", "B"):
        liv = json.loads((LD / f"session_{sess}_living.json").read_text(encoding="utf-8"))["turns"]
        cla = json.loads((LD / f"session_{sess}_classic.json").read_text(encoding="utf-8"))["turns"]
        for i in range(PER_SESSION):
            living_is_a = rng.random() < 0.5
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
    print(f"{len(pairs)} pairs; living on side A in {sum(k['A'] == 'living' for k in key)}")


if __name__ == "__main__":
    main()
