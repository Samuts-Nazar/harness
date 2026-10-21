"""Campaign setup on the engine's saved campaigns (task 9): `open_campaign` continues the current
campaign (a pointer file in the campaigns folder) or starts a new one.

The scene reuses the prototype: a Witcher inn, Рагнар as the player character, two NPCs. Records are
English with Ukrainian names (task 10, 12), so the seeds below are English; the player's panel is
translated for display (`Translator`).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator

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


class Translator:
    """English record text to Ukrainian for the player's panel only (the records stay English).
    One batched call for the strings not yet translated; the cache is kept in the campaign folder."""

    SYSTEM = ("You translate short game-record lines into natural Ukrainian. Keep names, places "
              "and titles exactly as written. Reply with a JSON array of strings, same length "
              "and order as the input.")

    def __init__(self, provider: Provider, model: str, path: Path | None) -> None:
        self.provider, self.model, self.path = provider, model, path
        self.cache: dict[str, str] = {}
        try:
            if path is not None:
                self.cache = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass

    def __call__(self, texts: list[str]) -> list[str]:
        todo = [t for t in dict.fromkeys(texts) if t not in self.cache]
        if todo:
            try:
                raw = self.provider.complete(self.model, [
                    {"role": "system", "content": self.SYSTEM},
                    {"role": "user", "content": json.dumps(todo, ensure_ascii=False)}])
                got = json.loads(raw[raw.index("["): raw.rindex("]") + 1])
                if isinstance(got, list) and len(got) == len(todo):
                    self.cache.update({a: str(b) for a, b in zip(todo, got)})
                    if self.path is not None:
                        self.path.write_text(json.dumps(self.cache, ensure_ascii=False),
                                             encoding="utf-8")
            except Exception:  # noqa: BLE001 - a display nicety must never break the game
                pass
        return [self.cache.get(t, t) for t in texts]


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

    def transcript(self) -> list[dict[str, Any]]:
        """What the player has seen so far, rebuilt from the event log (a reopened campaign)."""
        out: list[dict[str, Any]] = [{"kind": "intro", "text": self.intro}]
        for e in self.engine.log.active([NARRATION, UTTERANCE, ACTION]):
            if e.type == NARRATION:
                out.append({"kind": "narr", "text": e.payload["text"]})
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
                item = {"kind": "npc", "who": who, "event": e.id,
                        "name": self.engine.ctx.label(PLAYER, who, e.id),
                        "text": e.payload["text"]}
                if e.payload.get("interrupted"):
                    item["cut"] = True
                out.append(item)
        return out


def seed_player_state(eng: Engine, traits: Traits | None) -> list[tuple[str, str, bool]]:
    """The player character's live state at the start: the sword and the scar of the scene, plus
    what the character file says (observable and hidden). Observable items are perceived by the
    NPCs present when the character enters the scene (`enter_scene`); whether one reacts is the
    salience judgment's call. Returns what was applied."""
    wanted: list[tuple[str, str, bool]] = [(EQUIPMENT, "steel sword", True),
                                           (INJURY, "old scar under the shirt", False)]
    if traits:
        wanted += [(c, i, c != INTERNAL) for c, i in traits.observable]
        wanted += [(c, i, False) for c, i in traits.hidden]
    done: list[tuple[str, str, bool]] = []
    for cat, item, obs in wanted:
        try:
            eng.apply_state_change(StateChange(PLAYER, cat, "add", item, obs))
        except StateError:
            continue  # the same item twice
        done.append((cat, item, obs))
    return done


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
