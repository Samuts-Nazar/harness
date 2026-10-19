"""Task 14 app tests: names as knowledge in the feed, asterisk actions, "how does he know that?",
the character's looks from a local file (invented text here; the real file is never used)."""
from __future__ import annotations

import json
import tempfile

from starlette.testclient import TestClient

from app.campaigns import PLAYER_LOOK, open_campaign
from app.game import Game
from app.server import create_app
from app.stacks import LOOKS, fake_stack
from harness.models import ACTION, PLAYER

SHEET = "Invented test sheet. The character has golden eyes and black claws and a scar."


def make(stack=None, root=None, data_file=None) -> Game:
    stack = stack or fake_stack()
    root = root or tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: open_campaign(stack, root=root, new=new, data_file=data_file), pace=0.0)


def sheet(tmp_path):
    f = tmp_path / "char.md"
    f.write_text(SHEET, encoding="utf-8")
    return f


# -- names in the feed ----------------------------------------------------------------------------
def test_strangers_are_described_not_named_in_the_feed_until_they_say_who_they_are():
    g = make()
    g.start_turn("Добрий вечір.")
    g.wait_idle()
    t = g.transcript
    assert "Горст" not in t[0]["text"] and "Ельза" not in t[0]["text"], "the intro names nobody"
    npc = next(e for e in t if e["kind"] == "npc")
    assert npc["name"] == "Кремезний сивий чоловік" and isinstance(npc["event"], int)
    speaker = next(e for e in g.events_after(0) if e["type"] == "speaker")
    assert speaker["name"] == "Кремезний сивий чоловік"
    assert "Горст" not in json.dumps(g.state()["panel"], ensure_ascii=False)


def test_a_name_the_player_types_is_known_to_the_player():
    g = make()
    g.start_turn("Привіт, Горсте.")
    g.wait_idle()
    npc = next(e for e in g.transcript if e["kind"] == "npc")
    assert npc["name"] == "Горст"


# -- actions --------------------------------------------------------------------------------------
def test_asterisk_action_is_an_observable_action_and_the_text_is_kept_verbatim():
    g = make()
    text = "*стукаючи нігтями по столу* Ну?"
    g.start_turn(text)
    g.wait_idle()
    mine = [e for e in g.transcript if e["kind"] == "player"]
    assert mine[0]["text"] == text
    acts = [e for e in g.eng.log.active([ACTION]) if e.payload.get("actor") == PLAYER]
    assert [a.payload["text"] for a in acts] == ["стукаючи нігтями по столу"]
    assert set(acts[0].witnesses) >= {"horst", "elza"}
    g.eng.close()


def test_a_reopened_campaign_shows_the_verbatim_input_once():
    root = tempfile.mkdtemp(prefix="harness-app-")
    g = make(root=root)
    g.start_turn("*киваю* Так.")
    g.wait_idle()
    before = [dict(t) for t in g.transcript]
    g.eng.close()
    g2 = make(root=root)
    assert [t for t in g2.transcript if t["kind"] == "player"] == [
        t for t in before if t["kind"] == "player"]
    assert [t["text"] for t in g2.transcript if t["kind"] == "player"] == ["*киваю* Так."]


# -- how does he know that ------------------------------------------------------------------------
def test_challenge_endpoint_channel_and_no_channel():
    stack = fake_stack()
    g = make(stack)
    c = TestClient(create_app(g))
    c.post("/api/turn", json={"text": "Що сталося на млині?"})
    g.wait_idle()
    ev = next(e for e in g.transcript if e["kind"] == "npc")["event"]
    # the offline judge picks the first channel
    r = c.post("/api/challenge", json={"event": ev, "explanation": "звідки він знає"}).json()
    assert r["verdict"] == "channel" and r["public"] and r["detail"] and not r["regenerated"]
    assert c.post("/api/challenge", json={}).status_code == 400
    # now there is no channel: the line is regenerated and the feed shows the new text
    stack.judge.rules["knowledge_channel"] = "none"
    old = next(e for e in g.transcript if e["kind"] == "npc")["text"]
    r = c.post("/api/challenge", json={"event": ev, "explanation": "не міг знати"}).json()
    assert r["verdict"] == "no_channel" and r["regenerated"] and r["text"] != old
    now = next(e for e in g.transcript if e["kind"] == "npc")
    assert now["text"] == r["text"] and now["event"] == r["new_event"]
    assert c.get("/api/state").json()["transcript"][-1]["text"] == r["text"]


