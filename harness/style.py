"""Style (task 15): how NPCs and the narrator are asked to write, so the lines read like living
people in Sapkowski's Ukrainian translation and not like an assistant.

Everything about wording lives here; `context.py` only calls it. Parts:

- `Style`: the world's style sheet (`worlds/<world>/style.md`, by section), the prompt wording for
  NPC calls and the narrator, and runtime *exemplars*: 1-3 short passages picked from the local
  book file (`data/witcher_books.txt`, never committed) that match the situation.
- NPC output with its own beats: an NPC writes speech with the dash and may weave its own small
  actions into it, as the books do. `split_npc_output` separates speech from beats; the engine
  stores the beats as the NPC's observable actions. `foreign_voice` detects an NPC writing for
  somebody else.
- `ExemplarIndex`: passages of the book file, scored against a situation text.
- `manner_messages` / `parse_manner`: a cheap model writes a few manner notes per NPC, once.
- `assistant_isms`: a small detector for the phrases that give a model away (grading and the
  debug report only; nothing is regenerated because of it).
"""
from __future__ import annotations

import math
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Iterable, Sequence

from .models import CharacterProfile
from .providers import Messages

if TYPE_CHECKING:
    from .shape import Shape

REPO = Path(__file__).resolve().parents[1]
WORLDS = REPO / "worlds"
DASHES = "—–"


# ---------------------------------------------------------------------------------------------
# NPC output: speech and own beats
# ---------------------------------------------------------------------------------------------
_SPLIT = re.compile(r"\s+[—–]\s+")
_LEAD = re.compile(r"^\s*[—–]\s*")
_TAG_VERBS = ("каж", "сказ", "мовив", "мовл", "відпов", "відказ", "спита", "запита", "питав",
              "питає", "промов", "додав", "додає", "продовж", "озвав", "заявив")
_PRON = {"він", "вона", "воно", "вони"}


@dataclass
class NpcOutput:
    speech: str  # what is said aloud, joined
    beats: list[str] = field(default_factory=list)  # own actions and manner, as written
    has_dash: bool = False  # the text used dialogue dashes at all


def _is_tag(beat: str) -> bool:
    """A bare speech tag ("каже Горст", "відповів староста"): no action in it."""
    words = re.findall(r"\w+", beat.lower())
    return 0 < len(words) <= 4 and any(w.startswith(_TAG_VERBS) for w in words)


_PRESENT_END = ("ить", "їть", "ається", "ється", "иться", "ться", "ає", "яє", "ує", "юєте", "оче",
                "іче", "ече", "иче", "є")
_PAST_END = ("ав", "ив", "ув", "ев", "яв", "ала", "ила", "ула", "ела", "яла", "али", "или", "ули",
             "ели", "яли", "ало", "ило", "уло", "іла", "іли", "іло", "ед", "ed")
_PAST_REFL = ("вся", "лася", "лося", "лися", "лась", "лось", "лись")  # not imperatives: "-йся"
_PREFIXES = ("під", "по", "за", "на", "ви", "роз", "при", "від", "пере", "об", "с", "з", "у", "в")
_IRREGULAR = {"потер", "втер", "витер", "обтер", "ліг", "сів", "виліз", "поліз", "заліз", "приніс",
              "виніс", "поніс", "відніс", "зніс", "вліз", "помер", "здер", "задер", "запер",
              "був", "була", "було", "були", "зник", "замовк", "змовк", "крикнув", "зберіг",
              "втік", "підвів", "повів", "привів", "зрів", "вдарив"}
_NOT_VERBS = {"школа", "стіл", "село", "тіло", "діло", "число", "чоло", "зло", "добро", "кров",
              "любов", "мала", "хвиля", "скеля", "земля", "стріла", "кола", "вона", "ніколи"}
_SPEAKERS = {"я", "ми", "ти", "ви", "мені", "мене", "тобі", "тебе", "нам", "нас", "вам", "вас"}
_GERUND = ("ючи", "ячи", "ачи", "вши", "шись", "вшись")


