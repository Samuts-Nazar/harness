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

from harness.glossary import Glossary
from harness.models import EQUIPMENT, INJURY, NARRATION, PLAYER, UTTERANCE, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import Messages, Provider
from harness.state import StateChange
from harness.style import Style

ROOT = Path(__file__).resolve().parent.parent
DATA_FILE = ROOT / "data" / "Ragnar.md"  # local, never committed
CAMPAIGNS = ROOT / "campaigns"  # git-ignored
PLACEHOLDER = "Молодий мандрівник, що сидить у кутку корчми, спиною до стіни."
START_TIME = 13 * 24 * 60 + 19 * 60 + 40  # day 14, 19:40
TITLE = "Корчма «Вовче Гніздо»"
INTRO = (
    "Корчма «Вовче Гніздо» гуде, наче розтривожений вулик: брязкіт кухлів, чийсь хрипкий сміх, "
    "запах мокрої вовни й смаженої цибулі. Ти сидиш у кутку, спиною до стіни. Сталевий меч лежить "
    "поруч на лаві. До столу підходять двоє: староста Горст і вдова мірошника Ельза."
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


def profiles() -> list[CharacterProfile]:
    return [
        CharacterProfile(PLAYER, "Рагнар", player_description()),
        CharacterProfile("horst", "Горст", "Кремезний сивий староста села Брідки. Стриманий, "
                         "торгується, боїться того, що виє на млині."),
        CharacterProfile("elza", "Ельза", "Вдова мірошника. Гостра на язик, недовіряє Горсту, "
                         "знає про млин більше, ніж каже."),
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
        sys = messages[0]["content"] if messages else ""
        if "narrator" in sys:
            return "narrator"
        if "fact extractor" in sys:
            return "extractor"
        if "observable actions" in sys:
            return "director: actions"
        if "You help write characters" in sys:
            return "manner notes"
        if "translate" in sys.lower():
            return "translator"
        if sys.startswith("You are "):
            return "npc: " + sys[8:].split(".")[0]
        return "judge"

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

    def transcript(self) -> list[dict[str, Any]]:
        """What the player has seen so far, rebuilt from the event log (a reopened campaign)."""
        out: list[dict[str, Any]] = [{"kind": "intro", "text": self.intro}]
        for e in self.engine.log.active([NARRATION, UTTERANCE]):
            if e.type == NARRATION:
                out.append({"kind": "narr", "text": e.payload["text"]})
                continue
            who = e.payload["speaker"]
            if who == PLAYER:
                out.append({"kind": "player", "text": e.payload["text"]})
            else:
                item = {"kind": "npc", "who": who, "name": self.engine.ctx.name(who),
                        "text": e.payload["text"]}
                if e.payload.get("interrupted"):
                    item["cut"] = True
                out.append(item)
        return out


def _pointer(root: Path) -> Path:
    return root / "current.txt"


def open_campaign(stack: Stack, *, root: Path | str = CAMPAIGNS, new: bool = False,
                  name: str | None = None) -> Campaign:
    """Continue the current campaign, or start a new one (`new=True`, or none exists yet)."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    glossary = Glossary.for_world("witcher")
    cur = _pointer(root)
    if name is None and not new and cur.exists():
        name = cur.read_text().strip()
    if name and not new and Engine.campaign_exists(name, root):
        eng = Engine.open_campaign(name, rec, root=root, models=stack.models, judge=stack.judge,
                                   glossary=glossary, style=Style.load("witcher"))
    else:
        name = name if (new and name) else time.strftime("inn-%Y%m%d-%H%M%S")
        while Engine.campaign_exists(name, root):
            name += "x"
        eng = Engine.create_campaign(
            name, rec, profiles(), Scene(TITLE, ("horst", "elza"), START_TIME), root=root,
            models=stack.models, judge=stack.judge, glossary=glossary,
            style=Style.load("witcher"))
        for text, knowers in SEEDS:
            eng.facts.add_canon(text, knowers=[(k, "told") for k in knowers])
        eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "steel sword", True))
        eng.apply_state_change(StateChange(PLAYER, INJURY, "add", "old scar under the shirt",
                                           False))
        eng.enter_scene(PLAYER)
    cur.write_text(name)
    tr = Translator(rec, stack.models.extractor, root / name / "translations.json")
    return Campaign(eng, rec, stack.spend, stack.live, name, tr)
