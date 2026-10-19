"""Task-7 prompts with a variant switch: 'uk' (original Ukrainian context) or 'en' (English context),
plus an explicit Ukrainian output-language instruction in both variants."""
import json
from pathlib import Path
from experiments.bakeoff import prompts as P
from . import en_items as E

TS = Path(__file__).resolve().parents[1] / "bakeoff" / "testset"
NARR = {i["id"]: i for i in json.loads((TS / "narrator.json").read_text())}
NPCS = {i["id"]: i for i in json.loads((TS / "npc.json").read_text())}

LANG = "Відповідай українською мовою: весь текст (опис, дії, репліки) має бути українською."
LANG_EXTRACT = {"uk": "Пиши поле content у фактах українською мовою.",
                "en": "Write the content field of every fact in English."}


# 'enu' = English context, but proper nouns (names, places) written in their Ukrainian forms.
UK_PROPER = [("Philippa Eilhart", "Філіппа Ейльгарт"), ("Vernon Roche", "Вернон Роше"), ("Kaer Morhen", "Каер Морхен"),
             ("Kaedwen", "Кедвен"), ("Novigrad", "Новіград"), ("Nilfgaard", "Нільфгаард"), ("Yaruga", "Яруга"),
             ("Maribor", "Марибор"), ("Geralt", "Ґеральт"), ("Philippa", "Філіппа"), ("Temeria", "Темерія"),
             ("Triss Merigold", "Тріс Мерігольд"), ("Jaskier (Dandelion)", "Любисток (Лютик)"),
             ("Blue Stripes", "«Блакитні смуги»"), ("Under the Grey Mouse", "Під сірою мишею"),
             ("Ragnar", "Рагнар"), ("Vesemir", "Весемір"), ("Lambert", "Ламберт"), ("Eskel", "Ескель"),
             ("Coen", "Койон"), ("Triss", "Тріс"), ("Jaskier", "Любисток"), ("Hostomyl", "Гостомил"),
             ("Roche", "Роше"), ("Marta", "Марта")]
UK_ROLE = {"guard": "Вартовий", "merchant": "Купець", "smith": "Коваль", "child": "Дівчинка"}


def _uk(s):
    if isinstance(s, str):
        for a, b in UK_PROPER:
            s = s.replace(a, b)
        return s
    if isinstance(s, (list, tuple)):
        return type(s)(_uk(x) for x in s)
    return s


def _variant(it, v):
    if v == "uk":
        return it, P.nm, P.PROFILES
    if v == "enu":
        it, nmf, pr = _variant(it, "en")
        it = {k: (_uk(x) if k in ("location", "time", "canon", "campaign", "knows", "noticed", "attitudes", "state", "recent")
                  and k != "recent" else x) for k, x in it.items()}
        if it["id"].startswith("n"):
            it["recent"] = [(c, _uk(t)) for c, t in it["recent"]]
        return it, (lambda c: UK_ROLE.get(c) or P.NAMES.get(c, c)), {k: _uk(x) for k, x in pr.items()}
    it = dict(it)
    e = (E.NARRATOR if it["id"].startswith("n") else E.NPC)[it["id"]]
    for k in ("location", "time", "canon", "campaign", "knows", "noticed", "attitudes", "state"):
        if k in e:
            it[k] = e[k]
    if "recent" in e and it["id"].startswith("n"):
        it["recent"] = e["recent"]
    # NPC items: recent holds only player lines, which stay Ukrainian
    return it, (lambda c: E.NAMES.get(c, c)), E.PROFILES


def _render(fn, it, nmf, profiles):
    old_nm, old_pr = P.nm, P.PROFILES
    P.nm, P.PROFILES = nmf, profiles
    try:
        return fn(it)
    finally:
        P.nm, P.PROFILES = old_nm, old_pr


def narrator(iid, v):
    msgs = _render(P.narrator, *_variant(NARR[iid], v))
    msgs[0] = dict(msgs[0], content=msgs[0]["content"] + " " + LANG)
    return msgs


def npc(iid, v):
    msgs = _render(P.npc, *_variant(NPCS[iid], v))
    msgs[0] = dict(msgs[0], content=msgs[0]["content"] + " " + LANG)
    return msgs


def extractor(it, v):
    msgs = P.extractor(it)
    msgs[1] = dict(msgs[1], content=msgs[1]["content"] + "\n\n" + LANG_EXTRACT[v])
    return msgs
