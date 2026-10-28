"""Campaign setup on the engine's saved campaigns (task 9): `open_campaign` continues the current
campaign (a pointer file in the campaigns folder) or starts a new one.

The scene reuses the prototype: a Witcher inn, Рагнар as the player character, two NPCs. Records are
English with Ukrainian names (task 10, 12), so the seeds below are English; the player's panel is
translated for display (`Translator`).
"""
from __future__ import annotations

import difflib
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

from harness import items, readable
from harness.decisions import full_role
from harness.glossary import Glossary
from harness.models import (
    ACTION, APPEARANCE, EQUIPMENT, INJURY, INTERNAL, NARRATION, PLAYER, UTTERANCE, CharacterProfile,
    Scene,
)
from harness.pipeline import Engine, ModelConfig
from harness.profile import load_profile
from harness.providers import Messages, Provider
from harness.state import StateChange, StateError

from .character import Traits, derive_traits
from .inks import InkBook, token_for
from harness.style import Style

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "Ragnar.md"  # local, never committed
CAMPAIGNS = ROOT / "campaigns"  # git-ignored
PLACEHOLDER = "Молодий мандрівник, що сидить у кутку корчми, спиною до стіни."
PLAYER_LOOK = "молодий незнайомець із мечем"  # until the character file says more
HORST_LOOK, ELZA_LOOK = "кремезний сивий чоловік", "жінка в темній хустці"
START_TIME = 13 * 24 * 60 + 19 * 60 + 40  # day 14, 19:40
TITLE = "Корчма «Вовче Гніздо»"
INTRO = (
    "Корчма «Вовче Гніздо» гуде, наче розтривожений вулик: брязкіт кухлів, чийсь хрипкий сміх, "
    "запах мокрої вовни й смаженої цибулі. Ти сидиш у кутку, спиною до стіни. Сталевий меч лежить "
    "поруч на лаві. До столу підходять двоє місцевих: кремезний сивий чоловік і жінка в темній "
    "хустці."
)
SEEDS = [  # English records, Ukrainian names
    ("Witchers hunt monsters for coin.", ["horst", "elza"]),
    ("For the fifth night in a row something has been howling at the old mill by the dam; two "
     "village boys were found dead by the dam.", ["horst", "elza", PLAYER]),
    ("The mill belonged to the miller whose widow Ельза still lives nearby.", ["horst", "elza"]),
    ("You, Рагнар, came to Брідки looking for work and a bed.", [PLAYER]),
]


def player_description() -> str:
    """Short description of the player character from the local file, else a placeholder."""
    try:
        for para in DATA_FILE.read_text(encoding="utf-8").split("\n\n"):
            para = para.strip()
            if para and not para.startswith(("#", "-", "*")):
                return para[:300].rsplit(" ", 1)[0]
    except OSError:
        pass
    return PLACEHOLDER


def profiles(player_look: str = PLAYER_LOOK) -> list[CharacterProfile]:
    """The cast. `appearance` is what others call a person by until they learn the name."""
    return [
        CharacterProfile(PLAYER, "Рагнар", player_description(), appearance=player_look),
        CharacterProfile("horst", "Горст", "Кремезний сивий староста села Брідки. Стриманий, "
                         "торгується, боїться того, що виє на млині.", appearance=HORST_LOOK),
        CharacterProfile("elza", "Ельза", "Вдова мірошника. Гостра на язик, недовіряє Горсту, "
                         "знає про млин більше, ніж каже.", appearance=ELZA_LOOK),
    ]


@dataclass
class Stack:
    """What a campaign needs from the outside: model access and judging."""
    provider: Provider
    judge: object
    models: ModelConfig
    spend: object | None = None  # harness.policy.Spend in live mode
    live: bool = False


