"""Story-day tracking for canon ingestion (task 16).

Task 13 found that every model loses count of the story days in the second half of an arc. Here the
model never has the last word on a day:

1. two models each build a scene timeline (day range, part, place);
2. code checks it against the text: days never go back, the first story scene is day 1, and a day
   increase between neighbouring scenes needs a cue in the text (code finds the cue words);
3. scenes where the models disagree or the check fails go to one arbitration call that sees the
   scene, both answers and the cues code found; vague cues keep a day range (day_lo..day_hi);
4. the result is checked again; what still fails is widened to a range, never silently kept.

Pure functions plus `build()`, which takes a provider; tests drive it with a fake one.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Sequence

from ..providers import Provider
from . import extract
from .chunk import Para
from .vocab import PARTS

NUMBERS = {"один": 1, "одного": 1, "два": 2, "дві": 2, "двох": 2, "три": 3, "трьох": 3, "чотири": 4,
           "чотирьох": 4, "п'ять": 5, "шість": 6, "сім": 7, "вісім": 8, "десять": 10}
_NUM = "|".join(sorted((re.escape(k) for k in NUMBERS), key=len, reverse=True))

# (regex, meaning, delta in days relative to the scene before; None = a duration, see `hint`)
NEXT_DAY = re.compile(r"на (?:другий|наступний|слідуючий|третій) день|наступного (?:дня|ранку|вечора)|"
                      r"другого дня|назавтра|на другий ранок|наступної ночі", re.I)
COUNT_DAYS = re.compile(rf"(?:ще |вже |через |за |протягом )?({_NUM})\s+(?:повних\s+)?(?:дні|днів|день|доби|діб)", re.I)
SECOND_DAY = re.compile(r"вже другий день|другий день|третій день", re.I)
MOON = re.compile(r"до повн\w+ місяц\w+", re.I)
LATER_IN_DAY = re.compile(r"(?:пізно )?(?:ввечері|вночі|на світанку|на ранок|вранці|опівдні|опівночі|перед ранком|надвечір)",
                          re.I)


@dataclass
class Scene:
    from_line: int
    to_line: int
    day_lo: int | None
    day_hi: int | None
    part: str
    place: str | None
    cue: str = ""
    flags: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"from_line": self.from_line, "to_line": self.to_line, "day_lo": self.day_lo,
                "day_hi": self.day_hi, "part": self.part, "place": self.place, "cue": self.cue,
                "flags": self.flags}


def cues_in(text: str) -> list[str]:
    """Time cues the code finds in a stretch of text, as short readable hints for the arbiter."""
    out: list[str] = []
    for m in NEXT_DAY.finditer(text):
        out.append(f"'{m.group(0)}' = the next day (one day after the scene before)")
    for m in COUNT_DAYS.finditer(text):
        n = NUMBERS.get(m.group(1).lower())
        ctx = text[max(0, m.start() - 40): m.end() + 40].replace("\n", " ")
        out.append(f"'{ctx.strip()}': a span of {n} day(s) (to an event, or how long something lasted)")
    for m in SECOND_DAY.finditer(text):
        out.append(f"'{m.group(0)}': counts days of a state that began earlier")
    for m in MOON.finditer(text):
        ctx = text[max(0, m.start() - 40): m.end() + 30].replace("\n", " ")
        out.append(f"'{ctx.strip()}': the full moon is a fixed future date")
    return out


DAWN = re.compile(r"на світанку|перед ранком|розвидн|сірість світанку|світанок|вранці", re.I)


def moon_days(text: str) -> list[int]:
    """Numbers of days to the full moon that a text states ('ще чотири дні до повного місяця')."""
    out = []
    for m in MOON.finditer(text):
        tail = text[max(0, m.start() - 30): m.end() + 40].lower()
        n = next((NUMBERS[w] for w in re.findall(r"[\w']+", tail) if w in NUMBERS), None)
        if n:
            out.append(n)
    return out


PLAN_AFTER = re.compile(r"після повн", re.I)
PART_RANK = {p: i for i, p in enumerate(("dawn", "morning", "noon", "afternoon", "evening", "night"))}


def plan_after_moon(text: str) -> list[int]:
    """Days-to-full-moon numbers whose sentence is followed by 'після повні' (a stated plan to act after it)."""
    out = []
    for m in MOON.finditer(text):
        tail = text[m.end(): m.end() + 60]
        if PLAN_AFTER.search(tail):
            head = text[max(0, m.start() - 30): m.end() + 40].lower()
            n = next((NUMBERS[w] for w in re.findall(r"[\w']+", head) if w in NUMBERS), None)
            if n:
                out.append(n)
    return out


def is_gap(prev: "Scene", cur: "Scene") -> bool:
    """The narration skips time between two scenes: the part of day goes back, or the place changes."""
    pr, cr = PART_RANK.get(prev.part), PART_RANK.get(cur.part)
    if pr is not None and cr is not None and cr < pr:
        return True
    return bool(prev.place and cur.place and prev.place != cur.place)


def has_day_cue(text: str) -> bool:
    """A real 'a day has passed' cue. A number of days next to 'до повного місяця' is a calendar fact
    (see moon_days), not a cue that this scene is on another day."""
    if NEXT_DAY.search(text) or SECOND_DAY.search(text):
        return True
    for m in COUNT_DAYS.finditer(text):
        around = text[max(0, m.start() - 30): m.end() + 30]
        if not MOON.search(around):
            return True
    return False


def scene_text(paras: Sequence[Para], s: Scene) -> str:
    return "\n".join(p.text for p in paras if s.from_line <= p.line <= s.to_line)


def parse_scenes(obj: dict[str, Any]) -> list[Scene]:
    out = []
    for s in obj.get("scenes") or []:
        if not isinstance(s, dict) or not isinstance(s.get("from_line"), int) or not isinstance(s.get("to_line"), int):
            continue
        lo = s.get("day_lo", s.get("day"))
        hi = s.get("day_hi", lo)
        lo = lo if isinstance(lo, int) and lo >= 1 else None
        hi = hi if isinstance(hi, int) and hi >= 1 else lo
        if lo is not None and hi is not None and hi < lo:
            lo, hi = hi, lo
        part = s.get("part") if s.get("part") in PARTS else "unknown"
        place = s.get("place") if isinstance(s.get("place"), str) and s.get("place", "").strip() else None
        out.append(Scene(s["from_line"], s["to_line"], lo, hi, part, place, str(s.get("cue") or "")))
    out.sort(key=lambda x: x.from_line)
    return out


def scene_at(scenes: Sequence[Scene], line: int) -> Scene | None:
    for s in scenes:
        if s.from_line <= line <= s.to_line:
            return s
    return None


def overlap(a: Scene | None, b: Scene | None) -> bool:
    if a is None or b is None or a.day_lo is None or b.day_lo is None:
        return a is not None and b is not None and a.day_lo is None and b.day_lo is None
    return a.day_lo <= (b.day_hi or b.day_lo) and b.day_lo <= (a.day_hi or a.day_lo)


def check(scenes: Sequence[Scene], paras: Sequence[Para], *, repair: bool = False) -> dict[int, list[str]]:
    """Problems per scene index. Frame scenes (day None) are skipped. With repair=True the rules that
    have one right answer are applied in place (a scene that continues the one before it without a cue
    takes its day; a scene after a gap that carries out a stated plan takes the planned day) and the
    scene is flagged; the problems are still reported."""
    issues: dict[int, list[str]] = {}
    prev: Scene | None = None
    moon_targets: list[int] = []   # absolute days on which the text says the full moon falls
    plans: list[int] = []          # full-moon days after which someone said they would act
    first = True
    for i, s in enumerate(scenes):
        if s.day_lo is None:
            if not first:
                issues[i] = ["no day after the story has started"]
            continue
        probs: list[str] = []
        if first and s.day_lo != 1:
            probs.append("first story scene is not day 1")
        first = False
        text = scene_text(paras, s)
        hi = s.day_hi if s.day_hi is not None else s.day_lo
        if prev is not None:
            prev_lo = prev.day_lo or 0
            prev_hi = prev.day_hi if prev.day_hi is not None else prev_lo
            if hi < prev_lo:
                probs.append(f"day goes back ({hi} after {prev_lo})")
            if s.day_lo > prev_hi:
                jump = s.day_lo - prev_hi
                pending = [t for t in moon_targets if t >= prev_hi]
                dawn_wrap = jump == 1 and s.part in ("dawn", "morning") and bool(DAWN.search(text)) and prev.part in ("evening", "night")
                if has_day_cue(text) or dawn_wrap:
                    pass
                elif pending:
                    if hi > min(pending) + 1:
                        probs.append(f"day {hi} is later than the full moon (day {min(pending)}) allows")
                else:
                    probs.append(f"day rises by {jump} with no cue word in the scene and no calendar fact")
                    if repair:
                        s.day_lo, s.day_hi = prev_lo if prev_lo else prev_hi, prev_hi
                        s.flags.append("repaired_continuation")
                        hi = s.day_hi
        if prev is not None and plans and is_gap(prev, s):
            target = plans[0]
            if s.day_lo < target or hi > target + 1:
                probs.append(f"a plan to act after the full moon (day {target}) is pending and this scene follows a "
                             f"gap in the narration: it must be on day {target} or {target + 1}, not {s.day_lo}-{hi}")
                if repair:
                    s.day_lo, s.day_hi = target, target + 1
                    s.flags.append("repaired_plan")
                    hi = s.day_hi
                    plans.pop(0)
            else:
                plans.pop(0)
        for n in moon_days(text):
            moon_targets.append(s.day_lo + n)
        for n in plan_after_moon(text):
            plans.append(s.day_lo + n)
        if probs:
            issues[i] = probs
        prev = s
    return issues


TIMELINE_USER = """Text (every paragraph starts with its line tag [L<number>]):

