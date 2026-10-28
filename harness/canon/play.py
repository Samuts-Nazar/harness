"""Canon in play (task 16): a campaign that starts inside the canon, background knowledge from a life,
scheduled canon events, proportional canon pull and the canon drift check.

Everything reads a `Canon` store (harness/canon/retrieve.py) and writes campaign records through the
engine's own stores: nothing here lets a model write state. Time: story minutes (day 1 00:00 = 0) in the
store; the campaign clock starts at 0 at the start moment, so `campaign_t = story_t - start_t`
(`CanonCampaign.offset`). Knowledge about the past therefore sits at negative campaign times.

Contract with the world engine (task 17): harness/canon/api.py.
"""
from __future__ import annotations

import json
import re
import threading
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable, Sequence

from ..facts import _tokens
from ..judge import Judge, JudgeError
from ..models import HEARD, SCRIPTED, TOLD, WITNESSED, CharacterProfile, format_time
from .api import Background, CanonCampaign, EventVerdict, Knower, ScheduledEvent
from .retrieve import Canon

if TYPE_CHECKING:
    from ..pipeline import Engine

OWN_LIFE = "own life"
HOW = {"witnessed": WITNESSED, "sensed": WITNESSED, "innate": WITNESSED, "told": TOLD,
       "heard": HEARD, "overheard": HEARD, "hearsay": HEARD, "inferred": HEARD, "read": HEARD}
Phrase = Callable[[str], str]   # a cheap-model text call: prompt -> text


# ---- scheduled canon events (the list task 17 executes) -------------------------------------
def scheduled_events(canon: Canon, after_t: int, until_t: int | None = None) -> list[ScheduledEvent]:
    """Story events with t_from in (after_t, until_t], in story order, with participants and knowers.
    Dated events (a story day) and `before` events (a season before day 1, `t_prec` 'season': a
    flashback that lies in the future of a campaign starting before it); events of unknown time
    carry an earlier time forward and are never scheduled."""
    out: list[ScheduledEvent] = []
    with canon._lock:
        rows = canon.con.execute(
            "SELECT r.id, r.body, r.place, r.t_from, c.day, c.ekind, c.loudness, c.gist_uk, c.order_key FROM record r "
            "JOIN canon_event c ON c.id=r.id WHERE r.t_from > ? AND (c.day IS NOT NULL OR r.t_prec = 'season') "
            + ("AND r.t_from <= ? " if until_t is not None else "") + "ORDER BY r.t_from, c.order_key",
            (after_t, until_t) if until_t is not None else (after_t,)).fetchall()
        for r in rows:
            parts = canon.con.execute(
                "SELECT entity FROM canon_participant WHERE event_id=? AND role IN "
                "('actor','target','victim','speaker','listener','witness')", (r["id"],)).fetchall()
            ids = tuple(dict.fromkeys(p["entity"] for p in parts))
            kn = tuple(Knower(k["entity"], canon.name(k["entity"]), k["channel"], k["source"], k["learned_t"])
                       for k in canon.con.execute("SELECT * FROM canon_knower WHERE event_id=? ORDER BY learned_t", (r["id"],)))
            rx = tuple((x["party"], x["reaction"]) for x in canon.con.execute(
                "SELECT party, reaction FROM canon_reaction WHERE event_id=?", (r["id"],)))
            out.append(ScheduledEvent(
                id=r["id"], t=r["t_from"], day=r["day"], place=r["place"],
                place_name=canon.name(r["place"]) if r["place"] else None, participants=ids,
                participant_names=tuple(canon.name(i) for i in ids), summary=r["gist_uk"] or r["body"],
                knowers=kn, notability=float(r["loudness"]), kind=r["ekind"], reactions=rx))
    return out


