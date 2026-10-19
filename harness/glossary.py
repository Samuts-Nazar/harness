"""Per-world glossary of canonical names, places and titles (task 12).

The player reads Ukrainian; records are English (task 10). Names, places and titles must stay in
their canonical Ukrainian form in both. The glossary is applied in code:
- when records are written (facts, state items, observable actions) and to what the models
  produced for the player (narration, NPC lines), so a Latin or misspelled variant never lands in
  the log;
- when a context is rendered, so the model always sees one form;
- as a short list inside the prompts ("use these forms"), limited to the names that occur there.

An entry has a canonical form, optional Latin-script forms (replaced whole), and wrong Cyrillic
spellings given as stems (a Ukrainian case ending after the stem is kept: "Хорста" becomes
"Горста"). `stem` is the declension stem of the canonical form when it differs from it
("Ельза" has stem "Ельз", "Любисток" has stem "Любист"). `cases` lists oblique forms seen in the
text: they are never "corrected", and the first one (the genitive) replaces a Latin possessive
("Foltest's" becomes "Фольтеста"; without `cases` it stays "Фольтест's"). `proper` is false for
common nouns ("відьмак", "орен"): they are kept for checks on Ukrainian text but never swapped
inside English text and never offered as names. Names are never *added* to text, only replaced,
so a correct text is left untouched.

One format and one loader serve both play and the canon ingestion (task 14 merged the two).
"""
from __future__ import annotations

import difflib
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

WORLDS = Path(__file__).resolve().parents[1] / "worlds"
# Ukrainian case endings that may follow a name stem.
ENDINGS = ("ами", "ові", "єві", "ів", "ам", "ах", "ом", "ем", "єм", "ою", "ею", "єю", "а", "у", "і",
           "ї", "е", "є", "ю", "я", "и", "")
_END_RE = "(" + "|".join(ENDINGS) + ")"
_WORD = r"\w"


@dataclass(frozen=True)
class Entry:
    canonical: str
    kind: str = "person"  # person | place | title | collective | creature | item | term
    stem: str = ""  # declension stem of `canonical` (default: the canonical form itself)
    latin: tuple[str, ...] = ()
    wrong: tuple[str, ...] = ()
    cases: tuple[str, ...] = ()  # correct oblique forms seen in the text; cases[0]: genitive
    proper: bool = True  # False: a common noun (checks only, never swapped, never a "name")
    id: str = ""

    @property
    def base(self) -> str:
        return self.stem or self.canonical


@dataclass
class Found:
    canonical: str
    form: str  # the variant as it appeared in the text
    replacement: str


