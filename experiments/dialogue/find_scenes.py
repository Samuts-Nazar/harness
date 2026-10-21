"""Rank scenes of the local book file by distinct speakers and dialogue density (task LD-8).

Prints LINE RANGES, COUNTS and name stems only, never text. The book path is the local, uncommitted
`data/witcher_books.txt` (override with argv[1]).

Approximations (the corpus does not name speakers):
- A "name" is a word stem (first 5 letters) that is capitalised in >= 90% of its mid-sentence
  occurrences and occurs >= 20 times capitalised. Distinct speakers of a window = names that
  occur >= 2 times in it (people mentioned in passing are counted too, so it is an upper bound).
- Windows: 60 consecutive non-empty paragraphs, step 20. Density = share of dash paragraphs.
  Windows need >= 25 dialogue lines. Score = speakers * density; the top windows that do not
  overlap are listed. Line ranges are the 1-based file lines of the window.

    python -m experiments.dialogue.find_scenes [book] [--top 10]
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

BOOK = Path("/home/cock/projects/harness/data/witcher_books.txt")
WIN, STEP, MIN_DIALOGUE = 60, 20, 25
TITLES = [(19, "Відьмак"), (807, "Дещиця істини"), (1537, "Менше зло"), (2599, "Питання ціни"),
          (3529, "Край світу"), (4729, "Останнє бажання")]  # first book, by start line
BOOK1_END = 6300  # the commentary after it has no dialogue
_WORD = re.compile(r"[А-ЯҐЄІЇа-яґєії'’]{3,}")
_DASH = re.compile(r"^\s*[—–]")


def story_of(line: int) -> str:
    name = "later volumes"
    if line < BOOK1_END:
        name = "frame"
        for start, title in TITLES:
            if line >= start:
                name = title
    return name


def name_stems(paras: list[tuple[int, str]]) -> set[str]:
    cap: Counter[str] = Counter()
    low: Counter[str] = Counter()
    for _, p in paras:
        toks = list(_WORD.finditer(p))
        for m in toks:
            w = m.group()
            stem = w[:5].lower()
            before = p[:m.start()].rstrip()
            sentence_start = not before or before[-1] in ".!?…—–«\"(:"
            if w[0].isupper():
                if not sentence_start:
                    cap[stem] += 1
            else:
                low[stem] += 1
    return {s for s, n in cap.items() if n >= 20 and n / (n + low[s]) >= 0.9}


def main(argv: list[str]) -> int:
    args = [a for a in argv if not a.startswith("--")]
    top = int(argv[argv.index("--top") + 1]) if "--top" in argv else 10
    args = [a for a in args if a != str(top)]
    path = Path(args[0]) if args else BOOK
    paras = [(i + 1, t.strip()) for i, t in enumerate(path.read_text(encoding="utf-8").splitlines())
             if t.strip()]
    stems = name_stems(paras)
    rows = []
    for s in range(0, max(len(paras) - WIN, 1), STEP):
        w = paras[s:s + WIN]
        dlg = sum(1 for _, p in w if _DASH.match(p))
        if dlg < MIN_DIALOGUE:
            continue
        seen: Counter[str] = Counter()
        for _, p in w:
            for m in _WORD.finditer(p):
                if m.group()[0].isupper() and m.group()[:5].lower() in stems:
                    seen[m.group()[:5].lower()] += 1
        speakers = sum(1 for n in seen.values() if n >= 2)
        rows.append((speakers * dlg / WIN, speakers, dlg / WIN, dlg, w[0][0], w[-1][0],
                     ", ".join(k for k, _ in seen.most_common(4))))
    rows.sort(reverse=True)
    picked: list[tuple] = []
    for r in rows:
        if all(r[5] < q[4] or r[4] > q[5] for q in picked):
            picked.append(r)
        if len(picked) == top:
            break
    print(f"name stems: {len(stems)}; windows ranked: {len(rows)}")
    print("rank  lines          story            speakers  density  dialogue_lines  top name stems")
    for i, (score, sp, dens, dlg, a, b, who) in enumerate(picked, 1):
        print(f"{i:>4}  {a:>6}-{b:<6}  {story_of(a):<15}  {sp:>8}  {dens:>7.2f}  {dlg:>6}  {who}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
