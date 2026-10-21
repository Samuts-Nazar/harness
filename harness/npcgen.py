"""Long-run NPC foundations (task 19, 18B "change now"). Everything here is code and seeded: the
model never invents a name, a trait, an age or a death.

1. Core and mutable layers. A profile has an immutable `core` (voice, drives, values) set once; the
   mutable layers (memories, attitudes, live state) are derived from the log. `build_core` writes
   the core text from structured parts; `Engine.set_core` refuses a second write.
2. Names, traits and quirks for non-canon NPCs come from tables below, by culture, seeded by the
   campaign seed and a slot, so the same campaign always makes the same person, and a name already
   used in the campaign (cast, canon, glossary) is never reused.
3. Age, birth and mortality: every NPC the player knows gets `Vitals` (birth time, a lifespan drawn
   once from a per-culture table). Aging and natural death are computed from them in code; the model
   only narrates ("Х помер") from the fact the death writes. Marriage and children are hooks only
   (`Vitals.spouse`, `Vitals.children`): nothing reads them yet.

The tables are the project's own (plausible forms for each people, written in Ukrainian), not
taken from the books. The calendar is the placeholder of `harness/world/clock.py` (360-day year);
`EPOCH_YEAR` is a placeholder year for the start of play.
"""
from __future__ import annotations

import random
import zlib
from dataclasses import dataclass, field, replace
from typing import Iterable, Sequence

from .models import CharacterProfile

YEAR_MIN = 360 * 24 * 60  # the placeholder calendar of harness/world/clock.py
EPOCH_YEAR = 1263          # placeholder: the year of campaign minute 0

NORDLING, NORTHERN, NILFGAARDIAN, ELVEN, DWARVEN, HALFLING = (
    "nordling", "northern", "nilfgaardian", "elven", "dwarven", "halfling")
CULTURES = (NORDLING, NORTHERN, NILFGAARDIAN, ELVEN, DWARVEN, HALFLING)

# -- names -------------------------------------------------------------------------------------
# (male, female, by-names). A by-name is how that people tells two people of one name apart.
NAMES: dict[str, tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]] = {
    NORDLING: (  # the isles of the north-west sea: raiders, fishers, shield-bearers
        ("Ґюнар", "Бйорн", "Торвальд", "Гаральд", "Ульф", "Ейнар", "Рагнвальд", "Свен", "Хельґе",
         "Кнут", "Оддвар", "Арнульф", "Торбйорн", "Ґрімкел", "Сигурд", "Ерік"),
        ("Хільда", "Астрід", "Ґудрун", "Сіґні", "Торгерда", "Інґа", "Бйорґ", "Ульфгільд", "Ранґа",
         "Вігдіс", "Тордіс", "Гальдіс", "Ейра", "Сольвей"),
        ("Залізний Кулак", "Чорний Весляр", "Сивий", "Однобровий", "Штормовий", "Китобій",
         "Кривий Якір", "Рудий", "Мовчун", "Довгий Спис")),
    NORTHERN: (  # the Northern kingdoms: farmers, townsfolk, soldiers; Slavic-sounding
        ("Зденко", "Ярош", "Вацко", "Богуш", "Станіслав", "Мирослав", "Радим", "Ґжеґож", "Лешек",
         "Владко", "Ярополк", "Ціборик", "Любомир", "Борис", "Домаш", "Бран", "Влодек", "Тихомир"),
        ("Мірра", "Ярина", "Божена", "Любава", "Зоська", "Власта", "Дарина", "Милена", "Ружена",
         "Ґоґна", "Ванда", "Збислава", "Ярмила", "Богдана"),
        ("Коваль", "Ткач", "Бондар", "Рибалка", "Гончар", "Сліпий", "Малий", "Рудий", "Довбуш",
         "Вовк", "Кривоніс", "Шульга", "Черемха", "Сивоок")),
    NILFGAARDIAN: (  # the empire of the south: official, long, Latin-flavoured
        ("Мартеллус", "Юліан", "Кассіан", "Валеріус", "Октавіан", "Серафин", "Лукреціус", "Феліціан",
         "Антоніус", "Корвін", "Максенцій", "Тіберіан", "Аурелій", "Домітіан"),
        ("Корнелія", "Валентина", "Люцінія", "Октавія", "Аурелія", "Серена", "Фабіола", "Юнія",
         "Клавдія", "Лівія", "Марцелла", "Феліція"),
        ("аб Ренарт", "ан Вальдо", "аеп Кассіус", "та Корвін", "аб Марцелл", "ан Серано",
         "аеп Люціан", "та Октавус")),
    ELVEN: (  # the Elder Folk (Aen Seidhe): old, flowing, never short
        ("Айдан", "Ейтне", "Іорвет", "Фаелін", "Ґеллен", "Мерідан", "Коінн", "Седрік", "Тайгерн",
         "Аваллак", "Лорєль", "Еохайр"),
        ("Філавандрель", "Ейтнє", "Мелеаґ", "Ліліан", "Серіель", "Анаріель", "Аглаїс", "Ґаелле",
         "Іорлет", "Лаеліа", "Морвудд"),
        ("Аен Сейдхе", "з Дол Блатанна", "Лісовий Шепіт", "Сріблястий Потік", "Сивий Вогонь")),
    DWARVEN: (  # the mountain people: short, hard, clan-bound
        ("Золтан", "Яр", "Мунро", "Бальдур", "Хьялмар", "Бренн", "Горан", "Торін", "Дорґал",
         "Скальд", "Брокк", "Ґімрік"),
        ("Дага", "Брунхільда", "Торґа", "Мюрна", "Хельґа", "Ґільда", "Дорна", "Скара", "Ґрета"),
        ("Залізоруб", "Кам'янобород", "Гірський Молот", "Чорна Копальня", "Глибокий Ґрунт",
         "Червона Руда", "Міцна Кирка")),
    HALFLING: (  # small, rooted people of the river valleys: farms and orchards
        ("Дагоберт", "Ґаспар", "Філібер", "Теодульф", "Бертран", "Мартен", "Оноре", "Гільберт",
         "Люсьєн", "Рейнар"),
        ("Бланш", "Жозетта", "Колетта", "Евлалія", "Мадлен", "Оділь", "Фелісіті", "Рожетта",
         "Аделіна"),
        ("Теплий Пагорб", "Сад-Яблунь", "Мирний Брід", "Тихий Млин", "Біля Вишні", "Довге Поле")),
}

