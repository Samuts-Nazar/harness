"""Campaign setup, kept behind ONE function (`open_campaign`) so the file-backed campaigns from
task 9 can replace the in-memory engine by changing only this module.

The scene reuses the prototype: a Witcher inn, Рагнар as the player character, two NPCs.
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from harness.db import SCHEMA
from harness.models import EQUIPMENT, INJURY, PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.providers import Messages, Provider
from harness.state import StateChange

DATA_FILE = Path(__file__).resolve().parent.parent / "data" / "Ragnar.md"  # local, never committed
PLACEHOLDER = "Молодий мандрівник, що сидить у кутку корчми, спиною до стіни."
LANGUAGE_HINT = (
    "\n\nLanguage: write all prose and all speech in Ukrainian (українська), natural and literary. "
    "JSON keys and character ids stay exactly as specified."
)
START_TIME = 13 * 24 * 60 + 19 * 60 + 40  # day 14, 19:40
INTRO = (
    "Корчма «Вовче Гніздо» гуде, наче розтривожений вулик: брязкіт кухлів, чийсь хрипкий сміх, "
    "запах мокрої вовни й смаженої цибулі. Ти сидиш у кутку, спиною до стіни. Сталевий меч лежить "
    "поруч на лаві. До столу підходять двоє: староста Горст і вдова мірошника Ельза."
)


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
    """Wraps the provider: records every call (role, model, seconds, cost) for the debug view
    and appends the output-language hint to narrator and NPC prompts. The language hint is a
    stand-in until the engine has its own output-language setting (task 9)."""

    def __init__(self, inner: Provider, models: ModelConfig, spend: object | None,
                 language_hint: str = LANGUAGE_HINT) -> None:
        self.inner, self.models, self.spend, self.hint = inner, models, spend, language_hint
        self.calls: list[dict] = []  # type: ignore[type-arg]

    @staticmethod
    def role(messages: Messages) -> str:
        sys = messages[0]["content"] if messages else ""
        if "narrator" in sys:
            return "narrator"
        if "fact extractor" in sys:
            return "extractor"
        if sys.startswith("You are "):
            return "npc: " + sys[8:].split(".")[0]
        return "judge"

    def complete(self, model: str, messages: Messages) -> str:
        role = self.role(messages)
        if role == "narrator" or role.startswith("npc"):
            messages = [{**messages[0], "content": messages[0]["content"] + self.hint},
                        *messages[1:]]
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


@dataclass
class Campaign:
    engine: Engine
    recorder: Recorder
    spend: object | None
    live: bool
    title: str = "Корчма «Вовче Гніздо»"
    intro: str = INTRO


def open_campaign(stack: Stack) -> Campaign:
    """Start a fresh in-memory campaign. (Continue/load from disk plugs in here.)"""
    rec = Recorder(stack.provider, stack.models, stack.spend)
    # turns run in a worker thread; Game guarantees one thread touches the DB at a time
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    eng = Engine(rec, profiles(), Scene("Корчма «Вовче Гніздо»", ("horst", "elza"), START_TIME),
                 models=stack.models, judge=stack.judge, conn=conn)  # type: ignore[arg-type]
    eng.facts.add_canon("Відьмаки полюють на чудовиськ за гроші.",
                        knowers=[("horst", "told"), ("elza", "told")])
    eng.facts.add_canon(
        "Вже п'яту ніч поспіль на старому млині біля греблі щось виє; двох хлопців з "
        "села знайшли біля греблі мертвими.",
        knowers=[("horst", "told"), ("elza", "told"), (PLAYER, "told")])
    eng.facts.add_canon("Млин належав мірошникові, чия вдова Ельза досі живе поруч.",
                        knowers=[("horst", "told"), ("elza", "told")])
    eng.facts.add_canon("Ти, Рагнар, прийшов у Брідки, шукаючи роботу й нічліг.",
                        knowers=[(PLAYER, "told")])
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "сталевий меч", True))
    eng.apply_state_change(StateChange(PLAYER, INJURY, "add", "старий шрам під сорочкою", False))
    eng.enter_scene(PLAYER)
    return Campaign(eng, rec, stack.spend, stack.live)