class Recorder:
    """Wraps the provider: records every call (role, model, seconds, cost) for the debug view.
    Safe under threads when the inner provider is (the engine's parallel turn)."""

    def __init__(self, inner: Provider, models: ModelConfig, spend: object | None) -> None:
        self.inner, self.models, self.spend = inner, models, spend
        self.calls: list[dict] = []  # type: ignore[type-arg]

    @property
    def parallel_ok(self) -> bool:
        return bool(getattr(self.inner, "parallel_ok", False))

    @staticmethod
    def role(messages: Messages) -> str:
        return full_role(messages)

    def complete(self, model: str, messages: Messages) -> str:
        role = self.role(messages)
        cost0 = getattr(self.spend, "total", 0.0)
        t0 = time.monotonic()
        out = ""
        try:
            out = self.inner.complete(model, messages)
            return out
        finally:
            self.calls.append({
                "role": role, "model": model, "seconds": round(time.monotonic() - t0, 2),
                "cost": round(getattr(self.spend, "total", 0.0) - cost0, 6),
                "chars_in": sum(len(m["content"]) for m in messages), "chars_out": len(out)})

    def stream(self, model: str, messages: Messages) -> Iterator[str]:
        yield from self.inner.stream(model, messages)


def _english(text: str) -> bool:
    """A leftover English run: three or more Latin-letter words (names in Latin are not that)."""
    return len(re.findall(r"(?<![\w'])[A-Za-z]{2,}(?![\w'])", text)) >= 3


def _phonetic(word: str) -> str:
    """A rough Ukrainian spelling-insensitive key: Олдріх and Ольдрих are one name."""
    w = word.lower().replace("ї", "и").replace("і", "и").replace("є", "е")
    return re.sub(r"[ьʼ'’]", "", w)


def pin_names(text: str, names: list[str]) -> str:
    """One spelling per character: a capitalised word that is a variant spelling (transliteration
    drift, a case ending kept) of a character's name is written as that name, so the panel does
    not say Ольдрих in one line and Олдріх in the next."""
    if not names or not text:
        return text
    keys = [(n, _phonetic(n)) for n in names if len(n) >= 4 and n[:1].isupper()]

    def fix(m: re.Match[str]) -> str:
        word = m.group(0)
        for name, key in keys:
            for cut in (0, 1, 2):
                stem = word[: len(word) - cut] if cut else word
                if len(stem) < 3:
                    break
                if stem == name:
                    return word  # already the pinned spelling
                if _phonetic(stem) == key:
                    return name + word[len(stem):]
        for name, key in keys:
            if len(key) >= 5 and difflib.SequenceMatcher(None, _phonetic(word), key).ratio() >= 0.9:
                if word != name:
                    return name
        return word

    return re.sub(r"(?<![\w'])[А-ЯІЇЄҐ][а-яіїєґ'’ʼ-]{3,}", fix, text)


