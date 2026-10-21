"""Model stacks: an offline scripted Ukrainian fake (default) and the live OpenRouter stack."""
from __future__ import annotations

import json
import os

import threading

from harness.judge import (
    DecisionJudge, EscalatingJudge, FakeJudge, FallbackJudge, LLMJudge,
)
from harness.director import EXCHANGE_HEADER, NOBODY, PLAYER_FLOOR
from harness.pipeline import ModelConfig
from harness.policy import DEFAULT_JUDGE_FIRST, FALLBACKS, Spend
from harness.providers import Messages, OpenRouterProvider

from .campaigns import Stack


NARRATIONS = [  # (text, observable actions); who speaks is decided by the director (fake rules below)
    ("Дощ барабанить по ґонту, і корчма ніби стискається навколо вогнища. Кремезний сивий чоловік "
     "обтрушує мокрий плащ і довго, оцінююче дивиться на меч біля твоєї руки.",
     ["Горст looks at Рагнар's sword"]),
    ("Жінка в темній хустці нервово м'яє фартух. За сусіднім столом хтось замовкає й прислухається, "
     "а вогонь у каміні тріскає, кидаючи тіні на стіни.", ["Ельза leans closer to the table"]),
    ("Кремезний сивий чоловік кладе на стіл важкий шкіряний кошіль. Глухо дзенькає метал, і жінка "
     "в темній хустці різко підводить очі, ніби це дзенькання вдарило її.",
     ["Горст puts a leather purse on the table"]),
]
LINES = {
    "Горст": [
        "Ти відьмак, так? Не відповідай, бачу по очах. Слухай уважно: вже п'яту ніч на млині "
        "щось виє, і двох наших хлопців знайшли біля греблі. Я дам тобі п'ятдесят оренів, і ще "
        "п'ятдесят, коли повернешся з доказом. Більше в громади немає.",
        "Аванс тридцять оренів. Решту отримаєш у Брідках, від мене особисто. Скажи тільки, що "
        "тобі потрібно: срібло, пастки чи люди, і хлопці все знайдуть до світанку.",
    ],
    "Ельза": [
        "Не слухай його, відьмаку. Він торгується з нами ще до того, як щось зробив. Млин мій, "
        "і я знаю, що там живе. Прийди туди сам, до світанку, і я розповім те, чого він не "
        "скаже при людях.",
        "Тридцять, а як же. Тільки гроші нічого не вирішують, бо чудовисько на млині не питає, "
        "скільки йому заплатили за твою голову, відьмаку.",
    ],
}
GENERIC_LINES = ["Гм. Чого тобі, чужинцю?", "Я вже все сказав. Іди своєю дорогою."]
LOOKS = {  # what the offline stack "reads" from a character file when there is one
    "label": "юнак із золотими очима та мечем",
    "observable": [{"category": "appearance", "item": "golden eyes"},
                   {"category": "appearance", "item": "black claws"}],
    "hidden": [{"category": "appearance", "item": "scars across the back"}],
}
FACTS = [
    "Горст offers the witcher fifty orens and as much again for proof",
    "Ельза urged Рагнар to come to the mill before dawn",
    "Горст put a purse with the advance on the table",
]
CHANGES = [  # one state change per extractor call, then none (the scripted state stays valid)
    {"character": "player", "category": "internal", "op": "add", "item": "wary",
     "observable": False, "source": "narration"},
    {"character": "player", "category": "inventory", "op": "add", "item": "purse with the advance",
     "observable": True, "source": "narration"},
]


class FakeUk:
    """Scripted offline provider, Ukrainian text, any number of turns (it cycles). Thread-safe, so
    the engine's parallel turn runs on it too."""

    parallel_ok = True

    def __init__(self) -> None:
        self.n = {"narrator": 0, "extractor": 0, "actions": 0}
        self.lines: dict[str, int] = {}
        self.calls: list[tuple[str, Messages]] = []
        self._lock = threading.Lock()

    def complete(self, model: str, messages: Messages) -> str:
        sys = messages[0]["content"]
        with self._lock:
            self.calls.append((model, messages))
            if "narrator" in sys:
                text, _ = NARRATIONS[self.n["narrator"] % len(NARRATIONS)]
                self.n["narrator"] += 1
                return text
            if "observable actions" in sys:
                _, acts = NARRATIONS[self.n["actions"] % len(NARRATIONS)]
                self.n["actions"] += 1
                return "\n".join(acts)
            if "You help write characters" in sys:  # manner notes (task 15)
                return "Говорить повільно, зважуючи слова.\nЧасто озирається на двері."
            if "translate" in sys:
                body = json.loads(messages[1]["content"])
                return json.dumps([TRANSLATIONS.get(t, t) for t in body], ensure_ascii=False)
            if "character sheet" in sys:  # the look of the player character (task 14)
                return json.dumps(LOOKS, ensure_ascii=False)
            if "fact extractor" in sys:
                i = self.n["extractor"]
                self.n["extractor"] += 1
                diff = {"new_facts": [{"content": FACTS[i % len(FACTS)], "source": "narration",
                                       "notability": 0.4}],
                        "state_changes": [CHANGES[i]] if i < len(CHANGES) else []}
                return json.dumps(diff, ensure_ascii=False)
            name = sys[8:].split(".")[0]
            lines = LINES.get(name, GENERIC_LINES)  # any other cast (the Vizima campaign)
            i = self.lines.get(name, 0)
            self.lines[name] = i + 1
            return lines[i % len(lines)]

    def stream(self, model, messages):  # type: ignore[no-untyped-def]
        yield self.complete(model, messages)


