"""Prompts and calls for canon extraction: an entity pass over the whole arc, then event windows."""
from __future__ import annotations

import json
import re
from typing import Any

from ..providers import Provider
from .vocab import ATTITUDES, CHANNELS, EKINDS, PARTS, REACTIONS

ENTITY_SYSTEM = """You build a canon database for a role-playing game engine from a Ukrainian translation of a novel.
Read only the text you are given. Do not use anything you remember about the books: if the text does not say it, do not write it.
Answer with one JSON object and nothing else (no commentary, no code fences)."""

ENTITY_USER = """Text (every paragraph starts with its line tag [L<number>]):

{text}

List every character, group, place and notable item or creature that appears in this text, including unnamed ones that act or matter (e.g. "the innkeeper", "the miller", "the pockmarked man").
JSON shape:
{{"entities": [{{
  "id": "char:velerad | coll:vizim-guards | place:old-palace | item:silver-sword | creature:strzyga",
  "type": "person|collective|place|item|creature",
  "name": "canonical Ukrainian name exactly as the text spells it, nominative case; for unnamed ones a short Ukrainian description such as корчмар",
  "aliases": ["other Ukrainian forms and titles the text uses for the same entity"],
  "unnamed": true or false,
  "who": "English, 1-2 sentences: who or what it is, only from the text",
  "role": "English, a few words: function in this story",
  "standing": "English: how others treat or regard this character, their social position, as the text shows (empty for places)",
  "knows": [{{"fact": "English: something this character would know from their own life or job that is not shown happening on the page", "basis": "text|inferred"}}],
  "member_of": ["coll:..."],
  "first_line": 123
}}]}}
Rules:
- Use the Ukrainian forms from the text for all names. Each entity once; merge titles and nicknames into aliases.
- "knows" is only for people: at most 4 items, only what the text directly supports (basis text) or what their job/position clearly implies (basis inferred). No invented backstory.
- Groups are entities too (townsfolk, guards, tavern guests, sorcerers who were called, the royal council) with type collective; put people into groups through member_of only when the text shows it.
- The opening scene has a woman who is never named; include her as an unnamed entity.
- Places: towns, taverns, palaces, crypt, regions, gates. Include the realm names when mentioned."""

EVENT_SYSTEM = ENTITY_SYSTEM

EVENT_USER = """Entities known so far (id | Ukrainian name | type | aliases):
{entities}

Events already extracted from earlier windows (do not repeat them; each is in story order):
{prior}

Text window (every paragraph starts with its line tag [L<number>]):

{text}

Extract the events of THIS window. An event is a discrete thing that happens or is established in the story world: an action, a speech act with consequences, an arrival, a decision, a death, a revelation, an offer, a deal. Also extract past events that characters tell about (history) as their own events, flagged by time kind "before". Do not make an event for pure description or for every line of dialogue; merge small beats of one scene into one event, but keep separate every event that someone could later ask about (a killing, an offer, a threat, a bribe, a promise, a lie, a plan).

JSON shape:
{{"new_entities": [ same shape as an entity: id, type, name, aliases, unnamed, who, role, standing, knows, member_of, first_line - ONLY for people, groups or places missing from the list above ],
 "events": [{{
  "id": "e1",
  "what": "English, 1-2 sentences, concrete: who did what to whom, with names in Ukrainian",
  "ekind": one of {ekinds},
  "loudness": 0.0-1.0 (0 = private, only those present ever know; 0.3 = a tavern talks about it; 0.6 = the whole town; 1.0 = the whole realm and beyond),
  "place": "place id or null",
  "time": {{"kind": "day|before|unknown", "day": integer, "part": one of {parts} or "unknown", "years_before": number or null}},
  "participants": [{{"entity": "id", "role": "actor|target|victim|speaker|listener|witness|bystander|subject"}}],
  "knowers": [{{"entity": "id", "channel": one of {channels}, "source": "id of the person who told it, or null", "line": line tag number where the text shows they learn it, "when": null or a time object like above if they learn it later than the event}}],
  "reactions": [{{"party": "id", "reaction": one of {reactions}, "attitude": one of {attitudes}, "text": "English, the reaction as the text shows it"}}],
  "lines": [line numbers that support the event],
  "quote": "a verbatim fragment of the Ukrainian text, at most 15 words, copied exactly, taken from those lines",
  "confidence": 0.0-1.0
}}]}}

Rules:
- Time: "day" counts story days. Day 1 is the day the stranger arrives in the city (the late afternoon). Work out later days from explicit cues in the text (the next day, days left to the full moon, days the hero was unconscious). Events before day 1 that happened in the past use kind "before" and years_before as best the text allows (null if it does not say). The opening frame scene (before the story of the stranger) and anything the text gives no time for: kind "unknown". Give the part of the day when the text says or implies it, otherwise "unknown".
- knowers = the people or groups who, by the text, know that this event happened: those who take part, are present, or are shown being told on the page (channel "told", source = the teller; "heard"/"hearsay" for second-hand or rumour; "overheard"; "witnessed" only for those who saw or took part). Never add someone just because they could have known. If a character tells a past event to another, the listener is a knower with channel "told" and source the teller, and "line" is where the telling is. If the narrator shows something nobody in the world knows (a character's private thought, something that happens alone), leave knowers empty or only list those who know.
- reactions = what other parties are shown doing in response to the event, chosen from the closed list. If the text shows no reaction, leave reactions empty. Do not invent reactions.
- Do not state anything the text does not state. Keep uncertainty in "confidence". Do not use outside knowledge.
- "quote" must be copied exactly from the text, one fragment, not translated."""