class Translator:
    """English record text to Ukrainian for the player's panel only (the records stay English).
    One batched call for the strings not yet translated; the cache is kept in the campaign folder.
    A line that comes back still English (a line that mixes Ukrainian fragments with English looks
    already translated to a model) is asked once more with a stricter instruction, and if it is
    still English it is shown but not cached."""

    SYSTEM = ("You translate short game-record lines into natural Ukrainian. Keep names, places "
              "and titles exactly as written. Reply with a JSON array of strings, same length "
              "and order as the input.")
    STRICT = (SYSTEM + " Some lines MIX Ukrainian fragments (descriptions, names) with English "
              "words: keep the Ukrainian fragments and translate every English word, so that no "
              "English remains. Never return a line unchanged when it contains English.")

    def __init__(self, provider: Provider, model: str, path: Path | None) -> None:
        self.provider, self.model, self.path = provider, model, path
        self.cache: dict[str, str] = {}
        self.names = []
        self.labels = []
        try:
            if path is not None:
                self.cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    labels: list[str]  # how the player sees each stranger (their look): one wording each
    names: list[str]  # the campaign's character names, set by the game: one spelling each

    def _ask(self, system: str, todo: list[str]) -> dict[str, str]:
        if self.names:
            system += (" Spell these character names exactly like this, in every case form "
                       "(Ukrainian declension is fine): " + ", ".join(self.names) + ".")
        if self.labels:
            system += (" When a line refers to one of these people by role or look, use exactly "
                       "this wording: " + "; ".join(self.labels) + ".")
        raw = self.provider.complete(self.model, [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(todo, ensure_ascii=False)}])
        got = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
        if isinstance(got, list) and len(got) == len(todo):
            return {a: str(b) for a, b in zip(todo, got)}
        return {}

    def __call__(self, texts: list[str]) -> list[str]:
        todo = [t for t in dict.fromkeys(texts)
                if t not in self.cache or (_english(self.cache[t]) and _english(t))]
        if todo:
            done: dict[str, str] = {}
            for system in (self.SYSTEM, self.STRICT):
                try:
                    done.update(self._ask(system, todo))
                except Exception:  # noqa: BLE001 - a display nicety must never break the game
                    break
                todo = [t for t in todo if _english(done.get(t, t))]
                if not todo:
                    break
            self.cache.update({a: b for a, b in done.items() if not _english(b)})
            if self.path is not None and any(not _english(b) for b in done.values()):
                try:
                    self.path.write_text(json.dumps(self.cache, ensure_ascii=False),
                                         encoding="utf-8")
                except OSError:
                    pass
            done = {a: b for a, b in done.items() if _english(b)}
        else:
            done = {}
        return [pin_names(self.cache.get(t) or done.get(t, t), self.names) for t in texts]


@dataclass
class Campaign:
    engine: Engine
    recorder: Recorder
    spend: object | None
    live: bool
    name: str = ""
    translate: Translator | None = None
    title: str = TITLE
    intro: str = INTRO
    world: Any = None  # harness.world.World when the campaign has a world beyond the scene (task 17)
    inks: InkBook | None = None
    assistant: bool = True  # the turn assistant's suggestions (a game package may switch them off)

    def __post_init__(self) -> None:
        if self.inks is None:
            d = self.engine.campaign_dir
            self.inks = InkBook(d / "inks.json" if d else None)

    def tok(self, cid: str) -> str:
        """The opaque client key of a character in this campaign."""
        return token_for(self.inks.salt, cid)

    def speaker_ids(self) -> list[str]:
        """Everyone the player has seen speak or act, in order of first appearance."""
        out: list[str] = []
        for e in self.engine.log.active([UTTERANCE, ACTION]):
            if e.type == ACTION and e.payload.get("gesture"):
                who = e.payload.get("by") or (e.participants[0] if e.participants else "")
            elif e.type == UTTERANCE:
                who = e.payload.get("speaker")
            else:
                continue
            if who and who != PLAYER and who not in out:
                out.append(who)
        return out

    def transcript(self) -> list[dict[str, Any]]:
        """What the player has seen so far, rebuilt from the event log (a reopened campaign)."""
        out: list[dict[str, Any]] = [{"kind": "intro", "text": self.intro}]
        for e in self.engine.log.active([NARRATION, UTTERANCE, ACTION, readable.READ_EVENT]):
            if e.type == readable.READ_EVENT:  # what the player read, as he saw it
                if e.payload.get("reader") == PLAYER:
                    from .game import read_entry  # game imports this module
                    out.append(read_entry(e))
                continue
            if e.type == NARRATION:
                out.append({"kind": "narr", "text": e.payload["text"], "event": e.id})
                continue
            if e.type == ACTION and e.payload.get("gesture"):
                # a gesture-only step of an NPC, shown as their action (as the live path does)
                by = e.payload.get("by") or (e.participants[0] if e.participants else "")
                names = self.engine.names
                text = (names.mask(PLAYER, str(e.payload.get("text", "")), before=e.id)
                        if names else str(e.payload.get("text", ""))).strip()
                if text:
                    out.append({"kind": "npc_act", "tok": self.tok(by), "text": text, "event": e.id,
                                "label": self.engine.ctx.label(PLAYER, by, e.id)})
                continue
            if e.type == ACTION and e.payload.get("actor") != PLAYER:
                continue  # observable actions of narration are not shown as such
            who = e.payload.get("speaker", e.payload.get("actor"))
            if who == PLAYER:
                if e.payload.get("part", 1) > 1:
                    continue  # the rest of an input that was split into actions and speech
                out.append({"kind": "player", "text": e.payload.get("raw", e.payload["text"])})
            else:
                # the label is what the player knew of this person when they spoke
                item = {"kind": "npc", "tok": self.tok(who), "event": e.id,
                        "label": self.engine.ctx.label(PLAYER, who, e.id),
                        "text": e.payload["text"]}
                if e.payload.get("interrupted"):
                    item["cut"] = True
                out.append(item)
        return out


