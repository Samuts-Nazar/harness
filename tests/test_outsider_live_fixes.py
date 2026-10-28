"""Fixes for the problems the outsider live check found (reports/outsider/SUMMARY.md, 1-4 and 8).
Fake providers and judges; invented texts only. The tests on the real «Кров ельфів» store
(be.db) skip when it is absent."""
from __future__ import annotations

import json
import pathlib

import pytest

from canon_fixture import make_store
from conftest import diff, fact, make_engine
from harness import readable
from harness.canon.play import CanonPlay, name_form
from harness.canon.retrieve import Canon
from harness.director import NOBODY
from harness.extractor import validate_diff
from harness.judge import FakeJudge, default_fake_judge
from harness.models import EQUIPMENT, INVENTORY, PLAYER, SCENE_ENTRY, CharacterProfile, Scene
from harness.pipeline import Engine, ModelConfig
from harness.portrait import parse_portrait
from harness.providers import FakeProvider
from harness.scene_cast import SAME_TAG, SceneCast
from harness.state import StateChange

ROOT = pathlib.Path(__file__).resolve().parents[1]
_CANDIDATES = [ROOT / "campaigns/canon/be.db",
               pathlib.Path("/home/cock/projects/harness/campaigns/canon/be.db")]
BE = next((p for p in _CANDIDATES if p.is_file()), None)
needs_be = pytest.mark.skipif(BE is None, reason="local canon store be.db is absent")
LOOK = "жінка в чорно-білому, з чорними кучерями"   # Yennefer's portrait look
NENNEKE = "огрядна літня жриця в білому"


# -- 1. a present person described without a name is no walk-in -----------------------------------
def _cast_engine(lister, rules=None, look=LOOK, nenneke=False):
    profiles = [CharacterProfile(PLAYER, "Ілько", "Чужинець.", appearance="бородань в окулярах"),
                CharacterProfile("yennefer", "Йеннефер", "A sorceress.", appearance=look),
                CharacterProfile("nenneke", "Неннеке", "A priestess.", appearance=NENNEKE)]
    judge = FakeJudge({"director_narration": True, "director_next": NOBODY, **(rules or {})})
    prov = FakeProvider(script={"narrator": ["Жінка в чорно-білій сукні дивиться на вас."],
                                "npc": [], "extractor": [*lister, "none", diff()]})
    present = (PLAYER, "yennefer", "nenneke") if nenneke else (PLAYER, "yennefer")
    eng = Engine(prov, profiles, Scene("храм Мелітеле", present, time=0),
                 models=ModelConfig(), judge=judge, narration="prose", record_language=None)
    eng.scene_cast = SceneCast(None, culture="northern")
    return eng, judge


def _walkins(eng):
    return [c for c in eng.scene.present if c.startswith("npc_walkin")]


def test_present_person_by_her_look_admits_no_walkin():
    eng, _ = _cast_engine([LOOK])
    eng.turn("Підводжуся з землі.")
    assert _walkins(eng) == [] and set(eng.scene.present) == {PLAYER, "yennefer"}
    # the brief's case: the narration's «жінка в чорно-білій сукні» is her (typed choice)
    eng, _ = _cast_engine(["жінка в чорно-білій сукні"], {SAME_TAG: "yennefer"})
    eng.turn("Підводжуся з землі.")
    assert _walkins(eng) == []
    assert not [e for e in eng.log.active([SCENE_ENTRY]) if e.payload["character"] != PLAYER
                and e.payload["character"] != "yennefer"]


def test_present_person_in_other_words_found_by_the_typed_judgment():
    """The narrator's words share nothing with her label: the batched choice decides."""
    eng, judge = _cast_engine(["чарівниця з фіалковими очима"], {SAME_TAG: "yennefer"})
    eng.turn("Підводжуся з землі.")
    assert _walkins(eng) == []
    asked = [q for _, qs in judge.asked for q in qs.values() if q.tag == SAME_TAG]
    assert asked and "yennefer" in asked[0].options and "new" in asked[0].options
    assert any(n["kind"] == "scene_cast_same_person" for n in eng.devlog)
    # a different person stays a passer-by (the judgment's default: someone else)
    eng2, _ = _cast_engine(["худий хлопчик-посильний"])
    eng2.turn("Підводжуся з землі.")
    assert len(_walkins(eng2)) == 1


