"""Check every form in worlds/witcher/glossary.json against the Ukrainian book text by counting.

    nix develop --command python experiments/glossary_check.py [path/to/witcher_books.txt]

For each entry, over the whole book and over the first story (file lines 7-694, the arc the canon
pilot ingests): how often the canonical form occurs (stem plus a case ending), how many of the
listed oblique cases occur, and how often the glossary would REPLACE something (what `fix` changes
in the book text itself, counted per wrong or Latin form). Rules the counts must satisfy:
- a canonical form that the books contain must occur (names we invented are listed as such);
- a wrong or Latin form must be rarer than the canonical form (a "wrong" spelling that is the
  majority spelling means the entry is backwards);
- every listed oblique case should occur (a case never seen is flagged, not removed: it comes from
  grammar, not from the books).
The book text is local and never committed; only counts are printed.
"""
import re
import sys
from collections import Counter
from pathlib import Path

from harness.glossary import ENDINGS, Glossary

END = "(?:" + "|".join(ENDINGS) + ")"
W = r"\w"
ARC = (7, 694)  # file lines of "Голос розуму-1" and "Відьмак" (canon pilot, T13-1)


def count(text: str, form: str, endings: bool) -> int:
    pat = rf"(?<!{W}){re.escape(form)}{END if endings else ''}(?!{W})"
    return len(re.findall(pat, text, re.IGNORECASE))


def replaced(g: Glossary, text: str) -> Counter[tuple[str, str]]:
    """What the glossary changes in `text`: (canonical, original form) -> times."""
    _, found = g.fix(text)
    return Counter((f.canonical, f.form) for f in found)


def main() -> None:
    path = Path(sys.argv[1] if len(sys.argv) > 1 else "data/witcher_books.txt")
    lines = path.read_text(encoding="utf-8").splitlines()
    book = "\n".join(lines)
    arc = "\n".join(lines[ARC[0] - 1: ARC[1]])
    g = Glossary.for_world("witcher")
    rep_book, rep_arc = replaced(g, book), replaced(g, arc)
    print(f"{len(g.entries)} entries; book {len(book):,} characters, arc {len(arc):,}")
    print(f"{'entry':24s} {'kind':6s} {'book':>5s} {'arc':>4s} {'cases':>7s}  replaced in book / arc")
    absent, backwards, cases_zero = [], [], []
    for e in g.entries:
        nb, na = count(book, e.base, True), count(arc, e.base, True)
        if e.base != e.canonical:
            nb, na = nb + count(book, e.canonical, False), na + count(arc, e.canonical, False)
        cs = {c: count(book, c, False) for c in e.cases}
        reps = {(c, f): n for (c, f), n in rep_book.items() if c == e.canonical}
        reps_arc = {(c, f): n for (c, f), n in rep_arc.items() if c == e.canonical}
        total, total_arc = sum(reps.values()), sum(reps_arc.values())
        if nb == 0:
            absent.append(e.canonical)
        if total and total > nb:
            backwards.append((e.canonical, nb, dict(reps)))
        for c, n in cs.items():
            if n == 0:
                cases_zero.append((e.canonical, c))
        shown = ", ".join(f"{f}={n}" for (_, f), n in sorted(reps.items(), key=lambda x: -x[1])[:4])
        print(f"{e.canonical:24s} {'name' if e.proper else 'common':6s} {nb:5d} {na:4d} "
              f"{sum(1 for n in cs.values() if n)}/{len(cs):<5d}  {total}/{total_arc}  {shown}")
    print("\nnot in the book:", ", ".join(absent) or "-")
    print("REPLACES MORE OFTEN THAN THE CANONICAL FORM OCCURS (other translators in the file? see the note in the glossary):",
          backwards or "-")
    print("cases never seen:", cases_zero or "-")


if __name__ == "__main__":
    main()
