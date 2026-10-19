"""Canon interface for the rest of the engine (task 16 <-> task 17).

Time is in-world minutes of the story: day 1 00:00 = 0, so day N hour H = (N-1)*1440 + H*60.
A campaign keeps its own world clock; `CanonCampaign.offset` maps story minutes to campaign minutes
(campaign_t = story_t - offset), so the world engine never has to know story days.

Entity ids are canon entity ids (e.g. "char:velerad"); `*_name` fields carry the display name.

What task 17 uses:
    scheduled_events(canon, after_t, until_t=None) -> list[ScheduledEvent]   what canon says happens next
    ScheduledEvent.knowers                                                   who learns it, how, when
    judge_event(...)  -> EventVerdict                                        re-judge when the player changed things
    background(canon, character, topic, ...) -> Background | None           what a person knows from their life

Canon secrets never come through `background`: it only returns what the person's own life gives.
All functions are plain Python over a `harness.canon.retrieve.Canon` store (read only).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

MIN_PER_DAY = 1440


def story_t(day: int, hour: float = 0.0) -> int:
    return int((day - 1) * MIN_PER_DAY + hour * 60)


@dataclass(frozen=True)
class Knower:
    entity: str            # canon entity id
    name: str
    channel: str           # witnessed | told | heard | overheard | hearsay | inferred | ...
    source: str | None     # entity id of whoever informed them (None for witnesses)
    learned_t: int | None  # story minutes when they learn it (None = unknown, treat as event time)


@dataclass(frozen=True)
class ScheduledEvent:
    """A canon event that happens after the start moment unless the player's acts changed its preconditions."""
    id: int
    t: int                       # story minutes (start of the event)
    day: int | None
    place: str | None            # canon place entity id
    place_name: str | None
    participants: tuple[str, ...]   # entity ids who take part (present)
    participant_names: tuple[str, ...]
    summary: str                 # what happens, one or two sentences (Ukrainian gist when available)
    knowers: tuple[Knower, ...]  # everyone who learns it, with channel and time
    notability: float            # 0..1 (loudness): how far it should travel
    kind: str = "other"
    reactions: tuple[tuple[str, str], ...] = ()   # (party entity id, reaction word)


@dataclass(frozen=True)
class Background:
    """A fact a person knows from their own life (role, years, place, standing). Source is always 'own life'."""
    character: str
    topic: str
    text: str
    source: str = "own life"
    t: int | None = None   # story minutes when it was judged (log time); the knowledge itself is of the past


@dataclass(frozen=True)
class EventVerdict:
    event_id: int
    outcome: str      # "happens" | "differently" | "does_not_happen"
    reason: str
    new_summary: str | None = None   # for "differently": what happens instead
    t: int | None = None


@dataclass
class CanonCampaign:
    """The start moment of a campaign inside the canon: where the story is when play begins."""
    start_t: int                 # story minutes
    place: str | None            # canon place entity id of the first scene
    offset: int = 0              # story_t - campaign_t
    present: list[str] = field(default_factory=list)   # canon person ids in the first scene

    def to_campaign_t(self, t: int) -> int:
        return t - self.offset

    def to_story_t(self, campaign_t: int) -> int:
        return campaign_t + self.offset


JudgeFn = Callable[[str], str]   # a cheap-model call: prompt -> text


# Implementations live in harness/canon/play.py; these wrappers keep the contract readable in one file.
def scheduled_events(canon, after_t: int, until_t: int | None = None) -> list[ScheduledEvent]:  # noqa: ANN001
    from .play import scheduled_events as impl
    return impl(canon, after_t, until_t)


def background(canon, character: str, topic: str, *, judge: JudgeFn, as_of: int,   # noqa: ANN001
               stored: Sequence[Background] = ()) -> Background | None:
    from .play import background as impl
    return impl(canon, character, topic, judge=judge, as_of=as_of, stored=stored)


def judge_event(canon, event: ScheduledEvent, changes: Sequence[str], *, judge: JudgeFn,   # noqa: ANN001
                at_t: int) -> EventVerdict:
    from .play import judge_event as impl
    return impl(canon, event, changes, judge=judge, at_t=at_t)
