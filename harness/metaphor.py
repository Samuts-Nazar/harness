"""Metaphor-as-state guard (task 19, 18A: Hidden Door's "took his hand" added a severed hand to the
inventory). A state change that reads a figure of speech literally is dropped in code.

The cases it catches:
- a bare body part (hand, eye, heart, head, ...) added as an item, equipment or clothing, unless the
  segment says it was cut off, torn out or the like (a trophy, a severed limb);
- a bare body part as an injury (an injury is "a cut hand", not "hand");
- an abstract noun (courage, trust, attention, ...) added as an item.
It works on English and Ukrainian record text (records are English with Ukrainian names, but the
extractor may write either). It is deliberately narrow: it only fires on a bare noun, so "iron hand
(prosthesis)" or "bandaged hand" pass.
"""
from __future__ import annotations

import re

BODY = (
    "hand", "hands", "arm", "arms", "eye", "eyes", "heart", "head", "finger", "fingers", "foot",
    "feet", "leg", "legs", "ear", "ears", "tongue", "nose", "shoulder", "shoulders", "back",
    "face", "hair", "mind", "soul", "life", "breath", "voice", "lap", "knee", "knees", "neck",
    "рука", "руки", "руку", "рук", "око", "очі", "очей", "серце", "серця", "голова", "голову",
    "палець", "пальці", "пальця", "нога", "ноги", "ногу", "вухо", "вуха", "язик", "ніс",
    "плече", "плечі", "спина", "спину", "обличчя", "волосся", "розум", "душа", "душу", "життя",
    "подих", "голос", "коліно", "коліна", "шия", "шию",
)
ABSTRACT = (
    "courage", "trust", "attention", "hope", "patience", "silence", "respect", "fear", "luck",
    "time", "interest", "doubt", "mercy", "pity", "advice", "attitude", "sympathy",
    "відвага", "довіра", "увага", "надія", "терпіння", "мовчання", "повага", "страх", "щастя",
    "час", "інтерес", "сумнів", "милість", "жалість", "порада", "симпатія",
)
SEVERED = re.compile(
    r"sever|cut off|chop|hack(?:ed)? off|rip(?:ped)? off|tore off|torn off|amputat|"
    r"dismember|decapitat|beheaded|gouge|plucked out|torn out|ripped out|"
    r"відруба|відтя|відірва|відсік|відрізал|ампут|обезгол|вирва|видер|відсічен",
    re.IGNORECASE)
FILLER = {"his", "her", "its", "their", "the", "a", "an", "left", "right", "own", "of", "лівий",
          "правий", "ліва", "права", "ліве", "праве", "свою", "його", "її", "їх", "мою", "твою"}
CATS_ITEM = ("inventory", "equipment", "clothing")


def _bare(item: str, words: tuple[str, ...]) -> bool:
    toks = [t for t in re.findall(r"[\w'’]+", item.lower())
            if t not in FILLER and not re.search(r"['’]s$", t)]  # "the innkeeper's hand"
    return bool(toks) and all(t in words for t in toks) and any(t in words for t in toks)


def literal_reading(category: str, op: str, item: str, segment_text: str = "") -> str | None:
    """A reason (text) if this state change reads a metaphor literally, else None."""
    if op not in ("add", "reveal"):
        return None
    if category in CATS_ITEM or category == "appearance":
        if category == "appearance" and not _bare(item, ABSTRACT):
            return None  # "golden eyes" is an appearance; only a bare abstract noun is wrong there
        if _bare(item, BODY) and not SEVERED.search(segment_text + " " + item):
            return f"{item!r} is a body part, not an item (a figure of speech read literally)"
        if _bare(item, ABSTRACT):
            return f"{item!r} is an abstract noun, not an item"
    if category == "injury" and _bare(item, BODY):
        return f"{item!r} is a body part, not an injury"
    return None
