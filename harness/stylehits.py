"""Prose-quality detector (task: user graded texts down to 1). A cheap, deterministic scan of
generated Ukrainian text for the shapes the user rejected: invented similes and aphorisms, objects
named by their material, vague mystical non-events. It only flags; nothing is blocked or
regenerated because of a hit (the engine logs `style_hit` and counts hits per turn).

Kinds:
- `simile`: a comparison ("як у", "як той", "наче", "ніби", "немов", "мов") that grows a relative
  clause ("... що дивиться на коня"), or runs longer than `LONG_SIMILE` words.
- `aphorism`: "це не X, це Y" balance, or "X — це Y" definition inside a line of speech.
- `metonymy`: a material used as the object of holding, wearing, going in/on, taking (шовк, мідь,
  сталь, срібло, оксамит, полотно): "ходить у шовках", "тримає мідь".
- `mystic`: an inanimate thing acting "сам/сама/само" next to "краще не ...", or the aside
  "краще не розмірковувати/питати/думати ...".
"""
from __future__ import annotations

import re
from dataclasses import dataclass

LONG_SIMILE = 14  # words from the comparison marker to the end of the sentence
_FLAGS = re.IGNORECASE


@dataclass(frozen=True)
class StyleHit:
    kind: str
    text: str  # the offending stretch, as written


_W = r"[\w'’-]+"
_MARK = r"(?:як\s+(?:у|той|та|те|ті)|наче|ніби|немов|мов)"
_SIMILE_REL = re.compile(
    rf"\b{_MARK}\b(?:\s+{_W}){{1,6}}?\s*,?\s+(?:що|який|яка|яке|які|котрий|котра)\s+{_W}[^.!?…\n]*", _FLAGS)
_SIMILE_LONG = re.compile(rf"\b{_MARK}\b[^.!?…\n]*", _FLAGS)

_NOT_X_BUT_Y = re.compile(
    r"\b(?:це|то)\s+не\s+[^.!?…\n,;—]{1,40}\s*(?:[,;]|\s[—–])\s*(?:це|то)\b[^.!?…\n]{0,30}", _FLAGS)
_DEFINITION = re.compile(rf"(?<![.!?…,:;—–])\b{_W}\s+[—–]\s+це\s+[^.!?…\n]{{0,40}}", _FLAGS)

_VERB = (r"(?:тримає\w*|тримав\w*|тримала|тримаю|тримати|тримають|держить|держав\w*|носить|носив\w*|"
         r"носила|носиш|носять|носити|ходить|ходив\w*|ходила|ходиш|ходять|ходити|бере|брав\w*|"
         r"брала|беруть|брати|взяв\w*|взяла)")
_MATERIAL = (r"(?:шовк(?:у|и|ом|ах|ів)?|мід(?:ь|і|дю)|сталь|сталі|сталлю|срібл(?:о|а|у|ом|і)|"
             r"оксамит(?:у|и|ом|ах|ів)?|полотн(?:о|а|у|ом|і))")
_METONYMY = re.compile(
    rf"\b{_VERB}\s+(?:(?:у|в|на|з|із)\s+)?(?:{_W}\s+)?{_MATERIAL}\b"
    rf"|\b(?:у|в|на)\s+{_MATERIAL}\s+{_VERB}\b", _FLAGS)

_SELF = re.compile(r"\bсам(?:а|о|і)?\b", _FLAGS)
_BETTER_NOT = re.compile(r"\bкраще\s+не\b", _FLAGS)
_MYSTIC_ASIDE = re.compile(
    r"\bкраще\s+не\s+(?:розмірковувати|питати|думати|вдумуватися|знати|уточнювати|допитуватися)"
    r"[^.!?…\n]*", _FLAGS)

_SENT = re.compile(r"[^.!?…\n]+[.!?…]*")


def style_hits(text: str, long_simile: int = LONG_SIMILE) -> list[StyleHit]:
    """All likely offenders in `text`, in order of appearance."""
    out: list[tuple[int, StyleHit]] = []
    seen: set[tuple[str, int]] = set()

    def add(kind: str, m: re.Match[str]) -> None:
        key = (kind, m.start())
        if key not in seen:
            seen.add(key)
            out.append((m.start(), StyleHit(kind, " ".join(m.group(0).split()))))

    rel_spans = [m.span() for m in _SIMILE_REL.finditer(text)]
    for m in _SIMILE_REL.finditer(text):
        add("simile", m)
    for m in _SIMILE_LONG.finditer(text):
        if len(m.group(0).split()) > long_simile and not any(s <= m.start() < e for s, e in rel_spans):
            add("simile", m)
    for m in _NOT_X_BUT_Y.finditer(text):
        add("aphorism", m)
    offset = 0
    for para in text.split("\n"):
        if re.match(r"\s*[—–]", para):  # a line of speech
            for m in _DEFINITION.finditer(para):
                key = ("aphorism", offset + m.start())
                if key not in seen:
                    seen.add(key)
                    out.append((offset + m.start(), StyleHit("aphorism", " ".join(m.group(0).split()))))
        offset += len(para) + 1
    for m in _METONYMY.finditer(text):
        add("metonymy", m)
    mystic: list[tuple[int, int]] = []
    for m in _SENT.finditer(text):
        if _SELF.search(m.group(0)) and _BETTER_NOT.search(m.group(0)):
            mystic.append(m.span())
            add("mystic", m)
    for m in _MYSTIC_ASIDE.finditer(text):
        if not any(s <= m.start() < e for s, e in mystic):
            add("mystic", m)
    out.sort(key=lambda p: p[0])
    return [h for _, h in out]


def count_by_kind(hits: list[StyleHit]) -> dict[str, int]:
    c: dict[str, int] = {}
    for h in hits:
        c[h.kind] = c.get(h.kind, 0) + 1
    return c