{text}

Build the scene timeline of this text. A scene is a continuous stretch of lines in one time and one place.
JSON shape:
{{"scenes": [{{"from_line": 9, "to_line": 17, "day_lo": integer or null, "day_hi": integer or null,
  "part": one of {parts} or "unknown",
  "place": "short name of the place in Ukrainian, in the form the text uses (a tavern, an office, a palace, a courtyard), or null",
  "cue": "English: the fact in the text that fixes the day and part, with the Ukrainian words quoted"}}]}}
Rules:
- Scenes cover every line of the text once, in order, without gaps.
- Day 1 is the day the stranger arrives in the city (late afternoon). Later days are counted only from explicit cues. Ukrainian idioms: "на другий день" and "наступного дня" mean the next day; "до повного місяця ще чотири дні" means the full moon is four days after the day of that sentence; "вже другий день" counts days of a state (such as unconsciousness) that began earlier. A scene that continues the same evening or night keeps the same day. Something done "after the full moon" is on the night of the full moon or the night after.
- If the text fixes the day exactly, day_lo = day_hi. If it only allows a range, give the range (day_lo < day_hi) instead of guessing one day.
- The opening scene before the stranger arrives is a separate frame scene with both days null.
- Scenes that only retell earlier events (a character telling a story) keep the day of the telling.
- Do not use anything you remember about the books."""

ARBITER_USER = """Two readers built a day-by-day timeline of a story text. They disagree on the scenes below, or code found a problem in them. Decide each scene's day range.

