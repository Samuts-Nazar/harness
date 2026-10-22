"""The player character is the player's: the world's prose never repeats the player's words and
never decides what the player character does (docs/decisions.md, "Player character").

Two deterministic helpers, used by the narrator path in `Engine._narrate` and by the resolution
paragraph:
- `strip_player_quotes`: quoted speech (guillemets, quotes, a dialogue dash) that repeats the
  player's latest utterance is removed. The UI already shows the player's line.
- `flag_player_acts`: sentences whose subject is the player character with a finite verb of
  deliberate action ("Ти кладеш...", "Ти стояв...", "<Name> бере..."). Perception and body
  sentences ("ти чуєш", "тебе нудить") are not flagged. The engine asks the judge one batched
  yes/no question per flagged sentence; a sentence the judge confirms is dropped.
"""
from __future__ import annotations

import re

from .narrator import DASH_SPEECH_RE, QUOTE_RE

_SENT_END = re.compile(r"(?<=[.!?…])(\s+)")
_WORD = re.compile(r"[\w'’ʼ-]+", re.UNICODE)
_BOUNDARY = re.compile(r"[.!?…]\s+|\n")
_TAG_AFTER = re.compile(r"^\s*,?\s*[—–]\s*[^.!?…\n]*[.!?…]?")

# "ти" + a finite verb: present 2nd person (-ш, -шся) or past tense (-в, -ла, -ло, -ли, -вся...)
_PRESENT = re.compile(r"\w+[аеєиіїюя]ш(?:ся|сь)?$", re.IGNORECASE)
_PAST = re.compile(r"\w+(?:в|ла|ло|ли)(?:ся|сь)?$", re.IGNORECASE)
_PERCEPTION = re.compile(
    r"^(?:ч[уі]|по?ч[уі]|бач|по?бач|побач|відчу|відчув|помі|нюх|чув|смак|здаєт|"
    r"усвідом|розум|знаєш|знав|пам[’'ʼ]ят|гляд|дивишся|помітив|завмира)", re.IGNORECASE)


def split_sentences(text: str) -> list[str]:
    """Sentences with their trailing whitespace, so that "".join(...) == text."""
    parts = _SENT_END.split(text)
    out: list[str] = []
    for i in range(0, len(parts), 2):
        out.append(parts[i] + (parts[i + 1] if i + 1 < len(parts) else ""))
    return [s for s in out if s]


def _tokens(text: str) -> list[str]:
    return [w.lower().replace("’", "'").replace("ʼ", "'") for w in _WORD.findall(text)]


def _repeats(span: str, player: set[str], player_seq: str) -> bool:
    toks = _tokens(span)
    if len(toks) < 4:
        return False
    if " ".join(toks) in player_seq:
        return True
    return sum(t in player for t in toks) / len(toks) >= 0.7


def strip_player_quotes(text: str, player_text: str) -> tuple[str, list[str]]:
    """Remove quoted speech that repeats `player_text` (normalised, or mostly the same words).
    A lead-in left bare ("Ти кажеш:") goes with it. Returns the text and the removed spans."""
    ptoks = _tokens(player_text)
    pset, pseq = set(ptoks), " ".join(ptoks)
    removed: list[str] = []
    changed = True
    while changed:
        changed = False
        spans = [(m.start(), m.end(), m.group()) for m in QUOTE_RE.finditer(text)]
        spans += [(m.start(), m.end(), m.group()) for m in DASH_SPEECH_RE.finditer(text)]
        for start, end, raw in sorted(spans):
            if not _repeats(raw, pset, pseq):
                continue
            tail = text[end:]
            tag = _TAG_AFTER.match(tail) if raw[0] != "—" and raw[0] != "–" else None
            end2 = end + (tag.end() if tag else 0)
            head = text[:start]
            cut = 0
            for b in _BOUNDARY.finditer(head):
                cut = b.end()
            lead = head[cut:]
            if lead.strip() and (lead.rstrip().endswith((":", ",")) or len(_tokens(lead)) <= 3):
                start = cut
            text = (text[:start] + text[end2:]).strip()
            text = re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([,.;!?])", r"\1", text))
            removed.append(raw)
            changed = True
            break
    return text, removed


def flag_player_acts(sentences: list[str], player_name: str) -> list[int]:
    """Indices of sentences where the player character is the subject of a deliberate act."""
    name_re = re.compile(rf"\b{re.escape(player_name)}\b\s+(\w+)", re.IGNORECASE) if player_name \
        else None
    flagged: list[int] = []
    for i, s in enumerate(sentences):
        acts: list[str] = []
        for m in re.finditer(r"(?<!\w)ти(?!\w)\s+(\w+)(?:\s+(\w+))?", s, re.IGNORECASE):
            acts += [w for w in m.groups() if w and (_PRESENT.match(w) or _PAST.match(w))]
        if name_re is not None:  # the name as the subject: any verb-like word after it
            acts += [m.group(1) for m in name_re.finditer(s) if len(m.group(1)) >= 4]
        acts = [v for v in acts if not _PERCEPTION.match(v)]
        if acts:
            flagged.append(i)
    return flagged


PLAYER_ACT_Q = (
    "Does this sentence make the player character do, say, decide, think or feel something "
    "that the player did not write? Perception (seeing, hearing, smelling) and body "
    "sensations imposed by the world do not count; neither does an act already named in the "
    "player's input. Sentence: {sentence}")
