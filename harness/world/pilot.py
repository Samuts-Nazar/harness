"""The Vizima pilot setup (task 17): the map, a small cast, the collectives, an evening in the
tavern «Під Лисом», and a player character who is a demon without limits. Used by the live check
and available to the app. Records are English, names Ukrainian (task 10)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ..judge import Judge
from ..models import PLAYER, CharacterProfile, Scene
from ..pipeline import Engine, ModelConfig
from ..providers import Provider
from .canon_adapter import CanonSource
from .places import VIZIMA_EXTRA, vizima
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


# -- the pilot on the real canon (task 19) -----------------------------------------------------
# Situation A of the Vizima arc: the tavern «Під Лисом», day 3 evening. The campaign clock is the
# story clock (offset 0), so "день 3, 20:00" is the same in the book's calendar and on screen.
CANON_PLACES = {
    "place:pid-lysom": "tavern", "place:old-palace": "palace", "place:new-palace": "palace",
    "place:crypt": "palace", "place:guardroom": "guardhouse", "place:lynvar-gate": "gate",
    "place:vizim": "market", "place:old-narakort": "market",
    "place:кабінет-бургомістра": "office", "place:зал-де-король-приймає": "palace",
    "place:головна-зала": "palace", "place:подвір-я-старого-палацу": "palace",
    "place:зруйнована-кімната-старого-палацу": "palace",
}
CANON_GROUPS = {"coll:vizim-guards": "vizim_guards", "coll:vizim-townsfolk": "vizim_townsfolk",
                "coll:vizim-officials": "vizim_guards"}
# non-canon people of the scene: names, traits, voice and age come from the code tables
EXTRA_CAST = (  # (slot, occupation, home place, appearance, goal)
    ("guard", "міський вартовий", "tavern", "вартовий без шолома, з кухлем",
     "do his duty to the city guard and report anything dangerous to the sergeant"),
    ("drunk", "візник", "tavern", "п'яний візник у кутку",
     "drink in peace and not be thrown out"),
    ("trader", "торговка тканиною", "market", "жінка з ринку, що продає тканину",
     "sell cloth at the market and hear every piece of news first"),
    ("sergeant", "сержант варти", "guardhouse", "кремезний сержант із кордегардії",
     "keep order in Vizima and answer to Velerad"),
)
CANON_PLAYER = CharacterProfile(
    PLAYER, "Демон", "A demon in human shape, a being without limits.",
    appearance="чорнявий чужинець із золотими очима")


@dataclass(frozen=True)
class CanonStart:
    """A canon start moment of the Vizima arc: when (story minutes), where (canon place and map
    place), which canon people stand in the scene and which seeded locals live where. Situation A
    is the default; the others come from worlds/witcher/start_points.yaml (`from_dict`)."""
    id: str = "vidmak_A_tavern"
    t: int = START_TIME
    canon_place: str = "place:pid-lysom"
    place_id: str = "tavern"                  # the map place of the first scene
    here: tuple[str, ...] = ("char:innkeeper",)   # canon people in the first scene
    extras: tuple[tuple[str, str, str, str, str], ...] = EXTRA_CAST  # (slot, occupation, home, look, goal)
    pairs: tuple[tuple[str, str], ...] = (("guard", "drunk"), ("innkeeper", "guard"),
                                          ("innkeeper", "drunk"))  # who knows whom (slot or cid)
    intro: str = ""
    portraits: tuple[tuple[str, str], ...] = ()   # (canon entity, portrait id): who plays a portrait

    @classmethod
    def from_dict(cls, cid: str, d: dict[str, Any]) -> "CanonStart":
        h, m = str(d.get("time", "00:00")).split(":")
        extras = tuple((str(x["slot"]), str(x["occupation"]), str(x.get("home", d["map_place"])),
                        str(x["look"]), str(x["goal"])) for x in d.get("extras", []))
        return cls(cid, (int(d["day"]) - 1) * 1440 + int(h) * 60 + int(m), str(d["canon_place"]),
                   str(d["map_place"]), tuple(d.get("here", [])), extras,
                   tuple((str(a), str(b)) for a, b in d.get("acquainted", [])),
                   str(d.get("situation", "")),
                   tuple((str(k), str(v)) for k, v in (d.get("portraits") or {}).items()))

    @property
    def map_extra(self) -> tuple[str, ...]:
        """The extra Vizima map places this start needs (see `places.VIZIMA_EXTRA`)."""
        return (self.place_id,) if self.place_id in VIZIMA_EXTRA else ()

    def world_map(self) -> Any:
        return vizima(*self.map_extra)

    @property
    def location(self) -> str:
        return self.world_map().name(self.place_id)

    def in_scene(self) -> list[str]:
        """The seeded locals standing in the first scene (their home is the start place)."""
        return [f"npc_{slot}" for slot, _o, home, _l, _g in self.extras if home == self.place_id]


SITUATION_A = CanonStart()


def canon_collectives(wmap: Any, canon: Any) -> list[Any]:
    """The town, the guard, Velerad and the king: task 16's canon characters (names from the store)."""
    from .world import Collective

    def nm(ent: str, default: str) -> str:
        try:
            got = canon.name(ent)
            return got if got and got != ent else default
        except Exception:  # noqa: BLE001 - a store without this entity
            return default

    return [
        Collective("vizim_townsfolk", nm("coll:vizim-townsfolk", "мешканці Визіма"), "market",
                   "town", tuple(wmap.places),
                   role="the townsfolk of Vizima: traders, craftsmen, drinkers, gossips"),
        Collective("vizim_guards", nm("coll:vizim-guards", "стражники"), "guardhouse",
                   "authority", ("gate",), up="velerad",
                   role="the city guard, practical and wary of trouble"),
        Collective("velerad", nm("char:velerad", "Велерад"), "palace", "authority", up="foltest",
                   role="Velerad, the king's chief officer for order, cautious and well informed"),
        Collective("foltest", nm("char:foltest", "Фольтест"), "palace", "authority",
                   role="Foltest, the king of Temeria, in his palace"),
    ]


