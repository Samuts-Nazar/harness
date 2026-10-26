"""Who knows what, and from where (task 14).

Two uses of the same listing of a character's channels (the things that could explain a claim):
- `report(engine, character)`: the debug view, per character: fact / name / heard / seen /
  background, each with how, the source, when and the event it came from;
- `challenge` (Engine.challenge_line): the player says an NPC line could not have been known. The
  engine picks, among the speaker's channels, the one that explains the claim, if any.

A channel is an `Item`. Facts carry the knower row (how, source, when, event); names carry the
learning event; heard lines are the dialogue the character witnessed; the profile description
stands for the character's own life ("background").
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING, Any

from .models import ACTION, PLAYER, format_time

if TYPE_CHECKING:
    from .pipeline import Engine

FACT, NAME, SEEN, BACKGROUND, STATE = "fact", "name", "seen", "background", "state"
OWN_LIFE = "own life"  # knower source of a fact judged from the character's own life


@dataclass(frozen=True)
class Item:
    key: str
    kind: str  # FACT | NAME | SEEN | BACKGROUND | STATE
    text: str  # what is known (real names: this is for judges and the debug view)
    how: str  # witnessed | heard | told | introduced | ... | background
    source: str | None  # character id the knowledge came from (None: perceived directly)
    when: int | None  # in-world minutes when it was learned
    event: int | None  # the event it came from
    fact_id: int | None = None
    canon: bool = False


def items_for(eng: "Engine", character: str, before: int | None = None) -> list[Item]:
    """The character's channels. `before`: only what was known before that event id (what the
    character could draw on when a given line was said)."""
    out: list[Item] = []

    def add(kind: str, text: str, how: str, source: str | None, when: int | None,
            event: int | None, fact_id: int | None = None, canon: bool = False) -> None:
        out.append(Item(str(len(out) + 1), kind, text, how, source, when, event, fact_id, canon))

    mem = eng.deriver.derive(character, eng.scene.time, debug=True)
    for it in mem.knows:
        f, k = it.fact, it.knower
        if before is not None and k.event_id is not None and k.event_id >= before:
            continue
        canon = f.store == "canon"  # pre-campaign knowledge has no meaningful "when"
        if k.source == OWN_LIFE:  # judged lazily from the character's life (canon/play.py)
            add(BACKGROUND, f.content, "background", None, None, k.event_id, f.id, canon=True)
            continue
        add(FACT, f.content, k.how, k.source, None if canon else k.learned_at, k.event_id, f.id,
            canon=canon)
    for subj, ev in eng.names.known_map(character, before).items():
        if subj == character:
            continue
        add(NAME, f"knows that {eng.names.describe(subj)} is called {eng.names.real(subj)}",
            ev.payload["how"], ev.payload.get("source"), ev.game_time, ev.id)
    seen = [e for e in eng.log.recent_dialogue(witnessed_by=character, limit=eng.ctx.history_limit)
            if before is None or e.id < before]
    for e in seen:
        who = eng.names.real(e.payload.get("speaker") or e.payload.get("actor") or "")
        text = (f"{who} did: {e.payload['text']}" if e.type == ACTION and e.payload.get("actor")
                else e.payload["text"] if e.type == ACTION else f"{who} said: {e.payload['text']}")
        add(SEEN, text, "heard", e.payload.get("speaker"), e.game_time, e.id)
    for s in mem.state:
        add(STATE, f"{s.category}: {s.item}", "witnessed", None, None, None)
    prof = eng.profiles.get(character)
    if prof and prof.description:
        add(BACKGROUND, prof.description, "background", None, None, None)
    return out


# -- wording for the player ---------------------------------------------------------------------
_UK = {
    "now": "щойно", "today": "сьогодні", "yesterday": "вчора",
    "days": lambda n: f"{n} {_plural(n, 'день', 'дні', 'днів')} тому",
    "witnessed": "бачив це на власні очі", "from_player": "почув це від тебе",
    "from_someone": "чув про це від когось", "told": "знає про це з розповідей",
    "common": "це загальновідоме в цих краях",
    "name_introduced": "знає ім'я: людина сама назвалась", "name_acquainted": "вони знайомі раніше",
    "name_told": "чув це ім'я від когось", "name_overheard": "чув це ім'я мимохідь",
    "name_player": "знає ім'я, бо ти його назвав", "name_canon": "знає ім'я з власного життя",
    "seen": "почув у цій розмові", "background": "це з його власного життя",
    "state": "бачить на власні очі",
}
_EN = {
    "now": "just now", "today": "today", "yesterday": "yesterday",
    "days": lambda n: f"{n} days ago",
    "witnessed": "saw it with their own eyes", "from_player": "heard it from you",
    "from_someone": "heard it from someone", "told": "knows it from stories",
    "common": "it is common knowledge here",
    "name_introduced": "knows the name: the person gave it", "name_acquainted": "they already know each other",
    "name_told": "heard the name from someone", "name_overheard": "heard the name in passing",
    "name_player": "knows the name because you said it", "name_canon": "knows the name from their own life",
    "seen": "heard it in this conversation", "background": "part of their own life",
    "state": "sees it themselves",
}


def _plural(n: int, one: str, few: str, many: str) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return one
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return few
    return many


def _lang(eng: "Engine") -> dict[str, Any]:
    return _EN if (eng.output_language or "").lower().startswith("en") else _UK


def rough_time(eng: "Engine", when: int | None) -> str:
    """"щойно", "сьогодні", "вчора", "3 дні тому": no clock times in play."""
    if when is None:
        return ""
    L = _lang(eng)
    delta = max(eng.scene.time - when, 0)
    if delta < 60:
        return L["now"]
    days = delta // 1440
    return L["today"] if days == 0 else L["yesterday"] if days == 1 else L["days"](days)


def public_channel(eng: "Engine", item: Item) -> str:
    """Channel type and rough time, as the player may read it ("чув про це від когось два дні
    тому"); the source's name is not given, and nothing of the content."""
    L = _lang(eng)
    if item.kind == NAME:
        phrase = L.get("name_" + item.how, L["name_overheard"])
    elif item.kind == SEEN:
        phrase = L["seen"]
    elif item.kind == BACKGROUND:
        phrase = L["background"]
    elif item.kind == STATE:
        phrase = L["state"]
    elif item.source == PLAYER:
        phrase = L["from_player"]
    elif item.how == "witnessed":
        phrase = L["witnessed"]
    elif item.canon:
        phrase = L["common"]
    elif item.source is not None:
        phrase = L["from_someone"]
    else:
        phrase = L["told"]
    when = rough_time(eng, item.when)
    return f"{phrase} {when}".strip()


def detail(eng: "Engine", item: Item) -> str:
    """The full event behind the channel (the spoiler): what, how, from whom, when."""
    src = f", from {eng.names.real(item.source)}" if item.source else ""
    when = f", {format_time(item.when)}" if item.when is not None else ""
    ev = f", event #{item.event}" if item.event is not None else ""
    return f"{item.text} ({item.kind}, {item.how}{src}{when}{ev})"


def report(eng: "Engine", character: str) -> list[dict[str, Any]]:
    """The debug listing: everything the character knows and from where."""
    out = []
    for it in items_for(eng, character):
        d = asdict(it)
        d["source_name"] = eng.names.real(it.source) if it.source else None
        d["when_text"] = format_time(it.when) if it.when is not None else None
        out.append(d)
    return out
