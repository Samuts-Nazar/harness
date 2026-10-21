"""Characters the narration brings into a scene (living dialogue, task 9).

The narrator may write a person into the scene who is not a scene character (in the Vizima pilot
it wrote Ґеральт into «Під Лисом»). Such a person could never speak and the director could never
pick them. After the narrator, before delivery, `SceneCast.review` finds the people the
narration shows present who are not in the scene (one cheap list call; the model only lists, code
decides) and decides for each:

- someone already in the scene (by name or appearance): nothing to do;
- a known character who is not here: walking in from nearby (`scene.outside`) is fine; else the
  world says where they are (`where`), and elsewhere means drift; no information: a typed
  plausibility judgment;
- a canon person: the canon calendar (`CastSource.whereabouts`) says where they are at this time;
  elsewhere means drift; no canon event near this time: a typed plausibility judgment;
- anyone else is an invented passer-by: a generated NPC (harness/npcgen.py) whose label is how
  the narration showed them.

Drift rejects the narration with a note for the narrator; the others are admitted by the engine
(`Engine.enter_scene`), so they can speak and the director can choose them. A person is shown by
appearance until the player character learns the name (harness/names.py).

The world-specific part (the canon store, the map) comes in through `CastSource` and the
`where`/`here` callbacks; this module knows no world.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Protocol

from .judge import JudgeError, choice_q, yes_no_q
from .models import PLAYER, format_time

if TYPE_CHECKING:
    from .pipeline import Engine

HERE, ELSEWHERE, UNKNOWN = "here", "elsewhere", "unknown"
MAX_PEOPLE = 4  # a narration that brings in more is listed only this far

LIST_PROMPT = """Below is a passage of narration from a role-playing game, and the people who are in the scene now.

In the scene now: {present}
Location: {location}

Narration:
{narration}