@pytest.mark.parametrize("mention", ["молода жриця в білому", "жриця в білому фартусі",
                                     "стара жінка", "жінка з кошиком", "жінка в чорній сукні"])
def test_real_new_people_next_to_present_ones_are_admitted(mention):
    """Generic words («жриця», «жінка», «в білому») never merge a newcomer with Nenneke or
    Yennefer: only all of a label's distinctive words do (the judgment's default: someone else)."""
    eng, _ = _cast_engine([mention], nenneke=True)
    eng.turn("Озираюся.")
    assert len(_walkins(eng)) == 1, mention


def test_same_look_rule():
    from harness.scene_cast import _same_look
    assert _same_look("огрядна літня жриця в білому", NENNEKE)
    assert _same_look("огрядну жрицю в білому", NENNEKE)        # inflected, generic words aside
    assert not _same_look("молода жриця в білому", NENNEKE)
    assert not _same_look("жриця в білому фартусі", NENNEKE)
    assert _same_look("жінка з чорними кучерями в чорно-білому", LOOK)
    assert not _same_look("жінка в чорно-білій сукні", LOOK)     # left to the judgment


def test_missing_same_person_judgment_admits():
    from harness.judge import JudgeError

    def down(q, state):
        raise JudgeError("no judge")
    eng, _ = _cast_engine(["чарівниця з фіалковими очима"], {SAME_TAG: down})
    eng.turn("Підводжуся з землі.")
    assert len(_walkins(eng)) == 1


def test_the_old_misspelt_label_was_the_cause():
    """With her label a name form (the old «Йеннфер»), the same mention became a new woman."""
    eng, _ = _cast_engine([LOOK], look="Йеннфер")
    eng.turn("Підводжуся з землі.")
    assert len(_walkins(eng)) == 1


# -- 2. a canon person's label is a description, never a name form -------------------------------
def _store_with_misspelt_alias():
    con, _ = make_store()
    con.execute("INSERT INTO canon_alias VALUES ('char:mirko','Мірку')")   # a declined name form
    con.execute("INSERT INTO canon_alias VALUES ('char:mirko','мірко-мандрівник')")
    con.execute("INSERT INTO canon_alias VALUES ('char:mirko','Мирко')")   # a misspelling
    con.commit()
    return Canon(con)


def test_name_form_rule():
    assert name_form("Йеннфер", "Йеннефер") and name_form("йеннефер", "Йеннефер")
    assert name_form("Дальку", "Далька") and name_form("ґеральте", "Ґеральт")
    assert not name_form("бургомістр", "Велерад") and not name_form("біловолосий", "Ґеральт")


def test_profile_label_never_an_alias_name_form():
    from harness.canon.api import CanonCampaign
    play = CanonPlay(_store_with_misspelt_alias(), CanonCampaign(start_t=0, place=None, offset=0))
    p = play.profile_for("char:mirko")
    assert p.name == "Мірко" and p.appearance == ""   # no describing alias: no label from a name
    assert play.profile_for("char:mirko", look=LOOK).appearance == LOOK  # the portrait's look
    assert play.profile_for("char:bart").appearance == "корчмар"        # describing aliases stay
    assert play.profile_for("char:yarosh").appearance == "староста"


def test_portrait_look_parsed():
    base = {"id": "p", "character": "c", "name": "N", "phase": "x", "core": "y",
            "stances": [{"id": "s", "rung": ["stranger"], "does": "d", "sounds": "s"}],
            "hidden": "h", "leaks": [], "voice": "v", "never": "n"}
    assert parse_portrait(base).look == ""
    assert parse_portrait({**base, "look": f"  {LOOK} "}).look == LOOK


@needs_be
def test_ellander_yennefer_label_has_no_name_form(tmp_path, monkeypatch):
    from app import newgame
    from app.game import Game
    from app.newgame import parse
    from app.stacks import fake_stack
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)
    monkeypatch.delenv("HARNESS_CANON_DB_BE", raising=False)
    fix = ROOT / "app" / "tests" / "fixtures" / "outsider_ellander.yaml"
    stack = fake_stack()
    pkg = parse(fix.read_text(encoding="utf-8"))
    g = Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=BE), pace=0.0)
    eng = g.eng
    for cid in ("yennefer", "nenneke", "ciri"):
        label = eng.profiles[cid].appearance
        assert label and eng.names.hidden(cid)
        for w in label.split():
            assert not name_form(w, eng.profiles[cid].name), (cid, label)
        assert "Йенн" not in label and "Ненн" not in label and "Цір" not in label
    assert eng.profiles["yennefer"].appearance == LOOK
    assert eng.names.ref(PLAYER, "yennefer") == LOOK


