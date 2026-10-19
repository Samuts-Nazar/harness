"""Task 15 bake-off situations, rendered with the real ContextBuilder (old / new / new+exemplars).

Ten NPC moments: three at the inn (Горст opens, Ельза answers, Горст haggles) and seven from the
task 7 set. Three narrator moments at the inn. Contexts are the engine's own (English seed records
with Ukrainian names for the inn; the task 7 Ukrainian records for the rest).
"""
from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from app.campaigns import INTRO, SEEDS, START_TIME, TITLE, profiles as inn_profiles
from harness.glossary import Glossary
from harness.models import HEARD, NARRATION, PLAYER, WITNESSED, CharacterProfile, Scene
from harness.pipeline import Engine
from harness.providers import FakeProvider
from harness.style import Style

TS = Path(__file__).resolve().parents[1] / "bakeoff" / "testset"
NPC_SET = {i["id"]: i for i in json.loads((TS / "npc.json").read_text())}
PROF = json.loads((TS / "profiles.json").read_text())
G = Glossary.for_world("witcher")

HORST_OLD = ("Є справа. П’яту ніч поспіль виє біля старого млина, а двох хлопців знайшли мертвими "
             "коло греблі. Ми хочемо, щоб ти з’ясував, що там водиться, і поклав тому край. За "
             "плату, звісно. Скільки коштує твоя робота, Рагнаре?")

INN = {  # id -> (npc, prior lines [(speaker, text)], note)
    "i1": ("horst", [(PLAYER, "Сідайте. Я слухаю вас.")], "Горст відкриває розмову"),
    "i2": ("elza", [(PLAYER, "Сідайте. Я слухаю вас."), ("horst", HORST_OLD),
                    (PLAYER, "А ви що скажете, пані? Ви ж не просто так прийшли.")],
           "Ельза відповідає"),
    "i3": ("horst", [(PLAYER, "Сідайте. Я слухаю вас."), ("horst", HORST_OLD),
                     (PLAYER, "П'ятдесят оренів за двох мертвих хлопців і те, що виє? Ні. "
                              "Сто п'ятдесят.")], "Горст торгується"),
}
TASK7 = ["c03", "c07", "c08", "c11", "c05", "c06", "c10"]

NARR = {
    "n1": ("Я киваю їм на лаву навпроти й кладу долоню на меч. Мовчу.", None),
    "n2": ("Я дивлюся на Горста й роблю вигляд, що зважую, чи мені взагалі це потрібно.", None),
    "n3": ("Я виходжу з корчми під дощ і йду до старого млина.", "Греблі біля млина"),
}


def _engine(profs: list[CharacterProfile], scene: Scene) -> Engine:
    return Engine(FakeProvider(), profs, scene, glossary=G)


def inn_engine(iid: str) -> tuple[Engine, str]:
    npc, prior, _ = INN[iid]
    eng = _engine(inn_profiles(), Scene(TITLE, (PLAYER, "horst", "elza"), START_TIME))
    for text, who in SEEDS:
        eng.facts.add_canon(text, knowers=[(k, "told") for k in who])
    eng._event(NARRATION, [], {"text": INTRO}, witnesses=[])
    for speaker, text in prior:
        eng._utterance(speaker, text)
    return eng, npc


def task7_engine(iid: str) -> tuple[Engine, str]:
    it = NPC_SET[iid]
    names = PROF["names"]
    profs = [CharacterProfile(c, names.get(c, c), PROF["profiles"].get(c, "")) for c in it["present"]]
    profs = [replace(p, description="Мандрівник, гравець.") if p.id == PLAYER else p for p in profs]
    eng = _engine(profs, Scene(it["location"], tuple(it["present"]), 3 * 24 * 60 + 19 * 60))
    for text, src in it["knows"]:
        how = HEARD if src else WITNESSED
        eng.facts.add_canon(text, knowers=[(it["npc"], how, src) if src else (it["npc"], how)])
    for speaker, text in it["recent"]:
        eng._utterance(speaker, text)
    return eng, it["npc"]


def narrator_engine(nid: str) -> tuple[Engine, str]:
    text, loc = NARR[nid]
    eng = _engine(inn_profiles(), Scene(loc or TITLE, (PLAYER, "horst", "elza"), START_TIME))
    for t, who in SEEDS:
        eng.facts.add_canon(t, knowers=[(k, "told") for k in who])
    eng._event(NARRATION, [], {"text": INTRO}, witnesses=[])
    return eng, text


def npc_ids() -> list[str]:
    return [*INN, *TASK7]


def npc_messages(iid: str, variant: str, manners: dict[str, str], style_ex: Style, style_plain: Style
                 ) -> list[dict[str, str]]:
    eng, npc = inn_engine(iid) if iid in INN else task7_engine(iid)
    if variant != "old":
        eng.ctx.style = style_ex if variant == "ex" else style_plain
        p = eng.profiles[npc]
        eng.profiles[npc] = replace(p, manner=manners.get(npc, ""))
    return eng.ctx.character_view(npc, eng.scene).messages()


def narrator_messages(nid: str, variant: str, style_ex: Style, style_plain: Style
                      ) -> list[dict[str, str]]:
    eng, text = narrator_engine(nid)
    eng.ctx.narration = "prose"
    if variant != "old":
        eng.ctx.style = style_ex if variant == "ex" else style_plain
    return eng.ctx.narrator(eng.scene, text)
