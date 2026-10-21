"""World profile (living dialogue, task LD-1): the rhythm of a world's dialogue, measured as
numbers from a corpus, the yardstick later tasks compare engine output against.

Only numbers are kept (`worlds/<world>/profile.json`), never text from the corpus.

Corpus format: one paragraph per line, dialogue paragraphs start with a dash (— or –). Speech
and the author's beats are separated by `style.split_npc_output`.

Approximations:
- Speaker runs: consecutive dash paragraphs with no narration paragraph between them count as
  alternating speakers (a run of N dash paragraphs = N turns). The corpus does not name speakers.
- Narration between: share of adjacent dialogue-line pairs that have a non-dash paragraph
  between them; narration median is over those paragraphs only.
- Engine lines (`profile_of_lines`) have no narration paragraphs, so the three narration and run
  metrics are 0.0 there and should not be compared.

CLI: `python -m harness.profile build <world> <corpus_path>`.
"""
from __future__ import annotations

import json
import re
import statistics
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Sequence

from .style import WORLDS, split_npc_output

BINS = ("1", "2-3", "4-7", "8-15", "16-30", "31+")
MIN_LINES = 50
_DASH = re.compile(r"^\s*[—–]")


@dataclass
class DialogueLine:
    speech: str
    beats: list[str]
    words: int
    is_question: bool
    has_beat: bool
    paragraph: int


def _bin(n: int) -> str:
    for name, hi in (("1", 1), ("2-3", 3), ("4-7", 7), ("8-15", 15), ("16-30", 30)):
        if n <= hi:
            return name
    return "31+"


def _line(para: str, idx: int) -> DialogueLine | None:
    out = split_npc_output(para)
    words = len(out.speech.split())
    if not words:
        return None
    return DialogueLine(out.speech, list(out.beats), words, out.speech.rstrip().endswith("?"),
                        bool(out.beats), idx)


def _paragraphs(text: str) -> list[str]:
    return [p.strip() for p in text.splitlines() if p.strip()]


def dialogue_lines(text: str) -> list[DialogueLine]:
    lines = []
    for i, para in enumerate(_paragraphs(text)):
        if _DASH.match(para) and (dl := _line(para, i)):
            lines.append(dl)
    return lines


@dataclass
class WorldProfile:
    length_bins: dict[str, float] = field(default_factory=dict)
    median_words: float = 0.0
    question_share: float = 0.0
    no_beat_share: float = 0.0
    narration_between_share: float = 0.0
    narration_median_words: float = 0.0
    speaker_run_mean: float = 0.0
    n_lines: int = 0
    source: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "WorldProfile":
        return cls(**{k: d[k] for k in cls.__dataclass_fields__ if k in d})


def _core(lines: list[DialogueLine]) -> dict:
    n = len(lines)
    counts = {b: 0 for b in BINS}
    for l in lines:
        counts[_bin(l.words)] += 1
    return dict(
        length_bins={b: counts[b] / n for b in BINS},
        median_words=float(statistics.median(l.words for l in lines)),
        question_share=sum(l.is_question for l in lines) / n,
        no_beat_share=sum(not l.has_beat for l in lines) / n,
        n_lines=n)


def profile_from_text(text: str, source: str) -> WorldProfile:
    paras = _paragraphs(text)
    lines = dialogue_lines(text)
    if len(lines) < MIN_LINES:
        raise ValueError("no dialogue lines found in dash format")
    # narration paragraphs sitting between two dialogue lines, and speaker runs
    pos = {l.paragraph for l in lines}
    pairs = between = 0
    narr_words: list[int] = []
    runs: list[int] = []
    run = 0
    prev = None  # paragraph index of previous dialogue line
    for l in lines:
        if prev is not None:
            gap = [paras[j] for j in range(prev + 1, l.paragraph) if j not in pos]
            pairs += 1
            if gap:
                between += 1
                narr_words.extend(len(g.split()) for g in gap if not _DASH.match(g))
            run = run + 1 if l.paragraph == prev + 1 else (runs.append(run) or 1)
        else:
            run = 1
        prev = l.paragraph
    runs.append(run)
    return WorldProfile(
        **_core(lines),
        narration_between_share=between / pairs if pairs else 0.0,
        narration_median_words=float(statistics.median(narr_words)) if narr_words else 0.0,
        speaker_run_mean=sum(runs) / len(runs),
        source=source)


def profile_of_lines(lines: Sequence[str]) -> WorldProfile:
    dl = [x for i, t in enumerate(lines) if (x := _line(t, i))]
    if not dl:
        raise ValueError("no dialogue lines")
    return WorldProfile(**_core(dl), source="engine")


def distance(a: WorldProfile, b: WorldProfile) -> dict[str, float]:
    out = {k: abs(getattr(a, k) - getattr(b, k)) for k in (
        "median_words", "question_share", "no_beat_share", "narration_between_share",
        "narration_median_words", "speaker_run_mean")}
    out["length_bins_l1"] = sum(abs(a.length_bins.get(k, 0.0) - b.length_bins.get(k, 0.0))
                                for k in BINS)
    return out


def _path(world: str) -> Path:
    return WORLDS / world / "profile.json"


def load_profile(world: str) -> WorldProfile | None:
    try:
        return WorldProfile.from_dict(json.loads(_path(world).read_text(encoding="utf-8")))
    except (OSError, ValueError, TypeError):
        return None


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] != "build":
        print("usage: python -m harness.profile build <world> <corpus_path>", file=sys.stderr)
        return 2
    _, world, corpus = argv
    p = profile_from_text(Path(corpus).read_text(encoding="utf-8"), Path(corpus).name)
    out = _path(world)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(p.to_dict(), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(p.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
