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

from harness.canon.retrieve import Canon
from harness.glossary import Glossary
from harness.models import Scene
from harness.pipeline import Engine
from harness.style import Style
from harness.world import pilot
from harness.world.pilot import CANON_PLAYER, START_TIME
from harness.world.places import vizima
from harness.world.world import World

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


def canon_path(explicit: str | os.PathLike[str] | None = None) -> Path | None:
    """The canon store to use: the argument, $HARNESS_CANON_DB, or the local default; None if the
    file is not there."""
    if explicit is False:  # type: ignore[comparison-overlap]
        return None  # a scenario that must run without canon (the offline regression sessions)
    for c in (explicit, os.environ.get("HARNESS_CANON_DB"), DEFAULT_CANON):
        if c and Path(c).is_file():
            return Path(c)
    return None


def open_vizima(stack: Stack, *, root: Path | str = CAMPAIGNS, new: bool = False,
                name: str | None = None, canon_db: str | os.PathLike[str] | bool | None = None,
                seed: int | str | None = None) -> Campaign:
    """Continue the current Vizima campaign, or start a new one at situation A."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    cur = _pointer(root)
    if name is None and not new and cur.exists():
        name = cur.read_text().strip()
    store = canon_path(canon_db)
    canon = None
    if store is not None:
        embedder = None
        if stack.live:
            from harness.canon.embed import OpenRouterEmbedder
            embedder = OpenRouterEmbedder("qwen/qwen3-embedding-8b")
        canon = Canon(store, embedder)
    kw = dict(models=stack.models, judge=stack.judge, glossary=Glossary.for_world("witcher"),
              style=Style.load("witcher"))
    reopened = bool(name) and not new and Engine.campaign_exists(name, root)
    if reopened:
        eng = Engine.open_campaign(name, rec, root=root, **kw)  # type: ignore[arg-type]
        play = None
    else:
        name = name if (new and name) else time.strftime("vizima-%Y%m%d-%H%M%S")
        while Engine.campaign_exists(name, root):
            name += "x"
        eng = Engine.create_campaign(
            name, rec, [CANON_PLAYER], Scene("корчма «Під Лисом»", (), START_TIME), root=root,
            player_unlimited=True, outcomes=True, seed=seed if seed is not None else name, **kw)
        with eng.conn:
            eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                             ("app_kind", json.dumps(KIND)))
        if canon is not None:
            play = pilot.populate_canon_campaign(eng, canon)
        else:
            play = None
            _populate_without_canon(eng)
    if canon is not None:
        world = pilot.make_canon_world(eng, canon, stack.judge, play=play)
    else:
        world = _world_without_canon(eng)
    cur.write_text(name)
    tr = Translator(rec, stack.models.extractor, root / name / "translations.json")
    return Campaign(eng, rec, stack.spend, stack.live, name, tr, title=TITLE, intro=INTRO,
                    world=world)


def _populate_without_canon(eng: Engine) -> None:
    """No canon store: the same tavern with the code-made people only."""
    for slot, occ, _home, look, _goal in pilot.EXTRA_CAST:
        eng.add_npc(eng.fresh_npc(slot, "northern", occupation=occ), appearance=look)
    ids = pilot.canon_extra_ids()
    eng.acquaint(ids["guard"], ids["drunk"])
    for c in (ids["guard"], ids["drunk"], "player"):
        eng.enter_scene(c)


def _world_without_canon(eng: Engine) -> World:
    wmap = vizima()
    ids = pilot.canon_extra_ids()
    cast = {ids[s]: home for s, _o, home, _l, _g in pilot.EXTRA_CAST}
    goals = {ids[s]: g for s, _o, _h, _l, g in pilot.EXTRA_CAST}
    return World(eng, wmap, collectives=pilot.canon_collectives(wmap, _NoNames()), cast=cast,
                 goals=goals)


class _NoNames:
    def name(self, eid: str) -> str:
        return eid
