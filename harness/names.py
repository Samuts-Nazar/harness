"""Names are knowledge (task 14).

A character knows another's name only through a channel: introduced, told, overheard, their own
life or canon. Until then everyone else is referred to by what can be observed (the profile's
`appearance`, a short phrase), the same phrase every time, so the model can tell people apart.

Learning a name is an event (`NAME_LEARNED`, cause = the utterance it came from), so it has a
source like any fact and a rollback removes it with the line it came from. The registry is
derived from the log; nothing is stored beside it.

Only characters that have an appearance are "hidden": a profile without one is known by name to
everyone (tests, minimal setups).
"""
from __future__ import annotations

import re
from typing import Iterable, Mapping

from .eventlog import EventLog
from .glossary import ENDINGS, Glossary
from .models import NAME_LEARNED, CharacterProfile, Event, Scene

FALLBACK_LABEL = "незнайомець"
# How a character came to know the name.
OWN, ACQUAINTED, INTRODUCED, TOLD, OVERHEARD, CANON, PLAYER_SAID = (
    "own", "acquainted", "introduced", "told", "overheard", "canon", "player")
_END = "(?:" + "|".join((*ENDINGS, "о")) + ")"  # "о": the vocative of names in -а (Ельзо!)


def _stem(name: str, glossary: Glossary | None) -> str:
    if glossary is not None:
        for e in glossary.entries:
            if e.canonical.lower() == name.lower():
                return e.base
    if len(name) > 3 and name[-1].lower() in "ая" and " " not in name:
        return name[:-1]
    return name


class Names:
    def __init__(self, log: EventLog, profiles: Mapping[str, CharacterProfile],
                 glossary: Glossary | None = None) -> None:
        self.log, self.profiles, self.glossary = log, profiles, glossary
        self._patterns: dict[tuple[str, str], re.Pattern[str]] = {}

    # -- who is hidden, how they are called -------------------------------------------------
    def hidden(self, cid: str) -> bool:
        p = self.profiles.get(cid)
        return bool(p and p.appearance.strip())

    def label(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return (p.appearance.strip() if p else "") or FALLBACK_LABEL

    def real(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return p.name if p else cid

    def _pattern(self, cid: str) -> re.Pattern[str]:
        """Matches the name in any Ukrainian case (stem plus an ending), not inside a longer word."""
        name = self.real(cid)
        pat = self._patterns.get((cid, name))
        if pat is None:
            words = name.split()
            parts = [re.escape(_stem(w, self.glossary) if i == len(words) - 1 else w)
                     for i, w in enumerate(words)]
            pat = re.compile(r"(?<!\w)" + r"\s+".join(parts) + _END + r"(?!\w)", re.IGNORECASE)
            self._patterns[(cid, name)] = pat
        return pat

    def mentions(self, text: str, among: Iterable[str] | None = None) -> list[str]:
        """Ids of the hidden characters whose name occurs in `text`, in order of first mention."""
        ids = [c for c in (among if among is not None else self.profiles) if self.hidden(c)]
        hits = []
        for c in ids:
            m = self._pattern(c).search(text)
            if m:
                hits.append((m.start(), c))
        return [c for _, c in sorted(hits)]

    # -- the registry -----------------------------------------------------------------------
    def events(self, viewer: str | None = None) -> list[Event]:
        return [e for e in self.log.active([NAME_LEARNED])
                if viewer is None or e.payload["viewer"] == viewer]

    def known_map(self, viewer: str, before: int | None = None) -> dict[str, Event]:
        """subject -> the event in which `viewer` learned the name (first one). `before`: only
        events with a smaller id (what was known when an earlier event happened)."""
        out: dict[str, Event] = {}
        for e in self.events(viewer):
            if before is None or e.id < before:
                out.setdefault(e.payload["subject"], e)
        return out

    def knows(self, viewer: str, subject: str, before: int | None = None) -> bool:
        if viewer == subject or not self.hidden(subject):
            return True
        return subject in self.known_map(viewer, before)

    def learn(self, viewer: str, subject: str, *, how: str, scene: Scene,
              source: str | None = None, cause_id: int | None = None, note: str = "") -> Event | None:
        """Record that `viewer` learned the name of `subject`. None when it was known already."""
        if self.knows(viewer, subject):
            return None
        return self.log.append(
            NAME_LEARNED, game_time=scene.time, location=scene.location,
            participants=[viewer], witnesses=[], notability=0.2, cause_id=cause_id,
            payload={"viewer": viewer, "subject": subject, "how": how, "source": source,
                     "text": note or f"{self.real(viewer)} learned the name {self.real(subject)}"})

    def acquaint(self, a: str, b: str, scene: Scene, *, how: str = ACQUAINTED,
                 mutual: bool = True) -> None:
        """Setup: `a` knows `b` by name (and the other way round when `mutual`): prior
        acquaintance, own life or canon."""
        self.learn(a, b, how=how, scene=scene)
        if mutual:
            self.learn(b, a, how=how, scene=scene)

    # -- rendering --------------------------------------------------------------------------
    def ref(self, viewer: str | None, cid: str, before: int | None = None) -> str:
        """How `viewer` refers to `cid`: the name if they know it, else the appearance. viewer
        None: the omniscient view (code, judges), always the real name."""
        if viewer is None or self.knows(viewer, cid, before):
            return self.real(cid)
        return self.label(cid)

    def describe(self, cid: str) -> str:
        """For code-side judges and listers: the real name with the appearance."""
        return f"{self.real(cid)} ({self.label(cid)})" if self.hidden(cid) else self.real(cid)

    def known_set(self, viewer: str) -> frozenset[str]:
        """Ids whose name `viewer` knows, read now (a worker thread must not touch the database,
        so the engine takes this snapshot on the main thread)."""
        return frozenset(self.known_map(viewer))

    def unknown_mentioned(self, viewer: str, text: str, also_heard: str = "",
                          known: frozenset[str] | None = None) -> list[str]:
        """Hidden characters whose name occurs in `text` although `viewer` does not know it.
        A name that occurs in `also_heard` (words the viewer has just heard) counts as heard.
        `known`: a snapshot from `known_set` (default: read the registry now)."""
        known = self.known_set(viewer) if known is None else known
        return [c for c in self.mentions(text)
                if c != viewer and c not in known
                and not (also_heard and self._pattern(c).search(also_heard))]

    def mask(self, viewer: str | None, text: str, before: int | None = None,
             known: frozenset[str] | None = None) -> str:
        """`text` with the names `viewer` does not know replaced by their appearance."""
        if viewer is None or not text:
            return text
        known = frozenset(self.known_map(viewer, before)) if known is None else known
        for c in self.profiles:
            if self.hidden(c) and c != viewer and c not in known:
                text = self._pattern(c).sub(self.label(c), text)
        return text

    def known_ids(self, viewer: str | None) -> list[str]:
        """Characters whose real name `viewer` may see."""
        return [c for c in self.profiles if viewer is None or self.knows(viewer, c)]