def _is_verb(w: str) -> bool:
    """A third-person verb form (past or present), strict enough to leave nouns alone."""
    if w in _NOT_VERBS:
        return False
    if w in _IRREGULAR:
        return True
    if len(w) >= 4 and (w.endswith(_PAST_END) or w.endswith(_PAST_REFL)):
        return True
    if len(w) >= 6 and w.endswith("ів") and re.search(r"[аеиіоуя][^аеиіоуяю]+ів$", w):
        return True  # прошепотів, ревів (a genitive plural noun is rare this early in a piece)
    if len(w) >= 5 and w.endswith(_PRESENT_END):
        return True
    # consonant-final past with a prefix: замовк, підвів, зник
    return len(w) >= 5 and w.endswith(("вк", "ик", "ік", "ід", "ів")) and w.startswith(_PREFIXES)


def _is_beat(piece: str, names: Iterable[str] = ()) -> bool:
    """Does a piece between dashes read as a narrated act or a speech tag? It does if, with no
    I/we/you before it, it starts with he/she/they, has a known name early, has a speech-tag
    stem, or has a third-person verb among its first three words (or later, after a leading
    participial clause). Anything else (an adverb, a noun, an imperative) is the speech going
    on after a dash."""
    words = re.findall(r"[\w']+", piece.lower())[:8]
    if not words:
        return False
    known = {n.lower() for n in names if n}
    gerund = any(w.endswith(_GERUND) for w in words[:3])
    for i, w in enumerate(words):
        if w in _SPEAKERS or (i == 0 and w in {"це", "то", "ось", "так", "ні", "тут", "там"}):
            return False
        if w in _PRON and i == 0:
            return True
        if w in known and i < 3:
            return True
        if w.startswith(_TAG_VERBS) and len(w) > 3:
            return True
        if _is_verb(w) and (i <= 2 or gerund):
            return True
    return False


def _speech_tail(s: str) -> str:
    return re.sub(r"[,;:]\s*$", ".", s.strip())


def split_npc_output(text: str, names: Iterable[str] = ()) -> NpcOutput:
    """Separate speech from the NPC's own beats in book-style dialogue. In a paragraph that
    starts with a dash the pieces between dashes alternate speech, beat, speech, ...; a paragraph
    that starts without a dash begins with a beat. A text with no dash at all is plain speech
    (the old form). A piece longer than 40 words is never a beat (a dash inside a speech). `names`: known
    character names, which mark a piece as a beat."""
    text = text.strip()
    if not re.search(r"(?:^|\s)[—–](?:\s|$)", text):
        return NpcOutput(text, [], False)
    speech: list[str] = []
    beats: list[str] = []
    for para in (p.strip() for p in re.split(r"\n+", text)):
        if not para:
            continue
        if _LEAD.match(para):
            pieces, is_beat = _SPLIT.split(_LEAD.sub("", para)), False
        elif _SPLIT.search(para):
            pieces, is_beat = _SPLIT.split(para), True
        else:
            beats.append(para)
            continue
        speech_closed = True  # nothing of this paragraph's speech yet
        for piece in pieces:
            piece = piece.strip()
            if not piece:
                is_beat = not is_beat
                continue
            if is_beat and len(piece.split()) <= 40:
                if not _is_beat(piece, names):  # a dash inside the speech, not a narrated act
                    if speech and not speech_closed:
                        speech[-1] = f"{speech[-1]} — {piece}"
                    else:
                        speech.append(piece)
                    speech_closed = False
                    continue
                if not _is_tag(piece):
                    beats.append(piece)
                speech_closed = True
            else:
                speech.append(piece)
                speech_closed = False
            is_beat = not is_beat
    joined = ""
    for piece in speech:  # "..., — додав він. — Тут" : the comma was for the tag
        if joined and joined.endswith(",") and piece[:1].isupper():
            joined = joined[:-1] + "."
        joined = f"{joined} {piece}" if joined else piece
    return NpcOutput(_speech_tail(joined) if joined else "", beats, True)


def beat_as_action(beat: str, name: str, aliases: Iterable[str] = ()) -> str:
    """A beat as one observable-action sentence naming the actor ("озирнувся, стишив голос" ->
    "Горст озирнувся, стишив голос."). `aliases`: how the actor is shown to a player who does
    not know the name (the appearance label); a beat that opens with one names the actor."""
    b = beat.strip().strip(",;:").strip()
    if not b:
        return ""
    for a in sorted((a.strip() for a in aliases if a and a.strip()), key=len, reverse=True):
        if b.lower().startswith(a.lower()) and (len(b) == len(a) or not b[len(a)].isalnum()):
            b = name + b[len(a):]
            break
    first = b.split(None, 1)
    if first and first[0].lower() in _PRON:
        b = name + (" " + first[1] if len(first) > 1 else "")
    elif name and name[:4].lower() not in b.lower():
        b = f"{name} {b[0].lower() + b[1:]}"
    b = b[0].upper() + b[1:]
    return b if b[-1] in ".!?…" else b + "."