def test_no_store_stand_in_keeps_the_portrait_look(tmp_path, monkeypatch):
    from app import newgame
    from app.game import Game
    from app.newgame import parse
    from app.stacks import fake_stack
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)
    monkeypatch.delenv("HARNESS_CANON_DB_BE", raising=False)
    fix = ROOT / "app" / "tests" / "fixtures" / "outsider_ellander.yaml"
    stack = fake_stack()
    pkg = parse(fix.read_text(encoding="utf-8"))
    g = Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=False), pace=0.0)
    assert g.eng.profiles["yennefer"].appearance == LOOK
    assert g.eng.names.ref(PLAYER, "yennefer") == LOOK


# -- 3. containers through the extractor ---------------------------------------------------------
def _pack(eng):
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "рюкзак", True,
                                       id="item:рюкзак", location="worn"))
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "ноутбук", True,
                                       id="item:ноутбук", location="in:item:рюкзак"))
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "ліхтарик", True,
                                       id="item:ліхтарик", location="in:item:рюкзак"))


def _ch(op, item, iid, **kw):
    return {"character": PLAYER, "category": "inventory", "op": op, "item": item, "id": iid,
            "observable": True, "source": "player", **kw}


TURN2 = "Знімаю рюкзак, розстібаю його, дістаю ноутбук і відкриваю свої нотатки про духа лампи."


def _validate(eng, changes, text=TURN2):
    return validate_diff(json.loads(diff(fact("f", "player"), changes=changes)),
                         present=eng.scene.present, sources={"player", "narration"},
                         state=eng.live.snapshot(), characters=set(eng.scene.present),
                         texts={"player": text}, fuzzy=True)


def test_remove_is_never_rewritten_nor_dropped():
    """Consumed, broken, burned or thrown items stay `remove` and are removed, also next to an
    open or a move of their container (review round 1: no text matching, no rewrite)."""
    probes = [
        ("Дістаю з рюкзака ліхтарик і розбиваю його об камінь.",
         (_ch("remove", "ліхтарик", "item:ліхтарик"),)),
        ("Розстібаю рюкзак і викидаю ліхтарик у річку.",
         (_ch("open", "рюкзак", "item:рюкзак"), _ch("remove", "ліхтарик", "item:ліхтарик"))),
        ("Знімаю рюкзак і спалюю ліхтарик у багатті.",
         (_ch("move", "рюкзак", "item:рюкзак", location="on:ground"),
          _ch("remove", "ліхтарик", "item:ліхтарик"))),
        ("Дістаю батончик і з'їдаю його.", (_ch("remove", "ліхтарик", "item:ліхтарик"),)),
    ]
    for text, changes in probes:
        eng, _ = make_engine({}, item_ids=True)
        _pack(eng)
        d = _validate(eng, changes, text=text)
        assert not d.dropped, text
        assert ("remove", "ліхтарик") in [(c.op, c.item) for c in d.changes], text
        for c in d.changes:
            eng._apply_change(c, eng.log.active()[-1])
        assert (INVENTORY, "ліхтарик") not in eng.live.snapshot()[PLAYER], text


def test_take_out_opens_the_bag_and_is_observed_once():
    eng, _ = make_engine({}, item_ids=True)
    _pack(eng)
    d = _validate(eng, (_ch("move", "рюкзак", "item:рюкзак", location="on:ground"),
                        _ch("move", "ноутбук", "item:ноутбук", location="in_hand")))
    assert [(c.op, c.item, c.location) for c in d.changes] == [
        ("move", "рюкзак", "on:ground"), ("open", "рюкзак", None),
        ("move", "ноутбук", "in_hand")]
    for c in d.changes:
        eng._apply_change(c, eng.log.active()[-1])
    snap = eng.live.snapshot()[PLAYER]
    assert snap[(INVENTORY, "ноутбук")].location == "in_hand" and snap[(INVENTORY, "рюкзак")].open
    seen = [f.content for f in eng.facts.visible_to("innkeeper", eng.scene.time)]
    assert sum("ліхтарик" in x for x in seen) == 1 and sum("ноутбук" in x for x in seen) == 1


