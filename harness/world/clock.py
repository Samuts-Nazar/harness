"""One world clock (the scene's time, in minutes since the campaign epoch) and the judgment of
what a turn costs in time (ideas A6: one duration judgment, a bucket resolved to minutes in code).

`interpret_questions` builds ONE batched question set for a player turn: how long it takes, whether
the player goes somewhere, whether the player waits or skips time. Code resolves the answers.
"""
from __future__ import annotations

from typing import Mapping

from ..judge import Question, choice_q

HOUR, DAY = 60, 24 * 60
# Time hierarchy (scene, day, season, year). The calendar is a placeholder: four seasons of 90 days
# (a 360-day year); a world with its own calendar replaces `SEASON_DAYS`. The scene scale is
# minutes, the day scale is what `World.skip_days` runs, seasons and years are a documented hook.
SEASON_DAYS, YEAR_DAYS = 90, 360
SEASONS = ("winter", "spring", "summer", "autumn")


def parts(t: int) -> dict[str, int | str]:
    """The clock reading as a hierarchy: year, season, day (0-based since the epoch), day of the
    season, hour, minute."""
    day, rem = divmod(t, DAY)
    year, day_of_year = divmod(day, YEAR_DAYS)
    season, day_of_season = divmod(day_of_year, SEASON_DAYS)
    return {"year": year + 1, "season": SEASONS[season], "day": day + 1,
            "day_of_season": day_of_season + 1, "hour": rem // HOUR, "minute": rem % HOUR}


def scale_of(minutes: int) -> str:
    """Which regime a span of time belongs to (ideas A6 2.6): scene, segment (hours to a day),
    skip (days), season, year."""
    if minutes < 60:
        return "scene"
    if minutes <= DAY:
        return "segment"
    if minutes < SEASON_DAYS * DAY:
        return "skip"
    return "season" if minutes < YEAR_DAYS * DAY else "year"

DURATION_BUCKETS: dict[str, tuple[str, int]] = {  # name -> (description, minutes)
    "moment": ("a few seconds to a minute (a glance, a word, a gesture)", 1),
    "minutes": ("a few minutes (a short exchange, a small task)", 5),
    "half_hour": ("about half an hour (a long talk, a meal, a short errand)", 30),
    "hour": ("about an hour", 60),
    "hours": ("several hours", 180),
    "half_day": ("about half a day", 360),
    "day": ("about a day", DAY),
    "days": ("several days", 3 * DAY),
    "week": ("about a week", 7 * DAY),
}
WAIT_TARGETS: dict[str, tuple[str, int]] = {  # name -> (description, hour of day)
    "until_morning": ("waits until the morning", 7),
    "until_noon": ("waits until midday", 12),
    "until_evening": ("waits until the evening", 19),
    "until_night": ("waits until the night", 23),
}
STAY = "stay"
NO_WAIT = "no"
WAIT_FOR = "duration"
DURATION_TAG, MOVE_TAG, WAIT_TAG = "turn_duration", "turn_move", "turn_wait"


def minutes_of(bucket: str) -> int:
    return DURATION_BUCKETS[bucket][1]


def until_hour(now: int, hour: int) -> int:
    """Minutes from `now` to the next time the clock shows `hour`:00 (a full day if it is that
    hour right now)."""
    target = hour * 60
    delta = (target - now % DAY) % DAY
    return delta or DAY


def interpret_questions(places: Mapping[str, str], here: str) -> dict[str, Question]:
    """`places`: id -> display name of the other places the player may go to."""
    move_opts = {STAY: "the player stays where they are", **{pid: f"the player goes to {n}"
                                                            for pid, n in places.items()
                                                            if pid != here}}
    wait_opts = {NO_WAIT: "the player does not wait or skip any time",
                 WAIT_FOR: "the player waits or lets a stated length of time pass",
                 **{k: d for k, (d, _) in WAIT_TARGETS.items()}}
    return {
        "duration": choice_q(
            "How much in-world time does what the player does or says in this turn take (not "
            "counting any trip or wait)? Judge by the situation: a spoken line is a moment, "
            "a haggle or a meal longer.",
            {k: d for k, (d, _) in DURATION_BUCKETS.items()}, tag=DURATION_TAG),
        "move": choice_q(
            "Does the player in this turn leave for another place? Only if they say or clearly "
            "mean that they go, walk or head there now.", move_opts, tag=MOVE_TAG),
        "wait": choice_q(
            "Does the player in this turn wait, rest, sleep or skip ahead in time? If they name "
            "a time of day, pick that target; if they name a length of time (an hour, a night), "
            "pick the duration option.", wait_opts, tag=WAIT_TAG),
    }