INN_STATE = ((EQUIPMENT, "steel sword", True), (INJURY, "old scar under the shirt", False))


def seed_player_state(eng: Engine, traits: Traits | None,
                      base: tuple[tuple[str, str, bool], ...] = INN_STATE,
                      skip: tuple[str, ...] = ()) -> list[tuple[str, str, bool]]:
    """The player character's live state at the start: `base` (the inn scene's sword and scar;
    a game package gives none), plus what the character file says (observable and hidden).
    Observable items are perceived by the NPCs present when the character enters the scene
    (`enter_scene`); whether one reacts is the salience judgment's call. Returns what was
    applied. `skip` drops those categories of the character file's items (a package with an
    explicit inventory gives its own equipment and inventory)."""
    wanted: list[tuple[str, str, bool]] = list(base)
    if traits:
        wanted += [(c, i, c != INTERNAL) for c, i in traits.observable if c not in skip]
        wanted += [(c, i, False) for c, i in traits.hidden if c not in skip]
    done: list[tuple[str, str, bool]] = []
    for cat, item, obs in wanted:
        try:
            eng.apply_state_change(StateChange(PLAYER, cat, "add", item, obs))
        except StateError:
            continue  # the same item twice
        done.append((cat, item, obs))
    return done


# -- an explicit starting inventory (game packages) -------------------------------------------

_WORN = {"worn", "на тілі", "одягнене", "одягнено"}
_HAND = {"in hand", "in_hand", "в руці", "у руці", "в руках", "у руках"}
_POCKET = {"pocket", "кишеня", "в кишені", "у кишені"}


def classify_where(where: str) -> str | None:
    """`worn`, `in_hand` or `pocket` for the built-in places of an inventory entry, else None
    (then it must name a container entry)."""
    w = " ".join((where or "worn").casefold().split())
    if w in _WORN:
        return "worn"
    if w in _HAND:
        return "in_hand"
    if w in _POCKET:
        return "pocket"
    return None


def _find_container(where: str, entries: list[dict]) -> int | None:
    """Index of the container entry that `where` names (exact name, else the one container whose
    name contains it or is contained in it), or None."""
    w = " ".join(where.casefold().split())
    boxes = [(i, " ".join(e["name"].casefold().split())) for i, e in enumerate(entries)
             if e.get("container")]
    for i, n in boxes:
        if n == w:
            return i
    part = [i for i, n in boxes if w and (w in n or n in w)]
    return part[0] if len(part) == 1 else None