def test_words_alone_open_nothing():
    """«дістаюся до храму» (or any text) opens no bag: only a move of an item inside does."""
    eng, _ = make_engine({}, item_ids=True)
    _pack(eng)
    d = _validate(eng, (_ch("move", "рюкзак", "item:рюкзак", location="on:ground"),),
                  text="Дістаюся до храму й ставлю рюкзак на землю.")
    assert [c.op for c in d.changes] == ["move"]
    # a move of an item that is not inside the bag opens nothing either
    eng.apply_state_change(StateChange(PLAYER, INVENTORY, "add", "ніж", True, id="item:ніж",
                                       location="worn"))
    d = _validate(eng, (_ch("move", "ніж", "item:ніж", location="in_hand"),),
                  text="Дістаю ніж.")
    assert [c.op for c in d.changes] == ["move"]


def test_corrected_form_and_implicit_open():
    eng, _ = make_engine({}, item_ids=True)
    _pack(eng)
    # the corrected diff the prompt asks for: move the pack, open it, move the laptop out
    d = _validate(eng, (_ch("move", "рюкзак", "item:рюкзак", location="on:ground"),
                        _ch("open", "рюкзак", "item:рюкзак"),
                        _ch("move", "ноутбук", "item:ноутбук", location="in_hand")))
    assert [c.op for c in d.changes] == ["move", "open", "move"] and not d.dropped
    # a move out of a closed container alone opens it first
    d = _validate(eng, (_ch("move", "ноутбук", "item:ноутбук", location="in_hand"),))
    assert [(c.op, c.item) for c in d.changes] == [("open", "рюкзак"), ("move", "ноутбук")]


def test_extractor_prompt_explains_containers():
    eng, _ = make_engine({}, item_ids=True)
    _pack(eng)
    p = eng.ctx.extractor(eng.scene, [("player", TURN2)])[-1]["content"]
    assert '"open"' in p and 'never a "remove"' in p and '"in_hand"' in p
    old, _ = make_engine({})
    assert '"open"' not in old.ctx.extractor(old.scene, [("player", "x")])[-1]["content"]


# -- 4. the reader's request is the lookup topic -------------------------------------------------
NOTES = ("Нотатки до гри.\nДух лампи звуть Ормаз.\nПрокидається, якщо лампу потерти.\n"
         "Боїться солоної води.\nСвітить зеленим поруч із брехнею.")


@pytest.mark.parametrize("turn,item,topic", [
    (TURN2, "ноутбук", "про духа лампи"),
    ("Гляну в нотатник, що там про джинів.", "нотатник", "про джинів"),
    ("*читаю нотатник*", "нотатник", "читаю нотатник"),
    ("Ну?", "нотатник", "Ну?"),                                   # nothing to pick: the whole turn
    # review round 1 probes
    ("Дивлюсь, що там у файлі про духів, і питаю її про місто.", "ноутбук", "про духів"),
    ("дивлюсь що там у файлі про духів і питаю її про місто", "ноутбук", "про духів"),
    ("Запитую її про Цірі й заглядаю в ноутбук.", "ноутбук",
     "Запитую її про Цірі й заглядаю в ноутбук."),              # «про» is talk: the whole turn
    ("Заглядаю в щоденник, що там написано про перевал.", "щоденник", "про перевал"),
    ("Шукаю в ноутбуці рецепт зілля.", "ноутбук", "Шукаю в ноутбуці рецепт зілля"),
    ("Хочу знайти в записнику адресу.", "записник", "Хочу знайти в записнику адресу"),
    ("Відкриваю ноутбук.", "ноутбук", "Відкриваю ноутбук."),    # no topic: the whole turn
    # quoted speech is no lookup: «про» inside it is ignored
    ("Кажу: «Розкажіть про храм», і гортаю нотатки про перевал.", "нотатки", "про перевал"),
    ("Кажу їй «зараз гляну про вас», і усміхаюся.", "ноутбук",
     "Кажу їй, і усміхаюся."),
])
def test_lookup_topic(turn, item, topic):
    assert readable.lookup_topic(turn, item) == topic