def foreign_voice(text: str, own: str, others: Iterable[str]) -> str | None:
    """Evidence that an NPC call wrote for somebody else: a `Name:` script line, or a beat that
    begins with another character's name (that person acts). Returns a short reason, or None."""
    others = [o for o in others if o and o != own]
    for o in others:
        if re.search(rf"^[ \t]*{re.escape(o)}[ \t]*:", text, re.IGNORECASE | re.MULTILINE):
            return f"script line for {o}"
    out = split_npc_output(text)
    for b in out.beats:
        head = b.strip(" ,;:\"«»").lower()
        for o in others:
            stem = o.lower()[: max(4, len(o) - 2)]
            if head.startswith(stem):
                return f"beat acts for {o}: {b[:40]}"
    return None


# ---------------------------------------------------------------------------------------------
# Assistant-isms
# ---------------------------------------------------------------------------------------------
ASSISTANT_PATTERNS = {
    "є справа": r"\bє\s+справа\b",
    "ми хочемо, щоб ти": r"\b(?:хочемо|хочу),?\s+щоб\s+(?:ти|ви)\b",
    "ціна питання": r"\bскільки\s+(?:коштує|варта)\s+(?:твоя|ваша)\s+(?:робота|послуга)",
    "за плату, звісно": r"\bза\s+плату,?\s+(?:звісно|звичайно|зрозуміло)",
    "filler звісно": r"\b(?:звісно|безумовно|неодмінно|звичайно)\b",
    "tidy offer": r"\b(?:чекаємо\s+твоєї\s+відповіді|дай\s+знати|я\s+готов\w+\s+обговорити)",
    "atmosphere cliche": r"(?:тиша\s+повисла|повітря\s+(?:стало|було)\s+(?:важк|густ)|холодок\s+(?:пробіг|пішов)|зловісн|тривожн\w+\s+тиш)",
    "announced feeling": r"\bя\s+(?:дуже\s+)?(?:боюся|хвилююся|переживаю|відчуваю\s+страх)\b",
}


def assistant_isms(text: str) -> list[str]:
    low = text.lower()
    return [k for k, p in ASSISTANT_PATTERNS.items() if re.search(p, low)]


# ---------------------------------------------------------------------------------------------
# Exemplars from the local book file
# ---------------------------------------------------------------------------------------------
_TOK = re.compile(r"[а-яіїєґ']{4,}", re.IGNORECASE)
# situation words (English record terms and Ukrainian) -> stems that match passages
TAGS: dict[str, tuple[tuple[str, ...], tuple[str, ...]]] = {
    "hire": (("witcher", "відьмак", "monster", "mill", "млин", "work", "job", "contract", "hire",
              "робот", "потвор"),
             ("відьма", "потвор", "робот", "староста", "замовл", "найм")),
    "haggle": (("orens", "oren", "pay", "price", "coin", "cost", "fee", "gold", "плат", "коштує",
                "орен", "гроші", "ціна", "money", "advance"),
               ("корон", "марок", "орен", "торг", "заплат", "плат", "грошв", "кошт", "дорог")),
    "tavern": (("inn", "tavern", "корчм", "ale", "beer", "innkeeper", "room", "supper", "stew"),
               ("корчм", "шинкв", "пива", "пиво", "кухл", "ночлі", "вечер")),
    "fear": (("fear", "afraid", "scared", "howl", "dead", "wolf", "monster", "виє", "мертв",
              "страх", "вовк"),
             ("боюс", "страх", "налякан", "жах", "лякат", "мор", "вовк", "вовкул")),
    "road": (("road", "forest", "camp", "дорог", "ліс", "табір", "traveller"),
             ("дорог", "лісу", "лісі", "табір", "багат", "стежк")),
    "court": (("lord", "mage", "queen", "king", "court", "палац", "чаклун", "королев"),
              ("королев", "чародій", "чародій", "князь", "король", "двір")),
}