# -- traits and quirks -----------------------------------------------------------------------------
TRAITS = ("обережний", "балакучий", "скупий", "щедрий", "підозріливий", "вірний слову",
          "боязкий", "гордовитий", "лінивий", "працьовитий", "жадібний до новин", "забобонний",
          "сентиментальний", "різкий на язик", "терплячий", "мстивий", "вдячний за кожну дрібницю",
          "недовірливий до чужинців", "побожний", "насмішкуватий")
QUIRKS = ("постійно крутить в пальцях монету", "заїкається, коли бреше", "ніколи не дивиться "
          "співрозмовнику в очі", "перед відповіддю довго мовчить", "примовляє народні приказки",
          "лічить усе вголос", "облизує губи перед кожною вимовою ціни", "скаржиться на коліно",
          "з усіма на 'ви', навіть з дітьми", "тихо наспівує, коли нервує",
          "поправляє рукав, коли чогось боїться", "сміється вдвічі голосніше, ніж треба",
          "завжди сідає спиною до стіни", "кличе всіх молодших 'дитино'")
VOICES = ("тихий і рівний", "голосний, вимовляє слова на сільський лад", "різкий, уривчастий",
          "повільний, з довгими паузами", "ввічливий до самого дна, і з холодком",
          "швидкий, ковтає закінчення", "ласкавий, зі зменшувальними словами",
          "сухий, ділової міри")
DRIVES = ("тримати свій дах над головою", "не накликати біди на родину", "розбагатіти на дрібницях",
          "бути в курсі всього, що діється в окрузі", "відплатити давню кривду",
          "дожити спокійно до старості", "довести, що чогось вартий", "берегти своє ремесло",
          "захистити молодших", "виглядати поважно в очах сусідів")
VALUES = ("слово дорожче за гроші", "чужим не вірити першим", "сім'я понад усе",
          "порядок краще за свободу", "борг треба віддавати", "не втручатися в чужі справи",
          "гості священні", "сила розв'язує суперечки", "кожен відповідає за себе")