def test_challenge_is_refused_while_a_turn_runs():
    g = make()
    g.challenging = True
    c = TestClient(create_app(g))
    assert c.post("/api/challenge", json={"event": 1}).status_code == 409
    assert c.get("/api/knowledge").status_code == 409


def test_debug_knowledge_lists_each_character_with_sources():
    g = make()
    g.start_turn("Привіт.")
    g.wait_idle()
    c = TestClient(create_app(g))
    k = c.get("/api/knowledge").json()
    assert set(k) == {"player", "horst", "elza"}
    items = k["horst"]["items"]
    assert any(i["kind"] == "name" and i["how"] == "acquainted" for i in items)
    assert any(i["kind"] == "fact" and i["how"] == "told" for i in items)
    assert any(i["kind"] == "seen" and i["when_text"] for i in items)
    assert not any(i["kind"] == "name" and "Рагнар" in i["text"] for i in items)


# -- the character's looks --------------------------------------------------------------------------
def test_looks_from_the_character_file_become_live_state_and_npcs_perceive_them(tmp_path):
    stack = fake_stack()
    stack.judge.rules["salience"] = lambda q, st: "golden eyes" in " ".join(st)
    camp = open_campaign(stack, root=tmp_path / "c", new=True, data_file=sheet(tmp_path))
    eng = camp.engine
    state = {(e.category, e.item): e.observable for e in eng.live.of(PLAYER)}
    assert state[("appearance", "golden eyes")] is True
    assert state[("appearance", "black claws")] is True
    assert state[("appearance", "scars across the back")] is False
    assert state[("equipment", "steel sword")] is True and state[("injury", "old scar under the shirt")] is False
    seen = {f.content for f in eng.facts.visible_to("horst", eng.scene.time)}
    assert f"{eng.ctx.name(PLAYER)} has golden eyes" in seen and f"{eng.ctx.name(PLAYER)} has black claws" in seen
    assert not any("scars across the back" in s for s in seen), "hidden stays hidden"
    assert eng.profiles[PLAYER].appearance == LOOKS["label"]
    # salience decides who reacts: horst's next context carries it, without the player's name
    ctx = "\n".join(m["content"] for m in eng.ctx.character("horst", eng.scene))
    assert "You have just noticed" in ctx and "golden eyes" in ctx and "Рагнар" not in ctx
    assert LOOKS["label"] in ctx
    eng.close()


def test_looks_are_cached_so_a_new_campaign_does_not_pay_again(tmp_path):
    stack = fake_stack()
    f = sheet(tmp_path)
    for i in range(2):
        open_campaign(stack, root=tmp_path / "c", new=True, data_file=f, name=f"x{i}").engine.close()
    sheet_calls = [m for _, m in stack.provider.calls if "character sheet" in m[0]["content"]]
    assert len(sheet_calls) == 1 and list((tmp_path / "c").glob("traits-*.json"))
    assert SHEET in sheet_calls[0][1]["content"], "the file goes to the cheap model, once"


def test_without_a_character_file_the_scene_keeps_its_plain_seeds(tmp_path):
    stack = fake_stack()
    camp = open_campaign(stack, root=tmp_path / "c", new=True, data_file=tmp_path / "nope.md")
    items = {(e.category, e.item) for e in camp.engine.live.of(PLAYER)}
    assert items == {("equipment", "steel sword"), ("injury", "old scar under the shirt")}
    assert camp.engine.profiles[PLAYER].appearance == PLAYER_LOOK
    assert not [1 for _, m in stack.provider.calls if "character sheet" in m[0]["content"]]
    camp.engine.close()


def test_a_broken_answer_from_the_model_keeps_the_plain_seeds(tmp_path):
    from app.character import parse_traits

    stack = fake_stack()
    orig = stack.provider.complete
    stack.provider.complete = lambda model, m: ("not json" if "character sheet" in m[0]["content"]
                                                 else orig(model, m))
    camp = open_campaign(stack, root=tmp_path / "c", new=True, data_file=sheet(tmp_path))
    assert {e.item for e in camp.engine.live.of(PLAYER)} == {"steel sword",
                                                             "old scar under the shirt"}
    camp.engine.close()
    t = parse_traits(json.dumps({"label": "x", "observable": [
        {"category": "appearance", "item": "golden eyes"}, {"category": "mood", "item": "sad"},
        {"category": "appearance", "item": "y" * 200}, "junk"],
        "hidden": [{"category": "appearance", "item": "golden eyes"},
                   {"category": "injury", "item": "scar"}]}))
    assert t.observable == [("appearance", "golden eyes")] and t.hidden == [("injury", "scar")]
