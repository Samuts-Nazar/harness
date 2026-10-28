"""Readable items: reading is an ordinary action (outsider plan 1, task 6; spec D2).

An item may carry `content` in campaign_meta `inventory_meta` (written by the package importer):
inline text, or `{"file": <relative path>}` searched on demand. A file is read at play time and
never copied into the repo or the campaign store.

One read:
1. `expand_terms`: one cheap typed call turns the request into at most 12 search terms (forms of
   the word, aliases, neighbouring concepts; not limited to any topic or set of characters);
2. `grep_file`: code finds the terms (case-insensitive, Ukrainian case endings as in
   `harness/glossary.py`), takes each hit with its neighbouring lines, merges overlapping hits and
   caps the result (2 000 characters per read; a one- or two-letter word is no term, and a word
   with very many hits only fills what the rarer terms leave);
3. one cheap reader call says what the passages say about the request, close to the text, with
   nothing added, plus short records (at most 600 characters each);
4. the duration judgment (the clock's buckets) gets the amount read and the clock moves on;
5. the records become the reader's knowledge: knower source `read: <item id>` at the time the
   reading ends (`knowledge.READ`). Anyone else who reads the item gets the same channel under
   their own name.

A missing file, an unsafe path, no content or no hits give a plain "nothing found" result: no
reader call, no time, no knowledge.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Sequence

from .glossary import ENDINGS
from .judge import choice_q, yes_no_q
from .knowledge import READ_PREFIX
from .models import TOLD
from .world import clock as clk

if TYPE_CHECKING:
    from .pipeline import Engine

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = PROJECT_ROOT / "data"
READ_EVENT = "item_read"
READ_DURATION_TAG, READ_INTENT_TAG = "read_duration", "read_intent"
MAX_TERMS = 12
CAP_CHARS = 2000  # one read returns at most this much text
RECORD_CHARS = 600  # one stored record
MAX_RECORDS = 6
MIN_TERM_LETTERS = 3  # «і», «на», «що»: no search term
COMMON_HITS = 300  # a term with more hit lines than this only fills what the others leave
NO_CONTENT = "У цій речі нема чого читати."
NO_FILE = "Файл не знайдено: нічого прочитати не вдалося."
NOTHING_FOUND = "Нічого про це не знайдено."
COULD_NOT_READ = "Прочитати не вдалося."

# The glossary's name endings plus the soft-stem and plural endings common nouns also take
# («стихій» / «стихію», «бажання» / «бажанню»), longest first, without the empty one.
_NOUN_ENDINGS = ("ями", "ях", "ям", "ій", "ію", "ії", "ей", "ої", "ь", "й", "о")
_ENDS = sorted({e for e in (*ENDINGS, *_NOUN_ENDINGS) if e}, key=len, reverse=True)
_END_RE = "(?:" + "|".join(_ENDS) + ")?"


@dataclass
class Passage:
    start: int  # 1-based first line
    end: int  # 1-based last line
    text: str
    terms: tuple[str, ...] = ()


@dataclass
class ReadResult:
    text: str  # what the reader read, as shown to the player
    minutes: int = 0
    records: list[str] = field(default_factory=list)
    found: bool = False
    terms: list[str] = field(default_factory=list)
    chars: int = 0  # characters of the passages read
    event_id: int | None = None
    item: str = ""  # the item's name, as the player knows it


# -- content ------------------------------------------------------------------------------------
def inventory_meta(eng: "Engine") -> dict[str, Any]:
    row = eng.conn.execute("SELECT value FROM campaign_meta WHERE key='inventory_meta'").fetchone()
    if not row:
        return {}
    try:
        meta = json.loads(row[0])
    except (TypeError, ValueError):
        return {}
    return meta if isinstance(meta, dict) else {}


def content_of(eng: "Engine", item_id: str) -> str | dict[str, Any] | None:
    c = (inventory_meta(eng).get(item_id) or {}).get("content")
    return c if isinstance(c, (str, dict)) and c else None


def readable_held(eng: "Engine", character: str) -> dict[str, str]:
    """id -> name of the items with content that `character` holds (any location)."""
    meta = inventory_meta(eng)
    out = {}
    for el in eng.live.snapshot().get(character, {}).values():
        if getattr(el, "id", None) and (meta.get(el.id) or {}).get("content"):
            out[el.id] = el.item
    return out


def item_name_in(snapshot: Any, item_id: str) -> str:
    """The name of the item with this id in a live-state snapshot (the bare id when gone)."""
    for elems in snapshot.values():
        for el in elems.values():
            if getattr(el, "id", None) == item_id:
                return el.item
    return item_id.removeprefix("item:")


def item_name(eng: "Engine", item_id: str) -> str:
    return item_name_in(eng.live.snapshot(), item_id)


def resolve_file(eng: "Engine", rel: str) -> Path | None:
    """The file a `{file: ...}` content names: a relative path under the project's `data/` (given
    as `data/x` or `x`), nowhere else (not the campaign directory: its memory files are not a
    book). Anything else (absolute, `..`, a path that leaves `data/` through a link) is refused:
    None. `data/` itself may be a link (to the main checkout). Existence is not checked here."""
    if not isinstance(rel, str) or not rel.strip():
        return None
    p = Path(rel.strip())
    if p.is_absolute() or ".." in p.parts:
        return None
    if p.parts and p.parts[0] == "data":  # `data/x` names the same file as `x`
        p = Path(*p.parts[1:])
    if not p.parts:
        return None
    base, full = DATA_DIR.resolve(), (DATA_DIR / p).resolve()
    return full if full.is_relative_to(base) else None


# -- term expansion ------------------------------------------------------------------------------
EXPAND_SYSTEM = (
    "You turn a reader's request into search terms for a plain-text search of a Ukrainian book. "
    "Return JSON only: {\"terms\": [\"...\"]}, at most 12 terms, most important first. Include: "
    "the key words of the request in Ukrainian in their dictionary form and their common "
    "inflected forms; other names of the same person, creature, place or thing (aliases, "
    "nicknames, titles, other spellings); and closely neighbouring concepts a passage about it "
    "would likely mention. Each term is one to three words, lowercase. Never generic words "
    "(і, що, він, був, людина, час).")


def _parse_json(raw: str) -> Any:
    """The first JSON object in `raw` (text before it, or after it, is ignored)."""
    text = raw or ""
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object")
    try:
        return json.JSONDecoder().raw_decode(text[start:])[0]
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise ValueError("no JSON object") from None
        return json.loads(m.group(0))


def _letters(term: str) -> int:
    return sum(ch.isalpha() for ch in term)


def _clean_terms(raw: Sequence[Any]) -> list[str]:
    out: list[str] = []
    for t in raw:
        if not isinstance(t, str):
            continue
        t = " ".join(t.casefold().split()).strip(" .,;:!?\"'«»")
        if _letters(t) >= MIN_TERM_LETTERS and t not in out:
            out.append(t)
    return out[:MAX_TERMS]


def _caller(llm: Any) -> Callable[[list[dict[str, str]]], str]:
    if callable(llm) and not hasattr(llm, "_complete"):
        return llm
    return lambda msgs: llm._complete("reader", msgs)


def expand_terms(llm: Any, request: str) -> list[str]:
    """At most 12 search terms for `request`. `llm`: the engine (role `reader`) or a callable
    taking chat messages. An unreadable answer falls back to the request's own words."""
    msgs = [{"role": "system", "content": EXPAND_SYSTEM},
            {"role": "user", "content": f"Request: {request}"}]
    try:
        got = _parse_json(_caller(llm)(msgs)).get("terms", [])
        terms = _clean_terms(got if isinstance(got, list) else [])
    except (ValueError, AttributeError):
        terms = []
    return terms or _clean_terms(re.findall(r"\w+", request))


