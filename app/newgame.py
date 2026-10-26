"""New game from a file (book UI task 5): the game package a player brings from any AI chat.

The package is YAML (UTF-8, Ukrainian values). Only `version: 1`, `world: witcher` and
`player.description` are required; a missing field means the world decides. `parse` validates it
with Ukrainian errors (field, problem, how to fix) and never fails on unknown fields: they are kept
in `notes` with a warning. `summary` is the card the player sees before starting: what is set and
what the world will decide. `open_package` builds the campaign through the existing builders:

- a canon start (`start.canon`, an id of `worlds/witcher/start_points.yaml`) is situation A of
  `app/vizima.py` with the package's player character (the canon store when present);
- a free start (`start.place/day/time/situation`) is a scene on the world map with people from
  `who_is_here`, made whole by `harness/npcgen.py` (or two passers-by when nobody is given).

The player sheet is used like the local character file of the inn campaign: `derive_traits` reads
it once (the one cheap call of the start, recorded) and gives the looks and the hidden traits.
Tone, pace, content limits, the canon setting and the notes go to the narrator as campaign intent
(`ContextBuilder.intent`); they never override `docs/decisions.md`. The full content-limit feature
(pause, veil and skip buttons) is not built here.

The format is documented for external AIs in `docs/new_game_instruction.md`.
"""
from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Callable

import yaml

from harness.glossary import Glossary
from harness.state import StateChange
from harness.models import EQUIPMENT, INTERNAL, INVENTORY, PLAYER, CharacterProfile, Scene
from harness.npcgen import NORTHERN, infer_sex, pick_name
from harness.pipeline import Engine
from harness.world import pilot
from harness.world.places import VIZIMA_EXTRA, Place, WorldMap, vizima
from harness.world.world import World

from . import vizima as viz
from .campaigns import (
    CAMPAIGNS, Campaign, Recorder, Stack, Translator, _pointer, seed_player_inventory,
    seed_player_state,
)
from .character import MAX_FILE, derive_traits
from .inks import INK_RE

ROOT = Path(__file__).resolve().parent.parent
START_POINTS = ROOT / "worlds" / "witcher" / "start_points.yaml"
KIND = "package"
WORLDS = ("witcher",)
MAX_PEOPLE = 6
MAX_TEXT = 200_000   # characters of a package, checked before the YAML parser runs
MAX_PORTRAIT_TEXT = 1_500   # characters of one person's free-text portrait
MAX_TONE = 1_000     # characters of `tone`; it reaches every narrator prompt
MAX_NOTES = 4_000    # characters of `notes` (with the unknown fields) that reach the narrator
MAX_SHOW = 300       # characters of one unknown field's value kept in the notes
LONG_LOOK = 8  # words: a longer appearance makes a clumsy label

# parts of the day a package may name instead of a clock time (minutes after midnight)
DAY_PARTS = {"світанок": 5 * 60, "ранок": 8 * 60, "полудень": 12 * 60, "день": 14 * 60,
             "вечір": 19 * 60, "ніч": 23 * 60, "північ": 0}
PART_OF = ((5 * 60, "Ніч"), (11 * 60, "Ранок"), (17 * 60, "День"), (22 * 60, "Вечір"),
           (24 * 60, "Ніч"))
ORDINAL_GEN = ("першого", "другого", "третього", "четвертого", "п'ятого", "шостого", "сьомого",
               "восьмого", "дев'ятого", "десятого")
CHOICES = {
    "canon": ("follow", "loose"), "pace": ("slow", "normal", "fast"),
    "outcomes": ("real", "unbounded"), "dialogue": ("living", "classic"),
    "assistant": ("on", "off"),
}
CHOICE_UK = {
    "follow": "книги як тяжіння", "loose": "канон лише як тло", "slow": "повільний",
    "normal": "звичайний", "fast": "швидкий", "real": "справжні (невдачі й смерть можливі)",
    "unbounded": "без меж (дії персонажа завжди вдаються)", "living": "живий",
    "classic": "класичний", "on": "увімкнено", "off": "вимкнено",
}
TOP = ("version", "world", "player", "start", "canon", "tone", "pace", "limits", "outcomes",
       "dialogue", "assistant", "inks", "notes", "title", "pitch")
PLAYER_KEYS = ("name", "description", "appearance", "traits", "knows", "unbounded", "hidden",
               "inventory", "latent")
ITEM_KEYS = ("name", "where", "condition", "notes", "container", "open", "hidden", "content",
             "power", "grants_sense")
SENSES = ("magic",)  # what an item may grant, and a person may have besides sight
MAX_ITEMS, MAX_ITEM_NAME, MAX_ITEM_NOTES, MAX_ITEM_CONTENT = 80, 80, 400, 4_000
START_KEYS = ("canon", "place", "day", "time", "situation", "who_is_here")
PERSON_KEYS = ("name", "role", "appearance", "attitude", "goal", "knows_player", "portrait",
               "portrait_text", "senses")
PACKAGES = ROOT / "worlds" / "witcher" / "packages"  # bundled game packages (the new-game list)
# an `attitude` that reads as friendly: a person who knows the player starts as an ally
# whole words only, so «другий», «подруга», «порада», «недружня», «невірна» do not count
FRIENDLY = re.compile(r"(?:друг|друга|другом|друзі|друзів|дружн\w*|дружб\w*|дружелюбн\w*|"
                      r"приязн\w*|прихильн\w*|тепл\w*|довір\w*|симпат\w*|радий|рада|раді|"
                      r"радіє|люб\w*|вірн\w*)", re.IGNORECASE)
# a word before it that turns it around («не довіряє», «без симпатії», «ніякої приязні»)
NEGATION = {"не", "ні", "без", "ніякої", "ніякого", "жодної", "жодного", "аніскільки", "анітрохи",
            "зовсім"}
_UK_WORD = re.compile(r"[\w'’-]+")
PACE_EN = {"slow": "slow: unhurried, detailed narration; let moments breathe",
           "fast": "fast: short narration that moves straight to what matters"}


@dataclass
class Issue:
    """One problem (or warning) in a package, for the player: Ukrainian text."""
    field: str
    problem: str
    fix: str

    def to_json(self) -> dict[str, str]:
        return {"field": self.field, "problem": self.problem, "fix": self.fix}


class PackageError(ValueError):
    def __init__(self, issues: list[Issue]) -> None:
        super().__init__("; ".join(f"{i.field}: {i.problem}" for i in issues))
        self.issues = issues


@dataclass
class Package:
    data: dict[str, Any]                       # normalised values (see `parse`)
    warnings: list[Issue] = field(default_factory=list)

    def to_json(self) -> dict[str, Any]:
        return self.data


