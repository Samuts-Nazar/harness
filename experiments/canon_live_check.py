"""Live check (task 16): start at situation A (day 3 evening, tavern «Під Лисом»), 5 turns, then show what the
innkeeper and a guard know and from where; one lazy background judgment; the scheduled canon events.

    PYTHONPATH=. python3 experiments/canon_live_check.py
"""
import json
import os

from dotenv import load_dotenv

from harness.canon.embed import OpenRouterEmbedder
from harness.canon.play import CanonPlay, what_knows
from harness.canon.retrieve import Canon
from harness.glossary import Glossary
from harness.judge import DecisionJudge, EscalatingJudge, FallbackJudge, LLMJudge
from harness.models import PLAYER, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.policy import FALLBACKS, DEFAULT_JUDGE_FIRST, Spend
from harness.providers import OpenRouterProvider

load_dotenv(".env")
key = os.environ["OPENROUTER_API_KEY"]
spend = Spend(0.30)
prov = OpenRouterProvider(key, spend=spend)
models = ModelConfig.live()
first = FallbackJudge(DecisionJudge(key, DEFAULT_JUDGE_FIRST, spend=spend), DecisionJudge(key, FALLBACKS["judge_first"], spend=spend))
judge = EscalatingJudge(first, LLMJudge(prov, models.judge, models.judge_fallback))

canon = Canon("campaigns/canon/pilot_v3.db", OpenRouterEmbedder("qwen/qwen3-embedding-8b"))
play = CanonPlay.at(canon, 3, 19, "place:pid-lysom")
player = CharacterProfile(PLAYER, "Раґнар", "Демон без меж у людській подобі.", appearance="чорнявий чужинець із золотими очима")
eng = Engine(prov, [player], Scene("корчма «Під Лисом», Визім", (PLAYER,), time=0), models=models, judge=judge,
             glossary=Glossary.for_world("witcher"))
play.install(eng, ["char:innkeeper"])
play.ensure_character(eng, "char:vizim-guards", cid="guard", member_of=["coll:vizim-guards"])
eng.profiles["guard"] = CharacterProfile("guard", "стражник", "Міський стражник, що зайшов випити.")
eng.enter_scene("innkeeper")
eng.enter_scene("guard")
eng.canon_guard = play.guard(judge)

TURNS = ["Заходжу до корчми, сідаю біля стійки й замовляю пива.",
         "Питаю корчмаря, що тут сталося позавчора.",
         "Питаю стражника, що він чув про відьмака, який нині в палаці.",
         "Питаю корчмаря, скільки коштує кімната на тиждень і хто в нього зазвичай ночує.",
         "Питаю обох, звідки в місті взялася стриґа і хто така Адда."]
for i, t in enumerate(TURNS, 1):
    res = eng.turn(t)
    print(f"\n=== turn {i}: {t}\n{res.narration}")
    for u in res.utterances:
        print(f"  {u.payload['speaker']}: {u.payload['text']}")

b = play.know_from_life(eng, "char:innkeeper", "ціни на постій і хто ночує в корчмі", judge)
print("\nbackground:", b)
c = play.know_from_life(eng, "char:innkeeper", "що замислив король щодо шлюбу принцеси", judge)
print("background (court matter):", c)

for who in ("innkeeper", "guard"):
    print(f"\n--- {who} knows")
    for k in what_knows(eng, who):
        print(f"  [{k['how']}{' <' + k['source'] if k['source'] else ''}] {k['text'][:150]}")
print("\n--- scheduled canon events after the start")
for e in play.upcoming(0)[:6]:
    print(f"  campaign t={play.start.to_campaign_t(e.t)} day {e.day} @ {e.place_name}: {e.summary[:100]}")
g = eng.canon_guard
print("\ndrift guard: rejected", len(g.rejected), "justified", len(g.drift))
for r in g.rejected:
    print("  rejected:", r["kind"], r["speaker"], r["text"][:120])
print("devlog kinds:", [n["kind"] for n in eng.devlog])
print("spend USD:", round(spend.total, 4))
