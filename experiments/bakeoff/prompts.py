"""Render test items with the SAME prompt templates as harness/context.py (copied verbatim)."""
import json
from pathlib import Path

TS = Path(__file__).parent / "testset"
_meta = json.loads((TS / "profiles.json").read_text())
NAMES, PROFILES = _meta["names"], _meta["profiles"]


def nm(c):
    return NAMES.get(c, c)


def header(it):
    return f"Location: {it['location']}\nTime: {it['time']}\nPresent: " + ", ".join(nm(c) for c in it["present"])


def narrator(it):
    parts = [header(it)]
    if it["canon"]:
        parts.append("Relevant canon:\n" + "\n".join(f"- {f}" for f in it["canon"]))
    if it["campaign"]:
        parts.append("Campaign state:\n" + "\n".join(f"- {f}" for f in it["campaign"]))
    st = [f"- {nm(c)}: {cat}: {item} ({'observable' if obs else 'hidden'})" for c, cat, item, obs in it["state"]]
    if st:
        parts.append("Character state:\n" + "\n".join(st))
    if it["recent"]:
        parts.append("Recent events:\n" + "\n".join(f"{nm(c)}: {t}" for c, t in it["recent"]))
    npcs = ", ".join(f"{c} ({nm(c)})" for c in it["present"] if c != "player")
    parts.append(
        f"The player does/says: {it['player']}\nNarrate what happens next.\n\n"
        "Reply with ONE JSON object and nothing else:\n"
        '{"description": <scene prose, no quoted speech>,\n'
        ' "observable_actions": [<one short sentence per thing a character does that anyone '
        "in the room could see or hear, naming the actor>],\n"
        f' "speakers": [<ids (the word before the parentheses) of characters who speak next, '
        f"only from: {npcs}>]}}\n"
        "Never write speech for anyone but the player: NPC lines are produced separately.")
    return [{"role": "system", "content": "You are the narrator of a role-playing game. Write vivid prose."},
            {"role": "user", "content": "\n\n".join(parts)}]


def npc(it):
    n = nm(it["npc"])
    parts = [header(it)]
    if it["knows"]:
        parts.append("What you know:\n" + "\n".join(
            f"- {t} (heard from {nm(s)})" if s else f"- {t}" for t, s in it["knows"]))
    if it.get("noticed"):
        parts.append("You have just noticed:\n" + "\n".join(f"- {t}" for t in it["noticed"]))
    if it.get("attitudes"):
        parts.append("How you feel about it:\n" + "\n".join(f"- {a}" for a in it["attitudes"]))
    if it["recent"]:
        parts.append("Recent conversation:\n" + "\n".join(f"{nm(c)}: {t}" for c, t in it["recent"]))
    parts.append(f"Say what {n} says next, aloud and in character. Write only {n}'s "
                 "own words as one continuous speech: no stage directions, no other characters' lines.")
    return [{"role": "system", "content": f"You are {n}. {PROFILES[it['npc']]}".strip()},
            {"role": "user", "content": "\n\n".join(parts)}]


def extractor(it):
    who = ", ".join(it["present"])
    keys = ", ".join(k for k, _ in it["segments"])
    body = "\n".join(f"[{k}] {t}" for k, t in it["segments"])
    cur = [f"- {c}: {cat}: {item} ({'observable' if obs else 'hidden'})" for c, cat, item, obs in it["state"]]
    instr = (
        "Extract new facts and live-state changes from the passages below as JSON, "
        "nothing else:\n"
        '{"new_facts": [{"content": str, "source": <one of: ' + keys + '>, '
        '"notability": number 0..1, "location": optional str}],\n'
        ' "state_changes": [{"character": <id>, "category": "injury"|"clothing"|"inventory"|'
        '"equipment"|"internal", "op": "add"|"remove"|"reveal"|"hide", "item": str, '
        '"observable": true|false, "source": <segment>}]}\n'
        f"Characters: {who}. Do not say who knows or saw a fact; that is decided elsewhere. "
        '"remove" only works on an item the character currently has; "reveal"/"hide" change '
        "whether an existing item is observable. Do not emit any other keys.\n"
        "Current state:\n" + ("\n".join(cur) if cur else "- (none)"))
    return [{"role": "system", "content": "You are a precise fact extractor."},
            {"role": "user", "content": instr + "\n\n" + body}]