def seed_player_inventory(eng: Engine, items_: list[dict[str, Any]]) -> dict[str, str]:
    """Give the player the package's explicit inventory: mint ids, set locations, add through
    `apply_state_change` (containers before what is inside them), then open the open containers.
    Condition, notes, content and power are owner-known: they are not part of the item text
    (so nobody perceives them) but stored in campaign_meta `inventory_meta` by item id.
    Returns name -> id."""
    taken = items.all_ids(eng.live.snapshot())
    ids: list[str] = []
    for e in items_:
        ids.append(items.mint_id(e["name"], taken))
        taken.add(ids[-1])
    parent: dict[int, int | None] = {}
    place: dict[int, str] = {}
    for i, e in enumerate(items_):
        kind = classify_where(e.get("where", ""))
        box = None if kind else _find_container(e.get("where", ""), items_)
        if kind is None and box is None:
            raise StateError(f"unknown place {e.get('where')!r} for {e['name']!r}")
        parent[i] = box
        place[i] = {"worn": "worn", "in_hand": "in_hand", "pocket": "worn"}.get(kind or "", "")
        if box is not None:
            place[i] = items.IN + ids[box]

    def depth(i: int) -> int:
        n, seen = 0, set()
        while parent[i] is not None and i not in seen:
            seen.add(i)
            i, n = parent[i], n + 1
        return n

    for i in sorted(range(len(items_)), key=lambda k: (depth(k), k)):
        e = items_[i]
        hidden = e.get("hidden")
        if hidden is None:
            hidden = classify_where(e.get("where", "")) == "pocket"
        eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", e["name"], not hidden,
                                           id=ids[i], location=place[i]))
    for i, e in enumerate(items_):
        if e.get("container") and e.get("open"):
            eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "open", e["name"]))
    keys = ("condition", "notes", "content", "power", "grants_sense")
    meta = {ids[i]: {k: e[k] for k in keys if e.get(k)} for i, e in enumerate(items_)}
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("inventory_meta", json.dumps(meta, ensure_ascii=False)))
    return {e["name"]: ids[i] for i, e in enumerate(items_)}


def _pointer(root: Path) -> Path:
    return root / "current.txt"


# "living": multi-line NPC exchanges, optional narration (default). "classic": the old director,
# kept for A/B generation (`python -m app --dialogue classic`).
DIALOGUE = "living"


def open_campaign(stack: Stack, *, root: Path | str = CAMPAIGNS, new: bool = False,
                  name: str | None = None, data_file: Path | str | None = None) -> Campaign:
    """Continue the current campaign, or start a new one (`new=True`, or none exists yet)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    glossary = Glossary.for_world("witcher")
    data_file = Path(data_file) if data_file else DATA_FILE
    cur = _pointer(root)
    if name is None and not new and cur.exists():
        name = cur.read_text().strip()
    if name and not new and Engine.campaign_exists(name, root):
        eng = Engine.open_campaign(name, rec, root=root, models=stack.models, judge=stack.judge,
                                   glossary=glossary, style=Style.load("witcher"),
                                   dialogue=DIALOGUE, world_profile=load_profile("witcher"))
    else:
        name = name if (new and name) else time.strftime("inn-%Y%m%d-%H%M%S")
        while Engine.campaign_exists(name, root):
            name += "x"
        # how the player character looks: one cheap call on the local character file (cached)
        traits = derive_traits(rec, stack.models.extractor, data_file, root)
        eng = Engine.create_campaign(
            name, rec, profiles(traits.label if traits and traits.label else PLAYER_LOOK),
            Scene(TITLE, ("horst", "elza"), START_TIME), root=root,
            models=stack.models, judge=stack.judge, glossary=glossary,
            style=Style.load("witcher"), dialogue=DIALOGUE, world_profile=load_profile("witcher"))
        eng.acquaint("horst", "elza")  # neighbours: they know each other by name
        for text, knowers in SEEDS:
            eng.facts.add_canon(text, knowers=[(k, "told") for k in knowers])
        seed_player_state(eng, traits)
        eng.enter_scene(PLAYER)  # whoever is present perceives what is observable
    cur.write_text(name)
    tr = Translator(rec, stack.models.extractor, root / name / "translations.json")
    return Campaign(eng, rec, stack.spend, stack.live, name, tr)
