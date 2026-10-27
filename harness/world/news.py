"""Spread of news: reach by notability, time and distance (pure code), named distortion operators
(ideas A1), and the prompts that write and check one version of an event.

Event types written by the world (all derived state comes from them):
- WORLD_NEWS      a noteworthy fact became news: payload {fact_id, origin, notability, text,
                  thread (None: it starts its own thread), participants, unresolved}
- THREAD_RESOLVED a thread of events was closed: payload {thread, reason}
- PERIOD_SUMMARY  a derived summary of one agent's life over a skipped period: payload
                  {character, from, to, text, sources}
- NEWS_DELIVERY   someone carried it to a collective: payload {news, to, at, carrier}
- NEWS_VERSION    a collective holds a version: payload {news, holder, place, text, operator,
                  hops, source, at, logged_at, fact_id, verified}
- NEWS_HEARD      a person learned the collective's version: payload {news, person, via, fact_id}
- WORLD_REACTION  an authority reacted: payload {news, authority, kind, target, eta, text}
- OFFSCREEN_UPDATE an agent's cheap update: payload {character, place, activity, kind, from, to}
- WORLD_MOVE      the player went somewhere or waited: payload {kind, from, to, minutes}
- WORLD_TICK      the world was advanced to a time: payload {to}
- WORLD_ARRIVAL   an authority's men reached the place the player is at: {reaction, text}
- WORLD_TRAIL    men of a "seek the person" order reached a place and found nobody (or the person):
                  payload {reaction, place, hop, next, eta, over, text}
- CANON_EXECUTED  a scheduled canon event happened (or was changed): payload {canon_id, outcome}
- CANON_DEFERRED  a scheduled canon event is held back: one of its people stands in the player's
                  scene at another place; payload {canon_id, t, held}
"""
from __future__ import annotations

import re

WORLD_NEWS, NEWS_DELIVERY, NEWS_VERSION, NEWS_HEARD = (
    "world_news", "news_delivery", "news_version", "news_heard")
WORLD_REACTION, OFFSCREEN_UPDATE, WORLD_MOVE, WORLD_TICK, CANON_EXECUTED, WORLD_ARRIVAL = (
    "world_reaction", "offscreen_update", "world_move", "world_tick", "canon_executed",
    "world_arrival")
CANON_DEFERRED = "canon_deferred"  # a canon event waits for its people to reach its place
WORLD_TRAIL = "world_trail"  # men looking for a person reached a place: found nobody / next place
THREAD_RESOLVED, PERIOD_SUMMARY = "thread_resolved", "period_summary"

NEWS_MIN_NOTABILITY = 0.65  # a fact below this stays with its witnesses
SPEECH_MIN_NOTABILITY = 0.8  # something only said aloud must be this loud to travel as news
BASE_DELAY = 10  # minutes before word starts to move
PACE_BASE = 2.2  # minutes of delay per minute of distance, minus the notability


def reach_minutes(notability: float) -> int:
    """How far (in walking minutes) news of this notability can travel. Quiet events do not leave
    their witnesses; the reach grows fast with notability: 0.65 about 2 hours of walking (the
    city), 0.7 about 4.5 hours, 0.8 about 12 hours, 0.9 a day, 1.0 a day and a half."""
    if notability < NEWS_MIN_NOTABILITY:
        return 0
    return int(12000 * (notability - 0.55) ** 2)


def about_the_stranger(text: str) -> str:
    """A rumour does not know the player character's label: "the player" becomes "the stranger"."""
    return re.sub(r"\b([Tt])he player\b(?!'s name)", lambda m: m.group(1) + "he stranger", text)


def arrival_delay(notability: float, distance: int) -> int | None:
    """Minutes after the event when the news reaches a place `distance` minutes away; None if it
    never does (out of reach). Loud news moves almost at walking pace, quiet news slower."""
    if distance > reach_minutes(notability):
        return None
    return int(BASE_DELAY + distance * (PACE_BASE - notability))


def hops(distance: int) -> int:
    """Retellings on the way: one per half hour of distance, and one for leaving the witnesses."""
    return 1 + distance // 30


# Named distortion operators (ideas A1 2.6). A version must be derivable from the true record by
# at most one of these; the operator is recorded with the version.
NO_DISTORTION = "none"
DISTORTIONS: dict[str, str] = {
    NO_DISTORTION: "told straight, nothing changed except that details are lost",
    "exaggerate": "the scale is exaggerated (more people, bigger, worse, more blood)",
    "lose_actor": "who did it is lost or swapped for a vaguer or wrong person",
    "lose_mitigation": "a mitigating detail disappears (the reason, the provocation, the harmlessness)",
    "supernatural_gloss": "a moral or supernatural explanation is added (a curse, a sign, a demon)",
    "shift_place": "the place or the time shifts a little",
    "better_known": "it is attributed to a better-known figure or group",
}
STANCES = {  # a collective's attitude to a version (closed list; the judge picks)
    "fear": "is afraid",
    "awe": "is awed or reveres it",
    "hostility": "turns hostile toward whoever is blamed",
    "contempt": "does not believe it and scorns the tale",
    "curiosity": "is curious and wants to know more",
    "indifference": "does not care",
}
MAX_VERSION_CHARS = 400


def writer_messages(true_text: str, operator: str, hops_: int, holder_name: str, *,
                    language: str | None) -> list[dict[str, str]]:
    change = DISTORTIONS[operator]
    body = (
        f"Event as it truly happened: {true_text}\n\n"
        f"Retell it the way people repeat it after it has passed through {hops_} retelling(s) "
        f"and reached {holder_name}. Change to apply: {change}. Add no other invented facts. "
        "The person called 'the player' (or 'Demon') is a stranger whose name these people do "
        "not know: call them 'the stranger', or by something seen. State the story itself; do not "
        "mention who is telling it. One or two sentences, third person, no quotation marks, no "
        "commentary."
        + (f" Write in {language}." if language else ""))
    return [{"role": "system", "content": "You write how a rumour is retold. Rumour writer."},
            {"role": "user", "content": body}]


def clean_version(raw: str) -> str | None:
    text = re.sub(r"\s+", " ", raw.strip().strip('"«»“”')).strip()
    if not text or len(text) > MAX_VERSION_CHARS:
        return None
    return text