@dataclass
class Glossary:
    entries: list[Entry] = field(default_factory=list)
    world: str = ""

    def __post_init__(self) -> None:
        self._compile()

    # -- loading ---------------------------------------------------------------------------
    @classmethod
    def from_dict(cls, data: dict) -> "Glossary":  # type: ignore[type-arg]
        entries = [Entry(e["canonical"], e.get("kind", "person"), e.get("stem", ""),
                         tuple(e.get("latin", ())), tuple(e.get("wrong", ())),
                         tuple(e.get("cases", ())), bool(e.get("proper", True)), e.get("id", ""))
                   for e in data.get("entries", [])]
        return cls(entries, data.get("world", ""))

    @classmethod
    def load(cls, path: Path | str) -> "Glossary":
        return cls.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))

    @classmethod
    def for_world(cls, world: str) -> "Glossary":
        return cls.load(WORLDS / world / "glossary.json")

    def add(self, entry: Entry) -> None:
        self.entries.append(entry)
        self._compile()

    # -- compiled patterns ------------------------------------------------------------------
    def _compile(self) -> None:
        live = [e for e in self.entries if e.proper]  # common nouns are never swapped
        latin: dict[str, Entry] = {}
        for e in live:
            for f in e.latin:
                latin[f.lower()] = e
        self._latin = latin
        forms = sorted(latin, key=len, reverse=True)
        self._latin_re = (re.compile(rf"(?<!{_WORD})(" + "|".join(re.escape(f) for f in forms)
                                     + rf")(['\u2019]s)?(?!{_WORD})", re.IGNORECASE)
                          if forms else None)
        self._correct = {x.lower() for e in self.entries for x in (e.canonical, *e.cases)}
        wrong: dict[str, Entry] = {}
        for e in live:
            for w in e.wrong:
                wrong[w.lower()] = e
        self._wrong = wrong
        stems = sorted(wrong, key=len, reverse=True)
        self._wrong_re = (re.compile(rf"(?<!{_WORD})(" + "|".join(re.escape(s) for s in stems)
                                     + rf"){_END_RE}(?!{_WORD})", re.IGNORECASE)
                          if stems else None)

    # -- applying ---------------------------------------------------------------------------
    def fix(self, text: str) -> tuple[str, list[Found]]:
        """The text with every known variant replaced, and what was replaced."""
        found: list[Found] = []

        def latin(m: re.Match[str]) -> str:
            e = self._latin[m.group(1).lower()]
            poss = m.group(2)
            if poss and e.cases:  # "Foltest's" -> the genitive
                new = e.cases[0]
            else:
                new = e.canonical + (poss or "")
            found.append(Found(e.canonical, m.group(0), new))
            return new

        def wrong(m: re.Match[str]) -> str:
            e = self._wrong[m.group(1).lower()]
            end = m.group(2)
            new = e.canonical if end == "" else e.base + end
            if new.lower() == m.group(0).lower() or m.group(0).lower() in self._correct:
                return m.group(0)  # already a correct form (e.g. a genitive that looks like a stem)
            found.append(Found(e.canonical, m.group(0), new))
            return new

        if self._latin_re is not None:
            text = self._latin_re.sub(latin, text)
        if self._wrong_re is not None:
            text = self._wrong_re.sub(wrong, text)
        return text, found

    def apply(self, text: str) -> str:
        return self.fix(text)[0]

    def variants_in(self, text: str) -> list[Found]:
        return self.fix(text)[1]

    # -- measuring --------------------------------------------------------------------------
    def canonical_count(self, text: str) -> int:
        """How many times a name appears in its canonical form (stem plus an ending)."""
        n = 0
        for e in self.entries:
            n += len(re.findall(rf"(?<!{_WORD})(?:{re.escape(e.base)}{_END_RE}|{re.escape(e.canonical)})"
                                rf"(?!{_WORD})", text))
        return n

    def near_misses(self, text: str, cutoff: float = 0.82) -> list[tuple[str, str]]:
        """Capitalised words that look like a distorted canonical single-word name but are not
        any correct form of it: (word, canonical). A heuristic for the name-consistency check."""
        singles = {e.base.lower(): e.canonical for e in self.entries
                   if e.proper and " " not in e.canonical and e.canonical[:1].isalpha()}
        out: list[tuple[str, str]] = []
        for w in re.findall(rf"(?<!{_WORD})[А-ЯҐЄІЇ]{_WORD}+", text):
            lw = w.lower()
            if lw in {c.lower() for c in singles.values()} or any(
                    re.fullmatch(rf"{re.escape(s)}{_END_RE}", lw) for s in singles):
                continue
            if any(lw in (e.canonical.lower().split() or [""]) for e in self.entries):
                continue
            m = difflib.get_close_matches(lw, list(singles), n=1, cutoff=cutoff)
            if not m:  # also compare the word minus a possible ending
                for end in ("а", "у", "ові", "ом", "і", "ю", "я"):
                    if lw.endswith(end) and (m := difflib.get_close_matches(
                            lw[: -len(end)], list(singles), n=1, cutoff=cutoff)):
                        break
            if m:
                out.append((w, singles[m[0]]))
        return out

    # -- prompts ----------------------------------------------------------------------------
    def relevant(self, text: str, extra: Iterable[str] = ()) -> list[Entry]:
        """Entries whose canonical form, stem or variants occur in `text` (or in `extra`)."""
        hay = text.lower() + "\n" + "\n".join(x.lower() for x in extra)
        out = []
        for e in self.entries:
            if not e.proper:
                continue
            keys = [e.base, e.canonical, *e.latin, *e.wrong]
            if any(k.lower() in hay for k in keys if k):
                out.append(e)
        return out

    def prompt_line(self, text: str, extra: Iterable[str] = ()) -> str:
        names = [e.canonical for e in self.relevant(text, extra)]
        if not names:
            return ""
        return ("Names, places and titles are written in Ukrainian, exactly in these forms "
                "(decline them as the sentence needs, never transliterate or respell): "
                + "; ".join(names) + ".")

    def canonical_names(self) -> list[str]:
        return [e.canonical for e in self.entries]


EMPTY = Glossary([])


def glossary_or_empty(g: Glossary | None) -> Glossary:
    return g if g is not None else EMPTY


def apply_all(g: Glossary | None, texts: Sequence[str]) -> list[str]:
    return [g.apply(t) for t in texts] if g else list(texts)