def _stems(text: str) -> set[str]:
    return {w.lower()[:5] for w in _TOK.findall(text)}


@dataclass(frozen=True)
class Passage:
    text: str
    kind: str  # "dialogue" | "prose"
    stems: frozenset[str]


class ExemplarIndex:
    """Passages of the book file: dialogue runs (several lines with their business) and speechless
    prose paragraphs. Built once per process (about a second for the whole file)."""

    def __init__(self, text: str) -> None:
        self.dialogue: list[Passage] = []
        self.prose: list[Passage] = []
        df: dict[str, int] = {}
        paras = [p.strip() for p in text.split("\n")]
        run: list[str] = []

        def flush() -> None:
            nonlocal run
            if sum(1 for p in run if p[:1] in DASHES) >= 3:
                self._add_dialogue(run, df)
            run = []

        for p in paras:
            if not p:
                continue
            if "[" in p and re.search(r"\[\d+\]", p):  # footnote marker: translator's apparatus
                flush()
                continue
            if p[:1] in DASHES:
                run.append(p)
            elif run and len(p) < 320 and len(run) < 14:
                run.append(p)  # a narrative beat between the lines
            else:
                flush()
                if 220 <= len(p) <= 700 and not re.search(r"[—–«»\"“]", p):
                    self.prose.append(Passage(p, "prose", frozenset(_stems(p))))
        flush()
        for ps in (self.dialogue, self.prose):
            for q in ps:
                for s in q.stems:
                    df[s] = df.get(s, 0) + 1
        n = max(1, len(self.dialogue) + len(self.prose))
        self.idf = {s: math.log(n / (1 + c)) for s, c in df.items()}

    def _add_dialogue(self, run: list[str], df: dict[str, int]) -> None:
        # chop a long run into passages of at most ~850 characters, on paragraph borders
        cur: list[str] = []
        size = 0
        for p in run:
            if cur and size + len(p) > 850:
                self._keep(cur)
                cur, size = [], 0
            cur.append(p)
            size += len(p) + 1
        self._keep(cur)

    def _keep(self, cur: list[str]) -> None:
        text = "\n".join(cur)
        if (sum(1 for p in cur if p[:1] in DASHES) >= 3 and 260 <= len(text) <= 900
                and cur[0][:1] in DASHES):
            self.dialogue.append(Passage(text, "dialogue", frozenset(_stems(text))))

    def pick(self, situation: str, *, kind: str = "dialogue", k: int = 2, max_chars: int = 1500
             ) -> list[str]:
        """The best `k` passages for a situation text, within `max_chars` in all."""
        low = situation.lower()
        want = _stems(situation)
        boost: set[str] = set()
        for _, (cues, stems) in TAGS.items():
            if any(c in low for c in cues):
                boost.update(stems)
        pool = self.dialogue if kind == "dialogue" else self.prose
        scored: list[tuple[float, int, Passage]] = []
        for i, q in enumerate(pool):
            s = sum(self.idf.get(w, 0.0) for w in q.stems & want)
            s += 2.5 * sum(1 for w in boost if any(x.startswith(w[:5]) for x in q.stems))
            names = len(re.findall(r"(?<![.!?…—–\n])\s[А-ЯІЇЄҐ][а-яіїєґ']{2,}", q.text))
            s -= 2.0 * max(0, names - 1)  # canon people in the passage would leak into the scene
            if kind == "dialogue":
                s += 0.5 * min(8, q.text.count("\n"))
            scored.append((s, -i, q))
        scored.sort(key=lambda t: (t[0], t[1]), reverse=True)
        out: list[str] = []
        total = 0
        for _, _, q in scored:
            if len(out) >= k or total + len(q.text) > max_chars:
                continue
            out.append(q.text)
            total += len(q.text)
        return out


_index_lock = threading.Lock()
_index_cache: dict[str, ExemplarIndex | None] = {}


def books_path() -> Path | None:
    """The local book file: `HARNESS_BOOKS`, else `data/witcher_books.txt` in this checkout or in
    the main checkout of the repository (a worktree has no `data/`)."""
    env = os.environ.get("HARNESS_BOOKS")
    cands = [Path(env)] if env else []
    cands.append(REPO / "data" / "witcher_books.txt")
    try:  # a git worktree lives under <main>/.claude/worktrees/<name>
        cands.append(REPO.parents[2] / "data" / "witcher_books.txt")
    except IndexError:
        pass
    return next((c for c in cands if c.is_file()), None)


