"""The Vizima pilot setup (task 17): the map, a small cast, the collectives, an evening in the
tavern «Під Лисом», and a player character who is a demon without limits. Used by the live check
and available to the app. Records are English, names Ukrainian (task 10)."""
from __future__ import annotations

from typing import Any

from ..judge import Judge
from ..models import PLAYER, CharacterProfile, Scene
from ..pipeline import Engine, ModelConfig
from ..providers import Provider
from .canon_adapter import CanonSource
from .places import vizima
from .world import World, pilot_collectives

START_TIME = 2 * 24 * 60 + 20 * 60  # day 3, 20:00 (situation A, the evening)
HOME = {"innkeeper": "tavern", "brann": "tavern", "vatsko": "tavern", "myrra": "market",
        "sergeant": "guardhouse"}
GOALS = {
    "innkeeper": "keep the tavern open and stay out of trouble with the guard",
    "brann": "do his duty to the city guard and report anything dangerous to the sergeant",
    "myrra": "sell cloth at the market and hear every piece of news first",
    "sergeant": "keep order in Vizima and answer to Velerad",
}


def profiles() -> list[CharacterProfile]:
    return [
        CharacterProfile(PLAYER, "Демон", "A demon in human shape, a being without limits."),
        CharacterProfile("innkeeper", "Ярош", "Keeper of the tavern «Під Лисом». Heavy, careful, "
                         "afraid for his licence and his roof."),
        CharacterProfile("brann", "Бран", "A city guardsman off duty, drinking in the tavern. "
                         "Loyal to his sergeant, not very brave."),
        CharacterProfile("vatsko", "Вацко", "A regular drunk of the tavern, a carter. Believes "
                         "in nothing he cannot drink."),
        CharacterProfile("myrra", "Мірра", "A cloth seller at the Vizima market, sharp and "
                         "talkative."),
        CharacterProfile("sergeant", "Сержант Ґрім", "Sergeant of the city guard at the "
                         "guardhouse by the palace, gruff, practical."),
    ]


def build(provider: Provider, judge: Judge, models: ModelConfig, *, canon: CanonSource | None = None,
          style: Any = None, **engine_kw: Any) -> tuple[Engine, World]:
    scene = Scene("корчма «Під Лисом»", ("innkeeper", "brann", "vatsko"), START_TIME)
    eng = Engine(provider, profiles(), scene, models=models, judge=judge, style=style,
                 player_unlimited=True, **engine_kw)
    wmap = vizima()
    for a, b in (("innkeeper", "brann"), ("innkeeper", "vatsko"), ("brann", "vatsko")):
        eng.acquaint(a, b)
    eng.facts.add_canon("Vizima is the capital of Temeria; King Foltest rules from the old palace.",
                        knowers=[(c, "told") for c in HOME])
    eng.facts.add_canon("The city guard answers to Velerad, the king's officer for order.",
                        knowers=[(c, "told") for c in HOME])
    eng.enter_scene(PLAYER)
    world = World(eng, wmap, collectives=pilot_collectives(wmap), cast=HOME, goals=GOALS,
                  canon=canon)
    return eng, world