# -- grep ----------------------------------------------------------------------------------------
def _word_re(word: str) -> str:
    """A word with its Ukrainian case endings: the stem (one ending cut from words of four or
    more letters, at least three letters left) followed by any ending, as `Glossary` matches
    declined names."""
    w = word.casefold()
    stem = w
    if len(w) >= 4:
        for e in _ENDS:
            if w.endswith(e) and len(w) - len(e) >= 3:
                stem = w[: -len(e)]
                break
    return re.escape(stem) + _END_RE


def term_pattern(term: str) -> re.Pattern[str]:
    words = term.split()
    body = r"\s+".join(_word_re(w) for w in words)
    return re.compile(rf"(?<!\w){body}(?!\w)", re.IGNORECASE)


def _clip(line: str, pats: Sequence[re.Pattern[str]], budget: int) -> str:
    """A line longer than `budget`: the part around its first hit, cut at word boundaries."""
    if len(line) <= budget:
        return line
    pos = min((m.start() for p in pats if (m := p.search(line))), default=0)
    a = max(0, pos - budget // 2)
    b = min(len(line), a + budget)
    a = max(0, b - budget)
    part = line[a:b]
    if a > 0 and " " in part:
        part = part.split(" ", 1)[1]
    if b < len(line) and " " in part:
        part = part.rsplit(" ", 1)[0]
    return ("…" if a > 0 else "") + part.strip() + ("…" if b < len(line) else "")


def grep_lines(lines: Sequence[str], terms: Sequence[str], context_lines: int = 3,
               cap_chars: int = CAP_CHARS) -> list[Passage]:
    terms = _clean_terms(terms)
    if not terms:
        return []
    pats = {t: term_pattern(t) for t in terms}
    hits: dict[str, list[int]] = {t: [i for i, ln in enumerate(lines) if p.search(ln)]
                                  for t, p in pats.items()}
    hits = {t: h for t, h in hits.items() if h}
    if not hits:
        return []
    rare = {t: h for t, h in hits.items() if len(h) <= COMMON_HITS}
    use = rare or hits  # a common word counts only when nothing rarer was found
    weight = {t: 1.0 / math.log(2 + len(h)) for t, h in use.items()}
    line_terms: dict[int, set[str]] = {}
    for t, h in use.items():
        for i in h:
            line_terms.setdefault(i, set()).add(t)
    # windows around each hit line, overlapping or touching ones merged
    wins: list[list[int]] = []
    for i in sorted(line_terms):
        a, b = max(0, i - context_lines), min(len(lines) - 1, i + context_lines)
        if wins and a <= wins[-1][1] + 1:
            wins[-1][1] = max(wins[-1][1], b)
        else:
            wins.append([a, b])

    def score(w: list[int]) -> float:
        ts = set().union(*(line_terms.get(i, set()) for i in range(w[0], w[1] + 1)))
        return sum(weight[t] for t in ts)

    order = sorted(range(len(wins)), key=lambda k: (-score(wins[k]), k))
    chosen: list[Passage] = []
    left = cap_chars
    plist = [pats[t] for t in use]
    clean = [ln.rstrip("\n") for ln in lines]

    def size(a: int, b: int) -> int:
        return sum(len(clean[i]) + 1 for i in range(a, b + 1))

    for k in order:
        if left < 80:
            break
        wa, wb = wins[k]
        hit_lines = [i for i in range(wa, wb + 1) if i in line_terms]
        a, b = hit_lines[0], hit_lines[-1]
        if size(a, b) > left:  # the hits alone do not fit: the first hit line, clipped if long
            a = b = hit_lines[0]
        if size(a, b) > left:
            text = _clip(clean[a], plist, left - 1).strip()
        else:  # grow outward by context lines while it fits
            grew = True
            while grew:
                grew = False
                if a > wa and size(a - 1, b) <= left:
                    a, grew = a - 1, True
                if b < wb and size(a, b + 1) <= left:
                    b, grew = b + 1, True
            text = "\n".join(clean[a:b + 1]).strip()
        if not text:
            continue
        ts = tuple(sorted(set().union(*(line_terms.get(i, set()) for i in range(a, b + 1)))))
        chosen.append(Passage(a + 1, b + 1, text, ts))
        left -= len(text) + 1
    return sorted(chosen, key=lambda p: p.start)


def grep_file(path: Path, terms: list[str], context_lines: int = 3,
              cap_chars: int = CAP_CHARS) -> list[Passage]:
    """Passages of the file around the terms (see the module docstring). A missing file: []."""
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    return grep_lines(text.splitlines(), terms, context_lines, cap_chars)


# -- the reader ----------------------------------------------------------------------------------
READER_SYSTEM = (
    "You read passages of a text for someone who searches it. Use only the passages: say what "
    "they actually say about the request, close to the text, with nothing added, no outside "
    "knowledge and no guessing. Answer only the topic of the lookup: say nothing about what the "
    "reader does with his hands or body, the item, or anything else in the scene. Write the text "
    "in {out} only, with no word of any other language. If the passages say nothing about the "
    "topic, found is false. Return JSON only: "
    "{{\"found\": true|false, \"text\": \"what the passages say about the request, in {out}, at "
    "most 1200 characters\", \"records\": [\"one point the reader now knows from the text, in "
    "{rec}, at most 600 characters\"]}} with at most {n} records.")


def _cut(text: str, n: int) -> str:
    text = " ".join(str(text).split())
    if len(text) <= n:
        return text
    return text[: n - 1].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


# The lookup topic of a turn (outsider live check, problem 4): "Знімаю рюкзак, розстібаю його,
# дістаю ноутбук і відкриваю свої нотатки про духа лампи" looks up «про духа лампи», not the
# backpack. Derived in code, no model call (the read_intent judge has only yes/no, choice and score
# questions, so it cannot return the topic):
# - quoted speech is removed first (what he says is no lookup);
# - the turn is cut into clauses; a reading clause has a reading verb, or names the item (a name of
#   four letters or more, as a whole word with its endings); a clause that opens with «що/чи/де/як»
#   right after a reading clause continues it («Гляну в нотатник, що там про джинів»);
# - the topic is what follows «про»/about in the reading clauses (never in a later clause: «…і питаю
#   її про місто» is talk); without one, the reading clauses that have a verb;
# - otherwise, or when «про» stands only outside the reading clauses («Запитую її про Цірі й
#   заглядаю в ноутбук»), the whole turn without the quoted speech. Inline content up to 2 000
#   characters is read whole anyway; the reader's instruction says to answer only the lookup.
_QUOTED = re.compile(r"«[^»]*»|\"[^\"]*\"|“[^”]*”|„[^“”]*[“”]")
_CLAUSE = re.compile(r"[,;:.!?…\n]+|\s+(?:і|й|та|а|потім|and|then)\s+", re.IGNORECASE)
_CONTINUES = re.compile(r"^(?:що|чи|де|як|котр\w*|what|whether|where|how)(?!\w)", re.IGNORECASE)
_READ_VERB = re.compile(
    r"(?<!\w)(?:чита\w*|прочита\w*|перечита\w*|шука\w*|пошука\w*|знайд\w*|знайти|знаход\w*|"
    r"горта\w*|перегляда\w*|переглян\w*|загляда\w*|заглян\w*|глян\w*|напис\w*|"
    r"(?:по)?дивл\w*(?= (?:в|у|що)(?!\w)|$)|відкрива\w* (?:\w+ )?(?:нотат|запис|файл|сторін|"
    r"розділ|документ|лист)\w*|нотат\w*|запис\w*|read\w*|look\w* (?:up|for|in|at)|"
    r"search\w*|find\w*|notes?|written)(?!\w)", re.IGNORECASE)
_ABOUT = re.compile(r"(?<!\w)(?:про|щодо|стосовно|about|on the subject of)(?!\w)", re.IGNORECASE)
_MIN_ITEM = 4  # an item name shorter than this is not matched in the turn at all


def lookup_topic(text: str, item: str = "") -> str:
    """What the turn looks up in the item (see above). Never empty for a non-empty turn."""
    clean = re.sub(r"\s+([,.;:!?…])", r"\1",
                   " ".join(_QUOTED.sub(" ", text or "").replace("*", " ").split()))
    whole = clean or " ".join((text or "").split())
    name = item.strip()
    item_re = term_pattern(name.casefold()) if len(name) >= _MIN_ITEM else None
    parts = [p.strip() for p in _CLAUSE.split(clean) if p and p.strip()]
    verb = [bool(_READ_VERB.search(p)) for p in parts]
    reading = [v or bool(item_re is not None and item_re.search(p)) for p, v in zip(parts, verb)]
    for i in range(1, len(parts)):  # «…, що там про джинів» continues the reading clause before it
        if reading[i - 1] and not reading[i] and _CONTINUES.search(parts[i]):
            reading[i] = verb[i] = True
    if not any(reading):
        return whole
    topics: list[str] = []
    for p, r in zip(parts, reading):
        m = _ABOUT.search(p) if r else None
        if m and p[m.start():].strip() not in topics:
            topics.append(p[m.start():].strip())
    if topics:
        return "; ".join(topics)
    if any(_ABOUT.search(p) for p, r in zip(parts, reading) if not r):
        return whole  # the «про» is talk outside the lookup: no topic of the lookup to take
    with_verb = [p for p, r, v in zip(parts, reading, verb) if r and v]
    return "; ".join(with_verb) or whole


def _reader(eng: "Engine", request: str, passages: Sequence[Passage]) -> tuple[bool, str, list[str]]:
    out_lang = eng.output_language or "the language of the passages"
    rec_lang = eng.record_language or "the language of the passages"
    body = "\n\n".join(f"[lines {p.start}-{p.end}]\n{p.text}" for p in passages)
    msgs = [{"role": "system", "content": READER_SYSTEM.format(out=out_lang, rec=rec_lang,
                                                               n=MAX_RECORDS)},
            {"role": "user", "content": f"Request (the topic of the lookup): {request}\n\n"
                                        f"Passages:\n{body}"}]
    got: Any = None
    for attempt in range(2):  # an unreadable answer (a cheap model may run on and break its JSON)
        raw = eng._complete("reader", msgs)  # is asked once more
        try:
            got = _parse_json(raw)
            break
        except ValueError:
            eng._note("reader_unparsed", attempt=attempt + 1, chars=len(raw or ""))
    if got is None:
        return False, "", []
    if not isinstance(got, dict) or not got.get("found"):
        return False, "", []
    recs = [_cut(r, RECORD_CHARS) for r in (got.get("records") or []) if isinstance(r, str) and r.strip()]
    text = _cut(got.get("text") or "", CAP_CHARS)
    # the text shown to the player is the reader's own text in the output language; records
    # (record language) are never shown in its place, so a read without text found nothing
    return bool(text), text, recs[:MAX_RECORDS]


def read_minutes(eng: "Engine", character: str, item: str, request: str, chars: int) -> int:
    """The duration judgment for a read, with the amount read as its input."""
    words = max(1, chars // 6)
    q = {"duration": choice_q(
        "How much in-world time does this reading take: finding the place and reading the "
        "amount below with attention?",
        {k: d for k, (d, _) in clk.DURATION_BUCKETS.items()}, tag=READ_DURATION_TAG)}
    state = [f"{eng.names.real(character)} reads {item}, looking for: {request}",
             f"Characters read: {chars}", f"About {words} words"]
    got = eng.judge.ask(state, q)
    bucket = str(got["duration"].answer)
    return clk.minutes_of(bucket) if bucket in clk.DURATION_BUCKETS else clk.minutes_of("minutes")


def _log(eng: "Engine", character: str, item_id: str, request: str, res: ReadResult,
         **extra: Any) -> ReadResult:
    """The read as an event (also when nothing was found, so the player sees the result and a
    reopened campaign shows it again). Witness: the reader only."""
    ev = eng._event(READ_EVENT, [character], {
        "reader": character, "item": item_id, "item_name": res.item, "request": request,
        "terms": res.terms, "chars": res.chars, "minutes": res.minutes, "found": res.found,
        "text": res.text, "records": res.records, **extra}, witnesses=[character],
        notability=0.3)
    res.event_id = ev.id
    return res


def failed(eng: "Engine", character: str, item_id: str, request: str) -> ReadResult:
    """A read that could not run (no judge or model answered): logged, nothing learned."""
    return _log(eng, character, item_id, request,
                ReadResult(COULD_NOT_READ, item=item_name(eng, item_id)))


def read(engine: "Engine", character: str, item_id: str, request: str) -> ReadResult:
    """`character` reads item `item_id` looking for `request`. See the module docstring."""
    eng = engine
    content = content_of(eng, item_id)
    if content is None:
        return ReadResult(NO_CONTENT)
    name = item_name(eng, item_id)
    terms: list[str] = []
    if isinstance(content, str):  # inline text: a letter, a note
        lines = content.splitlines() or [content]
        if len(content) <= CAP_CHARS:
            passages = [Passage(1, len(lines), content.strip())]
        else:
            terms = expand_terms(eng, request)
            passages = grep_lines(lines, terms)
    else:
        path = resolve_file(eng, str(content.get("file", "")))
        if path is None or not path.is_file():
            eng._note("read_no_file", item=item_id, file=str(content.get("file", "")))
            return _log(eng, character, item_id, request, ReadResult(NO_FILE, item=name))
        terms = expand_terms(eng, request)
        passages = grep_file(path, terms)
    if not passages:
        eng._note("read_nothing_found", item=item_id, terms=terms)
        return _log(eng, character, item_id, request,
                    ReadResult(NOTHING_FOUND, terms=terms, item=name))
    chars = sum(len(p.text) for p in passages)
    found, text, recs = _reader(eng, request, passages)
    if not found:
        eng._note("read_nothing_found", item=item_id, terms=terms, chars=chars)
        return _log(eng, character, item_id, request,
                    ReadResult(NOTHING_FOUND, terms=terms, chars=chars, item=name))
    minutes = read_minutes(eng, character, name, request, chars)
    res = ReadResult(text, minutes, recs, True, terms, chars, item=name)
    eng.scene.time += minutes
    _log(eng, character, item_id, request, res,
         lines=[[p.start, p.end] for p in passages])
    for r in recs:
        eng.facts.add_campaign(r, source_event_id=res.event_id, game_time=eng.scene.time,
                               location=eng.scene.location, notability=0.4,
                               knowers=[(character, TOLD, READ_PREFIX + item_id)])
    eng.refresh_memory()
    return res


def read_intent(eng: "Engine", player_text: str, held: dict[str, str]) -> str | None:
    """Which held content item (if any) the player's action reads: one yes/no judgment per item,
    asked in one call. None when no item is read."""
    if not held:
        return None
    qs = {iid: yes_no_q(f"Does the player in this turn read, search or look something up in "
                       f"{name} (its text, files or pages)?", tag=READ_INTENT_TAG) for iid, name in held.items()}
    got = eng.judge.ask([f"The player's turn: {player_text}"], qs)
    for iid in held:
        if got.get(iid) is not None and got[iid].answer:
            return iid
    return None

