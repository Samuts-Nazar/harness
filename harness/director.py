"""Scene director (task 12): who takes the floor next, and which observable actions happened.

Narration and NPC lines are free prose; nothing structured is asked of the creative calls. The
structure is derived afterwards by two small, separate steps that know nothing about the engine:

- `decide_speakers(judge, state, npcs)`: the first-line decider (typed choice over the present
  characters plus "nobody", then one yes/no per other character: "would they also speak right
  after?"), all in ONE batched call. Returns ids in speaking order.
- `decide_next(judge, state, npcs)` (living dialogue, task LD-4): one step of an NPC exchange
  inside a turn. One batched call with two questions: who takes the floor next (an NPC, the
  player because someone just addressed them, or nobody) and the shape of that response
  (`harness/shape.py`). The engine repeats it after every line until the player or nobody is
  chosen, or the cap.
- `actions_messages(...)` / `parse_actions(raw)`: a cheap LLM lists what characters *did* in the
  narration that anyone in the room could see or hear. The caller runs the model.

Both are plain functions over text, so a later real-time live scene can call the same director
on a fragment of a scene (who takes the floor now, when silence is the right answer).
"""
from __future__ import annotations

import re
from typing import Mapping, Sequence

from .judge import Judge, Question, choice_q, yes_no_q
from .shape import Shape

NOBODY = "nobody"
PLAYER_FLOOR = "player"  # the floor returns to the player (same id as models.PLAYER)
FIRST_TAG, ALSO_TAG = "director_first", "director_also"
NEXT_TAG, SHAPE_TAG = "director_next", "director_shape"
# heads the lines of the exchange so far in the director's state (absent on the first step)
EXCHANGE_HEADER = "This exchange so far, in order (the last line was just said):"


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


# The order matters only to a judge that answers with the first option when it has no rule (the
# offline fake): a normal-length line, never silence by accident.
_SHAPES = {
    Shape.NORMAL: "a sentence or two",
    Shape.SHORT: "a short phrase or a short sentence",
    Shape.WORD: "a word or two",
    Shape.LONG: "several sentences (rare: a story, an argument that needs it)",
    Shape.GESTURE: "no words, only a small visible action (a shrug, a look, a nod)",
    Shape.SILENCE: "nothing at all: they let it pass",
}


def next_floor_questions(npcs: Mapping[str, str]) -> dict[str, Question]:
    """The batch for one exchange step: `next` (an NPC, the player, or nobody) and `shape`."""
    options = {
        **dict(npcs),
        PLAYER_FLOOR: "the player character: someone has just addressed them (by name, by how "
                      "they look, or with a question to them), or the talk naturally turns to "
                      "them",
        NOBODY: "no one: the talk has died down and the room goes quiet",
    }
    return {
        "next": choice_q(
            "The lines said so far in this exchange are listed in order; the last one is what "
            "was just said. Who takes the floor now? If the last line asked or addressed the "
            "player character, choose the player, and the others wait for the answer. If it was "
            "aimed at another character, that character answers, or someone cuts in, objects, "
            "teases or changes the subject, as people do. Choose nobody when the exchange has "
            "run its course. Someone who just spoke rarely speaks again at once.",
            options, tag=NEXT_TAG),
        "shape": choice_q(
            "If a character takes the floor now, how much do they say? Think of the character "
            "and their mood, of what was just said and the pace of the talk: in books most "
            "replies in a quick exchange are short.",
            {s.value: d for s, d in _SHAPES.items()}, tag=SHAPE_TAG),
    }


def decide_next(judge: Judge, state: Sequence[str], npcs: Mapping[str, str]
                ) -> tuple[str, Shape]:
    """One exchange step: (an NPC id, `PLAYER_FLOOR` or `NOBODY`; the shape of the response).
    `npcs`: id -> how the director knows them (never the player). An unknown answer is nobody;
    an unknown shape is normal."""
    if not npcs:
        return NOBODY, Shape.NORMAL
    got = judge.ask(state, next_floor_questions(npcs))
    nxt = str(got["next"].answer)
    if nxt not in npcs and nxt != PLAYER_FLOOR:
        nxt = NOBODY
    try:
        shape = Shape(str(got["shape"].answer))
    except ValueError:
        shape = Shape.NORMAL
    return nxt, shape


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
