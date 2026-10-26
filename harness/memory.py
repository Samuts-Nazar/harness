"""Per-character memory, derived from the event log (which stays the source of truth).

`MemoryDeriver.derive` is the one derivation: NPC context assembly reads it, and `MemoryWriter`
renders the same thing as Markdown files with Obsidian-style wikilinks. The files are engine
memory (not a player-facing document) and are rewritten from scratch after every committed turn
and after any rollback, so they can never disagree with the log.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Mapping

from . import items
from .agents import AgentRegistry, Intents
from .attitudes import Attitude, Attitudes, Notices
from .belief import BeliefFn
from .eventlog import EventLog
from .facts import FactStore
from .knowledge import read_item
from .models import CharacterProfile, Event, Fact, Knower, format_time
from .state import Element, LiveState


@dataclass(frozen=True)
class KnownItem:
    fact: Fact
    knower: Knower
    belief: float


@dataclass
class CharacterMemory:
    character: str
    knows: list[KnownItem] = field(default_factory=list)
    attitudes: list[tuple[Attitude, Fact]] = field(default_factory=list)
    state: list[Element] = field(default_factory=list)
    intents: list[Event] = field(default_factory=list)
    noticed: list[tuple[Event, Fact]] = field(default_factory=list)  # noteworthy, not yet shown


class MemoryDeriver:
    def __init__(self, facts: FactStore, intents: Intents, live: LiveState,
                 attitudes: Attitudes, notices: Notices, belief: BeliefFn) -> None:
        self.facts, self.intents, self.live = facts, intents, live
        self.attitudes, self.notices, self.belief = attitudes, notices, belief

    def derive(self, character: str, at_time: int, debug: bool = False) -> CharacterMemory:
        mem = CharacterMemory(character)
        for f in self.facts.visible_to(character, at_time):
            k = next(k for k in f.knowers if k.character == character)
            mem.knows.append(KnownItem(f, k, self.belief(character, f, k)))
        for a in self.attitudes.of(character):
            f = self.facts.get(a.fact_id)
            if f is not None:
                mem.attitudes.append((a, f))
        snap = self.live.snapshot()  # observability is derived (a closed container hides)
        # the character's own view: what it is not aware of is absent (the debug view keeps it)
        mem.state = [replace(e, observable=items.is_observable(e, snap))
                     for e in self.live.of(character, viewer=character, debug=debug)]
        mem.intents = self.intents.pending(character)
        for ev, fid in self.notices.pending(character):
            f = self.facts.get(fid)
            if f is not None:
                mem.noticed.append((ev, f))
        return mem


def slug(s: str) -> str:
    return re.sub(r"[^\w]+", "-", s.lower(), flags=re.UNICODE).strip("-") or "unnamed"


def place_link(loc: str) -> str:
    return f"[[place-{slug(loc)}]]"


class MemoryWriter:
    def __init__(self, root: Path, deriver: MemoryDeriver, log: EventLog,
                 profiles: Mapping[str, CharacterProfile], agents: AgentRegistry) -> None:
        self.root, self.deriver, self.log = root, deriver, log
        self.profiles, self.agents = profiles, agents

    def name(self, cid: str) -> str:
        p = self.profiles.get(cid)
        return p.name if p else cid

    def _who(self, cid: str) -> str:
        return f"[[{slug(cid)}|{self.name(cid)}]]"

    def regenerate(self, at_time: int) -> list[Path]:
        for sub in ("characters", "places", "events"):
            d = self.root / sub
            d.mkdir(parents=True, exist_ok=True)
            for old in d.glob("*.md"):
                old.unlink()
        written: list[Path] = []
        event_ids: set[int] = set()
        places: set[str] = set()
        for cid in self.profiles:
            mem = self.deriver.derive(cid, at_time, debug=True)  # dev files: all
            text = self._character_md(mem, event_ids, places)
            p = self.root / "characters" / f"{slug(cid)}.md"
            p.write_text(text)
            written.append(p)
        for eid in sorted(event_ids):
            if self.log.is_active(eid):
                ev = self.log.get(eid)
                places.add(ev.location)
                p = self.root / "events" / f"event-{eid}.md"
                p.write_text(self._event_md(ev))
                written.append(p)
        for loc in sorted(places):
            p = self.root / "places" / f"place-{slug(loc)}.md"
            p.write_text(self._place_md(loc, event_ids))
            written.append(p)
        return written

    # -- renderers ---------------------------------------------------------------------------
    def _character_md(self, mem: CharacterMemory, event_ids: set[int], places: set[str]) -> str:
        cid = mem.character
        prof = self.profiles.get(cid)
        out = [f"# {self.name(cid)}", "",
               f"id: `{cid}` · persistent agent: {'yes' if self.agents.is_agent(cid) else 'no'}"]
        if prof and prof.description:
            out.append(f"\n{prof.description}")
        out += ["", "## Knows"]
        for it in mem.knows:
            f, k = it.fact, it.knower
            if f.location:
                places.add(f.location)
            if f.source_event_id is not None:
                event_ids.add(f.source_event_id)
            if (item := read_item(k.source)) is not None:
                how = f"read in {item}"
            elif k.source is not None:
                how = f"{'told by' if k.how == 'told' else 'heard from'} {self._who(k.source)}"
            else:
                how = "perceived directly" if k.how == "witnessed" else k.how
            ev = f", {self._ev_link(k.event_id)}" if k.event_id is not None else ""
            loc = f", {place_link(f.location)}" if f.location else ""
            out.append(f"- {f.content} ({how}{ev}{loc}, {format_time(f.game_time)}, "
                       f"belief {it.belief:.2f}) ^fact-{f.id}")
        if not mem.knows:
            out.append("- (nothing)")
        out += ["", "## Attitudes"]
        for a, f in mem.attitudes:
            out.append(f"- toward [[{slug(cid)}#^fact-{f.id}]]: {a.stance} ({a.magnitude:g})")
        if not mem.attitudes:
            out.append("- (none)")
        out += ["", "## Live state"]
        for e in mem.state:
            out.append(f"- {e.category}: {e.item} ({'observable' if e.observable else 'hidden'})")
        if not mem.state:
            out.append("- (nothing)")
        out += ["", "## Pending intents"]
        for e in mem.intents:
            event_ids.add(e.id)
            out.append(f"- \"{e.payload['text']}\" ({self._ev_link(e.id)})")
        if not mem.intents:
            out.append("- (none)")
        if mem.noticed:
            out += ["", "## Noticed, not yet acted on"]
            out += [f"- {f.content}" for _, f in mem.noticed]
        return "\n".join(out) + "\n"

    @staticmethod
    def _ev_link(eid: int | None) -> str:
        return f"[[event-{eid}]]"

    def _event_md(self, ev: Event) -> str:
        text = ev.payload.get("text") or ev.payload.get("item") or ""
        out = [f"# Event {ev.id}: {ev.type}", "",
               f"- when: {format_time(ev.game_time)}", f"- where: {place_link(ev.location)}"]
        if ev.participants:
            out.append("- participants: " + ", ".join(self._who(c) for c in ev.participants))
        if ev.witnesses:
            out.append("- perceived by: " + ", ".join(self._who(c) for c in ev.witnesses))
        if ev.cause_id is not None:
            out.append(f"- caused by: {self._ev_link(ev.cause_id)}")
        if text:
            out += ["", f"> {text}"]
        return "\n".join(out) + "\n"

    def _place_md(self, loc: str, event_ids: set[int]) -> str:
        out = [f"# {loc}", "", "## Events here"]
        here = [eid for eid in sorted(event_ids)
                if self.log.is_active(eid) and self.log.get(eid).location == loc]
        out += [f"- {self._ev_link(e)}" for e in here] or ["- (none)"]
        return "\n".join(out) + "\n"