def world_portraits() -> tuple[dict[str, Any], str]:
    """The portraits of the Witcher world by id, and "" or what is wrong (Ukrainian) when a
    portrait file cannot be read (then no portraits)."""
    from harness import portrait as hp
    try:
        return hp.load_world_portraits("witcher"), ""
    except hp.PortraitError as e:
        return {}, (f"файл портрета «{Path(e.path).name}» зіпсований (поле {e.field}: "
                    f"{e.problem})")
    except OSError as e:
        return {}, f"портрети світу не читаються ({e.strerror or e})"


def bundled_packages() -> list[dict[str, str]]:
    """The game packages that come with the app (`worlds/witcher/packages/*.yaml`) for the
    new-game list: id, Ukrainian title and pitch, and the text that fills the box."""
    out = []
    for f in sorted(PACKAGES.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        try:
            raw = yaml.safe_load(text) or {}
        except yaml.YAMLError:
            continue
        if isinstance(raw, dict):
            out.append({"id": f.stem, "title": str(raw.get("title") or f.stem),
                        "pitch": str(raw.get("pitch") or ""), "text": text})
    return out


def start_points() -> dict[str, dict[str, Any]]:
    try:
        got = yaml.safe_load(START_POINTS.read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        return {}
    return {str(k): v for k, v in got.items() if isinstance(v, dict)}


def canon_start(cid: str) -> pilot.CanonStart:
    """The engine-side start of a canon moment (`start_points.yaml` entry `cid`); the intro is
    the entry's `situation`, or the built-in text of situation A."""
    st = pilot.CanonStart.from_dict(cid, start_points()[cid])
    return replace(st, intro=st.intro or viz.INTRO)


# -- parsing ----------------------------------------------------------------------------------

_FENCE = re.compile(r"```[ \t]*(?:ya?ml)?[ \t]*\n(.*?)```", re.DOTALL | re.IGNORECASE)


def _strip_chat(text: str) -> str:
    """The YAML of a package pasted together with the chat around it: the fenced block that
    holds `version:`, else the text as is."""
    blocks = _FENCE.findall(text)
    for b in blocks:
        if re.search(r"^\s*version\s*:", b, re.MULTILINE):
            return b
    return blocks[0] if blocks else text


class _NoAliases(yaml.SafeLoader):
    """SafeLoader that refuses aliases (`*name`): a package never needs them, and they allow
    self-referencing values and exponential expansion ("billion laughs")."""

    def compose_node(self, parent: Any, index: Any) -> Any:  # type: ignore[override]
        if self.check_event(yaml.events.AliasEvent):
            ev = self.peek_event()
            raise _AliasError(ev.start_mark)
        return super().compose_node(parent, index)


class _AliasError(Exception):
    def __init__(self, mark: Any) -> None:
        super().__init__("alias")
        self.mark = mark


def _show(v: Any) -> str:
    try:
        out = json.dumps(v, ensure_ascii=False) if isinstance(v, (dict, list)) else str(v)
    except (ValueError, TypeError, RecursionError):
        out = "…"
    return out if len(out) <= MAX_SHOW else out[:MAX_SHOW] + "…"


def _joined(v: Any) -> Any:
    """A free-text field given as a list of items: one text."""
    if isinstance(v, list) and all(isinstance(x, (str, int, float)) for x in v):
        return "; ".join(str(x).strip() for x in v if str(x).strip())
    return v


class _Checker:
    def __init__(self) -> None:
        self.errors: list[Issue] = []
        self.warnings: list[Issue] = []
        self.extra: list[str] = []  # unknown fields, kept in notes

    def err(self, f: str, problem: str, fix: str) -> None:
        self.errors.append(Issue(f, problem, fix))

    def unknown(self, where: str, d: dict[str, Any], known: tuple[str, ...]) -> None:
        for k, v in d.items():
            if k in known:
                continue
            f = f"{where}.{k}" if where else str(k)
            self.warnings.append(Issue(
                f, "Невідоме поле: застосунок його не розуміє.",
                "Нічого робити не треба: значення збережено в нотатках (notes) і оповідач його "
                "побачить. Якщо це одне з відомих полів, виправте назву."))
            self.extra.append(f"{f}: {_show(v)}")

    def text(self, f: str, v: Any, *, required: bool = False) -> str | None:
        if v is None or (isinstance(v, str) and not v.strip()):
            if required:
                self.err(f, "Поле обов'язкове, а його немає або воно порожнє.",
                         f"Додайте {f} з текстом українською.")
            return None
        if isinstance(v, bool) or isinstance(v, (dict, list)):
            self.err(f, "Тут має бути текст.", f"Запишіть {f} як звичайний рядок тексту.")
            return None
        return str(v).strip()

    def texts(self, f: str, v: Any) -> list[str] | None:
        """A text or a list of texts, as a list."""
        if v is None:
            return None
        items = v if isinstance(v, list) else [v]
        out: list[str] = []
        for i, it in enumerate(items):
            if isinstance(it, (dict, list, bool)) or it is None:
                self.err(f"{f}[{i + 1}]" if isinstance(v, list) else f,
                         "Тут має бути текст або список текстових пунктів.",
                         f"Запишіть кожен пункт {f} окремим рядком, що починається з «- ».")
                return None
            s = str(it).strip()
            if s:
                out.append(s)
        return out or None

    def flag(self, f: str, v: Any) -> bool | None:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        s = str(v).strip().lower()
        if s in ("true", "yes", "так", "on"):
            return True
        if s in ("false", "no", "ні", "off"):
            return False
        self.err(f, f"Незрозуміле значення «{_show(v)}»: потрібно так або ні.",
                 f"Напишіть {f}: true або {f}: false.")
        return None

    def choice(self, f: str, v: Any) -> str | None:
        if v is None:
            return None
        allowed = CHOICES[f]
        if isinstance(v, bool) and allowed == ("on", "off"):
            return "on" if v else "off"  # YAML 1.1 reads on/off as booleans
        s = str(v).strip().lower()
        if s in allowed:
            return s
        self.err(f, f"Незрозуміле значення «{_show(v)}».",
                 f"Оберіть одне з: {', '.join(allowed)} (або приберіть поле, тоді вирішить "
                 "світ).")
        return None


def _time_of_day(c: _Checker, f: str, v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        c.err(f, "Тут має бути час.", "Напишіть, наприклад, time: \"20:00\" або time: вечір.")
        return None
    if isinstance(v, int):  # YAML 1.1 reads 20:00 as 1200 (base 60): minutes after midnight
        if 0 <= v < 24 * 60:
            return v
    else:
        s = str(v).strip().lower()
        m = re.fullmatch(r"(\d{1,2})[:.](\d{2})", s)
        if m and int(m.group(1)) < 24 and int(m.group(2)) < 60:
            return int(m.group(1)) * 60 + int(m.group(2))
        if s in DAY_PARTS:
            return DAY_PARTS[s]
    c.err(f, f"Незрозумілий час «{_show(v)}».",
          "Напишіть годину в лапках, як \"20:00\", або одне слово: "
          + ", ".join(DAY_PARTS) + ".")
    return None


def _people(c: _Checker, v: Any) -> list[dict[str, Any]] | None:
    f = "start.who_is_here"
    if v is None:
        return None
    if not isinstance(v, list):
        c.err(f, "Тут має бути список людей.",
              "Запишіть кожну людину окремим пунктом «- role: ...» (див. приклад).")
        return None
    if len(v) > MAX_PEOPLE:
        c.err(f, f"Забагато людей у першій сцені ({len(v)}).",
              f"Залиште до {MAX_PEOPLE} найважливіших; решту світ додасть сам, коли треба.")
        return None
    out = []
    for i, p in enumerate(v):
        pf = f"{f}[{i + 1}]"
        if isinstance(p, str):
            p = {"role": p}
        if not isinstance(p, dict):
            c.err(pf, "Людину треба описати полями (role, attitude...).",
                  "Запишіть, наприклад: - role: корчмар")
            continue
        c.unknown(pf, p, PERSON_KEYS)
        person = {k: c.text(f"{pf}.{k}", p.get(k))
                  for k in ("name", "role", "appearance", "attitude", "goal")}
        person = {k: x for k, x in person.items() if x}
        look = person.get("appearance", "")
        if len(look.split()) > LONG_LOOK:
            c.warnings.append(Issue(
                f"{pf}.appearance", "Опис зовнішності задовгий: саме так персонаж називатиме "
                "цю людину, доки не дізнається ім'я.",
                "Скоротіть до 3–7 слів (наприклад, «жінка в червоній хустці»); решту можна "
                "перенести в attitude або notes."))
        got = c.texts(f"{pf}.senses", p.get("senses")) or []
        senses = [s.casefold() for s in got]
        for s in senses:
            if s not in SENSES:
                c.err(f"{pf}.senses", f"Невідоме чуття «{_show(s)}».",
                      "Можна лише senses: [magic] (зір є в усіх).")
        if senses and all(s in SENSES for s in senses):
            person["senses"] = list(dict.fromkeys(senses))
        kp = c.flag(f"{pf}.knows_player", p.get("knows_player"))
        person["knows_player"] = bool(kp)
        pid = c.text(f"{pf}.portrait", p.get("portrait"))
        if pid:
            known, broken = world_portraits()
            if pid in known:
                person["portrait"] = pid
            elif broken:
                c.err(f"{pf}.portrait", f"Портрет «{_show(pid)}» зараз недоступний.",
                      f"У застосунку {broken}; приберіть поле portrait або виправте файл.")
            else:
                c.err(f"{pf}.portrait", f"Невідомий портрет «{_show(pid)}».",
                      "Оберіть один із готових портретів світу: " + (", ".join(sorted(known))
                      or "(поки жодного)") + "; або приберіть поле portrait.")
        text = c.text(f"{pf}.portrait_text", p.get("portrait_text"))
        if text and person.get("portrait"):
            c.warnings.append(Issue(
                f"{pf}.portrait_text", "У людини є і portrait, і portrait_text: потрібен лише один.",
                "Використано готовий портрет portrait, а portrait_text проігноровано."))
        elif text:
            if len(text) > MAX_PORTRAIT_TEXT:
                c.warnings.append(Issue(
                    f"{pf}.portrait_text", f"Опис задовгий ({len(text)} знаків): беруться перші "
                    f"{MAX_PORTRAIT_TEXT}.", "Скоротіть до головного: ядро, чужі й близькі, "
                    "що гріє й злить, що приховує, як говорить."))
            person["portrait_text"] = text[:MAX_PORTRAIT_TEXT]
        if not (person.get("role") or person.get("name") or person.get("appearance")):
            c.err(pf, "Невідомо, хто це: немає ні ролі, ні імені, ні зовнішності.",
                  "Додайте хоча б role (наприклад, «корчмар»).")
            continue
        out.append(person)
    return out


def _inventory(c: "_Checker", v: Any) -> list[dict[str, Any]] | None:
    """The explicit starting inventory: a list of entries, validated (Ukrainian issues)."""
    if v is None:
        return None
    if not isinstance(v, list):
        c.err("player.inventory", "inventory має бути списком речей.",
              "Запишіть кожну річ окремим пунктом «- name: ...» (див. інструкцію).")
        return None
    if len(v) > MAX_ITEMS:
        c.err("player.inventory", f"Забагато речей ({len(v)}): можна до {MAX_ITEMS}.",
              "Залиште найважливіше; дрібниці об'єднайте («набір інструментів»).")
        return None
    from .campaigns import _find_container, classify_where
    out: list[dict[str, Any]] = []
    for n, raw in enumerate(v, 1):
        f = f"player.inventory[{n}]"
        if not isinstance(raw, dict):
            c.err(f, "Річ має бути набором полів (name, where...).",
                  "Запишіть: - name: ліхтарик")
            continue
        raw = {str(k): x for k, x in raw.items()}
        c.unknown(f, raw, ITEM_KEYS)
        e: dict[str, Any] = {}
        e["name"] = c.text(f"{f}.name", raw.get("name"), required=True)
        if e["name"] and len(e["name"]) > MAX_ITEM_NAME:
            c.err(f"{f}.name", f"Назва задовга ({len(e['name'])} знаків; можна до "
                  f"{MAX_ITEM_NAME}).", "Залиште коротку назву, подробиці — в notes.")
        e["where"] = c.text(f"{f}.where", raw.get("where")) or "worn"
        e["condition"] = c.text(f"{f}.condition", raw.get("condition"))
        e["notes"] = c.text(f"{f}.notes", raw.get("notes"))
        if e["notes"] and len(e["notes"]) > MAX_ITEM_NOTES:
            c.err(f"{f}.notes", f"Нотатки задовгі ({len(e['notes'])} знаків; можна до "
                  f"{MAX_ITEM_NOTES}).", "Скоротіть; великий текст винесіть у content.")
        e["power"] = c.text(f"{f}.power", raw.get("power"))
        gs = c.text(f"{f}.grants_sense", raw.get("grants_sense"))
        if gs and gs.casefold() not in SENSES:
            c.err(f"{f}.grants_sense", f"Невідоме чуття «{_show(gs)}».",
                  "Річ може дати лише чуття magic (grants_sense: magic) тому, хто її носить.")
            gs = None
        e["grants_sense"] = gs.casefold() if gs else None
        for k in ("container", "open", "hidden"):
            e[k] = c.flag(f"{f}.{k}", raw.get(k))
        e["container"], e["open"] = bool(e["container"]), bool(e["open"])
        if e["open"] and not e["container"]:
            c.warnings.append(Issue(f"{f}.open", "open має сенс лише для контейнера.",
                                    "Додайте container: true або приберіть open."))
        content = raw.get("content")
        if isinstance(content, dict):
            content = {str(k): x for k, x in content.items()}
            path = c.text(f"{f}.content.file", content.get("file"), required=True)
            if path and (path.startswith(("/", "~")) or ".." in path.replace("\\", "/").split("/")):
                c.err(f"{f}.content.file", "Шлях до файлу має бути відносним, без «..».",
                      "Запишіть, наприклад: content: {file: notes/diary.txt}")
                path = None
            e["content"] = {"file": path} if path else None
        else:
            e["content"] = c.text(f"{f}.content", content)
            if e["content"] and len(e["content"]) > MAX_ITEM_CONTENT:
                c.err(f"{f}.content", f"Вміст задовгий ({len(e['content'])} знаків; можна до "
                      f"{MAX_ITEM_CONTENT}).", "Скоротіть або винесіть у файл: content: {file: ...}")
        out.append({k: x for k, x in e.items() if x is not None and x != ""})
    names: dict[str, int] = {}
    for n, e in enumerate(out, 1):
        key = " ".join(str(e.get("name", "")).casefold().split())
        if key in names:
            c.err(f"player.inventory[{n}].name", f"Назва «{e['name']}» повторюється.",
                  "Дайте речам різні назви (наприклад, «кабель USB-C» і «кабель живлення»): "
                  "на назву посилається where.")
        names[key] = n
    boxes = [e for e in out if e.get("container") and e.get("name")]
    parent: dict[int, int | None] = {}
    for i, e in enumerate(out):
        if not e.get("name"):
            continue
        where = e.get("where", "worn")
        if classify_where(where):
            parent[i] = None
            continue
        j = _find_container(where, out)
        if j is None:
            hint = ("; контейнери: " + ", ".join(b["name"] for b in boxes)) if boxes else ""
            c.err(f"player.inventory[{i + 1}].where",
                  f"Невідоме місце «{where}»: це не «worn», «in hand», «pocket» і не назва "
                  "контейнера з цього списку.",
                  "Напишіть worn (на тілі), in hand (в руці), pocket (кишеня) або точну назву "
                  "речі з container: true" + hint + ".")
        elif j == i:
            c.err(f"player.inventory[{i + 1}].where", "Річ не може лежати сама в собі.",
                  "Вкажіть інше місце.")
        else:
            parent[i] = j
    for i in parent:
        seen, cur = set(), i
        while parent.get(cur) is not None:
            if cur in seen:
                c.err(f"player.inventory[{i + 1}].where",
                      "Контейнери лежать один в одному по колу.", "Розірвіть коло: "
                      "один із них має бути worn або in hand.")
                break
            seen.add(cur)
            cur = parent[cur]
    return out


def parse(text: str) -> Package:
    """Validate a package. Raises PackageError with every problem found (Ukrainian)."""
    c = _Checker()
    text = text or ""
    if len(text) > MAX_TEXT:
        raise PackageError([Issue(
            "файл", f"Файл завеликий ({len(text) // 1000} тис. знаків; можна до "
            f"{MAX_TEXT // 1000} тис.).",
            "Скоротіть опис персонажа або нотатки: світові досить головного.")])
    try:
        raw = yaml.load(_strip_chat(text), Loader=_NoAliases)  # noqa: S506 - a safe loader
    except _AliasError as e:
        raise PackageError([Issue(
            "файл", f"Посилання &/* у файлі не підтримуються (рядок {e.mark.line + 1}).",
            "Запишіть значення повністю там, де воно потрібне, без &назва і *назва.")]) from None
    except RecursionError:
        raise PackageError([Issue("файл", "Файл занадто глибоко вкладений.",
                                  "Спростіть структуру за прикладом з інструкції.")]) from None
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None)
        where = f" (рядок {mark.line + 1}, позиція {mark.column + 1})" if mark else ""
        raise PackageError([Issue(
            "файл", f"Це не читається як YAML{where}: {getattr(e, 'problem', '') or e}.",
            "Перевірте відступи (лише пробіли, однакові для одного рівня), двокрапки після "
            "назв полів і лапки навколо тексту, що містить двокрапку або #.")]) from None
    if not isinstance(raw, dict):
        raise PackageError([Issue(
            "файл", "Файл порожній або це не набір полів «назва: значення».",
            "Вставте весь YAML-блок, що починається з «version: 1».")])
    raw = {str(k): v for k, v in raw.items()}
    c.unknown("", raw, TOP)
    d: dict[str, Any] = {}

    v = raw.get("version")
    if v is None:
        c.err("version", "Немає версії формату.", "Додайте першим рядком: version: 1")
    elif v != 1 and str(v).strip() != "1":
        c.err("version", f"Невідома версія «{_show(v)}»: застосунок знає лише версію 1.",
              "Напишіть version: 1 і перевірте поля за інструкцією.")
    d["version"] = 1
    w = raw.get("world")
    if w is None:
        c.err("world", "Не вказано світ.", "Додайте: world: witcher")
    elif str(w).strip().lower() not in WORLDS:
        c.err("world", f"Світ «{_show(w)}» поки недоступний.",
              "Зараз є лише світ Відьмака: world: witcher")
    d["world"] = "witcher"

    pl = raw.get("player")
    player: dict[str, Any] = {}
    if not isinstance(pl, dict):
        c.err("player", "Немає опису персонажа гравця." if pl is None else
              "player має бути набором полів (name, description...).",
              "Додайте розділ player: з полем description: — хто ваш персонаж, вільним текстом.")
    else:
        c.unknown("player", {str(k): x for k, x in pl.items()}, PLAYER_KEYS)
        player["description"] = c.text("player.description", pl.get("description"),
                                        required=True)
        if player["description"] and len(player["description"]) > MAX_FILE:
            c.warnings.append(Issue("player.description",
                                    f"Опис дуже довгий; прочитано перші {MAX_FILE} знаків.",
                                    "Скоротіть опис або винесіть найважливіше на початок."))
        for k in ("name", "appearance"):
            player[k] = c.text(f"player.{k}", pl.get(k))
        for k in ("traits", "knows", "hidden", "latent"):
            player[k] = c.texts(f"player.{k}", pl.get(k))
        player["unbounded"] = c.flag("player.unbounded", pl.get("unbounded"))
        inv = _inventory(c, pl.get("inventory"))
        if inv:
            player["inventory"] = inv
    d["player"] = {k: x for k, x in player.items() if x is not None}

    st = raw.get("start")
    start: dict[str, Any] = {}
    if st is not None and not isinstance(st, dict):
        c.err("start", "start має бути набором полів.",
              "Або start: {canon: <id>}, або поля place, day, time, situation (див. інструкцію).")
    elif isinstance(st, dict):
        st = {str(k): x for k, x in st.items()}
        c.unknown("start", st, START_KEYS)
        free = [k for k in ("place", "day", "time", "situation") if st.get(k) is not None]
        if st.get("canon") is not None:
            cid = str(st["canon"]).strip()
            points = start_points()
            if cid not in points:
                c.err("start.canon", f"Невідомий канонічний момент «{cid}».",
                      "Оберіть один із: " + ", ".join(points) + "; або опишіть старт вільно "
                      "(place, day, time, situation).")
            else:
                start["canon"] = cid
            if free:
                c.err("start", "Вказано і канонічний момент, і вільний старт ("
                      + ", ".join(free) + ").",
                      "Залиште щось одне: або canon, або place/day/time/situation.")
        start["place"] = c.text("start.place", st.get("place"))
        start["situation"] = c.text("start.situation", st.get("situation"))
        day = st.get("day")
        if day is not None:
            try:
                if isinstance(day, bool):
                    raise ValueError
                start["day"] = int(str(day).strip())
                if start["day"] < 1:
                    raise ValueError
            except ValueError:
                start.pop("day", None)
                c.err("start.day", f"Незрозумілий день «{_show(day)}».",
                      "Напишіть номер дня гри цифрою, від 1 (наприклад, day: 3).")
        start["time"] = _time_of_day(c, "start.time", st.get("time"))
        start["who_is_here"] = _people(c, st.get("who_is_here"))
    d["start"] = {k: x for k, x in start.items() if x is not None}

    for k in ("canon", "pace", "outcomes", "dialogue", "assistant"):
        got = c.choice(k, raw.get(k))
        if got is not None:
            d[k] = got
    tone = c.text("tone", _joined(raw.get("tone")))
    if tone and len(tone) > MAX_TONE:
        tone = tone[:MAX_TONE].rsplit(" ", 1)[0] + "…"
        c.warnings.append(Issue("tone", f"Опис тону задовгий; оповідач побачить перші {MAX_TONE} знаків.",
                                "Опишіть тон кількома реченнями."))
    if tone:
        d["tone"] = tone

    lim = raw.get("limits")
    if lim is not None:
        if not isinstance(lim, dict):
            c.err("limits", "limits має містити два списки: avoid і veil.",
                  "Запишіть: limits: {avoid: [чого не має бути], veil: [що лише за кадром]}")
        else:
            lim = {str(k): x for k, x in lim.items()}
            c.unknown("limits", lim, ("avoid", "veil"))
            got = {k: c.texts(f"limits.{k}", lim.get(k)) for k in ("avoid", "veil")}
            got = {k: x for k, x in got.items() if x}
            if got:
                d["limits"] = got

    inks = raw.get("inks")
    if inks is not None:
        if not isinstance(inks, dict):
            c.err("inks", "inks має бути набором «хто: колір».",
                  "Запишіть, наприклад: inks: {корчмар: \"#e8a87c\"}")
        else:
            ok: dict[str, str] = {}
            for who, col in inks.items():
                if not isinstance(col, str) or not INK_RE.match(col.strip()):
                    c.err(f"inks.{who}", f"Колір «{_show(col)}» не у форматі #rrggbb.",
                          "Запишіть колір шістьма шістнадцятковими цифрами в лапках, "
                          "наприклад \"#8fb8e8\".")
                    continue
                ok[str(who).strip()] = col.strip().lower()
            if ok:
                d["inks"] = ok

    for k, cap in (("title", 80), ("pitch", 400)):  # the bundled list's name and blurb
        v = c.text(k, raw.get(k))
        if v:
            d[k] = v[:cap]

    notes = c.text("notes", _joined(raw.get("notes")))
    if c.extra:
        notes = "\n".join(([notes] if notes else []) + ["Інші побажання з файлу:"] + c.extra)
    if notes and len(notes) > MAX_NOTES:
        notes = notes[:MAX_NOTES].rsplit(" ", 1)[0] + "…"
        c.warnings.append(Issue("notes", f"Нотатки задовгі; оповідач побачить перші {MAX_NOTES} "
                                "знаків.", "Залиште в notes лише найважливіше."))
    if notes:
        d["notes"] = notes

    if d.get("outcomes") == "real" and d["player"].get("unbounded"):
        c.warnings.append(Issue(
            "player.unbounded", "outcomes: real скасовує player.unbounded: true.",
            "Якщо персонаж має бути без меж, напишіть outcomes: unbounded."))
    if c.errors:
        raise PackageError(c.errors)
    return Package(d, c.warnings)


def unbounded(pkg: Package) -> bool:
    """`outcomes` overrides `player.unbounded`; the default is real outcomes."""
    o = pkg.data.get("outcomes")
    if o is not None:
        return o == "unbounded"
    return bool(pkg.data["player"].get("unbounded"))


# -- the summary card -------------------------------------------------------------------------

def _short(s: str, n: int = 180) -> str:
    s = " ".join(s.split())
    return s if len(s) <= n else s[:n].rsplit(" ", 1)[0] + "…"


def day_phrase(day: int, minute: int) -> str:
    """«Вечір третього дня»."""
    part = next(p for limit, p in PART_OF if minute < limit)
    nth = ORDINAL_GEN[day - 1] if 1 <= day <= len(ORDINAL_GEN) else f"{day}-го"
    return f"{part} {nth} дня"


def _clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def title(pkg: Package, place: str | None = None) -> str:
    """The line above the page: the canon moment's title, or the start place."""
    st = pkg.data["start"]
    if pkg.data.get("title"):
        return str(pkg.data["title"])
    if "canon" in st:
        return str(start_points()[st["canon"]].get("title", st["canon"]))
    place = place or st.get("place")
    if place and vizima(*VIZIMA_EXTRA).resolve(place):
        return f"Визім · {place}"
    name = pkg.data["player"].get("name")
    return " · ".join(x for x in (place, name) if x) or "Нова гра"


def summary(pkg: Package) -> dict[str, Any]:
    """What is set and what the world decides, for the card before the start (Ukrainian)."""
    d, p, st = pkg.data, pkg.data["player"], pkg.data["start"]
    out: list[dict[str, str]] = []
    world: list[str] = []

    def put(label: str, value: Any, missing: str | None = None) -> None:
        if value:
            out.append({"label": label, "value": value if isinstance(value, str) else
                        "; ".join(value)})
        elif missing:
            world.append(missing)

    put("Персонаж", _short(p.get("description", "")))
    put("Ім'я", p.get("name"), "Ім'я персонажа")
    put("Зовнішність", p.get("appearance") and _short(p["appearance"], 140),
        "Зовнішність (з опису персонажа)")
    put("Риси", p.get("traits"))
    put("Що знає на старті", p.get("knows"))
    if p.get("hidden"):
        put("Приховане", f"{len(p['hidden'])} — бачите лише ви")
    if "canon" in st:
        sp = start_points()[st["canon"]]
        put("Старт", f"канонічний момент: {sp.get('title', st['canon'])} "
            f"({sp.get('book', '')}), {day_phrase(int(sp.get('day', 1)), _minute(sp))}")
        put("Ситуація", sp.get("pitch"))
        put("Де Ґеральт", sp.get("geralt"))
    else:
        put("Старт", " · ".join(x for x in (
            st.get("place"), st.get("day") and f"день {st['day']}",
            st.get("time") is not None and _clock(st["time"])) if x) or None)
        if not st.get("place"):
            world.append("Місце старту")
        if st.get("day") is None or st.get("time") is None:
            world.append("День і час")
        put("Ситуація", st.get("situation") and _short(st["situation"], 220),
            "Ситуація на старті")
    people = st.get("who_is_here") or []
    cast = ([str(start_points()[st["canon"]]["who"])] if "canon" in st
            and start_points()[st["canon"]].get("who") else [])
    put("Хто поруч", cast + [", ".join(x for x in (q.get("name"), q.get("role")) if x)
                             or q.get("appearance", "") for q in people],
        "Люди поруч" if "canon" not in st else None)
    canon = CHOICE_UK[d["canon"]] if "canon" in d else None
    if canon and d["canon"] == "follow" and "canon" not in st:  # gravity needs a canon moment
        canon += " — діє лише з канонічним стартом; у власній сцені сюжет книг не притягується"
    put("Канон", canon)
    put("Тон", d.get("tone"), "Тон (як у Сапковського)")
    put("Темп", CHOICE_UK[d["pace"]] if "pace" in d else None)
    lim = d.get("limits", {})
    lim_parts = ([f"не буде: {', '.join(lim['avoid'])}"] if lim.get("avoid") else []) + \
        ([f"лише за кадром: {', '.join(lim['veil'])}"] if lim.get("veil") else [])
    put("Межі", "; ".join(lim_parts) or None, "Межі вмісту (жодних обмежень не задано)")
    put("Наслідки", CHOICE_UK["unbounded" if unbounded(pkg) else "real"])
    put("Діалоги", CHOICE_UK[d["dialogue"]] if "dialogue" in d else None)
    put("Підказки дій", CHOICE_UK[d["assistant"]] if "assistant" in d else None)
    put("Кольори", [f"{k} {v}" for k, v in d.get("inks", {}).items()] or None)
    put("Нотатки", d.get("notes") and _short(d["notes"], 220))
    return {"title": title(pkg), "set": out, "world": world,
            "warnings": [w.to_json() for w in pkg.warnings]}


def _minute(sp: dict[str, Any]) -> int:
    t = sp.get("time", "00:00")
    if isinstance(t, int):
        return t
    h, m = str(t).split(":")
    return int(h) * 60 + int(m)


def limits_text(pkg: Package) -> str:
    """Only the content limits, for every prompt that writes what the player reads (NPCs too)."""
    lim, lines = pkg.data.get("limits", {}), []
    if lim.get("avoid"):
        lines.append("- Content the player does not want in this game at all (never show it, "
                     "never let it happen on the page; the world steers elsewhere): "
                     + "; ".join(lim["avoid"]))
    if lim.get("veil"):
        lines.append("- Content that may happen only off-screen: say in one plain sentence that "
                     "it happened, never show it in detail: " + "; ".join(lim["veil"]))
    return "\n".join(lines)


# -- campaign intent (the narrator) -----------------------------------------------------------

def intent_text(pkg: Package) -> str:
    """The package's wishes as the narrator reads them: English frame, the player's words."""
    d, lines = pkg.data, []
    if d.get("tone"):
        lines.append(f"- Tone: {d['tone']}")
    if d.get("pace") in PACE_EN:
        lines.append(f"- Pace: {PACE_EN[d['pace']]}.")
    if limits_text(pkg):
        lines.append(limits_text(pkg))
    if d.get("canon") == "loose":
        lines.append("- Canon: the books are only background here; do not pull events toward "
                     "the saga's plot.")
    sit = d["start"].get("situation")
    if not sit and d["start"].get("canon") in start_points():
        sit = start_points()[d["start"]["canon"]].get("situation")  # a canon moment's own opening
    if sit:
        lines.append(f"- The opening situation the player chose (the start of the story): {sit}")
    if d.get("notes"):
        lines.append(f"- The player's notes: {d['notes']}")
    return "\n".join(lines)


# -- building the campaign --------------------------------------------------------------------

def _sheet(pkg: Package, name: str) -> str:
    """The player sheet as a character file for `derive_traits` (like data/Ragnar.md)."""
    p = pkg.data["player"]
    parts = [f"# {name}", p.get("description", "")]
    if p.get("appearance"):
        parts.append("## Зовнішність (видно з першого погляду)\n" + p["appearance"])
    if p.get("traits"):
        parts.append("## Риси\n" + "\n".join(f"- {t}" for t in p["traits"]))
    if p.get("hidden"):
        parts.append("## Приховане (ніхто не бачить на перший погляд)\n"
                     + "\n".join(f"- {t}" for t in p["hidden"]))
    return "\n\n".join(parts) + "\n"


def _player_name(pkg: Package, seed: str) -> str:
    """The package's name, or one from the npcgen tables (never a canon name)."""
    p = pkg.data["player"]
    if p.get("name"):
        return p["name"]
    sex = infer_sex(p.get("description", ""), p.get("appearance", "")) or "m"
    canon = [e.canonical for e in Glossary.for_world("witcher").entries if e.kind == "person"]
    return pick_name(NORTHERN, sex, seed, "player", canon)


def _player_profile(pkg: Package, name: str, label: str) -> CharacterProfile:
    p = pkg.data["player"]
    desc = _short(p.get("description", ""), 600)
    if p.get("traits"):
        desc += " Риси: " + "; ".join(p["traits"]) + "."
    return CharacterProfile(PLAYER, name, desc, appearance=label or "незнайомець")


def _free_map(place: str) -> tuple[WorldMap, str]:
    """The world map with the start place on it (a place not on the map is added, unlinked)."""
    wmap = vizima(*VIZIMA_EXTRA)
    got = wmap.resolve(place)
    if got is None:
        got = wmap.add_place(Place("start", place, "the start place of this campaign"))
    return wmap, got.id


def _build_people(eng: Engine, people: list[dict[str, Any]]) -> tuple[list[str], dict[str, str]]:
    """The package's people (or two passers-by when none are given), made whole by npcgen."""
    ids, goals = [], {}
    texted: list[tuple[str, str, str]] = []   # (npc, free-text portrait, starting rung)
    for i, q in enumerate(people, 1):
        role = q.get("role")
        look = q.get("appearance") or role or q.get("name", "")
        spec = eng.fresh_npc(f"here{i}", NORTHERN, occupation=role, appearance=look,
                             description=q.get("attitude", ""))
        if q.get("name"):
            spec = replace(spec, name=q["name"])
        # a portrait person's age is the portrait's business: no generated age to contradict it
        age = "" if q.get("portrait") else f", {spec.vitals.age(eng.scene.time)} років"
        desc = " ".join(x for x in (
            f"{spec.name.split()[0]}, {spec.occupation}{age}.", q.get("attitude") and f"Toward the newcomer: {q['attitude']}.",
            q.get("goal") and f"Wants: {q['goal']}.") if x)
        eng.add_npc(spec, description=desc, appearance=look)
        if q.get("senses"):  # stored with the profile: survives reopen and replay
            eng.profiles[spec.id] = replace(eng.profiles[spec.id],
                                            senses=("sight", *q["senses"]))
            if eng._owns_conn:
                eng._save_setup()
        ids.append(spec.id)
        goals[spec.id] = q.get("goal") or q.get("attitude") or f"go about the day as a {spec.occupation}"
        if q.get("knows_player"):
            eng.acquaint(spec.id, PLAYER)
        if q.get("portrait"):
            eng.bind_portrait(spec.id, q["portrait"], rung_seed(q))
        elif q.get("portrait_text"):  # the author's free text, made into a portrait once
            texted.append((spec.id, q["portrait_text"], rung_seed(q)))
    if texted:   # the conversions are independent calls: made concurrently
        eng.make_short_portraits(texted)
    return ids, goals


def rung_seed(person: dict[str, Any]) -> str:
    """The rung a package person starts on toward the player: one who knows the player is an
    ally when the attitude reads friendly, else a client; anyone else is a stranger."""
    if not person.get("knows_player"):
        return "stranger"
    words = [w.lower() for w in _UK_WORD.findall(person.get("attitude", ""))]
    for i, w in enumerate(words):
        if FRIENDLY.fullmatch(w) and not (i and words[i - 1] in NEGATION):
            return "ally"
    return "client"


def _passers_by(eng: Engine, place_id: str) -> list[dict[str, Any]]:
    """Nobody given: two people of the place (the world decides): a tavern has its keeper and a
    guest; elsewhere two different trades from the npcgen tables, seeded."""
    if place_id == "tavern":
        return [{"role": "корчмар"}, {"role": "візник"}]
    roles: list[str] = []
    for i in range(1, 12):
        occ = eng.fresh_npc(f"probe{i}", NORTHERN).occupation
        if occ not in roles:
            roles.append(occ)
        if len(roles) == 2:
            break
    return [{"role": r} for r in roles]


def _apply_inks(camp: Campaign, inks: dict[str, str]) -> None:
    eng = camp.engine
    for key, ink in inks.items():
        k = key.lower()
        for cid, prof in eng.profiles.items():
            if cid == PLAYER:
                continue
            names = {prof.name.lower(), prof.name.split()[0].lower(),
                     (prof.appearance or "").lower()}
            occ = prof.description.lower()
            if k in names or (k and k in occ):
                camp.inks.set(camp.tok(cid), ink)
                break
        else:
            eng._note("package_ink_unmatched", key=key)
    camp.inks.flush()


def _store(eng: Engine, key: str, value: Any) -> None:
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         (key, json.dumps(value, ensure_ascii=False)))


def _meta(eng: Engine, key: str) -> Any:
    row = eng.conn.execute("SELECT value FROM campaign_meta WHERE key=?", (key,)).fetchone()
    return json.loads(row[0]) if row else None


def open_package(stack: Stack, pkg: Package, *, root: Path | str = CAMPAIGNS,
                 canon_db: Any = None, name: str | None = None) -> Campaign:
    """A NEW campaign from a validated package; it becomes the current campaign."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    name = name or time.strftime("game-%Y%m%d-%H%M%S")
    while Engine.campaign_exists(name, root):
        name += "x"
    d, st = pkg.data, pkg.data["start"]
    pname = _player_name(pkg, name)
    folder = root / name
    folder.mkdir(parents=True, exist_ok=True)
    sheet = folder / "player.md"
    sheet.write_text(_sheet(pkg, pname), encoding="utf-8")
    # the one cheap call of the start: how the character looks, from the sheet (cached by text)
    traits = derive_traits(rec, stack.models.extractor, sheet, root)
    label = (traits.label if traits and traits.label else "") or _short(
        d["player"].get("appearance", ""), 60)
    player = _player_profile(pkg, pname, label)
    kw = viz.engine_kw(stack, d.get("dialogue"))
    inventory = d["player"].get("inventory")
    if inventory:
        kw["item_ids"] = True  # an explicit inventory has ids, locations and containers
    free = "canon" not in st

    def setup(eng: Engine) -> None:
        """Before anyone enters: the player's live state and what the character knows."""
        for fact in d["player"].get("knows", []):
            # what the character believes from their own life: a claim, not world truth
            eng.facts.add_canon(f"{pname} вважає (з власного життя, може помилятися): {fact}",
                                game_time=eng.scene.time,
                                knowers=[(PLAYER, "told", "own life, from another world")])
        if inventory:  # the package's own list replaces the equipment/inventory of the sheet
            seed_player_state(eng, traits, base=(), skip=(EQUIPMENT, INVENTORY))
            seed_player_inventory(eng, inventory)
        else:
            seed_player_state(eng, traits, base=())
        for text in d["player"].get("latent", []):
            # a power the character does not know of: only the magic sense perceives it
            eng.apply_state_change(StateChange(PLAYER, INTERNAL, "add", text, True, aware=False,
                                               channel="magic"))

    filled = {"name": pname} if not d["player"].get("name") else {}
    if not free:
        canon = viz.load_canon(stack, canon_db)
        cs = canon_start(st["canon"])
        eng, play = viz.create_situation_a(rec, root, name, canon, kw, player=player,
                                           unbounded=unbounded(pkg), kind=KIND, setup=setup,
                                           start=cs)
        if d.get("canon") == "loose":
            canon_used = None  # the books only as background: no canon gravity or guard
        else:
            canon_used = canon
        world = viz.situation_a_world(eng, canon_used, stack.judge, play if canon_used else None,
                                      start=cs)
        if canon_used is None:
            eng.canon_guard = None
        sp = start_points()[st["canon"]]
        intro, ttl = cs.intro, str(sp.get("title", viz.TITLE))
        people = st.get("who_is_here") or []
        extra_ids, _goals = _build_people(eng, people) if people else ([], {})
        for c in extra_ids:
            eng.enter_scene(c)
            world.cast[c] = world.here() or cs.place_id
            world.goals[c] = _goals[c]
        meta_world = {"kind": "situation_a", "canon": canon_used is not None, "start": cs.id,
                      "cast": {c: world.cast[c] for c in extra_ids}, "goals": _goals}
    else:
        place = st.get("place") or "корчма «Під Лисом»"
        day = st.get("day") or 1
        minute = st["time"] if st.get("time") is not None else 19 * 60
        if not st.get("place"):
            filled["place"] = place
        if st.get("day") is None or st.get("time") is None:
            filled["time"] = f"день {day}, {_clock(minute)}"
        wmap, here = _free_map(place)
        eng = Engine.create_campaign(
            name, rec, [player], Scene(wmap.name(here), (), (day - 1) * 1440 + minute),
            root=root, player_unlimited=unbounded(pkg), outcomes=True, seed=name, **kw)
        _store(eng, "app_kind", KIND)
        setup(eng)
        people = st.get("who_is_here") or _passers_by(eng, here)
        if not st.get("who_is_here"):
            filled["people"] = [q["role"] for q in people]
        ids, goals = _build_people(eng, people)
        for c in ids:
            eng.enter_scene(c)
        eng.enter_scene(PLAYER)
        sit = st.get("situation")  # reaches the narrator as intent (above), the player as the intro
        meta_world = {"kind": "free", "place": place, "cast": {c: here for c in ids},
                      "goals": goals}
        world = _free_world(eng, meta_world)
        intro = sit or f"{day_phrase(day, minute)}. {place[:1].upper() + place[1:]}."
        ttl = title(pkg, place)
    eng.ctx.intent = intent_text(pkg)
    eng.ctx.limits = limits_text(pkg)
    _store(eng, "package", {"data": d, "title": ttl, "intro": intro, "world": meta_world,
                            "filled": filled})
    eng._note("package_start", filled=filled, calls=len(rec.calls))
    tr = Translator(rec, stack.models.extractor, folder / "translations.json")
    camp = Campaign(eng, rec, stack.spend, stack.live, name, tr, title=ttl, intro=intro,
                    world=world, assistant=d.get("assistant", "on") == "on")
    if d.get("inks"):
        _apply_inks(camp, d["inks"])
    _pointer(root).write_text(name)  # only a fully built campaign becomes the current one
    return camp


def _free_world(eng: Engine, meta: dict[str, Any]) -> World:
    wmap, here = _free_map(meta["place"])
    on_map = here != "start"
    cols = pilot.canon_collectives(wmap, viz._NoNames()) if on_map else []
    from harness.scene_cast import SceneCast
    world = World(eng, wmap, collectives=cols, cast=meta["cast"], goals=meta["goals"])
    # people the narration brings in: passers-by from npcgen (no canon cast on a free start)
    eng.scene_cast = SceneCast(None, culture=NORTHERN, where=world.where, here=world.here)
    return world


def reopen(stack: Stack, name: str, *, root: Path | str = CAMPAIGNS, canon_db: Any = None
           ) -> Campaign:
    """Continue a saved package campaign: the engine from its log, the intent and the world
    from the stored package."""
    root = Path(root)
    rec = Recorder(stack.provider, stack.models, stack.spend)
    kw = viz.engine_kw(stack)
    kw.pop("dialogue")  # the campaign's own stored setting (a package may say classic)
    eng = Engine.open_campaign(name, rec, root=root, **kw)
    saved = _meta(eng, "package") or {}
    pkg = Package(saved.get("data") or {"player": {}, "start": {}})
    pkg.data.setdefault("start", {})
    eng.ctx.intent = intent_text(pkg)
    eng.ctx.limits = limits_text(pkg)
    mw = saved.get("world") or {}
    if mw.get("kind") == "situation_a":
        canon = viz.load_canon(stack, canon_db) if mw.get("canon") else None
        cid = mw.get("start")
        world = viz.situation_a_world(
            eng, canon, stack.judge,
            start=canon_start(cid) if cid in start_points() else pilot.SITUATION_A)
        if canon is None:
            eng.canon_guard = None
        world.cast.update(mw.get("cast", {}))
        world.goals.update(mw.get("goals", {}))
    else:
        world = _free_world(eng, mw)
    _pointer(root).write_text(name)
    tr = Translator(rec, stack.models.extractor, root / name / "translations.json")
    return Campaign(eng, rec, stack.spend, stack.live, name, tr, title=saved.get("title", name),
                    intro=saved.get("intro", ""), world=world,
                    assistant=pkg.data.get("assistant", "on") == "on")


def kind_of(name: str, root: Path | str) -> str | None:
    """The `app_kind` a saved campaign was made as (None: unknown or no campaign)."""
    path = Engine.campaign_path(name, root) / "campaign.db"
    if not path.exists():
        return None
    import sqlite3
    try:
        with sqlite3.connect(f"file:{path}?mode=ro", uri=True) as conn:
            row = conn.execute("SELECT value FROM campaign_meta WHERE key='app_kind'").fetchone()
    except sqlite3.Error:
        return None
    return json.loads(row[0]) if row else None


def opener(stack: Stack, *, root: Path | str = CAMPAIGNS,
           fallback: Callable[[bool], Campaign], canon_db: Any = None
           ) -> Callable[[bool], Campaign]:
    """The app's `open_campaign(new)`: continue the current campaign when it was made from a
    package, else whatever `fallback` opens (the Vizima or the inn campaign)."""
    def open_(new: bool) -> Campaign:
        cur = _pointer(Path(root))
        if not new and cur.exists():
            name = cur.read_text().strip()
            if name and kind_of(name, root) == KIND:
                return reopen(stack, name, root=root, canon_db=canon_db)
        return fallback(new)
    return open_