def canon_extra_ids(start: CanonStart = SITUATION_A) -> dict[str, str]:
    return {slot: f"npc_{slot}" for slot, *_ in start.extras}


def populate_canon_campaign(eng: Engine, canon: Any, start: CanonStart = SITUATION_A) -> Any:
    """A NEW campaign at a canon start (situation A by default): the canon people made with what
    they knew at that time, the code-made extras, the first scene. Returns the CanonPlay."""
    from ..canon.api import CanonCampaign
    from ..canon.play import CanonPlay, cid_of

    play = CanonPlay(canon, CanonCampaign(start_t=start.t, place=start.canon_place, offset=0),
                     portraits=dict(start.portraits))
    for ent, cid in (("char:innkeeper", "innkeeper"), ("char:velerad", "velerad"),
                     ("char:foltest", "foltest"), *CANON_GROUPS.items()):
        try:
            play.ensure_character(eng, ent, cid=cid)
        except Exception as e:  # noqa: BLE001 - a store without this person: the scene still runs
            eng._note("canon_person_missing", entity=ent, error=str(e)[:100])
    for slot, occ, _home, look, _goal in start.extras:
        eng.add_npc(eng.fresh_npc(slot, "northern", occupation=occ, appearance=look), appearance=look)
    ids = canon_extra_ids(start)
    here = [cid_of(e) for e in start.here if cid_of(e) in eng.profiles]
    for a, b in start.pairs:
        a, b = ids.get(a, a), ids.get(b, b)
        if a in eng.profiles and b in eng.profiles:
            eng.acquaint(a, b)
    for c in (*here, *start.in_scene(), PLAYER):
        eng.enter_scene(c)
    return play


def make_canon_world(eng: Engine, canon: Any, judge: Judge, *, play: Any = None,
                     start: CanonStart = SITUATION_A) -> World:
    """The world around an engine that was populated by `populate_canon_campaign` (also after a
    reopen: everything the world knows is derived from the log)."""
    from ..canon.api import CanonCampaign
    from ..canon.play import CanonPlay, cid_of
    from .canon_adapter import PlayCanon

    if play is None:
        play = CanonPlay(canon, CanonCampaign(start_t=start.t, place=start.canon_place, offset=0),
                         portraits=dict(start.portraits))
        for ent in ("char:innkeeper", "char:velerad", "char:foltest", *CANON_GROUPS):
            cid = CANON_GROUPS.get(ent) or cid_of(ent)
            if cid in eng.profiles:
                play.made[ent] = cid
    wmap = start.world_map()
    ids = canon_extra_ids(start)
    cast = {"innkeeper": "tavern", **{ids[s]: home for s, _o, home, _l, _g in start.extras}}
    goals = {ids[s]: g for s, _o, _h, _l, g in start.extras}
    goals["innkeeper"] = "keep the tavern open and stay out of trouble with the guard"
    pc = PlayCanon(play, judge, places=CANON_PLACES, groups=CANON_GROUPS,
                   text_call=lambda prompt: eng._complete(
                       "judge", [{"role": "user", "content": prompt}]))
    world = World(eng, wmap, collectives=canon_collectives(wmap, canon), cast=cast, goals=goals,
                  canon=pc)
    try:
        eng.canon_guard = play.guard(judge)
    except Exception:  # noqa: BLE001
        eng.canon_guard = None
    # people the narration brings in (living dialogue task 9): the canon calendar says whether a
    # canon person can be here; whoever can is admitted to the scene, passers-by from npcgen
    from ..canon.play import CanonCast
    from ..scene_cast import SceneCast
    eng.scene_cast = SceneCast(CanonCast(play, places=CANON_PLACES), culture="northern",
                               where=world.where, here=world.here)
    return world
