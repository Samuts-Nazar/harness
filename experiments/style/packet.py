"""Blind grading packets. Model and variant are hidden; items are shuffled with a fixed seed.

    python -m experiments.style.packet npc   -> raw/packet_npc_N.md (+ raw/key_npc.json)
"""
import json
import random
import sys
from pathlib import Path

from experiments.style import scenes as S
from harness.style import assistant_isms

RAW = Path(__file__).parent / "raw"
PER = 40


def main(kind: str) -> None:
    rows = [json.loads(x) for x in (RAW / f"{kind}.jsonl").read_text().splitlines()]
    rows = [r for r in rows if not r.get("error") and r["text"]]
    random.Random(15).shuffle(rows)
    key = {}
    for n in range(0, len(rows), PER):
        chunk = rows[n:n + PER]
        lines = []
        for j, r in enumerate(chunk):
            rid = f"{n + j + 1:03d}"
            key[rid] = {k: r[k] for k in ("id", "variant", "model", "sample")}
            if kind == "npc":
                npc = (S.INN[r["id"]][0] if r["id"] in S.INN else S.NPC_SET[r["id"]]["npc"])
                last = (S.INN[r["id"]][1][-1][1] if r["id"] in S.INN
                        else S.NPC_SET[r["id"]]["recent"][-1][1])
                head = f"situation {r['id']} / speaker {npc} / player's last line: {last}"
            else:
                head = f"scene {r['id']}: {S.NARR[r['id']][0]}"
            lines.append(f"### {rid}\n{head}\n\n{r['text']}\n")
        (RAW / f"packet_{kind}_{n // PER + 1}.md").write_text("\n".join(lines), encoding="utf-8")
    (RAW / f"key_{kind}.json").write_text(json.dumps(key, ensure_ascii=False))
    print(len(rows), "items")


if __name__ == "__main__":
    main(sys.argv[1])
