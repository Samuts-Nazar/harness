"""Offline simulation of the shape choice (Task 12): does the session's length distribution track
the world profile? Fake providers only, no network, no book text.

The fake decider answers the shape like the live one did in Task 8 (normal 46%, short 36%,
silence 12%, gesture 6%; it reports only its answer's probability, about 0.6). The fake writer
behaves like the live NPC model: it undershoots the asked length (Task 8: no line over 15 words,
median 6) and adds a beat to nearly every line unless told "no gesture" (then it still does
sometimes). "before" is the engine choosing the decider's answer; "after" is code sampling
against the profile (Engine._choose_shape).

    python -m experiments.dialogue.shape_sim [sessions] [turns]
"""
from __future__ import annotations

import json
import random
import re
import statistics
import sys
from typing import Any

from harness.director import ACTIONS_SYSTEM, NEXT_TAG, NOBODY, PLAYER_FLOOR, SHAPE_TAG
from harness.judge import CHOICE, FakeJudge, Judgment
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.profile import BINS, distance, load_profile, profile_of_lines
from harness.style import Style

DECIDER = {"normal": 0.46, "short": 0.36, "silence": 0.12, "gesture": 0.06}
PROFILES = [
    CharacterProfile(PLAYER, "Рагнар", "Мандрівник.", appearance="молодий незнайомець"),
    CharacterProfile("horst", "Горст", "Староста.", appearance="кремезний сивий чоловік",
                     manner="говорить уривками"),
    CharacterProfile("elza", "Ельза", "Вдова.", appearance="жінка в темній хустці",
                     manner="говорить тихо"),
]
WORDS = ("ніч млин вода хліб дорога вовк борошно гроші корчма вітер дощ поле стежка жито двері "
         "люди село пиво річка камінь").split()


class LiveLikeJudge(FakeJudge):
    """Shape answers drawn like the live decider's, with only the answer's probability."""

    def __init__(self, rng: random.Random) -> None:
        super().__init__({"director_narration": False})
        self.rng = rng

    def _make(self, q: Any, a: Any) -> Judgment:
        if q.kind == CHOICE and q.tag == SHAPE_TAG:
            ans = self.rng.choices(list(DECIDER), weights=list(DECIDER.values()))[0]
            return Judgment(ans, {}, 0.6, backend="fake")
        if q.kind == CHOICE and q.tag == NEXT_TAG:
            opts = [o for o in q.options if o not in (NOBODY, PLAYER_FLOOR)]
            ans = self.rng.choices(opts + [PLAYER_FLOOR, NOBODY], weights=[1.0] * len(opts) + [0.5, 0.3])[0]
            return Judgment(ans, {ans: 1.0}, 1.0, backend="fake")
        return super()._make(q, a)


class LiveLikeWriter:
    """The NPC calls: a line of about the asked length, shortened like the live model's."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng

    def complete(self, model: str, messages: list[dict[str, str]]) -> str:
        sys_ = messages[0]["content"] if messages else ""
        body = "\n".join(m["content"] for m in messages)
        if model != "npc":
            if sys_ == ACTIONS_SYSTEM:
                return "none"
            if model == "narrator":
                return "Дощ стукає у вікна корчми."
            return json.dumps({"new_facts": [], "state_changes": []})
        if "does not speak this turn" in body:
            return "Горст знизує плечима."
        m = (re.search(r"at least (\d+) and up to about (\d+)", body)
             or re.search(r"\((\d+)-(\d+) words\)", body) or re.search(r"(\d+)-(\d+) words", body))
        lo, hi = (int(m.group(1)), int(m.group(2))) if m else (5, 12)
        hi = min(hi, 45)
        want = self.rng.randint(lo, hi)
        n = max(1, round(want * self.rng.uniform(0.45, 1.0)))  # the live model undershoots
        speech = " ".join(self.rng.choice(WORDS) for _ in range(n)).capitalize() + "."
        told_none = "No gesture this line" in body
        beat = self.rng.random() < (0.3 if told_none else 0.95)
        return f"— {speech} — Горст потер підборіддя." if beat else f"— {speech}"

    def stream(self, model: str, messages: list[dict[str, str]]):
        yield self.complete(model, messages)


def session(seed: int, turns: int, sample: bool) -> list[str]:
    rng = random.Random(seed)
    eng = Engine(LiveLikeWriter(rng), PROFILES, Scene("Inn", (PLAYER, "horst", "elza")),
                 models=ModelConfig(), judge=LiveLikeJudge(rng), narration="prose",
                 style=Style(), world_profile=load_profile("witcher"), seed=seed,
                 record_language=None)
    eng.acquaint("horst", "elza")
    if not sample:
        eng._choose_shape = lambda npc, shape, dist, step: (shape, None)  # type: ignore[method-assign]
    for i in range(turns):
        eng.turn(f"Репліка {i}.")
    lines = list(eng.session_lines)
    eng.close()
    return lines


NAMES = ["Горст", "Ельза", "Рагнар", "кремезний", "жінка", "молодий"]


def numbers(lines: list[str]) -> dict[str, Any]:
    prof = load_profile("witcher")
    p = profile_of_lines(lines, NAMES)
    lb = p.length_bins
    return {"lines": p.n_lines, "share_1_3": round(lb["1"] + lb["2-3"], 3),
            "share_over_15": round(lb["16-30"] + lb["31+"], 3), "median": p.median_words,
            "no_beat_share": round(p.no_beat_share, 3),
            "l1": round(distance(p, prof, speech_only=True)["length_bins_l1"], 3),
            "bins": {b: round(lb[b], 3) for b in BINS}}


def main(argv: list[str]) -> int:
    n = int(argv[0]) if argv else 4
    turns = int(argv[1]) if len(argv) > 1 else 20
    prof = load_profile("witcher")
    lb = prof.length_bins
    print("profile:", json.dumps({"share_1_3": round(lb["1"] + lb["2-3"], 3),
                                  "share_over_15": round(lb["16-30"] + lb["31+"], 3),
                                  "median": prof.median_words,
                                  "no_beat_share": round(prof.no_beat_share, 3)}))
    for label, sample in (("before", False), ("after", True)):
        per = [numbers(session(s, turns, sample)) for s in range(n)]
        pooled = numbers([x for s in range(n) for x in session(s, turns, sample)])
        print(label, "per session L1:", [p["l1"] for p in per],
              "median L1", statistics.median(p["l1"] for p in per))
        print(label, "pooled:", json.dumps(pooled, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