def knowledge_as_of(canon: Canon, entity: str, as_of: int, *, also: Sequence[str] = ()) -> list[dict[str, Any]]:
    """Every canon event the entity (or a group it belongs to, or a group in `also`) knew by `as_of`,
    with the channel, the source and the time of learning: what an NPC created from canon carries."""
    with canon._lock:
        hs = [*canon.holders(entity), *also]
        ph = ",".join("?" * len(hs))
        out = []
        for k in canon.con.execute(
                f"SELECT k.*, r.body, r.t_from, r.place, c.gist_uk, c.loudness FROM canon_knower k "
                f"JOIN record r ON r.id=k.event_id JOIN canon_event c ON c.id=k.event_id "
                f"WHERE k.entity IN ({ph}) AND COALESCE(k.learned_t, r.t_from) <= ? ORDER BY r.t_from", (*hs, as_of)):
            out.append({"event": k["event_id"], "text": k["body"], "t": k["t_from"], "channel": k["channel"],
                        "source": k["source"], "learned_t": k["learned_t"], "holder": k["entity"],
                        "place": k["place"], "loudness": k["loudness"]})
        best: dict[int, dict[str, Any]] = {}
        for o in out:   # a person's own row wins over their group's
            if o["event"] not in best or o["holder"] == entity:
                best[o["event"]] = o
        return sorted(best.values(), key=lambda o: o["t"])


# ---- background knowledge from a life -------------------------------------------------------
BACKGROUND_Q = ("Would this person plausibly know about the topic from their own ordinary life: what their role, "
                "years lived, place and standing give them? Answer no if it would be a secret, a private matter of "
                "other people, or something only an expert elsewhere could know.")


def _life_context(canon: Canon, character: str) -> str:
    p = canon.profile(character) or {}
    lived = "; ".join(k.get("fact", "") for k in p.get("knows", []) if isinstance(k, dict))
    place = ""
    with canon._lock:
        r = canon.con.execute(
            "SELECT e.name FROM canon_knower k JOIN record r ON r.id=k.event_id JOIN entity e ON e.id=r.place "
            "WHERE k.entity=? AND r.place IS NOT NULL ORDER BY r.t_from LIMIT 1", (character,)).fetchone()
        if r:
            place = r["name"]
    return (f"Person: {p.get('name', character)}. Who: {p.get('who') or '?'}. Role: {p.get('role') or '?'}. "
            f"Standing: {p.get('standing') or '?'}. Usual place: {place or '?'}. Known from their life: {lived or 'nothing noted'}.")


def background(canon: Canon, character: str, topic: str, *, judge: Judge, as_of: int,
               phrase: Phrase | None = None, stored: Sequence[Background] = (),
               denied: Sequence[str] = ()) -> Background | None:
    """What `character` knows about `topic` from their own life, or None. One judgment ("would this person
    plausibly know X?"), asked once per (character, topic): the caller stores the answer (a Background
    record, or the topic in the denied list) so it stays consistent. Canon secrets never come through here:
    if canon holds an event on the topic that the character does not know and that stayed with few people,
    the answer is None without asking."""
    tt = _tokens(topic)
    for b in stored:
        if b.character == character and tt & _tokens(b.topic):
            return b
    if any(tt & _tokens(d) for d in denied):
        return None
    secrets = canon.secrets_about(character, topic, as_of)
    if secrets:   # embedding-near is not enough to block: keep only those a typed check says are the same matter
        from ..judge import yes_no_q
        qs = {}
        for x in secrets[:4]:
            r = canon.con.execute("SELECT r.body FROM record r WHERE r.id=?", (x["id"],)).fetchone()
            qs[str(x["id"])] = yes_no_q(f"Topic: {topic}\nRecord: {r['body']}\nDoes this record concern the same matter as the topic "
                                        "(so that answering the topic would reveal it)?", tag="canon_relevance")
        try:
            got = judge.ask([], qs)
        except JudgeError:
            return None   # cannot check: safe side
        if any(j.answer for j in got.values()):
            return None
    ctx = _life_context(canon, character) + f"\nTopic: {topic}"
    try:
        j = judge.yes_no(BACKGROUND_Q, ctx, tag="background_knowledge")
    except JudgeError:
        return None
    if not j.answer:
        return None
    text = f"{canon.name(character)} knows from their own life about: {topic}"
    if phrase is not None:
        try:
            line = phrase(
                "In one plain sentence, English, say what this person would ordinarily know about the topic from "
                "their own life. No secrets, no invented names or events, nothing about the current story.\n"
                + ctx).strip()
            if line:
                text = line
        except Exception:  # noqa: BLE001 - the generic record is enough
            pass
    return Background(character=character, topic=topic, text=text, source=OWN_LIFE, t=as_of)