List every OTHER person the narration shows physically present at this place right now (seen, heard or acting here). Not the people listed above, not anyone only mentioned, remembered, talked about or imagined, not animals.
One person per line: the name exactly as the narration writes it if it names them, otherwise a short description of how they look, in the narration's language (for example: худий хлопчик-посильний). Nothing else on the line.
If there is nobody else, answer: none"""


@dataclass(frozen=True)
class Whereabouts:
    """Where a person is at a time: HERE (the scene's place), ELSEWHERE (with a reason, for the
    narrator's note) or UNKNOWN (nothing says)."""
    status: str
    reason: str = ""


class CastSource(Protocol):
    """Canon people for `SceneCast` (harness/canon/play.py `CanonCast` is the real one)."""

    def identify(self, mention: str) -> str | None: ...       # canon person entity, or None
    def cid(self, entity: str) -> str: ...                    # the engine character id
    def whereabouts(self, entity: str, t: int, here_place: str | None,
                    here_name: str) -> Whereabouts: ...       # t: campaign minutes
    def describe(self, entity: str) -> str: ...               # who they are, for a judgment
    def admit(self, eng: "Engine", entity: str) -> str: ...   # create the character, return id


@dataclass
class Admission:
    """One person to bring into the scene. kind: "known" (cid set), "canon" (entity set) or
    "passer_by" (label set; sex from the judgment)."""
    kind: str
    mention: str
    cid: str | None = None
    entity: str | None = None
    label: str = ""
    sex: str | None = None


@dataclass
class Review:
    """`reject`: why the narration is drift (the note for the narrator), None if it stands.
    `admit`: who comes into the scene when it stands."""
    reject: str | None = None
    admit: list[Admission] = field(default_factory=list)
    people: list[str] = field(default_factory=list)


def parse_people(raw: str, limit: int = MAX_PEOPLE) -> list[str]:
    """The lister's lines: bullets, numbers and a trailing "(...)" removed; "none" means none."""
    out: list[str] = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip().strip('"«»').strip()
        line = re.sub(r"\s*\([^)]*\)\s*$", "", line).strip()
        if not line or line.lower().rstrip(".") in ("none", "немає", "нікого", "-"):
            continue
        if line not in out:
            out.append(line)
    return out[:limit]


def _same_look(a: str, b: str) -> bool:
    a, b = a.strip().lower(), b.strip().lower()
    return bool(a and b) and (a in b or b in a)


class SceneCast:
    """`source`: canon people (None: no canon). `culture`: the npcgen culture of passers-by.
    `where(cid)`: the world's place id of a character who is not here (None: unknown);
    `here()`: the world's place id of the scene."""

    def __init__(self, source: CastSource | None = None, *, culture: str,
                 where: Callable[[str], str | None] | None = None,
                 here: Callable[[], str | None] | None = None) -> None:
        self.source, self.culture, self.where, self.here = source, culture, where, here
        self._walkins = 0

    # -- finding the people ------------------------------------------------------------------
    def messages(self, eng: "Engine", narration: str) -> list[dict[str, str]]:
        sc = eng.scene
        present = "; ".join(eng.names.describe(c) + (" (the player character)" if c == PLAYER
                                                      else "") for c in sc.present)
        return [{"role": "user", "content": LIST_PROMPT.format(
            present=present or "nobody", location=sc.location, narration=narration)}]

    def _in_scene(self, eng: "Engine", mention: str) -> bool:
        for c in eng.scene.present:
            if eng.names._pattern(c).search(mention) or (
                    eng.names.hidden(c) and _same_look(mention, eng.names.label(c))):
                return True
            if mention.strip().lower() == eng.names.real(c).lower():
                return True
        return False

    def _profile_of(self, eng: "Engine", mention: str) -> str | None:
        """A known character (not in the scene) the mention names or matches by appearance."""
        for c in eng.profiles:
            if c == PLAYER or c in eng.scene.present:
                continue
            if eng.names._pattern(c).search(mention) or (
                    eng.names.hidden(c) and _same_look(mention, eng.names.label(c))):
                return c
        return None

    # -- the review --------------------------------------------------------------------------
    def review(self, eng: "Engine", narration: str) -> Review:
        """Main thread (reads the log and the world). One list call, then at most one batched
        judgment for the people nothing else decides."""
        try:
            raw = eng._complete("extractor", self.messages(eng, narration))
        except Exception as e:  # noqa: BLE001 - no list: the narration stands as before
            eng._note("scene_cast_unavailable", error=str(e)[:200])
            return Review()
        people = [p for p in parse_people(raw) if not self._in_scene(eng, p)]
        rv = Review(people=people)
        sc = eng.scene
        drift: list[str] = []
        ask: dict[str, Any] = {}
        pending: dict[str, Admission] = {}
        for i, m in enumerate(people):
            entity = self.source.identify(m) if self.source is not None else None
            cid = self.source.cid(entity) if entity is not None else self._profile_of(eng, m)
            if cid is not None and cid in sc.present:
                continue
            known = cid is not None and cid in eng.profiles
            if known and cid in sc.outside:  # nearby: walks in
                rv.admit.append(Admission("known", m, cid=cid))
                continue
            if entity is not None:  # a canon person: the canon calendar decides
                assert self.source is not None
                w = self.source.whereabouts(entity, sc.time,
                                            self.here() if self.here is not None else None,
                                            sc.location)
                adm = Admission("canon", m, cid=cid, entity=entity)
                if w.status == HERE:
                    rv.admit.append(adm)
                elif w.status == ELSEWHERE:
                    drift.append(f"{m}: {w.reason or 'canon puts this person elsewhere now'}")
                else:
                    about = self.source.describe(entity) + (f"; {w.reason}" if w.reason else "")
                    ask[f"p{i}"] = self._plausible_q(m, about, eng)
                    pending[f"p{i}"] = adm
                continue
            if known:  # a character of the campaign: the world says where they are
                assert cid is not None
                name = eng.names.real(cid)
                place = self.where(cid) if self.where is not None else None
                here = self.here() if self.here is not None else None
                if place is not None and here is not None:
                    if place == here:
                        rv.admit.append(Admission("known", m, cid=cid))
                    else:
                        drift.append(f"{name} is at {place} now, not here")
                    continue
                ask[f"p{i}"] = self._plausible_q(name, eng.ctx.describe(cid), eng)
                pending[f"p{i}"] = Admission("known", m, cid=cid)
                continue
            adm = Admission("passer_by", m, label=m)
            ask[f"s{i}"] = choice_q(f"Is the person described as «{m}» a man or a woman?",
                                    {"m": "a man or a boy", "f": "a woman or a girl"},
                                    tag="cast_sex")
            pending[f"s{i}"] = adm
            rv.admit.append(adm)
        if ask:
            try:
                got = eng.judge.ask([eng.ctx._scene_header(sc), f"Narration: {narration}"], ask)
            except JudgeError as e:
                eng._note("scene_cast_judge_unavailable", error=str(e)[:200])
                got = {}
            for k, adm in pending.items():
                j = got.get(k)
                if k.startswith("s"):
                    adm.sex = str(j.answer) if j is not None else None
                elif j is not None and j.answer:
                    rv.admit.append(adm)
                else:  # implausible, or no verdict: the narration may not place them here
                    drift.append(f"{adm.mention} would not plausibly be here now"
                                 + ("" if j is not None else " (could not be checked)"))
        if drift:
            rv.reject = ("Your last draft brought into the scene people who cannot be here now: "
                         + "; ".join(drift) + ". Rewrite it without them; they are not at "
                         f"{sc.location}.")
            rv.admit = []
        return rv

    def _plausible_q(self, who: str, about: str, eng: "Engine") -> Any:
        return yes_no_q(
            f"Could {who} plausibly be at {eng.scene.location} at {format_time(eng.scene.time)}, "
            f"given who they are ({about}) and what is known of where they are? Answer no if "
            "they would be elsewhere or have no reason to be here.", tag="cast_plausible")

    # -- admission ---------------------------------------------------------------------------
    def character_for(self, eng: "Engine", adm: Admission) -> str:
        """The engine character for an admission (created for canon people and passers-by)."""
        if adm.kind == "known":
            assert adm.cid is not None
            return adm.cid
        if adm.kind == "canon":
            assert self.source is not None and adm.entity is not None
            return self.source.admit(eng, adm.entity)
        while True:
            self._walkins += 1
            slot = f"walkin{self._walkins}"
            if f"npc_{slot}" not in eng.profiles:
                break
        spec = eng.fresh_npc(slot, self.culture,
                             **({"sex": adm.sex} if adm.sex in ("m", "f") else {}))
        prof = eng.add_npc(spec, description=f"Came into {eng.scene.location} during play.",
                           appearance=adm.label)
        return prof.id