TRANSLATIONS = {
    "steel sword": "сталевий меч", "old scar under the shirt": "старий шрам під сорочкою",
    "wary": "насторожений", "purse with the advance": "кошіль з авансом",
    "Witchers hunt monsters for coin.": "Відьмаки полюють на чудовиськ за гроші.",
    "For the fifth night in a row something has been howling at the old mill by the dam; two "
    "village boys were found dead by the dam.": "Вже п'яту ніч поспіль на старому млині біля "
    "греблі щось виє; двох хлопців з села знайшли біля греблі мертвими.",
    "The mill belonged to the miller whose widow Ельза still lives nearby.":
        "Млин належав мірошникові, чия вдова Ельза досі живе поруч.",
    "You, Рагнар, came to Брідки looking for work and a bed.":
        "Ти, Рагнар, прийшов у Брідки, шукаючи роботу й нічліг.",
}


def _forms(option: str) -> list[str]:
    """The ways a narration may refer to an option "Name (what is seen)": either part."""
    name, _, rest = option.partition(" (")
    return [name.lower(), rest.rstrip(")").lower()] if rest else [name.lower()]


def fake_judge() -> FakeJudge:
    """Offline judge: no leaks, no speech, not salient, neutral attitudes; the director picks the
    characters the narration names (the first named speaks first)."""
    def first(q, state):  # type: ignore[no-untyped-def]
        text = " ".join(state).split("Narration:")[-1]
        low = text.lower()
        hits = sorted((low.find(f), c) for c, n in q.options.items() if c != "nobody"
                      for f in _forms(n) if f and f in low)
        return hits[0][1] if hits else "nobody"

    def next_floor(q, state):  # type: ignore[no-untyped-def]
        """Living exchange: the first NPC the narration names speaks, then the player's turn."""
        if any(str(x).startswith(EXCHANGE_HEADER) for x in state):
            return PLAYER_FLOOR
        narration = [x for x in state if str(x).startswith("Narration:")]
        npcs = q.__class__(q.kind, q.text, {c: n for c, n in q.options.items()
                                            if c not in (PLAYER_FLOOR, NOBODY)}, tag=q.tag)
        got = first(npcs, narration)
        return got if got != NOBODY else next(iter(npcs.options), NOBODY)

    return FakeJudge({
        "attitude_direction": "neutral", "relationship_magnitude": 0,
        "director_first": first,
        "director_next": next_floor,
        "director_also": lambda q, st: any(
            f in " ".join(st).split("Narration:")[-1].lower()
            for f in _forms(q.text.split(" also ")[0].removeprefix("Would "))),
    })


def fake_stack() -> Stack:
    return Stack(FakeUk(), fake_judge(), ModelConfig("narrator", "npc", "extractor", "judge"))


def live_stack(budget: float = 0.25) -> Stack:
    """The defaults of harness/policy.py (task 9): luna narrator and NPC, deepseek extractor,
    d1-ultra first judge (pplx-decider as its fallback), luna as the escalation judge."""
    from dotenv import load_dotenv

    load_dotenv()  # network and secrets only with --live; the key is never printed
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("--live needs OPENROUTER_API_KEY (env or .env)")
    spend = Spend(budget)
    import uuid

    # one session id per run: OpenRouter routes the whole session to the same endpoint, so the
    # prompt cache of the long, stable prompt prefix is hit (task 19)
    provider = OpenRouterProvider(key, spend=spend, session_id=f"harness-{uuid.uuid4().hex[:16]}")
    models = ModelConfig.live()
    first = FallbackJudge(DecisionJudge(key, DEFAULT_JUDGE_FIRST, spend=spend),
                          DecisionJudge(key, FALLBACKS["judge_first"], spend=spend))
    judge = EscalatingJudge(first, LLMJudge(provider, models.judge, models.judge_fallback))
    return Stack(provider, judge, models, spend, live=True)