# ---- proportional canon pull ------------------------------------------------------------------
VERDICT_PROMPT = """A scheduled event of the book's story is about to happen. The player's acts may have changed what it depends on.

Event ({when}, at {place}): {summary}
Participants: {names}
What has happened in this campaign that touches the event's people, place or purpose:
{changes}

Rule: canon pull is proportional. Small acts do not change big events. Large or logically connected changes can, when the consequence is logical and fitting. Do not force the book's outcome against the facts above; do not drop it for a trivial change.

Reply with JSON only: {{"outcome": "happens" | "differently" | "does_not_happen", "reason": "one or two plain sentences naming the facts that decide it", "new_summary": "for differently: what happens instead, one sentence; else empty"}}"""


def judge_event(canon: Canon, event: ScheduledEvent, changes: Sequence[str], *, judge: Phrase, at_t: int) -> EventVerdict:
    """One judgment with the reason. No changes means no call: the event happens as written."""
    if not changes:
        return EventVerdict(event.id, "happens", "nothing the player did touches it", None, at_t)
    prompt = VERDICT_PROMPT.format(
        when=f"story day {event.day}", place=event.place_name or "?", summary=event.summary,
        names=", ".join(event.participant_names) or "?", changes="\n".join(f"- {c}" for c in changes))
    raw = judge(prompt)
    try:
        s = raw.strip()
        obj = json.loads(s[s.find("{"): s.rfind("}") + 1])
    except (ValueError, json.JSONDecodeError):
        return EventVerdict(event.id, "happens", "judgment unreadable: the event stands as written", None, at_t)
    outcome = obj.get("outcome") if obj.get("outcome") in ("happens", "differently", "does_not_happen") else "happens"
    return EventVerdict(event.id, outcome, str(obj.get("reason") or "")[:400],
                        (str(obj.get("new_summary")).strip() or None) if outcome == "differently" else None, at_t)


# ---- canon drift check --------------------------------------------------------------------------
CONTRADICT_Q = ("Does the TEXT state or clearly imply something that contradicts one of the CANON FACTS? "
                "Added detail that canon is silent about is not a contradiction. Answer yes only for a real conflict.")
EXPLAIN_Q = ("Do the CAMPAIGN EVENTS explain why the TEXT differs from the CANON FACTS (something that happened in "
             "this campaign makes the difference logical)? Answer yes only if one of them clearly does.")


class CanonGuard:
    """Narrated output that contradicts canon is checked against the campaign store: if a campaign event
    explains the deviation it is justified drift and accepted; otherwise it is a hallucination and the
    caller regenerates. The check reads canon through retrieval (the store is too large for a context).
    `refresh` runs on the main thread each turn (snapshot of the campaign); `check` may run in workers."""

    def __init__(self, canon: Canon, judge: Judge, *, offset: int = 0, k: int = 4) -> None:
        self.canon, self.judge, self.offset, self.k = canon, judge, offset, k
        self.campaign_text = ""
        self.now = 0
        self.drift: list[dict[str, Any]] = []     # justified drift, for the debug view
        self.rejected: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    def refresh(self, eng: "Engine") -> None:
        self.now = eng.scene.time
        facts = eng.facts.all_campaign(eng.scene.time)
        events = [e.payload.get("text", "") for e in eng.log.recent_dialogue(limit=12, include_narration=True)]
        self.campaign_text = "\n".join(f"- {f.content}" for f in facts[-20:]) + "\n" + "\n".join(f"- {t}" for t in events if t)

    def check(self, text: str, kind: str, speaker: str | None = None) -> str | None:
        """None: fine (or justified drift). A string: why it is rejected."""
        hits = self.canon.search_unfiltered(text, k=self.k)
        if not hits:
            return None   # canon says nothing about it
        facts = "\n".join(f"- (story day {h['day']}) {h['what_en']}" for h in hits if h["day"] is not None or h["t"] < 0)
        if not facts:
            return None
        ctx = f"CANON FACTS:\n{facts}\n\nTEXT ({kind}{', ' + speaker if speaker else ''}):\n{text}"
        try:
            j = self.judge.yes_no(CONTRADICT_Q, ctx, tag="canon_drift")
        except JudgeError:
            return None
        if not j.answer:
            return None
        try:
            e = self.judge.yes_no(EXPLAIN_Q, ctx + f"\n\nCAMPAIGN EVENTS:\n{self.campaign_text or '(none)'}", tag="canon_drift_justified")
        except JudgeError:
            e = None
        rec = {"kind": kind, "speaker": speaker, "text": text[:300], "canon": [h["id"] for h in hits]}
        with self._lock:
            if e is not None and e.answer:
                self.drift.append(rec)
                return None
            self.rejected.append(rec)
        return "contradicts canon: " + "; ".join(h["what_en"][:140] for h in hits[:2])


