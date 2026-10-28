"""The Vizima campaign of the app (task 19): the map, the book's canon (task 16), the world around
the scene (task 17), situation A (tavern «Під Лисом», day 3 evening) and a player character who is a
demon without limits (`player_unbounded`): ready for `docs/pilot_vizima_test_plan.md`.

Without a canon store (the file is local and git-ignored) the same campaign starts without canon:
the tavern, the map and the world still work; only the book's people and events are missing.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from harness.canon.retrieve import Canon
from harness.glossary import Glossary
from harness.models import CharacterProfile, Scene
from harness.pipeline import Engine
from harness.profile import load_profile
from harness.style import Style
from harness.world import pilot
from harness.world.pilot import CANON_PLAYER
from harness.world.places import vizima
from harness.world.world import World

from . import campaigns
from .campaigns import CAMPAIGNS, Campaign, Recorder, Stack, Translator, _pointer

TITLE = "Візім · корчма «Під Лисом»"
KIND = "vizima"
INTRO = (
    "Вечір третього дня. Корчма «Під Лисом» гуде: возії, дрібні торговці, двоє стражників, що "
    "зайшли випити по службі. За стійкою кремезний корчмар протирає кухлі й поглядає на двері. "
    "У місті балакають про те, що позавчора сталося за палацовим муром, і про чужинця з білим "
    "волоссям, якого нібито поселили в кордегардії. Ти заходиш і зупиняєшся на порозі."
)
DEFAULT_CANON = "campaigns/canon/pilot_v3.db"


def canon_path(explicit: str | os.PathLike[str] | None = None, *, store: str = "") -> Path | None:
    """The canon store to use: the argument, $HARNESS_CANON_DB, or the local default; None if the
    file is not there. `store`: a start point's own store file (e.g. `be.db` for «Кров ельфів»),
    looked up as $HARNESS_CANON_DB_<NAME> (BE for be.db), the argument when it is that file, else
    next to the argument, to $HARNESS_CANON_DB and to the local default (campaigns/canon)."""
    if explicit is False:  # type: ignore[comparison-overlap]
        return None  # a scenario that must run without canon (the offline regression sessions)
    if not store:
        for c in (explicit, os.environ.get("HARNESS_CANON_DB"), DEFAULT_CANON):
            if c and Path(c).is_file():
                return Path(c)
        return None
    env = os.environ.get("HARNESS_CANON_DB_" + Path(store).stem.upper().replace("-", "_"))
    near = [explicit, os.environ.get("HARNESS_CANON_DB"), DEFAULT_CANON]
    cands = [env, *[c for c in near if c and Path(c).name == store],
             *[Path(c).parent / store for c in near if c]]
    for c in cands:
        if c and Path(c).is_file():
            return Path(c)
    return None


def load_canon(stack: Stack, canon_db: str | os.PathLike[str] | bool | None = None, *,
               store: str = "") -> Canon | None:
    """The canon store of the Vizima arc (or the start's own `store`), or None when it is not
    there."""
    store = canon_path(canon_db, store=store)
    if store is None:
        return None
    embedder = None
    if stack.live and not stack.local:  # local mode: full-text recall only, no network
        from harness.canon.embed import OpenRouterEmbedder
        embedder = OpenRouterEmbedder("qwen/qwen3-embedding-8b")
    return Canon(store, embedder)


def engine_kw(stack: Stack, dialogue: str | None = None) -> dict:
    """What every Witcher campaign's engine gets (new or reopened)."""
    return dict(models=stack.models, judge=stack.judge, glossary=Glossary.for_world("witcher"),
                style=Style.load("witcher"), dialogue=dialogue or campaigns.DIALOGUE,
                world_profile=load_profile("witcher"), world="witcher",
                fast_timeout=stack.fast_timeout)


def create_situation_a(rec: Recorder, root: Path, name: str, canon: Canon | None, kw: dict, *,
                       player: CharacterProfile = CANON_PLAYER, unbounded: bool = True,
                       seed: int | str | None = None, kind: str = KIND,
                       setup: Callable[[Engine], None] | None = None,
                       start: pilot.CanonStart = pilot.SITUATION_A) -> tuple[Engine, object]:
    """A NEW campaign at a canon start (default situation A: the tavern «Під Лисом», day 3
    evening; the others are in worlds/witcher/start_points.yaml): the canon people when the
    store is there, the code-made extras always. Returns the engine and the CanonPlay (None
    without canon). Also used by game packages (app/newgame.py) with their own player;
    `setup(eng)` runs before anyone enters the scene (the player's live state, so the people
    present perceive what is observable)."""
    eng = Engine.create_campaign(
        name, rec, [player], Scene(start.location, (), start.t), root=root,
        player_unlimited=unbounded, outcomes=True, seed=seed if seed is not None else name, **kw)
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("app_kind", json.dumps(kind)))
    if setup is not None:
        setup(eng)
    if canon is not None:
        return eng, pilot.populate_canon_campaign(eng, canon, start)
    _populate_without_canon(eng, start)
    return eng, None


def situation_a_world(eng: Engine, canon: Canon | None, judge: object, play: object = None,
                      start: pilot.CanonStart = pilot.SITUATION_A) -> World:
    """The world around a canon-start campaign (new or reopened)."""
    if canon is not None:
        return pilot.make_canon_world(eng, canon, judge, play=play, start=start)
    return _world_without_canon(eng, start)


