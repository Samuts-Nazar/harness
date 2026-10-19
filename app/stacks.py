"""Model stacks: an offline scripted Ukrainian fake (default) and the live OpenRouter stack."""
from __future__ import annotations

import json
import os

from harness.judge import EscalatingJudge, JevJudge, LLMJudge, default_fake_judge
from harness.pipeline import ModelConfig
from harness.policy import DEFAULT_JEV, Spend
from harness.providers import Messages, OpenRouterProvider

from .campaigns import Stack

# Models chosen by the task 7 bake-off (docs/tools.md, Models). Defined here, not imported from
# harness.policy, because that module is being updated by task 9; after its merge these can
# move back to the policy defaults. The first judge (liquid/d1-ultra) needs task 9's generic
# decision client, so Jev stays the first judge until then.
NARRATOR_MODEL = NPC_MODEL = JUDGE_LLM_MODEL = "openai/gpt-6-luna"
EXTRACTOR_MODEL = "deepseek/deepseek-v4.1-flash-1017"

NARRATIONS = [
    (["horst"], "Дощ барабанить по ґонту, і корчма ніби стискається навколо вогнища. Горст "
     "обтрушує мокрий плащ і довго, оцінююче дивиться на меч біля твоєї руки.",
     ["Горст дивиться на меч Рагнара"]),
    (["elza"], "Ельза нервово м'яє фартух. За сусіднім столом хтось замовкає й прислухається, "
     "а вогонь у каміні тріскає, кидаючи тіні на стіни.",
     ["Ельза нахиляється ближче до столу"]),
    (["horst", "elza"], "Горст кладе на стіл важкий шкіряний кошіль. Глухо дзенькає метал, і "
     "Ельза різко підводить очі, ніби це дзенькання вдарило її.",
     ["Горст кладе кошіль на стіл"]),
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
FACTS = [
    "Горст пропонує відьмакові п'ятдесят оренів і ще стільки ж за доказ",
    "Ельза закликала Рагнара прийти на млин до світанку",
    "Горст виклав на стіл кошіль із авансом",
]
CHANGES = [  # one state change per extractor call, then none (the scripted state stays valid)
    {"character": "player", "category": "internal", "op": "add", "item": "насторожений",
     "observable": False, "source": "narration"},
    {"character": "player", "category": "inventory", "op": "add", "item": "кошіль з аванс-грошима",
     "observable": True, "source": "narration"},
]


class FakeUk:
    """Scripted offline provider, Ukrainian text, any number of turns (it cycles)."""

    def __init__(self) -> None:
        self.n = {"narrator": 0, "extractor": 0}
        self.lines: dict[str, int] = {}
        self.calls: list[tuple[str, Messages]] = []

    def complete(self, model: str, messages: Messages) -> str:
        self.calls.append((model, messages))
        sys = messages[0]["content"]
        if "narrator" in sys:
            speakers, text, acts = NARRATIONS[self.n["narrator"] % len(NARRATIONS)]
            self.n["narrator"] += 1
            return json.dumps({"description": text, "observable_actions": acts,
                               "speakers": speakers}, ensure_ascii=False)
        if "fact extractor" in sys:
            i = self.n["extractor"]
            self.n["extractor"] += 1
            diff = {"new_facts": [{"content": FACTS[i % len(FACTS)], "source": "narration",
                                   "notability": 0.4}],
                    "state_changes": [CHANGES[i]] if i < len(CHANGES) else []}
            return json.dumps(diff, ensure_ascii=False)
        name = sys[8:].split(".")[0]
        i = self.lines.get(name, 0)
        self.lines[name] = i + 1
        return LINES[name][i % len(LINES[name])]

    def stream(self, model, messages):  # type: ignore[no-untyped-def]
        yield self.complete(model, messages)


def fake_stack() -> Stack:
    return Stack(FakeUk(), default_fake_judge(), ModelConfig("narrator", "npc", "extractor", "judge"))


def live_stack(budget: float = 0.25, narrator: str = NARRATOR_MODEL, npc: str = NPC_MODEL,
               extractor: str = EXTRACTOR_MODEL, judge_llm: str = JUDGE_LLM_MODEL,
               jev: str = DEFAULT_JEV) -> Stack:
    from dotenv import load_dotenv

    load_dotenv()  # network and secrets only with --live; the key is never printed
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise SystemExit("--live needs OPENROUTER_API_KEY (env or .env)")
    spend = Spend(budget)
    provider = OpenRouterProvider(key, spend=spend)
    models = ModelConfig(narrator, npc, extractor, judge_llm)
    judge = EscalatingJudge(JevJudge(key, jev, spend=spend), LLMJudge(provider, judge_llm))
    return Stack(provider, judge, models, spend, live=True)