# ---- the campaign bridge ----------------------------------------------------------------------
_PRONOUNS = {"вона", "вони", "він", "воно"}


def name_form(alias: str, name: str) -> bool:
    """A form of the person's name, not a description: capitalised (a proper name, a misspelling
    of it, a nickname used as a name: «Йеннфер», «Дальку»), or sharing its first four letters
    with a word of the name («йеннефер», «ґеральте»)."""
    a = alias.strip()
    if not a or a[0].isupper():
        return True
    head = a.casefold()[:4]
    return len(head) == 4 and any(w.casefold().startswith(head) for w in name.split())


def cid_of(entity: str) -> str:
    """Engine character id for a canon entity id: the part after the prefix."""
    return entity.split(":", 1)[1].replace("-", "_")


@dataclass
class CanonPlay:
    """A campaign that starts at a canon moment. Create with the Canon store, the start (story day, hour,
    place), then `install(engine, cast)`. NPCs created from canon carry what they knew as of the start."""
    canon: Canon
    start: CanonCampaign
    made: dict[str, str] = field(default_factory=dict)   # canon entity -> engine character id
    portraits: dict[str, str] = field(default_factory=dict)  # canon entity -> world portrait id

    @classmethod
    def at(cls, canon: Canon, day: int, hour: float, place: str | None, present: Sequence[str] = ()) -> "CanonPlay":
        t = int((day - 1) * 1440 + hour * 60)
        return cls(canon, CanonCampaign(start_t=t, place=place, offset=t, present=list(present)))

    # -- characters from canon
    def profile_for(self, entity: str, *, cid: str | None = None, look: str = "") -> CharacterProfile:
        """The engine profile of a canon person. The appearance (the label everyone who does not
        know the name uses, harness/names.py) is a description, never a form of the name
        (decisions: "A name is knowledge"): `look` (the portrait's `look`) when given, else the
        first alias that describes rather than names (a role or a look: «бургомістр»,
        «біловолосий»), else none."""
        p = self.canon.profile(entity) or {}
        name = self.canon.name(entity)
        unnamed = bool(p.get("unnamed"))
        appearance = " ".join(look.split())
        if not unnamed and not appearance:
            with self.canon._lock:
                al = [r["alias"] for r in self.canon.con.execute("SELECT alias FROM canon_alias WHERE entity=?", (entity,))]
            for a in al:
                if (a.lower() != name.lower() and len(a) >= 5 and a.lower() not in _PRONOUNS
                        and " " not in a.strip() and not name_form(a, name)):
                    appearance = a
                    break
        desc = "; ".join(x for x in (p.get("who"), p.get("role"), p.get("standing")) if x)
        return CharacterProfile(cid or cid_of(entity), name, desc, "", appearance)

    def ensure_character(self, eng: "Engine", entity: str, *, cid: str | None = None,
                         member_of: Sequence[str] = ()) -> str:
        """Create the engine character for a canon entity (once) and write what they knew at the start
        as canon facts with channel, source and time. `member_of`: groups whose knowledge a person made
        from a group inherits (a guard from the town guards)."""
        if entity in self.made:
            return self.made[entity]
        port = eng.ctx.portraits.get(self.portraits.get(entity, ""))
        prof = self.profile_for(entity, cid=cid, look=getattr(port, "look", "") or "")
        eng.profiles[prof.id] = prof
        self.made[entity] = prof.id
        known = knowledge_as_of(self.canon, entity, self.start.start_t, also=member_of)
        for o in known:
            src = None
            if o["source"]:
                src = self.canon.name(o["source"])
            how = HOW.get(o["channel"], HEARD)
            eng.facts.add_canon(o["text"], game_time=o["t"] - self.start.offset,
                                location=self.canon.name(o["place"]) if o["place"] else "",
                                notability=float(o["loudness"]), knowers=[(prof.id, how, src)])
        eng._save_setup()
        if self.portraits.get(entity) in eng.ctx.portraits:  # this person plays a world portrait
            eng.bind_portrait(prof.id, self.portraits[entity])
        return prof.id

    def install(self, eng: "Engine", cast: Sequence[str], *, member_of: dict[str, Sequence[str]] | None = None) -> list[str]:
        """Create the cast and set which of them know each other by name, per canon: two named persons who
        took part in the same event before the start."""
        ids = [self.ensure_character(eng, e, member_of=(member_of or {}).get(e, ())) for e in cast]
        for i, a in enumerate(cast):
            for b in cast[i + 1:]:
                if self._acquainted(a, b):
                    eng.acquaint(self.made[a], self.made[b], how="canon")
        return ids

    def _acquainted(self, a: str, b: str) -> bool:
        pa, pb = self.canon.profile(a) or {}, self.canon.profile(b) or {}
        if pa.get("unnamed") or pb.get("unnamed"):
            return False
        with self.canon._lock:
            r = self.canon.con.execute(
                "SELECT 1 FROM canon_participant x JOIN canon_participant y ON x.event_id=y.event_id JOIN record r ON r.id=x.event_id "
                "WHERE x.entity=? AND y.entity=? AND x.role IN ('actor','speaker','listener','target') AND y.role IN "
                "('actor','speaker','listener','target') AND r.t_from <= ? LIMIT 1", (a, b, self.start.start_t)).fetchone()
        return r is not None

    # -- the future
    def upcoming(self, after_campaign_t: int = 0, until_campaign_t: int | None = None) -> list[ScheduledEvent]:
        a = after_campaign_t + self.start.offset
        u = None if until_campaign_t is None else until_campaign_t + self.start.offset
        return scheduled_events(self.canon, a, u)

    # -- background knowledge, stored per campaign
    def know_from_life(self, eng: "Engine", entity: str, topic: str, judge: Judge, *, phrase: Phrase | None = None) -> Background | None:
        cid = self.made.get(entity) or self.ensure_character(eng, entity)
        stored = self._stored_background(eng, cid, entity)
        denied = self._denied(eng, cid)
        b = background(self.canon, entity, topic, judge=judge, as_of=self.start.to_story_t(eng.scene.time), phrase=phrase,
                       stored=stored, denied=denied)
        if b is None:
            if not any(_tokens(topic) & _tokens(d) for d in denied):
                self._deny(eng, cid, topic)
            return None
        if b not in stored:
            eng.facts.add_canon(b.text, game_time=eng.scene.time - 1, location=eng.scene.location, notability=0.2,
                                knowers=[(cid, WITNESSED, OWN_LIFE)])
        return b

    def _stored_background(self, eng: "Engine", cid: str, entity: str) -> list[Background]:
        out = []
        for f in eng.facts.visible_to(cid, eng.scene.time, store="canon"):
            if any(k.character == cid and k.source == OWN_LIFE for k in f.knowers):
                out.append(Background(entity, f.content, f.content, OWN_LIFE, f.game_time))
        return out

    def _denied(self, eng: "Engine", cid: str) -> list[str]:
        r = eng.conn.execute("SELECT value FROM campaign_meta WHERE key=?", (f"background_no:{cid}",)).fetchone()
        return json.loads(r["value"]) if r else []

    def _deny(self, eng: "Engine", cid: str, topic: str) -> None:
        d = self._denied(eng, cid) + [topic]
        with eng.conn:
            eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                             (f"background_no:{cid}", json.dumps(d, ensure_ascii=False)))

    # -- proportional pull
    def changes_touching(self, eng: "Engine", event: ScheduledEvent) -> list[str]:
        """Campaign facts that mention the event's people or place: what the player's acts may have changed."""
        words = {w for n in (*event.participant_names, event.place_name or "") for w in _tokens(n) if len(w) > 3}
        out = []
        for f in eng.facts.all_campaign(eng.scene.time):
            t = _tokens(f.content)
            if any(w[:-1] in " ".join(t) for w in words):
                out.append(f.content)
        return out[-8:]

    def rejudge(self, eng: "Engine", event: ScheduledEvent, judge: Phrase) -> EventVerdict:
        """Re-judge a scheduled event whose preconditions the player may have changed; one judgment, the reason
        stored in the log (so a rollback removes it with the facts it came from)."""
        prior = self.verdict(eng, event.id)
        if prior is not None:
            return prior
        v = judge_event(self.canon, event, self.changes_touching(eng, event), judge=judge, at_t=eng.scene.time)
        eng.log.append(SCRIPTED, game_time=eng.scene.time, location=eng.scene.location, participants=[], witnesses=[],
                       notability=0.0, payload={"canon_verdict": {"event": v.event_id, "outcome": v.outcome,
                                                                  "reason": v.reason, "new_summary": v.new_summary}})
        return v

    def verdict(self, eng: "Engine", event_id: int) -> EventVerdict | None:
        for e in eng.log.active([SCRIPTED]):
            d = e.payload.get("canon_verdict")
            if d and d.get("event") == event_id:
                return EventVerdict(event_id, d["outcome"], d["reason"], d.get("new_summary"), e.game_time)
        return None

    def guard(self, judge: Judge) -> CanonGuard:
        return CanonGuard(self.canon, judge, offset=self.start.offset)