def open_vizima(stack: Stack, *, root: Path | str = CAMPAIGNS, new: bool = False,
                name: str | None = None, canon_db: str | os.PathLike[str] | bool | None = None,
                seed: int | str | None = None, dialogue: str | None = None) -> Campaign:
    """Continue the current Vizima campaign, or start a new one at situation A."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    cur = _pointer(root)
    if name is None and not new and cur.exists():
        name = cur.read_text().strip()
    canon = load_canon(stack, canon_db)
    kw = engine_kw(stack, dialogue)
    reopened = bool(name) and not new and Engine.campaign_exists(name, root)
    if reopened:
        eng = Engine.open_campaign(name, rec, root=root, **kw)  # type: ignore[arg-type]
        play = None
    else:
        name = name if (new and name) else time.strftime("vizima-%Y%m%d-%H%M%S")
        while Engine.campaign_exists(name, root):
            name += "x"
        eng, play = create_situation_a(rec, root, name, canon, kw, seed=seed)
    world = situation_a_world(eng, canon, stack.judge, play)
    cur.write_text(name)
    tr = Translator(rec, stack.models.extractor, root / name / "translations.json")
    return Campaign(eng, rec, stack.spend, stack.live, name, tr, title=TITLE, intro=INTRO,
                    world=world)


# The canon people a start puts in the first scene (`here`) have no profile without the canon
# store; the narrator still describes them, and a person who is only described never answers. A
# code-made stand-in keeps the scene whole (slot, occupation, home, look, goal).
_STAND_INS = {
    "char:innkeeper": ("innkeeper", "корчмар", "tavern", "кремезний корчмар за стійкою",
                       "keep the tavern open and stay out of trouble with the guard"),
}


def _stand_ins(start: pilot.CanonStart) -> tuple[tuple[str, str, str, str, str], ...]:
    return tuple(_STAND_INS[c] for c in start.here if c in _STAND_INS)


def _portrait_stand_ins(eng: Engine, start: pilot.CanonStart) -> None:
    """A general-builder start without its canon store: each canon person of the start is made
    from the portrait they play (its name and core), under their canon engine id, so the scene
    keeps the person and the portrait's senses; they carry no canon knowledge."""
    from harness.canon.play import cid_of
    portraits = dict(start.portraits)
    made: list[tuple[str, str]] = []
    for ent, _home, _goal in start.people:
        cid, pid = cid_of(ent), portraits.get(ent)
        port = eng.ctx.portraits.get(pid) if pid else None
        if port is None or cid in eng.profiles:
            continue
        # the portrait's look is the label until the name is learned (a name is knowledge)
        eng.profiles[cid] = CharacterProfile(cid, port.name, " ".join(port.core.split()[:60]),
                                             appearance=port.look)
        made.append((cid, port.id))
    eng._save_setup()
    for cid, pid in made:
        eng.bind_portrait(cid, pid)


def _populate_without_canon(eng: Engine, start: pilot.CanonStart = pilot.SITUATION_A) -> None:
    """No canon store: the same place with the code-made people only (and a stand-in for each
    canon person who would have been here)."""
    if start.general:
        _portrait_stand_ins(eng, start)
    stand = _stand_ins(start)
    for slot, occ, _home, look, _goal in (*start.extras, *stand):
        eng.add_npc(eng.fresh_npc(slot, "northern", occupation=occ, appearance=look), appearance=look)
    for ent, pid in start.portraits:  # a stand-in plays the portrait of the canon person it replaces
        if ent in _STAND_INS and pid in eng.ctx.portraits and ent in start.here:
            eng.bind_portrait(f"npc_{_STAND_INS[ent][0]}", pid)
    ids = {**pilot.canon_extra_ids(start), **{s: f"npc_{s}" for s, *_ in stand}}
    for a, b in start.pairs:
        a, b = ids.get(a, a), ids.get(b, b)
        if a in eng.profiles and b in eng.profiles:
            eng.acquaint(a, b)
    here = [f"npc_{s}" for s, _o, home, _l, _g in stand if home == start.place_id]
    if start.general:
        from harness.canon.play import cid_of
        here += [cid_of(e) for e in start.here if cid_of(e) in eng.profiles]
    for c in (*start.in_scene(), *here, "player"):
        eng.enter_scene(c)


def _world_without_canon(eng: Engine, start: pilot.CanonStart = pilot.SITUATION_A) -> World:
    wmap = start.world_map()
    if start.general:  # the portrait stand-ins live where the canon people would
        cast = {c: h for c, h in start.cast().items() if c in eng.profiles}
        return World(eng, wmap, collectives=[], cast=cast, goals=start.goals())
    stand = _stand_ins(start)
    ids = {**pilot.canon_extra_ids(start), **{s: f"npc_{s}" for s, *_ in stand}}
    cast = {ids[s]: home for s, _o, home, _l, _g in (*start.extras, *stand)}
    goals = {ids[s]: g for s, _o, _h, _l, g in (*start.extras, *stand)}
    return World(eng, wmap, collectives=pilot.canon_collectives(wmap, _NoNames()), cast=cast,
                 goals=goals)


class _NoNames:
    def name(self, eid: str) -> str:
        return eid
