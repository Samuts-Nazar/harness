"""Split an arc of the book into paragraphs (one file line each), passages and extraction windows."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Para:
    line: int           # 1-based line number in the source file
    text: str
    char_from: int      # offset inside the arc text
    chapter: str


@dataclass(frozen=True)
class Passage:
    ord: int
    chapter: str
    paras: tuple[Para, ...]

    @property
    def text(self) -> str:
        return "\n".join(p.text for p in self.paras)

    @property
    def line_from(self) -> int:
        return self.paras[0].line

    @property
    def line_to(self) -> int:
        return self.paras[-1].line

    @property
    def char_from(self) -> int:
        return self.paras[0].char_from

    @property
    def char_to(self) -> int:
        p = self.paras[-1]
        return p.char_from + len(p.text)


def file_sha256(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_arc(path: str | Path, first: int, last: int,
             chapters: list[tuple[int, str]]) -> list[Para]:
    """Non-empty lines first..last (1-based, inclusive). `chapters` = [(first line, title)]."""
    lines = Path(path).read_text(encoding="utf-8").split("\n")
    out: list[Para] = []
    off = 0
    for n in range(first, last + 1):
        t = lines[n - 1].strip()
        if not t:
            continue
        chap = [title for start, title in chapters if start <= n][-1]
        out.append(Para(n, t, off, chap))
        off += len(t) + 1
    return out


def make_passages(paras: list[Para], target: int = 1400) -> list[Passage]:
    """Greedy: add paragraphs until the passage reaches `target` characters; never cross a chapter."""
    out: list[Passage] = []
    cur: list[Para] = []
    size = 0
    for p in paras:
        if cur and (p.chapter != cur[0].chapter or size >= target):
            out.append(Passage(len(out), cur[0].chapter, tuple(cur)))
            cur, size = [], 0
        cur.append(p)
        size += len(p.text)
    if cur:
        out.append(Passage(len(out), cur[0].chapter, tuple(cur)))
    return out


def make_windows(passages: list[Passage], target: int = 7000) -> list[list[Passage]]:
    """Groups of whole passages of about `target` characters; never cross a chapter."""
    out: list[list[Passage]] = []
    cur: list[Passage] = []
    size = 0
    for ps in passages:
        if cur and (ps.chapter != cur[0].chapter or size >= target):
            out.append(cur)
            cur, size = [], 0
        cur.append(ps)
        size += len(ps.text)
    if cur:
        out.append(cur)
    return out


def tagged(window: list[Passage]) -> str:
    """Window text with a [L<line>] tag in front of every paragraph."""
    return "\n".join(f"[L{p.line}] {p.text}" for ps in window for p in ps.paras)


_WS = re.compile(r"\s+")
_Q = str.maketrans({"’": "'", "ʼ": "'", "`": "'", "«": '"', "»": '"',
                    "“": '"', "”": '"', "—": "-", "–": "-"})


def norm(s: str) -> str:
    """Normalise for quote matching: case, whitespace, quote and dash variants."""
    return _WS.sub(" ", s.translate(_Q)).strip().lower().strip(" .,;:!?…-\"")
