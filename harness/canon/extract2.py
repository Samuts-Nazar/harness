"""v2 prompts: a scene-timeline pass over the whole arc, then events per window where code (not the
event model) supplies story time and place from the timeline. Motivation: in v1 all three models lost
count of the story days in the second half of the arc (see reports/canon_pilot/SUMMARY.md)."""
from __future__ import annotations

from typing import Any

from .extract import ENTITY_SYSTEM, EVENT_SYSTEM, EVENT_USER, entity_lines
from .vocab import ATTITUDES, CHANNELS, EKINDS, PARTS, REACTIONS

TIMELINE_USER = """Text (every paragraph starts with its line tag [L<number>]):

{text}

Build the scene timeline of this text. A scene is a continuous stretch of lines in one time and one place.
JSON shape:
{{"scenes": [{{"from_line": 9, "to_line": 17, "day": integer or null, "part": one of {parts} or "unknown",
  "place": "short English name of the place if the text names or clearly implies it, else null",
  "cue": "English: the fact in the text that fixes the day and part (quote the Ukrainian cue)"}}]}}
Rules:
- Scenes cover every line of the text once, in order, without gaps.
- Day 1 is the day the stranger arrives in the city (late afternoon). Count later days only from explicit cues (the next day, a number of days left to an event, how long someone was unconscious, "late in the evening of the second day"). A scene that continues the same evening or night keeps the same day. If a cue says something happens after the full moon, place it after that day. If the text gives no cue, give your best reading and write "no cue" in "cue".
- The opening scene before the stranger arrives is a separate frame scene with day null.
- Do not use anything you remember about the books."""

_u = EVENT_USER
_u = _u.replace("Text window (every paragraph", "Scene timeline for this window (supplied by code; you do not output time or place):\n{scenes}\n\nText window (every paragraph")
_u = _u.replace(
    '  "place": "place id or null",\n  "time": {{"kind": "day|before|unknown", "day": integer, "part": one of {parts} or "unknown", "years_before": number or null}},\n',
    '  "past": number or null (only for events that characters tell about from before the story: years before the story began, best reading of the text, 0.5 for "recently", null if nothing is said; for events happening in the story leave null),\n')
_u = _u.replace(
    "Do not make an event for pure description or for every line of dialogue; merge small beats of one scene into one event",
    "Do not make an event for pure description, small talk, or every line of dialogue; merge the beats of one scene into one event (a negotiation is one event, a fight is one or two events)")
_u = _u.replace(
    "- knowers = ",
    "- Everyone in participants whose role is not bystander must also be in knowers (the actor knows what they did, a listener learns it). Write all text in English, including descriptions of unnamed people (the innkeeper); keep proper names in the Ukrainian form from the list.\n- knowers = ")
EVENT_USER2 = _u


def timeline_prompt(text: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": ENTITY_SYSTEM},
            {"role": "user", "content": TIMELINE_USER.format(text=text, parts=" | ".join(PARTS))}]


def event_prompt2(text: str, entities: list[dict[str, Any]], prior: list[str], scenes: str) -> list[dict[str, str]]:
    user = EVENT_USER2.format(
        entities=entity_lines(entities), prior="\n".join(prior) or "(none yet)", text=text, scenes=scenes,
        ekinds=" | ".join(EKINDS), parts=" | ".join(PARTS), channels=" | ".join(CHANNELS),
        reactions=" | ".join(REACTIONS), attitudes=" | ".join(ATTITUDES))
    return [{"role": "system", "content": EVENT_SYSTEM}, {"role": "user", "content": user}]
