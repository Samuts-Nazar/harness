"""Spread of news: reach by notability, time and distance (pure code), named distortion operators
(ideas A1), and the prompts that write and check one version of an event.

Event types written by the world (all derived state comes from them):
- WORLD_NEWS      a noteworthy fact became news: payload {fact_id, origin, notability, text}
- NEWS_DELIVERY   someone carried it to a collective: payload {news, to, at, carrier}
- NEWS_VERSION    a collective holds a version: payload {news, holder, place, text, operator,
                  hops, source, at, logged_at, fact_id, verified}
- NEWS_HEARD      a person learned the collective's version: payload {news, person, via, fact_id}
- WORLD_REACTION  an authority reacted: payload {news, authority, kind, target, eta, text}
- OFFSCREEN_UPDATE an agent's cheap update: payload {character, place, activity, kind, from, to}
- WORLD_MOVE      the player went somewhere or waited: payload {kind, from, to, minutes}
- WORLD_TICK      the world was advanced to a time: payload {to}
- WORLD_ARRIVAL   an authority's men reached the place the player is at: {reaction, text}
- CANON_EXECUTED  a scheduled canon event happened (or was changed): payload {canon_id, outcome}
"""
from __future__ import annotations

import re

WORLD_NEWS, NEWS_DELIVERY, NEWS_VERSION, NEWS_HEARD = (
    "world_news", "news_delivery", "news_version", "news_heard")
WORLD_REACTION, OFFSCREEN_UPDATE, WORLD_MOVE, WORLD_TICK, CANON_EXECUTED, WORLD_ARRIVAL = (
    "world_reaction", "offscreen_update", "world_move", "world_tick", "canon_executed",
    "world_arrival")

NEWS_MIN_NOTABILITY = 0.5  # a fact below this stays with its witnesses
BASE_DELAY = 10  # minutes before word starts to move
PACE_BASE = 2.2  # minutes of delay per minute of distance, minus the notability


def reach_minutes(notability: float) -> int:
    """How far (in walking minutes) news of this notability can travel. Quiet events do not leave
    their witnesses; the reach grows fast with notability: 0.5 about 80 minutes (the neighbouring
    streets), 0.7 about 12 hours of walking, 0.9 about a day and a half, 1.0 two days."""
    if notability < NEWS_MIN_NOTABILITY:
        return 0
    return int(8000 * (notability - 0.4) ** 2)


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
        f"Retell it the way {holder_name} repeat it after it has passed through {hops_} "
        f"retelling(s). Change to apply: {change}. Add no other invented facts. One or two "
        "sentences, third person, no quotation marks, no commentary."
        + (f" Write in {language}." if language else ""))
    return [{"role": "system", "content": "You write how a rumour is retold. Rumour writer."},
            {"role": "user", "content": body}]


def clean_version(raw: str) -> str | None:
    text = re.sub(r"\s+", " ", raw.strip().strip('"«»“”')).strip()
    if not text or len(text) > MAX_VERSION_CHARS:
        return None
    return text