# ---- who can be in a scene (living dialogue task 9) --------------------------------------------
NEAR_MINUTES = 240   # a canon event this close in time to now says where its people are


class CanonCast:
    """The canon calendar for `harness.scene_cast.SceneCast`: which canon person a narration names,
    where canon puts them at a time, and their engine character (a profile from canon, with what they
    knew at the start). `places`: canon place entity -> world place id; an unmapped place is compared
    with the scene's location by name."""

    def __init__(self, play: CanonPlay, *, places: dict[str, str] | None = None,
                 near: int = NEAR_MINUTES) -> None:
        self.play, self.places, self.near = play, dict(places or {}), near

    @property
    def canon(self) -> Canon:
        return self.play.canon

    def identify(self, mention: str) -> str | None:
        with self.canon._lock:
            for ent in self.canon._mentioned(mention):
                r = self.canon.con.execute("SELECT type FROM entity WHERE id=?", (ent,)).fetchone()
                if r is not None and r["type"] == "person":
                    return ent
        return None

    def cid(self, entity: str) -> str:
        return self.play.made.get(entity) or cid_of(entity)

    def _is_here(self, place: str | None, place_name: str, here_place: str | None, here_name: str) -> bool:
        if place is not None and place in self.places and here_place is not None:
            return self.places[place] == here_place
        return bool(here_name) and place_name.strip().lower() == here_name.strip().lower()

    def whereabouts(self, entity: str, t: int, here_place: str | None, here_name: str) -> "Whereabouts":
        """Where canon puts the person at campaign time `t`: the canon event with them that is nearest
        in time (within `near` minutes) and has a place. None near: the interval they are in, between the
        last known canon place before now and the next one after; both elsewhere is ELSEWHERE (lodged
        there), both here is HERE, anything else UNKNOWN with what is known (for a plausibility judgment)."""
        from ..scene_cast import ELSEWHERE, HERE, UNKNOWN, Whereabouts
        st = self.play.start.to_story_t(t)
        with self.canon._lock:
            rows = self.canon.con.execute(
                "SELECT r.t_from, r.place, c.day, c.gist_uk, r.body FROM canon_participant p "
                "JOIN record r ON r.id=p.event_id JOIN canon_event c ON c.id=r.id "
                "WHERE p.entity=? AND r.place IS NOT NULL AND r.t_from BETWEEN ? AND ? "
                "ORDER BY ABS(r.t_from - ?), r.t_from", (entity, st - self.near, st + self.near, st)).fetchall()
            if not rows:   # nothing near now: the interval between the last known place and the next
                q = ("SELECT r.t_from, r.place FROM canon_participant p JOIN record r ON r.id=p.event_id "
                     "WHERE p.entity=? AND r.place IS NOT NULL AND r.t_from {} ? ORDER BY r.t_from {} LIMIT 1")
                last = self.canon.con.execute(q.format("<=", "DESC"), (entity, st)).fetchone()
                nxt = self.canon.con.execute(q.format(">", "ASC"), (entity, st)).fetchone()
                lname = self.canon.name(last["place"]) if last is not None else ""
                nname = self.canon.name(nxt["place"]) if nxt is not None else ""
        if not rows:
            if last is None and nxt is None:
                return Whereabouts(UNKNOWN)
            here = [x is not None and self._is_here(x["place"], nm, here_place, here_name)
                    for x, nm in ((last, lname), (nxt, nname))]
            who = self.canon.name(entity)
            if last is not None and nxt is not None and not any(here):
                return Whereabouts(ELSEWHERE, f"canon has {who} lodged at {lname} since {format_time(last['t_from'])} "
                                              f"(story time), next at {nname} at {format_time(nxt['t_from'])}")
            if last is not None and nxt is not None and all(here):
                return Whereabouts(HERE, f"canon has {who} here from {format_time(last['t_from'])} "
                                         f"to {format_time(nxt['t_from'])}")
            parts = ([f"last seen in canon at {lname}, {round((st - last['t_from']) / 60)} h before now"]
                     if last is not None else []) + (
                [f"next in canon at {nname}, {round((nxt['t_from'] - st) / 60)} h after now"] if nxt is not None else [])
            return Whereabouts(UNKNOWN, "; ".join(parts))
        with self.canon._lock:
            r = rows[0]
            pname = self.canon.name(r["place"])
        if self._is_here(r["place"], pname, here_place, here_name):
            return Whereabouts(HERE, f"canon has them here on story day {r['day']}")
        hours = round(abs(r["t_from"] - st) / 60, 1)
        when = "now" if hours == 0 else f"{hours} h {'later' if r['t_from'] > st else 'earlier'}"
        return Whereabouts(ELSEWHERE, f"canon has {self.canon.name(entity)} at {pname} ({when}: "
                                      f"{(r['gist_uk'] or r['body'])[:120]})")

    def describe(self, entity: str) -> str:
        p = self.canon.profile(entity) or {}
        return "; ".join(x for x in (p.get("name"), p.get("who"), p.get("role"), p.get("standing")) if x) \
            or self.canon.name(entity)

    def admit(self, eng: "Engine", entity: str) -> str:
        """The engine character (created once from canon); canon people of the campaign who met them
        before the start know them by name (a reopened campaign has the profile already)."""
        if entity not in self.play.made and cid_of(entity) in eng.profiles:
            self.play.made[entity] = cid_of(entity)
        cid = self.play.ensure_character(eng, entity)
        for other, ocid in list(self.play.made.items()):
            if other != entity and ocid in eng.profiles and self.play._acquainted(entity, other):
                eng.acquaint(cid, ocid, how="canon")
        return cid


def what_knows(eng: "Engine", character: str) -> list[dict[str, Any]]:
    """The debug view: what a character knows, how and from where (facts only), for the live check."""
    out = []
    for f in eng.facts.visible_to(character, eng.scene.time + 10**9):
        for k in f.knowers:
            if k.character == character:
                out.append({"text": f.content, "how": k.how, "source": k.source, "store": f.store, "t": f.game_time})
    return out