def test_lookup_topic_short_item_name_needs_a_whole_word():
    # a name under four letters is never matched; a longer one only as a whole word (+ endings)
    assert readable.lookup_topic("Ніжно торкаюся її руки, а потім про дорогу.", "ніж") == \
        "Ніжно торкаюся її руки, а потім про дорогу."
    assert readable.lookup_topic("Листаю книжку про трави.", "лист") == \
        "Листаю книжку про трави."
    assert readable.lookup_topic("Беру лист про трави.", "лист") == "про трави"


def test_read_turn_reader_gets_the_topic_and_six_records(tmp_path):
    judge = default_fake_judge()
    judge.rules.update({"read_duration": "minutes", "read_intent": True})
    recs = [f"Запис {i}: дух лампи Ормаз." for i in range(8)]
    reader = json.dumps({"found": True, "text": "Дух лампи звуть Ормаз.", "records": recs},
                        ensure_ascii=False)
    eng, prov = make_engine({"narrator": ["N.", "N2."], "npc": ["Ага."],
                             "extractor": [diff(), diff()], "reader": [reader]},
                            judge=judge, campaign_dir=tmp_path, item_ids=True)
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "ноутбук", True,
                                       id="item:ноутбук", location="in_hand"))
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("inventory_meta", json.dumps({"item:ноутбук": {"content": NOTES}},
                                                       ensure_ascii=False)))
    res = eng.turn(TURN2, speakers=["innkeeper"])
    assert res.read is not None and res.read.found
    msgs = [m for model, m in prov.calls if model == "reader"][-1]
    user, system = msgs[-1]["content"], msgs[0]["content"]
    assert "про духа лампи" in user
    for verb in ("Знімаю", "розстібаю", "дістаю", "рюкзак"):
        assert verb not in user, verb
    assert "only the topic" in system and "no word of any other language" in system
    assert len(res.read.records) == 6 == readable.MAX_RECORDS
    rows = eng.conn.execute("SELECT COUNT(*) FROM fact_knowers WHERE source = ?",
                            ("read: item:ноутбук",)).fetchone()[0]
    assert rows == 6
    ev = eng.log.get(res.read.event_id)
    assert ev.payload["request"] == "про духа лампи"


# -- 8. the panel shows one chip per text --------------------------------------------------------
def test_panel_shows_one_chip_per_text(tmp_path, monkeypatch):
    from app import newgame
    from app.game import Game
    from app.newgame import parse
    from app.stacks import fake_stack
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)
    fix = ROOT / "app" / "tests" / "fixtures" / "outsider_ellander.yaml"
    stack = fake_stack()
    pkg = parse(fix.read_text(encoding="utf-8"))
    g = Game(lambda new: newgame.open_package(stack, pkg, root=tmp_path, canon_db=False), pace=0.0)
    g.eng.apply_state_change(StateChange(PLAYER, "appearance", "add", "окуляри", True))
    texts = [c["text"] for c in g._compute_panel()["chips"]]
    assert texts.count("окуляри") == 1


def test_unreadable_reader_answer_is_asked_once_more(tmp_path):
    judge = default_fake_judge()
    judge.rules.update({"read_duration": "minutes"})
    ok = json.dumps({"found": True, "text": "Дух лампи звуть Ормаз.",
                     "records": ["Дух лампи звуть Ормаз."]}, ensure_ascii=False)
    eng, prov = make_engine({"reader": ['{"found": true, "text": "Дух лампи', ok]},
                            judge=judge, campaign_dir=tmp_path, item_ids=True)
    eng.apply_state_change(StateChange(PLAYER, EQUIPMENT, "add", "ноутбук", True,
                                       id="item:ноутбук", location="in_hand"))
    with eng.conn:
        eng.conn.execute("INSERT OR REPLACE INTO campaign_meta (key, value) VALUES (?,?)",
                         ("inventory_meta", json.dumps({"item:ноутбук": {"content": NOTES}},
                                                       ensure_ascii=False)))
    res = readable.read(eng, PLAYER, "item:ноутбук", "про духа лампи")
    assert res.found and res.records == ["Дух лампи звуть Ормаз."]
    assert [n["kind"] for n in eng.devlog].count("reader_unparsed") == 1
    assert readable._parse_json('{"a": 1} і ще {текст}') == {"a": 1}
