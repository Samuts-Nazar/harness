"""Structured narrator output and detection of NPC speech inside it.

The narrator returns {"description", "observable_actions", "speakers"}. It must never write NPC
speech: lines come only from NPC calls. Detection is a code heuristic (quotes, `Name:` lines)
refined by a judge question; the pipeline rejects/regenerates and finally strips.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Collection

# double quotes, curly, guillemets, and single quotes (not apostrophes: those touch a letter)
QUOTE_RE = re.compile(
    r'"[^"\n]+"|“[^”\n]+”|«[^»\n]+»'
    r"|(?<!\w)'(?:[^'\n]|(?<=\w)'(?=\w)){3,}?'(?!\w)"  # apostrophes inside words stay inside
)
STAGE_RE = re.compile(r"\([^)\n]*\)|\*[^*\n]+\*")


class NarrationError(ValueError):
    """The narrator output is not the required structure."""


@dataclass
class NarratorOutput:
    description: str
    actions: list[str] = field(default_factory=list)
    speakers: list[str] = field(default_factory=list)

    def texts(self) -> list[str]:
        return [self.description, *self.actions]


def parse_narration(raw: str) -> NarratorOutput:
    text = raw.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    if m:
        text = m.group(1)
    try:
        data: Any = json.loads(text)
    except json.JSONDecodeError as e:
        raise NarrationError(f"not valid JSON: {e}") from e
    if not isinstance(data, dict) or set(data) - {"description", "observable_actions", "speakers"}:
        raise NarrationError("expected an object with description, observable_actions, speakers")
    desc = data.get("description")
    acts = data.get("observable_actions", [])
    spk = data.get("speakers", [])
    if not isinstance(desc, str) or not desc.strip():
        raise NarrationError("description must be non-empty text")
    if not isinstance(acts, list) or not all(isinstance(a, str) and a.strip() for a in acts):
        raise NarrationError("observable_actions must be a list of non-empty strings")
    if not isinstance(spk, list) or not all(isinstance(s, str) for s in spk):
        raise NarrationError("speakers must be a list of character ids")
    return NarratorOutput(desc.strip(), [a.strip() for a in acts], list(dict.fromkeys(spk)))


def _speaker_line_re(names: Collection[str]) -> re.Pattern[str]:
    alts = "|".join(re.escape(n) for n in names) or r"(?!)"
    return re.compile(rf"^[ \t]*(?:{alts})[ \t]*:[ \t]*\S[^\n]*", re.IGNORECASE | re.MULTILINE)


def has_speaker_line(text: str, npc_names: Collection[str]) -> bool:
    """A script-style `Name: words` line — direct speech, no judge needed."""
    return bool(_speaker_line_re(npc_names).search(text))


def has_quotes(text: str) -> bool:
    return bool(QUOTE_RE.search(text))


def strip_speech(text: str, npc_names: Collection[str]) -> str:
    text = _speaker_line_re(npc_names).sub("", text) if npc_names else text
    text = QUOTE_RE.sub("", text)
    return re.sub(r"[ \t]{2,}", " ", re.sub(r"\s+([,.;!?])", r"\1", text)).strip()


def clean_npc_line(text: str) -> str:
    """Keep only what is said aloud: drop (stage directions) and *actions*, and the quote marks a
    model sometimes wraps around its own line. Returns the original if nothing would be left."""
    out = STAGE_RE.sub(" ", text)
    out = re.sub(r"\s+", " ", out).strip()
    if len(out) >= 2 and out[0] in "\"“«" and out[-1] in "\"”»" and not QUOTE_RE.search(out[1:-1]):
        out = out[1:-1].strip()
    return out or text.strip()