OCCUPATIONS: dict[str, tuple[str, ...]] = {
    NORDLING: ("рибалка", "вояк", "корабел", "коваль", "мисливець на тюленів", "торговець хутром"),
    NORTHERN: ("корчмар", "візник", "ткач", "селянин", "дроворуб", "міський вартовий", "швець",
               "торговець"),
    NILFGAARDIAN: ("писар", "податківець", "легіонер", "купець", "слуга", "лікар"),
    ELVEN: ("мисливець", "мандрівний співак", "зброяр", "збирач трав", "розвідник"),
    DWARVEN: ("шахтар", "коваль", "зброяр", "охоронець каравану", "каменяр"),
    HALFLING: ("садівник", "пивовар", "пасічник", "мірошник", "городник"),
}

# -- lifespans -------------------------------------------------------------------------------------
# (typical natural lifespan in years, spread): drawn once per person. Violent death is not natural
# death and is never computed here. Elves and dwarves outlive humans by far.
LIFESPAN: dict[str, tuple[float, float]] = {
    NORDLING: (62, 14), NORTHERN: (60, 14), NILFGAARDIAN: (66, 13),
    ELVEN: (320, 90), DWARVEN: (250, 50), HALFLING: (95, 15),
}
# the age (years) where adulthood starts, by culture, for generated adults
ADULT_AT: dict[str, int] = {NORDLING: 16, NORTHERN: 16, NILFGAARDIAN: 18, ELVEN: 40, DWARVEN: 30,
                            HALFLING: 25}


def _rng(seed: int | str, *parts: object) -> random.Random:
    """A generator that depends only on the campaign seed and the slot, not on call order."""
    return random.Random(zlib.crc32(("|".join(str(p) for p in (seed, *parts))).encode()))


def _norm(name: str) -> str:
    return " ".join(name.lower().replace("'", "").replace("’", "").split())


def taken_names(profiles: Iterable[CharacterProfile], extra: Iterable[str] = ()) -> set[str]:
    """Names (full and the first word) already in the campaign."""
    out: set[str] = set()
    for n in [*(p.name for p in profiles), *extra]:
        out.add(_norm(n))
        out.add(_norm(n).split(" ")[0])
    return out


def pick_name(culture: str, sex: str, seed: int | str, slot: str | int,
              used: Iterable[str] = ()) -> str:
    """A name for `culture` and `sex` ("m"/"f") that is not in `used`. Deterministic for the same
    (seed, slot, used). The given name alone is tried first; if every given name of the culture
    is taken, a by-name is added; if still taken, a numeral-free distinct pair is searched."""
    if culture not in NAMES:
        raise ValueError(f"unknown culture {culture!r}")
    male, female, by = NAMES[culture]
    firsts = list(male if sex == "m" else female)
    taken = {_norm(u) for u in used} | {_norm(u).split(" ")[0] for u in used}
    rng = _rng(seed, "name", culture, sex, slot)
    rng.shuffle(firsts)
    for f in firsts:
        if _norm(f) not in taken:
            return f
    bys = list(by)
    rng.shuffle(bys)
    for f in firsts:
        for b in bys:
            full = f"{f} {b}"
            if _norm(full) not in taken:
                return full
    raise RuntimeError(f"no free name left for {culture}/{sex}")


