"""Scene director (task 12): who takes the floor next, and which observable actions happened.

Narration and NPC lines are free prose; nothing structured is asked of the creative calls. The
structure is derived afterwards by two small, separate steps that know nothing about the engine:

- `decide_speakers(judge, state, npcs)`: the first-line decider (typed choice over the present
  characters plus "nobody", then one yes/no per other character: "would they also speak right
  after?"), all in ONE batched call. Returns ids in speaking order.
- `actions_messages(...)` / `parse_actions(raw)`: a cheap LLM lists what characters *did* in the
  narration that anyone in the room could see or hear. The caller runs the model.

Both are plain functions over text, so a later real-time live scene can call the same director
on a fragment of a scene (who takes the floor now, when silence is the right answer).
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .judge import Judge, Question, choice_q, yes_no_q

NOBODY = "nobody"
FIRST_TAG, ALSO_TAG = "director_first", "director_also"


def speaker_questions(npcs: Mapping[str, str]) -> dict[str, Question]:
    """The batch: `first` (choice among all NPCs and nobody) and `also:<id>` per NPC."""
    options = {**{cid: name for cid, name in npcs.items()}, NOBODY: "no one speaks aloud now"}
    qs: dict[str, Question] = {"first": choice_q(
        "Who speaks aloud next in this scene? If the player's words or action are meant for "
        "someone (a question, a request, an offer, a challenge, an accusation), that person "
        "answers, unless the narration shows they cannot. A nod, a gesture or a look in the "
        "narration is not yet an answer: they still speak. If the player is not addressing "
        "anyone, choose whoever would naturally react aloud. Answer nobody only if no one at all "
        "would say anything now.",
        options, tag=FIRST_TAG)}
    if len(npcs) > 1:
        for cid, name in npcs.items():
            qs[f"also:{cid}"] = yes_no_q(
                f"Would {name} also speak aloud in this same moment, after the first speaker? "
                "(Answer no if the moment calls for only one voice.)", tag=ALSO_TAG)
    return qs


def decide_speakers(judge: Judge, state: Sequence[str], npcs: Mapping[str, str], *,
                    max_speakers: int = 2) -> list[str]:
    """Ids of the characters who speak next, in order (possibly empty: silence is an answer).
    `npcs`: id -> display name of the characters who may speak (never the player)."""
    if not npcs or max_speakers < 1:
        return []
    got = judge.ask(state, speaker_questions(npcs))
    first = str(got["first"].answer)
    if first == NOBODY or first not in npcs:
        return []
    rest = [(float(got[f"also:{c}"].probabilities.get("yes", 1.0 if got[f"also:{c}"].answer else 0.0)), c)
            for c in npcs if c != first and f"also:{c}" in got and got[f"also:{c}"].answer]
    rest.sort(key=lambda t: -t[0])  # the likelier voice goes first; stable for ties
    return [first, *(c for _, c in rest)][:max_speakers]


ACTIONS_SYSTEM = "You list the observable actions in a passage of narration."


def actions_messages(narration: str, *, names: Sequence[str] = (), language: str | None = None,
                     glossary_line: str = "", limit: int = 6) -> list[dict[str, str]]:
    who = ", ".join(names)
    body = (
        "List what characters physically do in the passage below that anyone in the room could "
        "see or hear (a drawn sword, a thrown coin, a nod, someone standing up, a door slammed). "
        "One short sentence per action, naming the actor, in the order they happen. Include only "
        f"things the passage states; at most {limit}. Skip thoughts, feelings nobody can see, and "
        "scenery. If nothing qualifies, answer exactly: none. No numbering, no bullets, no "
        "commentary."
        + (f" Write the sentences in {language}." if language else "")
        + (f"\nCharacters: {who}." if who else "")
        + (f"\n{glossary_line}" if glossary_line else "")
        + f"\n\nPassage:\n{narration}")
    return [{"role": "system", "content": ACTIONS_SYSTEM}, {"role": "user", "content": body}]


def parse_actions(raw: str, limit: int = 6) -> list[str]:
    out: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"')
        if not line or line.lower().rstrip(".") in ("none", "немає", "-"):
            continue
        out.append(line)
    return out[:limit]
