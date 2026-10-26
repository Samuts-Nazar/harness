"""Readable items and the READ knowledge channel (outsider plan 1, task 6). Fake provider and
judge, a tiny invented file in tmp_path; the saga file is never used here."""
from __future__ import annotations

import json

import pytest

from harness import knowledge, readable
from harness.judge import FakeJudge, default_fake_judge
from harness.models import EQUIPMENT, PLAYER
from harness.state import StateChange
from conftest import diff, make_engine

TEXT = """\
Розділ перший.
Старий торговець приніс на ярмарок мідну лампу.
Ніхто не знав, що в лампі живе джин.
Діти сміялися, а торговець мовчав.
Про джина говорили тільки пошепки.
Казали, що джини виконують три бажання.
Хто розбудить духа стихії, той заплатить дорого.
Минула зима, і ярмарок закрився.
""" + "".join(f"Порожній рядок {i}.\n" for i in range(5)) + """\
Розділ другий.
Мельник пив пиво з ковалем.
Коваль кував підкови до ранку.
""" + "".join(f"Ще рядок {i}.\n" for i in range(5)) + """\
Вони розмовляли з джинами уві сні.
"""

READER_OK = json.dumps({"found": True,
                        "text": "У лампі торговця живе джин; джини виконують три бажання.",
                        "records": ["У мідній лампі торговця живе джин.",
                                    "Джини виконують три бажання."]}, ensure_ascii=False)
TERMS = json.dumps({"terms": ["джин", "джини", "лампа", "бажання"]}, ensure_ascii=False)


def book(tmp_path, text=TEXT, name="book.txt"):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return p


def give(eng, item_id="item:notebook", name="нотатник", content=None, holder=PLAYER):
    eng.apply_state_change(StateChange(holder, EQUIPMENT, "add", name, True, id=item_id,
                                       location="in_hand"))
    row = eng.conn.execute("SELECT value FROM campaign_meta WHERE key='inventory_meta'").fetchone()
    meta = json.loads(row[0]) if row else {}
    if content is not None:
        meta[item_id] = {"content": content}
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("inventory_meta", json.dumps(meta, ensure_ascii=False)))


def engine(tmp_path, script=None, rules=None):
    judge = default_fake_judge()
    judge.rules.update({"read_duration": "minutes", **(rules or {})})
    eng, prov = make_engine(script or {}, judge=judge, campaign_dir=tmp_path, item_ids=True)
    return eng, prov


def read_facts(eng, who=PLAYER):
    return [it for it in knowledge.items_for(eng, who) if it.kind == knowledge.READ]


# -- term expansion ------------------------------------------------------------------------------
def test_expand_terms_includes_forms_and_aliases(tmp_path):
    many = ["Джин", "джини", "джина", "дух стихії", "елементаль", "лампа", "бажання", "джин",
            "ифрит", "марид", "демон", "дух", "чарівник", "пустеля", "пляшка"]
    eng, prov = engine(tmp_path, {"reader": [json.dumps({"terms": many}, ensure_ascii=False)]})
    terms = readable.expand_terms(eng, "що там про джинів?")
    assert terms[:3] == ["джин", "джини", "джина"]
    assert "дух стихії" in terms and "елементаль" in terms
    assert len(terms) == 12 and len(set(terms)) == 12  # capped and de-duplicated
    model, msgs = prov.calls[-1]
    assert model == "reader" and "що там про джинів?" in msgs[-1]["content"]
    # a plain callable works too; unreadable output falls back to the request's own words
    assert readable.expand_terms(lambda m: "no json", "лампа торговця") == ["лампа", "торговця"]


