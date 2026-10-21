"""Decision counter: how many decisions the engine made in a turn, a scene, a session.

A decision is one of:
- a typed judgment (`JudgmentLog` entry); `escalations` is how many of them went from the
  first-line decider to the LLM;
- a model call, counted per role (`llm_calls_by_role`: narrator, npc, extractor, ...), read from
  `Engine.llm_calls` (one role per attempt, recorded in `Engine._complete`, so any provider is counted);
- a code-made choice: a note the engine logs in `engine.devlog` whose kind is in
  `CODE_CHOICE_KINDS`. Later tasks (shape trimming, exchange cap stops) add their note kinds to
  that set; `code_choices` is the number of such notes in the turn.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Iterable

if TYPE_CHECKING:
    from .pipeline import Engine

# Engine note kinds that record a choice made by code, not by a model.
CODE_CHOICE_KINDS: set[str] = {
    "npc_name_leak",           # a leaked/distorted name masked in an NPC line
    "name_not_attached",       # a name the speaker could not know, dropped
    "npc_lowest_suspicion",    # no candidate passed: code picked the least suspicious
    "state_change_dropped",    # an extractor state change the code refused
    "narrator_speech_stripped",  # speech cut out of the narration
    "narrator_bad_speakers",   # unknown speakers filtered from the narrator's list
    "shape_regenerated",       # an NPC line far over its shape, asked again once
    "shape_trimmed",          # still over after that: cut at a sentence boundary
}


@dataclass(frozen=True)
class DecisionCount:
    judgments: int = 0
    escalations: int = 0
    llm_calls_by_role: dict[str, int] = field(default_factory=dict)
    code_choices: int = 0

    @property
    def total(self) -> int:
        return self.judgments + sum(self.llm_calls_by_role.values()) + self.code_choices

    def as_dict(self) -> dict[str, Any]:
        return {"judgments": self.judgments, "escalations": self.escalations,
                "llm_calls_by_role": dict(self.llm_calls_by_role),
                "code_choices": self.code_choices, "total": self.total}


def full_role(messages: list[dict[str, str]]) -> str:
    """The role of a model call, from its system prompt ("npc: Name" for NPC lines)."""
    sys = messages[0]["content"] if messages else ""
    if "Rumour writer" in sys:
        return "world: rumour"
    if "narrator" in sys:
        return "narrator"
    if "fact extractor" in sys:
        return "extractor"
    if "character sheet" in sys:
        return "setup: looks"
    if "observable actions" in sys:
        return "director: actions"
    if "You help write characters" in sys:
        return "manner notes"
    if "translate" in sys.lower():
        return "translator"
    if sys.startswith("You are "):
        return "npc: " + sys[8:].split(".")[0]
    return "judge"


def count_since(engine: "Engine", first_event_id: int, judgment_mark: int, call_mark: int,
                note_mark: int = 0) -> DecisionCount:
    """Decisions made since the marks (list lengths taken when the turn began).
    `first_event_id` is the turn's first event; the counts do not need it today, it is part of
    the interface so a count can be tied to the events it covers."""
    entries = engine.judgments.entries[judgment_mark:]
    by_role: dict[str, int] = {}
    for r in engine.llm_calls[call_mark:]:
        by_role[r] = by_role.get(r, 0) + 1
    notes = engine.devlog[note_mark:]
    return DecisionCount(
        judgments=len(entries),
        escalations=sum(1 for e in entries if e.get("escalated")),
        llm_calls_by_role=by_role,
        code_choices=sum(1 for n in notes if n.get("kind") in CODE_CHOICE_KINDS))


def aggregate(counts: Iterable[DecisionCount]) -> DecisionCount:
    """Scene or session totals."""
    j = e = c = 0
    roles: dict[str, int] = {}
    for d in counts:
        j, e, c = j + d.judgments, e + d.escalations, c + d.code_choices
        for r, n in d.llm_calls_by_role.items():
            roles[r] = roles.get(r, 0) + n
    return DecisionCount(j, e, roles, c)
