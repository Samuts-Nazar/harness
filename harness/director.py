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
from typing import Any, Mapping, Sequence

from .judge import Judge, Question, choice_q, yes_no_q
from .shape import Shape, decider_dist

NOBODY = "nobody"
PLAYER_FLOOR = "player"  # the floor returns to the player (same id as models.PLAYER)
FIRST_TAG, ALSO_TAG = "director_first", "director_also"
NEXT_TAG, SHAPE_TAG = "director_next", "director_shape"
NARRATION_TAG = "director_narration"
ADDRESSEE_TAG = "director_addressee"
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
    Shape.LONG: "several sentences (an explanation, a story, an argument)",
    Shape.GESTURE: "no words, only a small visible action (a shrug, a look, a nod)",
    Shape.SILENCE: "nothing at all: they let it pass",
}


def addressee_question(npcs: Mapping[str, str]) -> Question:
    """Which present character, if any, the player's latest words are a direct question or
    request to. Nobody is listed first: an unscripted judge answers it, so nothing is forced."""
    return choice_q(
        "Look at the player character's latest words (the last line of the player's input). Is "
        "it a direct question or request to one particular character who is present, someone "
        "who is expected to answer in words (asking a price, the news, a name, the way, whether "
        "something is so)? Choose that character. Choose nobody if it is an action, a remark to "
        "no one in particular, or if that character cannot hear or answer (they are far away, "
        "asleep, gone, or the narration shows they cannot).",
        {NOBODY: "no one: not a direct question to a particular present character", **dict(npcs)},
        tag=ADDRESSEE_TAG)


class AddressedDist(dict):  # type: ignore[type-arg]
    """The decider's shape distribution, marked: the player addressed `addressee` directly, so
    the step is a spoken answer (set by `_step`, read by the exchange loop)."""
    addressee: str = ""


def next_floor_questions(npcs: Mapping[str, str], prior: str = "", *, first: bool = False
                         ) -> dict[str, Question]:
    """The batch for one exchange step: `next` (an NPC, the player, or nobody) and `shape`.
    `prior`: a line about the world's usual reply length (`shape.shape_prior`), added to the
    shape question; none without a loaded profile. `first`: the first step of the turn, where
    the player's own words are the last thing said: adds `addressee`."""
    options = {
        **dict(npcs),
        PLAYER_FLOOR: "the player character: someone has just addressed them (by name, by how "
                      "they look, or with a question to them), or the talk naturally turns to "
                      "them",
        NOBODY: "no one: the talk has died down and the room goes quiet",
    }
    qs = {
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
            "replies in a quick exchange are short." + (f" {prior}" if prior else ""),
            {s.value: d for s, d in _SHAPES.items()}, tag=SHAPE_TAG),
    }
    if first and npcs:
        qs["addressee"] = addressee_question(npcs)
    return qs


def needs_narration_question() -> Question:
    """Yes/no: does this moment need a narrated passage, or is it just talk (living dialogue)."""
    return yes_no_q(
        "Does this moment need a narrated passage (a change of scene, an action with a visible "
        "result, someone arriving, a pause worth describing, an outcome to tell), or is it just "
        "talk? Answer yes only if a passage of narration is needed; a quick exchange of lines, "
        "a question and its answer, needs none.", tag=NARRATION_TAG)


def _step(got: Mapping[str, Any], npcs: Mapping[str, str]) -> tuple[str, Shape, dict[Shape, float]]:
    nxt = str(got["next"].answer)
    if nxt not in npcs and nxt != PLAYER_FLOOR:
        nxt = NOBODY
    j = got["shape"]
    try:
        shape = Shape(str(j.answer))
    except ValueError:
        shape = Shape.NORMAL
    dist: dict[Shape, float] = decider_dist(j.probabilities, shape.value, j.probability)
    who = str(got["addressee"].answer) if "addressee" in got else ""
    if who in npcs:
        # a direct question to a present character is answered by that character in words;
        # the answer may be evasive, a refusal or a lie, but not a shrug or silence
        spoken = {s: p for s, p in dist.items() if s not in (Shape.GESTURE, Shape.SILENCE)}
        shape = shape if shape not in (Shape.GESTURE, Shape.SILENCE) else Shape.SHORT
        marked = AddressedDist(spoken if sum(spoken.values()) else {shape: 1.0})
        marked.addressee = who
        return who, shape, marked
    return nxt, shape, dist


def decide_first_step(judge: Judge, state: Sequence[str], npcs: Mapping[str, str],
                      prior: str = "", *, with_dist: bool = False) -> tuple[Any, ...]:
    """The start of a living turn in ONE batched call: (does the moment need narration, then the
    first exchange step as `decide_next` answers it). The state has no narration yet; when the
    answer is yes the caller narrates and asks the first step again with the narration.
    `with_dist`: also the decider's distribution over the shapes (`shape.decider_dist`)."""
    qs = {"narration": needs_narration_question(),
          **(next_floor_questions(npcs, prior, first=True) if npcs else {})}
    got = judge.ask(state, qs)
    need = bool(got["narration"].answer)
    if not npcs:
        nxt, shape, dist = NOBODY, Shape.NORMAL, {}
    else:
        nxt, shape, dist = _step(got, npcs)
    return (need, nxt, shape, dist) if with_dist else (need, nxt, shape)


def decide_next(judge: Judge, state: Sequence[str], npcs: Mapping[str, str],
                prior: str = "", *, with_dist: bool = False, first: bool = False
                ) -> tuple[Any, ...]:
    """One exchange step: (an NPC id, `PLAYER_FLOOR` or `NOBODY`; the shape of the response).
    `npcs`: id -> how the director knows them (never the player). An unknown answer is nobody;
    an unknown shape is normal. `with_dist`: also the decider's distribution over the shapes.
    `first`: the first step of the turn (the player's words may be a direct question)."""
    if not npcs:
        return (NOBODY, Shape.NORMAL, {}) if with_dist else (NOBODY, Shape.NORMAL)
    nxt, shape, dist = _step(judge.ask(state, next_floor_questions(npcs, prior, first=first)), npcs)
    return (nxt, shape, dist) if with_dist else (nxt, shape)


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