# -- grep ----------------------------------------------------------------------------------------
def test_grep_finds_declined_forms(tmp_path):
    p = book(tmp_path)
    got = readable.grep_file(p, ["джин"], context_lines=0)
    lines = [ps.text for ps in got]
    assert any("живе джин" in t for t in lines)
    assert any("Про джина" in t for t in lines)
    assert any("джини виконують" in t for t in lines)
    assert any("з джинами" in t for t in lines)
    assert not any("Мельник" in t for t in lines)
    lamp = readable.grep_file(p, ["лампа"], context_lines=0)
    # «лампу», «лампі» on touching lines: one passage; case-insensitive
    assert [(ps.start, ps.end) for ps in lamp] == [(2, 3)]
    # overlapping windows are merged into one passage
    near = readable.grep_file(p, ["джин"], context_lines=3)
    starts = [(ps.start, ps.end) for ps in near]
    assert all(a[1] < b[0] for a, b in zip(starts, starts[1:]))


def test_grep_cap_on_common_word(tmp_path):
    filler = "".join(f"Рядок {i} і ще рядок, і так далі, і знову.\n" for i in range(3000))
    p = book(tmp_path, filler[: len(filler) // 2] + "Тут згадано джина в пляшці.\n"
             + filler[len(filler) // 2:])
    got = readable.grep_file(p, ["і"])
    assert sum(len(ps.text) for ps in got) <= 2000
    assert got == []  # a one-letter word is no search term at all
    got = readable.grep_file(p, ["рядок", "джин"])
    assert sum(len(ps.text) for ps in got) <= 2000
    assert any("джина в пляшці" in ps.text for ps in got)  # the rare term is not drowned out
    long_line = "слово " * 2000 + "джин " + "слово " * 2000
    got = readable.grep_file(book(tmp_path, long_line, "long.txt"), ["джин"])
    assert got and sum(len(ps.text) for ps in got) <= 2000 and "джин" in got[0].text


# -- reading -------------------------------------------------------------------------------------
def test_missing_file_returns_nothing_found(tmp_path):
    eng, prov = engine(tmp_path, {"reader": [TERMS]})
    give(eng, content={"file": "nope.txt"})
    n = eng.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0]
    t0 = eng.scene.time
    res = readable.read(eng, PLAYER, "item:notebook", "про джинів")
    assert not res.found and res.records == [] and res.minutes == 0
    assert "файл" in res.text.lower()
    assert eng.scene.time == t0 and read_facts(eng) == []
    assert not [m for m, _ in prov.calls if m == "reader"]  # no model call for a missing file
    assert eng.conn.execute("SELECT COUNT(*) FROM facts").fetchone()[0] == n
    # unsafe paths are refused before anything is opened
    for bad in ("../secret.txt", "/etc/passwd", "data/../../x.txt"):
        assert readable.resolve_file(eng, bad) is None
    book(tmp_path, name="ok.txt")
    assert readable.resolve_file(eng, "ok.txt") == (tmp_path / "ok.txt").resolve()
    res = readable.read(eng, PLAYER, "item:nothing", "що завгодно")
    assert not res.found and res.records == []


def test_no_hits_creates_no_knowledge(tmp_path):
    book(tmp_path)
    eng, prov = engine(tmp_path, {"reader": [json.dumps({"terms": ["дракон", "ящір"]},
                                                        ensure_ascii=False)]})
    give(eng, content={"file": "book.txt"})
    t0 = eng.scene.time
    res = readable.read(eng, PLAYER, "item:notebook", "про драконів")
    assert not res.found and res.records == [] and res.minutes == 0
    assert "нічого" in res.text.lower()
    assert read_facts(eng) == [] and eng.scene.time == t0
    assert len([m for m, _ in prov.calls if m == "reader"]) == 1  # expansion only, no reader call


def test_read_creates_knowledge_with_read_source(tmp_path):
    book(tmp_path)
    long_rec = "Джин " + "дуже " * 200 + "старий."
    reader = json.dumps({"found": True, "text": "Про джина: живе в лампі.",
                         "records": ["У мідній лампі торговця живе джин.", long_rec]},
                        ensure_ascii=False)
    eng, prov = engine(tmp_path, {"reader": [TERMS, reader]})
    give(eng, content={"file": "book.txt"})
    res = readable.read(eng, PLAYER, "item:notebook", "що там про джинів?")
    assert res.found and res.text == "Про джина: живе в лампі."
    assert len(res.records) == 2 and all(len(r) <= 600 for r in res.records)
    # the reader saw the passages and the question, not the whole file
    reader_msgs = [m for model, m in prov.calls if model == "reader"][-1]
    body = reader_msgs[-1]["content"]
    assert "живе джин" in body and "що там про джинів?" in body and "Мельник пив" not in body
    rows = eng.conn.execute(
        "SELECT f.content, k.character, k.source, k.learned_at FROM facts f JOIN fact_knowers k "
        "ON k.fact_id = f.id WHERE k.source LIKE 'read:%'").fetchall()
    assert {r[1] for r in rows} == {PLAYER}
    assert {r[2] for r in rows} == {"read: item:notebook"}
    assert {r[3] for r in rows} == {eng.scene.time}
    items = read_facts(eng)
    assert len(items) == 2 and items[0].how == "read"
    assert knowledge.public_channel(eng, items[0]).startswith("прочитав це")
    assert "нотатник" in knowledge.detail(eng, items[0])
    lines = eng.ctx.knowledge_lines(eng.deriver.derive(PLAYER, eng.scene.time))
    assert any("живе джин" in ln and "(read in нотатник)" in ln for ln in lines)
    # inline content is read directly, without a term expansion
    eng2, prov2 = engine(tmp_path / "b", {"reader": [READER_OK]})
    give(eng2, "item:letter", "лист", content="Джин живе в лампі. Бажань три.")
    assert readable.read(eng2, PLAYER, "item:letter", "про джина").found
    assert [m for m, _ in prov2.calls] == ["reader"]


def test_read_advances_clock_by_amount(tmp_path):
    book(tmp_path)
    big = "".join(f"Довгий рядок {i} про джина і його лампу, багато слів тут.\n" for i in range(80))
    book(tmp_path, big, "big.txt")
    seen = []

    def by_amount(q, state):
        seen.append(state)
        n = int(next(s for s in state if s.startswith("Characters read:")).split(":")[1])
        return "hour" if n > 1000 else "minutes"

    eng, _ = engine(tmp_path, {"reader": [TERMS, READER_OK, TERMS, READER_OK]},
                    {"read_duration": by_amount})
    give(eng, content={"file": "book.txt"})
    give(eng, "item:tome", "фоліант", content={"file": "big.txt"})
    t0 = eng.scene.time
    small = readable.read(eng, PLAYER, "item:notebook", "про джинів")
    assert small.minutes == 5 and eng.scene.time == t0 + 5
    large = readable.read(eng, PLAYER, "item:tome", "про джинів")
    assert large.minutes == 60 and eng.scene.time == t0 + 65
    assert len(seen) == 2  # one duration judgment per read, with the amount as its input


def test_claim_from_unread_text_still_rejected(tmp_path):
    book(tmp_path)

    def channel(q, state):
        return next((k for k, v in q.options.items() if v.startswith("[read]")), "none")

    eng, _ = engine(tmp_path, {"reader": [TERMS, READER_OK]}, {"knowledge_channel": channel})
    give(eng, content={"file": "book.txt"})
    readable.read(eng, PLAYER, "item:notebook", "про джинів")
    assert read_facts(eng) and read_facts(eng, "innkeeper") == []
    # the unknown-claim check sees nothing of the notebook for him...
    assert "живе джин" not in eng._prep_npc("innkeeper").check_prefix()
    # ...and "how does he know that" finds no channel
    line = eng._utterance("innkeeper", "У лампі торговця живе джин.")
    eng._utterance("bard", "Ну й казки.")
    res = eng.challenge_line(line.id, "він не читав нотатника")
    assert res.verdict == "no_channel"


def test_other_reader_gets_own_read_channel(tmp_path):
    book(tmp_path)

    def channel(q, state):
        return next((k for k, v in q.options.items() if v.startswith("[read]")), "none")

    eng, _ = engine(tmp_path, {"reader": [TERMS, READER_OK]}, {"knowledge_channel": channel})
    give(eng, content={"file": "book.txt"})
    readable.read(eng, "innkeeper", "item:notebook", "про джинів")  # he is shown the notebook
    got = read_facts(eng, "innkeeper")
    assert got and all(it.source == "read: item:notebook" for it in got)
    assert read_facts(eng) == []  # the player did not read it this time
    assert "живе джин" in eng._prep_npc("innkeeper").check_prefix()
    line = eng._utterance("innkeeper", "У лампі торговця живе джин.")
    eng._utterance("bard", "Ну й казки.")
    res = eng.challenge_line(line.id, "звідки він знає")
    assert res.verdict == "channel" and res.public.startswith("прочитав це")


def test_own_life_other_world_rendering(tmp_path):
    eng, _ = engine(tmp_path)
    eng.facts.add_canon("Гравець вважає: джини живуть у лампах.",
                        knowers=[(PLAYER, "told", knowledge.OWN_LIFE_OTHER_WORLD)])
    eng.facts.add_canon("Old belief.", knowers=[(PLAYER, "told", knowledge.OWN_LIFE)])
    lines = eng.ctx.knowledge_lines(eng.deriver.derive(PLAYER, eng.scene.time))
    assert "- Гравець вважає: джини живуть у лампах. (з власного життя, з іншого світу)" in lines
    assert "- Old belief. (from your own life)" in lines  # old saves render as before
    kinds = {it.text: it.kind for it in knowledge.items_for(eng, PLAYER)}
    assert kinds["Гравець вважає: джини живуть у лампах."] == knowledge.BACKGROUND


def test_package_knows_get_other_world_source(tmp_path):
    from app import newgame
    from app.game import Game
    from app.stacks import fake_stack

    text = ("version: 1\nworld: witcher\nplayer:\n  description: Інженер.\n  knows:\n"
            "    - Джини живуть у лампах.\nstart:\n  place: ринок\n  situation: Ринок.\n")
    stack = fake_stack()
    g = Game(lambda new: newgame.open_package(stack, newgame.parse(text), root=tmp_path,
                                              canon_db=False), pace=0.0)
    src = {r[0] for r in g.eng.conn.execute(
        "SELECT k.source FROM facts f JOIN fact_knowers k ON k.fact_id=f.id "
        "WHERE f.content LIKE '%Джини живуть%'")}
    assert src == {"own life, from another world"}


# -- the turn loop -------------------------------------------------------------------------------
def _turn_script(*reader):
    return {"narrator": ["N.", "N2."], "npc": ["Ага."], "extractor": [diff(), diff()],
            "reader": list(reader)}


def test_turn_reads_when_read_intent_yes(tmp_path):
    book(tmp_path)
    eng, prov = engine(tmp_path, _turn_script(TERMS, READER_OK), {"read_intent": True})
    give(eng, content={"file": "book.txt"})
    eng.turn("*відкриваю нотатник і шукаю про джинів*", speakers=["innkeeper"])
    assert read_facts(eng)
    narr = [m for model, m in prov.calls if model == "narrator"]
    assert narr and "У лампі торговця живе джин" in narr[0][-1]["content"]
    asked = [q.tag for _, qs in eng.judge.inner.asked for q in qs.values()]
    assert "read_intent" in asked


def test_turn_skips_read_intent_without_content_items(tmp_path):
    eng, prov = engine(tmp_path, _turn_script(), {"read_intent": True})
    give(eng)  # an item without content
    eng.turn("*читаю нотатник*", speakers=["innkeeper"])
    asked = [q.tag for _, qs in eng.judge.inner.asked for q in qs.values()]
    assert "read_intent" not in asked
    assert not [m for m, _ in prov.calls if m == "reader"]


def test_turn_no_read_when_intent_no(tmp_path):
    book(tmp_path)
    eng, prov = engine(tmp_path, _turn_script(), {"read_intent": False})
    give(eng, content={"file": "book.txt"})
    eng.turn("Добрий день.", speakers=["innkeeper"])
    assert read_facts(eng) == [] and not [m for m, _ in prov.calls if m == "reader"]
