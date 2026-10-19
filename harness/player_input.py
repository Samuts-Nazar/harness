"""The player's text: actions in asterisks, speech as plain text (task 14).

`*не піднімаючи очей, киваю* Є справа?` is an action followed by speech. Actions are observable
(perceived by those present under the normal rules); only speech is "said". The text itself is
kept verbatim by the caller; this module only splits it.

An unclosed asterisk makes the rest of the text an action (a forgotten closing mark is the
likelier slip than a plain `*`). A run of asterisks counts as one mark.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

ACTION, SPEECH = "action", "speech"


@dataclass(frozen=True)
class Part:
    kind: str  # ACTION | SPEECH
    text: str


def split_input(text: str) -> list[Part]:
    """The input as an ordered list of parts; empty parts are dropped. Text without an asterisk
    is a single speech part, unchanged (not stripped)."""
    if "*" not in text:
        return [Part(SPEECH, text)] if text.strip() else []
    parts: list[Part] = []
    inside = False
    for chunk in re.split(r"\*+", text):
        t = chunk.strip()
        if t:
            parts.append(Part(ACTION if inside else SPEECH, t))
        inside = not inside
    return parts


def has_action(parts: list[Part]) -> bool:
    return any(p.kind == ACTION for p in parts)


def render_for_model(parts: list[Part], original: str) -> str:
    """How the narrator and the scene director are shown the input. Plain speech is shown as it
    always was; with actions each part says what it is."""
    if not has_action(parts):
        return original
    return "\n".join(("does: " if p.kind == ACTION else "says: ") + p.text for p in parts)