def exemplar_index(path: Path | None = None) -> ExemplarIndex | None:
    path = path or books_path()
    if path is None:
        return None
    key = str(path)
    with _index_lock:
        if key not in _index_cache:
            try:
                _index_cache[key] = ExemplarIndex(path.read_text(encoding="utf-8"))
            except OSError:
                _index_cache[key] = None
        return _index_cache[key]


# ---------------------------------------------------------------------------------------------
# The style
# ---------------------------------------------------------------------------------------------
def _sections(md: str) -> dict[str, str]:
    out: dict[str, list[str]] = {}
    cur = ""
    for line in md.splitlines():
        if line.startswith("## "):
            cur = line[3:].strip().lower()
            out[cur] = []
        elif cur:
            out[cur].append(line)
    return {k: "\n".join(v).strip() for k, v in out.items()}


NPC_CORE = (
    "You write a living person of this world, as the people talk in Sapkowski's Witcher books in "
    "Ukrainian: specific, a little ugly, never tidy. People here do not explain themselves. They "
    "haggle, hedge, dodge, answer a question with a question, break themselves off, repeat a "
    "word, say less than they know and the real thing last and sideways. They are afraid, "
    "greedy, proud or tired in ways they show by what they do and avoid, never by announcing "
    "it. A line is a move in a bargain or a quarrel, not information handed over. No summary of "
    "the situation, no neat closing offer, no polite filler, no stock phrases of fiction.")

NPC_FORM = (
    "Form, as the Ukrainian books write dialogue: a dash opens speech. Your own small physical "
    "business and manner go in between, in the third person, in the same paragraph "
    "(\"— ..., — озирнувся {name}. — ...\"), or in a short clause before the dash, but only "
    "when it earns its place: many lines have no gesture at all. When there is one, it is a "
    "thing anyone present could see or hear (a glance round, a lowered voice, a spit, a pause, "
    "a hand to the purse). Not thoughts, not explanations. Speech can be short, and "
    "sometimes it should be. Answer the last thing said, not the whole situation.")

GESTURE_FORM = (  # the gesture-only shape: the reply is the action itself, stored as an action
    "Form: one short sentence in the third person about {name}, something anyone present could "
    "see or hear. No dash, no speech, no thoughts.")

NPC_LIMITS = (
    "You write only {name}: your own words and your own actions. Never another character's "
    "words or actions, and never anything the player character says, does, thinks or feels. "
    "No quotation marks, no stage directions in brackets, no 'Name:' lines. Say nothing you "
    "have no way of knowing.")

EXEMPLAR_NOTE = (
    "Style examples from other stories. Take only the rhythm, the dryness and the manner. The "
    "people, places and events in them are not in your scene; use none of their names, facts or "
    "phrases.")

NARR_CORE = (
    "You write the narration of a role-playing game in the manner of Sapkowski's Witcher books "
    "in Ukrainian: an ironic, worldly narrator who knows a little more than the hero and says it "
    "flatly. Concrete, ugly, specific detail (smell, dirt, the weight of a coin, a dog "
    "scratching), earthy comparisons, short flat sentences for danger and longer ones for "
    "crowds. Show the hero's alertness by what he watches. No stock atmosphere (ominous, "
    "palpable silence, a chill down the spine, the air grew heavy), no summarising of feelings, "
    "no moralising. Scenes move: someone does something, someone reacts. The characters' own "
    "small gestures while they speak are written with their lines by their own calls: narrate "
    "the scene, what the hero perceives and what happens around, not how somebody delivers a line.")

MANNER_SYSTEM = ("You help write characters for a dark-fantasy role-playing game set in a "
                 "Sapkowski-like world.")

# a profile cue picks the kind of passage to show; used when the caller gives no situation
DEFAULT_SITUATION = "розмова"


