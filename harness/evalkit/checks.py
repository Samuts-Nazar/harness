"""Automatic checks over a played log (task 19, 18A: isolation, fact and commitment survival, canon
drift, metaphor-as-state). Every check reads an `Engine` (a live one, or a campaign reopened from its
database or replayed from a cassette) and returns a `Report` of findings. Code decides wherever
code can; an LLM judge is used only with a reference (see `agreement`).

Isolation (no NPC states what it had no channel for)
    A name that exists in the world (a person, a place, a title: the profiles, the glossary, the
    capitalised names in the campaign facts) may appear in an NPC line only if the speaker could
    know it: it is in something the speaker knows or has seen (their knowledge as of that moment,
    the dialogue they heard, their own description, the scene header) or is common to all (a name
    on no record at all is not a leak: nothing could have leaked). The same test runs on the notes
    that steer a character: intents ("tell the player that ...") and the "(about: ...)" tellables
    of off-screen updates, because a hidden-door bug showed that a motivation note can reveal a
    secret.

Survival (things said or promised are still respected 20+ turns later)
    (a) structural: every fact that came from something said or done is still in the rendered
    memory of everyone who knew it, at the end of the run; (b) optional, judged by an LLM with the
    record as the reference: a later line of the same character does not contradict it.

Canon drift: the task 16 guard over every logged narration and NPC line.
Metaphor-as-state: a state change that reads a figure of speech literally (harness/metaphor.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Mapping, Sequence

from ..judge import Judge, JudgeError, yes_no_q
from ..metaphor import literal_reading
from ..models import ACTION, NARRATION, PLAYER, STATE_CHANGE, UTTERANCE, Event

NAME_RE = re.compile(r"[A-ZА-ЯІЇЄҐ][\w'’-]{3,}")
STEM = 5  # names are compared by their first five letters (Ukrainian cases)
# capitalised words that are not names (sentence starters, common Ukrainian/English openers)
COMMON = frozenset(w.lower()[:STEM] for w in (
    "Гм", "Так", "Ніби", "Може", "Хіба", "Тоді", "Якщо", "Коли", "Але", "Ось", "Ось", "Тут", "Там",
    "Чого", "Що", "Хто", "Чому", "Куди", "Скільки", "Слухай", "Добре", "Звісно", "Дякую",
    "Прошу", "Будь", "Гей", "Агов", "The", "This", "That", "They", "There", "When", "What",
    "Where", "Who", "Why", "Yes", "Hello", "Because", "However", "Maybe", "Perhaps", "Already",
    "Nothing", "Something", "Everyone", "Someone", "Nobody", "Anyone"))


@dataclass(frozen=True)
class Finding:
    check: str
    text: str                     # the offending text
    detail: str                   # why
    event: int | None = None
    who: str | None = None


@dataclass
class Report:
    check: str
    findings: list[Finding] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return not self.findings

    def __str__(self) -> str:
        head = f"{self.check}: {'ok' if self.ok else str(len(self.findings)) + ' finding(s)'} {self.stats}"
        return "\n".join([head, *[f"  - [{f.event}] {f.who or ''}: {f.detail} :: {f.text[:140]}"
                                  for f in self.findings]])


def names_in(text: str) -> set[str]:
    """Stems of the capitalised words that look like names."""
    return {w.lower()[:STEM] for w in NAME_RE.findall(text)} - COMMON


def _stems(text: str) -> set[str]:
    return {w.lower()[:STEM] for w in re.findall(r"[\w'’-]{4,}", text)}


def _turn_index(eng: Any) -> dict[int, int]:
    """Event id -> number of player inputs up to it (a turn counter)."""
    n, out = 0, {}
    for e in eng.log.active():
        if e.type == UTTERANCE and e.payload.get("speaker") == PLAYER and e.payload.get("part", 1) == 1:
            n += 1
        out[e.id] = n
    return out


def world_names(eng: Any, common: Iterable[str] = ()) -> set[str]:
    """Names of people in the world: the profiles, the glossary's persons and collectives, and the
    capitalised names inside campaign facts. Places, titles, creatures and things are common
    knowledge (every Vizimian knows "Візім"), as are the names in `common` (the world map)."""
    out: set[str] = set()
    for p in eng.profiles.values():
        out |= {w.lower()[:STEM] for w in re.findall(r"[\w'’-]{4,}", p.name)}
    skip: set[str] = set()
    g = getattr(eng, "glossary", None)
    if g is not None:
        for e in g.entries:
            stems = {w.lower()[:STEM] for w in re.findall(r"[\w'’-]{4,}", e.canonical)}
            (out if e.kind in ("person", "collective") else skip).update(stems)
    skip |= {w.lower()[:STEM] for c in [eng.scene.location, *common]
             for w in re.findall(r"[\w'’-]{4,}", c)}
    for (text,) in eng.conn.execute("SELECT content FROM facts"):  # campaign and canon
        out |= names_in(text)
    return out - COMMON - skip


def _known_stems(eng: Any, who: str, at_time: int, upto_event: int) -> set[str]:
    """Everything `who` could say a name from at that moment."""
    known: set[str] = set()
    for f in eng.facts.visible_to(who, at_time):
        known |= _stems(f.content)
    prof = eng.profiles.get(who)
    if prof:
        known |= _stems(prof.name + " " + prof.description + " " + prof.appearance + " " + prof.core)
    for e in eng.log.active([UTTERANCE, ACTION, NARRATION]):
        if e.id >= upto_event:
            break
        if who in e.witnesses or who in e.participants or e.payload.get("speaker") == who:
            known |= _stems(e.payload.get("text", ""))
    known |= _stems(eng.scene.location)
    return known


def check_isolation(eng: Any, common: Iterable[str] = ()) -> Report:
    rep = Report("isolation")
    world = world_names(eng, common)
    lines = notes = 0
    for e in eng.log.active([UTTERANCE]):
        who = e.payload.get("speaker")
        if who in (None, PLAYER) or who not in eng.profiles:
            continue
        lines += 1
        known = _known_stems(eng, who, e.game_time, e.id)
        for n in sorted(names_in(e.payload["text"]) & world):
            if n not in known:
                rep.findings.append(Finding(
                    "isolation", e.payload["text"],
                    f"{eng.profiles[who].name} names {n!r}*, which is in no record the speaker knew "
                    "or heard", e.id, who))
    # notes that steer a character: intents, and "(about: ...)" tellables of off-screen updates
    for e in eng.log.active(["intent_set"]):
        who = (e.participants or (None,))[0]
        if who is None or who not in eng.profiles:
            continue
        notes += 1
        text = e.payload.get("text", "")
        known = _known_stems(eng, who, e.game_time, e.id)
        for n in sorted(names_in(text) & world):
            if n not in known:
                rep.findings.append(Finding("isolation", text,
                                            f"an intent note holds {n!r}*, unknown to the character",
                                            e.id, who))
    for f in eng.facts.all_campaign(10**12):
        m = re.search(r"\(about: (.+)\)\s*$", f.content)
        if not m:
            continue
        notes += 1
        about = m.group(1).strip()
        for k in f.knowers:
            seen = {x.content for x in eng.facts.visible_to(k.character, 10**12)}
            if about not in seen:
                rep.findings.append(Finding(
                    "isolation", f.content,
                    f"the note is about a fact {k.character!r} does not know", f.source_event_id,
                    k.character))
    rep.stats = {"npc_lines": lines, "notes": notes}
    return rep


def check_survival(eng: Any, *, min_gap: int = 20, judge: Judge | None = None,
                   sample: int = 6) -> Report:
    """(a) structural survival; (b) with `judge`, up to `sample` pairs (a record, a much later line
    of the same character) are asked "does the line contradict the record?" (the record is the
    reference)."""
    rep = Report("survival")
    turns = _turn_index(eng)
    last_turn = max(turns.values(), default=0)
    checked = 0
    lost = 0
    for f in eng.facts.all_campaign(10**12):
        src = f.source_event_id
        if src is None or last_turn - turns.get(src, last_turn) < min_gap:
            continue
        ev = eng.log.get(src)
        if ev is None or ev.type not in (UTTERANCE, ACTION):
            continue  # only what was said or done
        for k in f.knowers:
            if k.character == PLAYER or k.character not in eng.profiles:
                continue
            mem = eng.deriver.derive(k.character, eng.scene.time)
            checked += 1
            if f.id not in {it.fact.id for it in mem.knows}:
                lost += 1
                rep.findings.append(Finding("survival", f.content,
                                            f"no longer in {k.character!r}'s memory after "
                                            f"{last_turn - turns[src]} turns", src, k.character))
    rep.stats = {"facts_checked": checked, "lost": lost, "turns": last_turn}
    if judge is not None:
        rep.stats["judged_pairs"], contradictions = _judge_contradictions(eng, judge, turns, min_gap,
                                                                         sample)
        rep.findings += contradictions
    return rep


def _judge_contradictions(eng: Any, judge: Judge, turns: Mapping[int, int], gap: int, sample: int
                          ) -> tuple[int, list[Finding]]:
    pairs: list[tuple[Any, Event]] = []
    lines = [e for e in eng.log.active([UTTERANCE]) if e.payload.get("speaker") not in (None, PLAYER)]
    for f in eng.facts.all_campaign(10**12):
        src = f.source_event_id
        if src is None:
            continue
        for e in lines:
            who = e.payload["speaker"]
            if (turns.get(e.id, 0) - turns.get(src, 0) >= gap
                    and any(k.character == who for k in f.knowers)):
                pairs.append((f, e))
    out: list[Finding] = []
    pairs = pairs[:: max(1, len(pairs) // max(sample, 1))][:sample]
    for f, e in pairs:
        try:
            j = judge.yes_no(
                "Does the LINE contradict the RECORD (says the opposite, or acts as if the record "
                "were not true)? Added detail is not a contradiction.",
                f"RECORD (what the character knows, reference): {f.content}\nLINE: {e.payload['text']}",
                tag="commitment_contradiction")
        except JudgeError:
            continue
        if j.answer:
            out.append(Finding("survival", e.payload["text"],
                               f"contradicts the record {f.content!r}", e.id, e.payload["speaker"]))
    return len(pairs), out


def check_canon_drift(eng: Any, guard: Any) -> Report:
    """Re-run the task 16 guard over every narration and NPC line."""
    rep = Report("canon_drift")
    n = 0
    for e in eng.log.active([NARRATION, UTTERANCE]):
        who = e.payload.get("speaker")
        if who == PLAYER:
            continue
        n += 1
        why = guard.check(e.payload["text"], "narration" if e.type == NARRATION else "npc_line", who)
        if why:
            rep.findings.append(Finding("canon_drift", e.payload["text"], why, e.id, who))
    rep.stats = {"texts": n, "justified_drift": len(getattr(guard, "drift", []))}
    return rep


def check_metaphor(eng: Any) -> Report:
    """State changes in the log that read a figure of speech literally."""
    rep = Report("metaphor_state")
    n = 0
    for e in eng.log.active([STATE_CHANGE]):
        n += 1
        cause = eng.log.get(e.cause_id) if e.cause_id else None
        seg = cause.payload.get("text", "") if cause else ""
        p = e.payload
        why = literal_reading(p.get("category", ""), p.get("op", ""), p.get("item", ""), seg)
        if why:
            rep.findings.append(Finding("metaphor_state", f"{p.get('op')} {p.get('item')}", why,
                                        e.id, (e.participants or (None,))[0]))
    rep.stats = {"state_changes": n}
    return rep


def run_all(eng: Any, *, guard: Any = None, judge: Judge | None = None, min_gap: int = 20
            ) -> dict[str, Report]:
    out = {"isolation": check_isolation(eng), "survival": check_survival(eng, min_gap=min_gap, judge=judge),
           "metaphor_state": check_metaphor(eng)}
    if guard is not None:
        out["canon_drift"] = check_canon_drift(eng, guard)
    return out


# -- LLM judging only with reference answers ---------------------------------------------------
@dataclass(frozen=True)
class Labelled:
    """One item graded by hand (by the Claude Code agent, never over the API): what is shown to the
    judge and the reference answer."""
    case: str
    context: str
    question: str
    expected: bool


def agreement(judge: Judge, items: Sequence[Labelled], *, tag: str = "eval_reference"
              ) -> dict[str, Any]:
    """How often a judge gives the reference answer: the number to read before trusting the judge."""
    rows = []
    for it in items:
        try:
            got = bool(judge.yes_no(it.question, it.context, tag=tag).answer)
        except JudgeError:
            got = None  # type: ignore[assignment]
        rows.append({"case": it.case, "expected": it.expected, "got": got})
    done = [r for r in rows if r["got"] is not None]
    agree = sum(1 for r in done if r["got"] == r["expected"])
    return {"n": len(items), "answered": len(done), "agree": agree,
            "agreement": round(agree / len(done), 3) if done else None, "rows": rows}
