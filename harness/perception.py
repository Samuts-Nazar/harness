"""Who perceived an event, computed in code from scene state. The extractor never decides this.

Model (simplest that supports the rule): a scene has a room. Characters in `present` are in the
room and see and hear everything that happens in it. Characters in `outside` are nearby but not
in the room and hear only loud things (notability >= LOUD). Nothing finer (zones, distances) yet.
"""
from __future__ import annotations

from dataclasses import dataclass

from .models import HEARD, TOLD, WITNESSED, Scene

LOUD = 0.7  # notability at or above which an event carries through the wall

SPEECH = "speech"  # words said by `speaker`
ACTION = "action"  # an observable action
DESCRIPTION = "description"  # narrator scene-setting; no character perceives it as such


@dataclass(frozen=True)
class Perception:
    character: str
    how: str  # witnessed | heard | told
    source: str | None  # None: perceived directly; else the speaker


def perceivers(
    scene: Scene, kind: str, notability: float, speaker: str | None = None
) -> list[Perception]:
    """Everyone who perceived something of this `kind` in `scene`.

    - action: present characters witness it; outside characters hear it if it is loud.
    - speech: the speaker knows what they said; other present characters are told by the
      speaker; outside characters hear it from the speaker if it is loud.
    - description: nobody (narrator-only knowledge).
    """
    if kind == DESCRIPTION:
        return []
    loud = notability >= LOUD
    out: list[Perception] = []
    for c in scene.present:
        if kind == ACTION:
            out.append(Perception(c, WITNESSED, None))
        elif c == speaker:
            out.append(Perception(c, WITNESSED, None))
        else:
            out.append(Perception(c, TOLD, speaker))
    if loud:
        for c in scene.outside:
            out.append(Perception(c, HEARD, speaker if kind == SPEECH else None))
    return out