Facts: day 1 is the day the stranger arrives in the city (late afternoon). Days never go back. Ukrainian idioms: "на другий день" and "наступного дня" mean the next day; "до повного місяця ще чотири дні" means the full moon is four days after the day of that sentence; "вже другий день" counts days of a state that began earlier. A character's stated plan fixes the date of the later scene that carries it out: if someone says he will act "after the full moon" and a later scene (after a gap in the narration) shows him acting, that scene is on the night of the full moon or the night after it, not earlier. A scene that directly continues the one before it in the same place, with no cue of a new day, is the same day. If the text cannot fix one day, give a range (day_lo < day_hi) that contains every reading the text allows; do not guess.

Scenes already settled (context): {settled}

Calendar facts fixed by earlier scenes (a scene after a gap in the narration may be several days later; use these):
{facts}

Scenes to decide:
{items}

Reply with JSON only: {{"scenes": [{{"index": number from the list, "day_lo": integer, "day_hi": integer, "part": one of {parts} or "unknown", "reason": "one English sentence naming the cue"}}]}}"""


def timeline_messages(text: str) -> list[dict[str, str]]:
    from .extract import ENTITY_SYSTEM
    return [{"role": "system", "content": ENTITY_SYSTEM},
            {"role": "user", "content": TIMELINE_USER.format(text=text, parts=" | ".join(PARTS))}]


def _fmt(s: Scene | None) -> str:
    if s is None or s.day_lo is None:
        return "none"
    d = f"{s.day_lo}" if s.day_hi in (None, s.day_lo) else f"{s.day_lo}-{s.day_hi}"
    return f"day {d} {s.part}"


def differing(base: Sequence[Scene], other: Sequence[Scene]) -> list[int]:
    started = False
    out = []
    for i, s in enumerate(base):
        o = scene_at(other, s.from_line)
        started = started or s.day_lo is not None
        if started and not overlap(s, o):
            out.append(i)
    return out


def calendar_facts(scenes: Sequence[Scene], paras: Sequence[Para], upto: int) -> list[str]:
    """Dates that earlier scenes fix for later ones (the full moon is N days after a given day)."""
    out = []
    for j in range(upto):
        s = scenes[j]
        if s.day_lo is None:
            continue
        txt = scene_text(paras, s)
        for m in MOON.finditer(txt):
            ctx = txt[max(0, m.start() - 160): m.end() + 260].replace("\n", " ")
            tail = txt[max(0, m.start() - 30): m.end() + 40].lower()
            n = next((NUMBERS[w] for w in re.findall(r"[\w']+", tail) if w in NUMBERS), None)
            day = f"day {s.day_lo}" if s.day_hi in (None, s.day_lo) else f"day {s.day_lo}-{s.day_hi}"
            out.append(f"scene [{j}] ({day}) says: ...{ctx}... "
                       + (f"-> the full moon is {n} days after that day" if n else ""))
    return out


def arbitrate(provider: Provider, model: str, base: list[Scene], other: list[Scene], paras: Sequence[Para],
              issues: dict[int, list[str]], cache: dict[str, Any] | None = None) -> dict[int, dict[str, Any]]:
    """Scenes in order. A scene is decided by the arbiter when the readers differ, code flagged it, or an
    earlier decision left it behind. Each call sees the scenes settled so far and the calendar facts
    they fix. Decisions are applied as they come (so later scenes see them)."""
    cache = cache if cache is not None else {}
    first_todo = set(differing(base, other))   # other problems are re-checked live, after earlier decisions
    decided: dict[int, dict[str, Any]] = {}
    for i, s in enumerate(base):
        again = check(base[: i + 1], paras).get(i)
        if i not in first_todo and not again:
            continue
        txt = scene_text(paras, s)
        excerpt = txt if len(txt) < 1800 else txt[:900] + " [...] " + txt[-900:]
        o = scene_at(other, s.from_line)
        prev = next((base[j] for j in range(i - 1, -1, -1) if base[j].day_lo is not None), None)
        item = (f"[{i}] lines {s.from_line}-{s.to_line}, place {s.place}\n"
                f"  reader A: {_fmt(s)} ({s.cue[:160]})\n  reader B: {_fmt(o)} ({(o.cue if o else '')[:160]})\n"
                f"  scene before (settled): {_fmt(prev)}\n  code found: {'; '.join(cues_in(txt)) or 'no cue words'}\n"
                f"  code problems: {'; '.join(issues.get(i, []) + (again or [])) or 'none (the readers differ)'}\n"
                f"  text: {excerpt}")
        facts = calendar_facts(base, paras, i)
        settled = "; ".join(f"[{j}] L{x.from_line}-{x.to_line} {_fmt(x)}" for j, x in enumerate(base[:i])
                            if x.day_lo is not None)
        for attempt in (0, 1):
            key = f"{i}" if attempt == 0 else f"{i}.retry"
            if key not in cache:
                extra = ""
                if attempt:
                    extra = ("\n\nYour previous answer for this scene failed a code check: "
                             + "; ".join(check(base[: i + 1], paras).get(i) or []) + ". Answer again.")
                msgs = [{"role": "system", "content": "You answer with one JSON object only."},
                        {"role": "user", "content": ARBITER_USER.format(
                            settled=settled or "none", items=item, parts=" | ".join(PARTS),
                            facts="\n".join(facts) or "none") + extra}]
                obj, _ = extract.ask_json(provider, model, msgs)
                rs = [r for r in obj.get("scenes") or [] if isinstance(r, dict) and isinstance(r.get("day_lo"), int)]
                cache[key] = rs[0] if rs else {}
            r = cache[key]
            if isinstance(r.get("day_lo"), int):
                decided[i] = r
                apply_arbitration(base, {i: r})
            if not check(base[: i + 1], paras).get(i):
                break
    return decided


def apply_arbitration(base: list[Scene], decided: dict[int, dict[str, Any]]) -> None:
    for i, r in decided.items():
        s = base[i]
        lo = r["day_lo"]
        hi = r["day_hi"] if isinstance(r.get("day_hi"), int) and r["day_hi"] >= lo else lo
        s.day_lo, s.day_hi = lo, hi
        if r.get("part") in PARTS:
            s.part = r["part"]
        s.cue = str(r.get("reason") or s.cue)
        s.flags.append("arbitrated")


def enforce(scenes: list[Scene]) -> None:
    """Last resort after arbitration: days never go back. A scene that still falls behind its
    predecessor is widened into the range from the earlier day up to its own, and flagged."""
    floor: int | None = None
    for s in scenes:
        if s.day_lo is None:
            continue
        if floor is not None and s.day_hi is not None and s.day_hi < floor:
            s.day_lo = s.day_hi = floor
            s.flags.append("clamped_monotonic")
        elif floor is not None and s.day_lo < floor:
            s.day_lo = floor
            s.flags.append("clamped_monotonic")
        floor = s.day_lo


def build(provider: Provider, models: tuple[str, str], arbiter: str, paras: Sequence[Para],
          *, cache: dict[str, Any] | None = None) -> tuple[list[Scene], dict[str, Any]]:
    """Two readers, code check, one arbitration. `cache` holds raw replies by key so a rerun costs nothing."""
    cache = cache if cache is not None else {}
    text = "\n".join(f"[L{p.line}] {p.text}" for p in paras)
    readers: list[list[Scene]] = []
    for k, m in enumerate(models):
        key = f"timeline_{k}"
        if key not in cache:
            obj, _ = extract.ask_json(provider, m, timeline_messages(text))
            cache[key] = obj
        readers.append(parse_scenes(cache[key]))
    base, other = readers
    issues_before = check(base, paras)
    differ = differing(base, other)
    decided = arbitrate(provider, arbiter, base, other, paras, issues_before, cache.setdefault("arbiter", {}))
    issues_after = check(base, paras)
    check(base, paras, repair=True)
    enforce(base)
    report = {"scenes": len(base), "issues_before": {str(k): v for k, v in issues_before.items()},
              "readers_differ": differ, "arbitrated": sorted(decided), "issues_after": {str(k): v for k, v in issues_after.items()},
              "issues_final": {str(k): v for k, v in check(base, paras).items()}}
    return base, report