class Style:
    """The wording of the creative calls. Construct with `Style.load("witcher")`.
    `exemplars`: add runtime book passages to the prompts (needs the local book file; silently
    off when it is absent)."""

    def __init__(self, sheet: dict[str, str] | None = None, *, exemplars: bool = False,
                 books: Path | None = None, npc_examples: int = 2, narrator_examples: int = 1
                 ) -> None:
        self.sheet = sheet or {}
        self.exemplars, self.books = exemplars, books
        self.npc_examples, self.narrator_examples = npc_examples, narrator_examples

    @classmethod
    def load(cls, world: str = "witcher", **kw: object) -> "Style":
        p = WORLDS / world / "style.md"
        sheet = _sections(p.read_text(encoding="utf-8")) if p.is_file() else {}
        return cls(sheet, **kw)  # type: ignore[arg-type]

    def _sec(self, *names: str) -> str:
        return "\n\n".join(f"{n.capitalize()}:\n{self.sheet[n]}" for n in names if self.sheet.get(n))

    # -- NPC ---------------------------------------------------------------------------------
    def npc_system(self, prof: CharacterProfile) -> str:
        parts = [f"You are {prof.name}. {prof.description}".strip()]
        if prof.manner and prof.manner != "-":
            parts.append(f"How {prof.name} talks: {prof.manner}")
        parts.append(NPC_CORE)
        parts.append(self._sec("dialogue", "voices by class", "irony and subtext", "what it avoids"))
        return "\n\n".join(p for p in parts if p)

    def npc_instruction(self, prof: CharacterProfile, language: str | None,
                        shape: "Shape | None" = None,
                        bounds: tuple[int, int] | None = None) -> str:
        """`bounds`: the words the shape allows (`shape.word_bounds`); the caller fits the reply
        to the same bounds. The language line appears once, at the end."""
        from .shape import Shape, shape_instruction  # shape imports this module
        form = (GESTURE_FORM if shape is Shape.GESTURE else NPC_FORM).format(name=prof.name)
        return (f"Write {prof.name}'s next turn: what {prof.name} says and does in this moment.\n"
                + (shape_instruction(shape, None, bounds=bounds, name=prof.name) + "\n"
                   if shape is not None else "")
                + form + "\n" + NPC_LIMITS.format(name=prof.name)
                + (f"\nWrite in {language}." if language else ""))

    def npc_examples_section(self, situation: str) -> str:
        if not self.exemplars or self.npc_examples <= 0:
            return ""
        idx = exemplar_index(self.books)
        if idx is None:
            return ""
        got = idx.pick(situation, kind="dialogue", k=self.npc_examples)
        if not got:
            return ""
        return EXEMPLAR_NOTE + "\n\n" + "\n\n---\n\n".join(got)

    # -- narrator ----------------------------------------------------------------------------
    def narrator_system(self) -> str:
        return "You are the narrator of a role-playing game.\n\n" + NARR_CORE + "\n\n" + self._sec(
            "narration", "what it avoids")

    def narrator_examples_section(self, situation: str) -> str:
        if not self.exemplars or self.narrator_examples <= 0:
            return ""
        idx = exemplar_index(self.books)
        if idx is None:
            return ""
        got = idx.pick(situation, kind="prose", k=self.narrator_examples, max_chars=900)
        return (EXEMPLAR_NOTE + "\n\n" + "\n\n---\n\n".join(got)) if got else ""


# ---------------------------------------------------------------------------------------------
# Manner notes, generated once per NPC
# ---------------------------------------------------------------------------------------------
def manner_messages(prof: CharacterProfile, style: Style | None = None, language: str = "English"
                    ) -> Messages:
    sheet = style._sec("voices by class") if style else ""
    body = (
        f"Character: {prof.name}. {prof.description}\n\n"
        "Write 4 to 6 short manner notes (each under 20 words) on how this person talks and behaves while talking: "
        "register and vocabulary, pace, verbal habits (what they repeat, how they stall), what "
        "they do with their hands or eyes, what they dodge, what they do when afraid or when "
        "bargaining. Concrete and specific to this person, not generic. Describe habits; never "
        "quote a catchphrase or an example sentence (a quoted phrase gets repeated in every line). "
        f"Notes only, one per line, no numbering, no names of other characters. Write in {language}."
        + (f"\n\nHow people of this world talk, by class (for orientation):\n{sheet}" if sheet else ""))
    return [{"role": "system", "content": MANNER_SYSTEM}, {"role": "user", "content": body}]


def parse_manner(raw: str, limit: int = 6) -> str:
    lines = []
    for line in raw.splitlines():
        line = re.sub(r"^\s*(?:[-*•]|\d+[.)])\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines[:limit])