@dataclass(frozen=True)
class Vitals:
    """Age and mortality of one person, from code. `birth_t` and `death_t` are campaign minutes
    (birth is negative: before play). `spouse` and `children` are hooks for a later feature."""
    character: str
    culture: str
    sex: str
    birth_t: int
    death_t: int          # the natural death, drawn once at creation
    spouse: str | None = None
    children: tuple[str, ...] = ()

    def age(self, now_t: int) -> int:
        return max(0, (now_t - self.birth_t) // YEAR_MIN)

    def birth_year(self) -> int:
        return EPOCH_YEAR + self.birth_t // YEAR_MIN

    def alive(self, now_t: int) -> bool:
        return now_t < self.death_t


def make_vitals(character: str, culture: str, sex: str, seed: int | str, *,
                age: int | None = None, now_t: int = 0) -> Vitals:
    """Draw the person's age (if not given: an adult, skewed to the middle of life) and their
    natural lifespan; a lifespan never ends before the current age + 1 year."""
    rng = _rng(seed, "vitals", character, culture, sex)
    mean, sd = LIFESPAN[culture]
    lifespan = max(mean * 0.35, rng.gauss(mean, sd))
    if age is None:
        lo = ADULT_AT[culture]
        age = int(lo + (lifespan - lo) * rng.betavariate(2, 2) * 0.85)
    lifespan = max(lifespan, age + 1 + rng.random() * 3)
    birth_t = now_t - int(age * YEAR_MIN + rng.random() * YEAR_MIN)
    death_t = birth_t + int(lifespan * YEAR_MIN)
    return Vitals(character, culture, sex, birth_t, death_t)


def old_age_text(v: Vitals, now_t: int) -> str:
    """What the NPC's own context may say about their age (computed, so it stays consistent)."""
    return f"You are {v.age(now_t)} years old (born in {v.birth_year()})."


def build_core(voice: str, drives: Sequence[str], values: Sequence[str],
               traits: Sequence[str] = (), quirk: str = "") -> str:
    """The immutable core as plain text: voice, drives, values (and traits/quirk). Set once."""
    parts = [f"Voice: {voice}.", "Drives: " + "; ".join(drives) + ".",
             "Values: " + "; ".join(values) + "."]
    if traits:
        parts.append("Character: " + ", ".join(traits) + ".")
    if quirk:
        parts.append(f"Habit: {quirk}.")
    return " ".join(parts)


@dataclass(frozen=True)
class NpcSpec:
    id: str
    name: str
    culture: str
    sex: str
    occupation: str
    traits: tuple[str, ...]
    quirk: str
    core: str
    vitals: Vitals

    def profile(self, description: str = "", appearance: str = "") -> CharacterProfile:
        desc = description or (
            f"{self.name.split()[0]}, {self.occupation}, {self.vitals.age(0)} років. "
            f"{self.traits[0].capitalize()}.")
        return CharacterProfile(self.id, self.name, desc, appearance=appearance, core=self.core)


def generate_npc(seed: int | str, slot: str | int, *, culture: str, sex: str | None = None,
                 used: Iterable[str] = (), age: int | None = None, occupation: str | None = None,
                 now_t: int = 0, id_prefix: str = "npc") -> NpcSpec:
    """A whole non-canon NPC from tables. The same (seed, slot, culture, used) always gives the
    same person. `used`: names already in the campaign (profiles, canon, glossary)."""
    rng = _rng(seed, "npc", slot, culture)
    sex = sex or rng.choice(("m", "f"))
    name = pick_name(culture, sex, seed, slot, used)
    cid = f"{id_prefix}_{slot}"
    traits = tuple(rng.sample(TRAITS, 2))
    quirk = rng.choice(QUIRKS)
    occ = occupation or rng.choice(OCCUPATIONS[culture])
    core = build_core(rng.choice(VOICES), rng.sample(DRIVES, 2), rng.sample(VALUES, 2), traits,
                      quirk)
    return NpcSpec(cid, name, culture, sex, occ, traits, quirk, core,
                   make_vitals(cid, culture, sex, seed, age=age, now_t=now_t))


def with_core(profile: CharacterProfile, core: str) -> CharacterProfile:
    """Set a profile's core once. A profile that has one refuses a different one."""
    if profile.core and profile.core != core:
        raise ValueError(f"the core of {profile.id!r} is immutable")
    return replace(profile, core=core)


@dataclass
class VitalsBook:
    """The vitals of every NPC the player knows, kept by the engine (saved with the setup)."""
    people: dict[str, Vitals] = field(default_factory=dict)

    def register(self, v: Vitals) -> None:
        self.people[v.character] = v

    def due(self, now_t: int, already: Iterable[str] = ()) -> list[Vitals]:
        """Natural deaths that have happened by `now_t`, oldest first, not yet recorded."""
        done = set(already)
        return sorted((v for v in self.people.values()
                       if v.character not in done and not v.alive(now_t)),
                      key=lambda v: (v.death_t, v.character))

    def to_json(self) -> list[list[object]]:
        return [[v.character, v.culture, v.sex, v.birth_t, v.death_t, v.spouse, list(v.children)]
                for v in self.people.values()]

    @classmethod
    def from_json(cls, rows: Sequence[Sequence[object]]) -> "VitalsBook":
        b = cls()
        for r in rows:
            b.register(Vitals(str(r[0]), str(r[1]), str(r[2]), int(r[3]), int(r[4]),  # type: ignore[call-overload]
                              r[5] if r[5] else None, tuple(r[6])))  # type: ignore[arg-type]
        return b