def entity_prompt(text: str) -> list[dict[str, str]]:
    return [{"role": "system", "content": ENTITY_SYSTEM},
            {"role": "user", "content": ENTITY_USER.format(text=text)}]


def entity_lines(entities: list[dict[str, Any]]) -> str:
    out = []
    for e in entities:
        al = "; ".join(e.get("aliases") or [])
        out.append(f"{e['id']} | {e.get('name', '')} | {e.get('type', '')} | {al}")
    return "\n".join(out)


def event_prompt(text: str, entities: list[dict[str, Any]], prior: list[str]) -> list[dict[str, str]]:
    user = EVENT_USER.format(
        entities=entity_lines(entities), prior="\n".join(prior) or "(none yet)", text=text,
        ekinds=" | ".join(EKINDS), parts=" | ".join(PARTS), channels=" | ".join(CHANNELS),
        reactions=" | ".join(REACTIONS), attitudes=" | ".join(ATTITUDES))
    return [{"role": "system", "content": EVENT_SYSTEM}, {"role": "user", "content": user}]


_FENCE = re.compile(r"^```(?:json)?\s*|\s*```$", re.I)


def parse_json(raw: str) -> dict[str, Any]:
    """Parse a model reply as one JSON object (fences and surrounding prose tolerated)."""
    s = _FENCE.sub("", raw.strip())
    try:
        out = json.loads(s)
    except json.JSONDecodeError:
        a, b = s.find("{"), s.rfind("}")
        if a < 0 or b <= a:
            raise
        out = json.loads(s[a:b + 1])
    if not isinstance(out, dict):
        raise ValueError("reply is not a JSON object")
    return out


class JsonFailure(RuntimeError):
    pass


def ask_json(provider: Provider, model: str, messages: list[dict[str, str]], *,
             tries: int = 2) -> tuple[dict[str, Any], int]:
    """Call the model and parse JSON; on a parse failure ask once more with the error. Returns
    (object, number of format failures before success)."""
    msgs = list(messages)
    fails = 0
    last = ""
    for _ in range(tries):
        raw = provider.complete(model, msgs)
        last = raw
        try:
            return parse_json(raw), fails
        except (json.JSONDecodeError, ValueError) as e:
            fails += 1
            msgs = list(messages) + [
                {"role": "assistant", "content": raw},
                {"role": "user", "content": f"That was not a single valid JSON object ({e}). "
                                            "Answer again with the JSON object only."}]
    raise JsonFailure(f"{model}: no valid JSON after {tries} tries: {last[:200]!r}")
