"""Game packages (book UI task 5): the YAML a player brings from an external AI chat, its
validation with Ukrainian errors, the summary card, and a campaign built from it. Fake stack, no
network."""
from __future__ import annotations

import pathlib

import pytest
from starlette.testclient import TestClient

from app import newgame
from app.game import Game
from app.newgame import PackageError, parse, summary
from app.server import create_app
from app.stacks import fake_stack
from harness.models import PLAYER

ROOT = pathlib.Path(__file__).resolve().parents[2]
EXAMPLE = (ROOT / "docs" / "game_package_example.yaml").read_text(encoding="utf-8")
MINIMAL = """\
version: 1
world: witcher
player:
  description: Колишній найманець, що втомився від війни і шукає тихого кута.
"""
CANON = """\
version: 1
world: witcher
player:
  name: Збислав
  description: Мандрівний лютняр, що співає за вечерю і боїться собак.
  unbounded: true
start:
  canon: vidmak_A_tavern
limits:
  avoid: [катування]
"""


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)


def issues(text: str) -> list:
    with pytest.raises(PackageError) as e:
        parse(text)
    return e.value.issues


def fields(text: str) -> list[str]:
    return [i.field for i in issues(text)]


# -- parsing and validation ------------------------------------------------------------------

def test_minimal_package_is_valid_and_leaves_the_rest_to_the_world():
    pkg = parse(MINIMAL)
    assert pkg.warnings == []
    assert pkg.data["player"]["description"].startswith("Колишній найманець")
    s = summary(pkg)
    world = " ".join(s["world"])
    assert "Ім'я" in world and "Місце" in world and "Люди" in world
    assert any(x["label"] == "Персонаж" for x in s["set"])


def test_full_example_is_valid_without_warnings():
    pkg = parse(EXAMPLE)
    assert pkg.warnings == []
    d = pkg.data
    assert d["player"]["name"] == "Вереска" and d["start"]["place"] == "ринок"
    assert d["assistant"] == "on"          # YAML 1.1 reads `on` as true: accepted
    assert d["start"]["time"] == 8 * 60    # «ранок»
    assert len(d["start"]["who_is_here"]) == 2
    assert d["limits"]["avoid"] == ["сексуальне насильство", "жорстокість до дітей"]
    s = summary(pkg)
    labels = [x["label"] for x in s["set"]]
    for want in ("Персонаж", "Ім'я", "Старт", "Хто поруч", "Межі", "Тон"):
        assert want in labels, want
    assert "Вереска" in s["title"] or "ринок" in s["title"]


def test_a_fenced_block_pasted_from_a_chat_is_read():
    pkg = parse("Ось ваш файл:\n\n```yaml\n" + MINIMAL + "```\nГарної гри!")
    assert pkg.data["world"] == "witcher"


def test_unknown_field_gives_a_warning_and_is_kept_in_notes():
    pkg = parse(MINIMAL + "weather: туман\nplayer_extra: 1\n")
    assert [w.field for w in pkg.warnings] == ["weather", "player_extra"]
    assert "туман" in pkg.data["notes"]
    assert all(w.fix for w in pkg.warnings)
    long = parse(MINIMAL + "start:\n  who_is_here:\n    - role: корчмар\n      appearance: "
                 "кремезний лисий чоловік у шкіряному фартусі з великим черпаком у руці\n")
    assert [w.field for w in long.warnings] == ["start.who_is_here[1].appearance"]
    pkg2 = parse(MINIMAL + "  horse: сива кобила\n")
    assert pkg2.warnings[0].field == "player.horse"
    assert "сива кобила" in pkg2.data["notes"]


@pytest.mark.parametrize("text, field", [
    ("world: witcher\nplayer: {description: x}\n", "version"),
    ("version: 2\nworld: witcher\nplayer: {description: x}\n", "version"),
    ("version: 1\nworld: mars\nplayer: {description: x}\n", "world"),
    ("version: 1\nworld: witcher\n", "player"),
    ("version: 1\nworld: witcher\nplayer: {name: Ян}\n", "player.description"),
    (MINIMAL + "pace: turbo\n", "pace"),
    (MINIMAL + "canon: strict\n", "canon"),
    (MINIMAL + "outcomes: maybe\n", "outcomes"),
    (MINIMAL + "dialogue: chat\n", "dialogue"),
    (MINIMAL + "inks: {Ярош: red}\n", "inks.Ярош"),
    (MINIMAL + "start: {canon: no_such_moment}\n", "start.canon"),
    (MINIMAL + "start: {canon: vidmak_A_tavern, place: ринок}\n", "start"),
    (MINIMAL + "start: {time: '25:99'}\n", "start.time"),
    (MINIMAL + "start: {day: 0}\n", "start.day"),
    (MINIMAL + "start: {who_is_here: [{role: корчмар, knows_player: дуже}]}\n",
     "start.who_is_here[1].knows_player"),
    (MINIMAL + "limits: заборонено все\n", "limits"),
    (MINIMAL + "  unbounded: інколи\n", "player.unbounded"),
])
def test_bad_values_give_readable_errors(text, field):
    got = issues(text)
    assert field in [i.field for i in got], [i.__dict__ for i in got]
    for i in got:
        assert i.problem and i.fix
        assert any("а" <= ch <= "я" for ch in i.problem.lower())  # Ukrainian, for the player


def test_yaml_syntax_error_names_the_line():
    got = issues("version: 1\nworld: witcher\nplayer:\n  description: [не закрито\n")
    assert got[0].field == "файл" and "рядок" in got[0].problem


def test_not_a_mapping_and_empty_input():
    assert fields("") == ["файл"]
    assert fields("- просто\n- список\n") == ["файл"]


def test_outcomes_override_player_unbounded():
    pkg = parse(MINIMAL + "  unbounded: true\noutcomes: real\n")
    assert newgame.unbounded(pkg) is False
    assert any(w.field == "player.unbounded" for w in pkg.warnings)
    assert newgame.unbounded(parse(MINIMAL + "  unbounded: true\n")) is True
    assert newgame.unbounded(parse(MINIMAL + "outcomes: unbounded\n")) is True
    assert newgame.unbounded(parse(MINIMAL)) is False


# -- building campaigns ----------------------------------------------------------------------

def make(tmp_path, text=None):
    stack = fake_stack()
    first = parse(text) if text else None
    opener = newgame.opener(stack, root=tmp_path, fallback=lambda new: pytest.fail("fallback"))
    g = Game(opener if first is None else (lambda new: newgame.open_package(
        stack, first, root=tmp_path, canon_db=False)), pace=0.0)
    return g, stack


def test_canon_start_builds_a_playable_campaign(tmp_path):
    g, stack = make(tmp_path, CANON)
    eng = g.eng
    assert eng.scene.location == "корчма «Під Лисом»"
    assert eng.scene.time == 2 * 1440 + 20 * 60
    assert eng.profiles[PLAYER].name == "Збислав"
    assert eng.ctx.player_unlimited and eng.outcomes_on
    assert "npc_guard" in eng.scene.present and g.camp.world is not None
    assert "катування" in eng.ctx.intent
    g.start_turn("Сідаю біля стійки й прошу кухоль пива.")
    g.wait_idle(20)
    kinds = [t["kind"] for t in g.transcript]
    assert kinds[0] == "intro" and "narr" in kinds
    narr_calls = [m for _, m in stack.provider.calls if "narrator" in m[0]["content"]]
    assert narr_calls and "катування" in narr_calls[0][0]["content"]


def test_free_start_uses_the_map_npcgen_and_the_package_people(tmp_path):
    g, stack = make(tmp_path, EXAMPLE)
    eng = g.eng
    assert eng.scene.location == "ринок"
    assert eng.scene.time == 2 * 1440 + 8 * 60
    assert eng.profiles[PLAYER].name == "Вереска"
    assert not eng.ctx.player_unlimited and eng.outcomes_on
    npcs = [c for c in eng.scene.present if c != PLAYER]
    assert len(npcs) == 2
    looks = [eng.profiles[c].appearance for c in npcs]
    assert "огрядна жінка в червоній хустці" in looks
    for c in npcs:
        assert eng.profiles[c].core                      # npcgen: a whole person
        assert not eng.names.knows(c, PLAYER)            # knows_player: false
        assert not eng.names.knows(PLAYER, c)
    assert g.camp.world is not None and g.camp.world.here() == "market"
    assert g.camp.intro.startswith("Ранок третього дня")
    # the player's hidden traits stay hidden; what the sheet says is seeded as live state
    snap = eng.live.snapshot()[PLAYER]
    assert any(not obs for obs in snap.values())
    # one cheap call at most to fill the gaps (the looks), recorded
    # (the panel's display translation, made for every campaign, is not part of the start)
    setup = [c for c in g.camp.recorder.calls if c["role"] != "translator"]
    assert len(setup) <= 1 and setup[0]["role"].startswith("setup")
    # the preset ink of the cloth seller
    trader = next(c for c in npcs if "хустці" in eng.profiles[c].appearance)
    assert g.camp.inks.inks.get(g.camp.tok(trader)) == "#e8a87c"
    g.start_turn("*показую торговці гребінець* Ви знаєте цього хлопця?")
    g.wait_idle(20)
    kinds = [t["kind"] for t in g.transcript]
    assert kinds[:2] == ["intro", "player"] and {"narr", "npc"} & set(kinds[2:])  # the world answers


def test_minimal_package_starts_with_everything_decided_by_the_world(tmp_path):
    g, _ = make(tmp_path, MINIMAL)
    eng = g.eng
    assert eng.profiles[PLAYER].name                     # a name from the tables
    assert len([c for c in eng.scene.present if c != PLAYER]) >= 1
    assert g.camp.intro
    assert not eng.ctx.player_unlimited


def test_package_campaign_reopens_with_its_intent(tmp_path):
    g, stack = make(tmp_path, CANON)
    name = g.camp.name
    g.eng.close()
    opener = newgame.opener(stack, root=tmp_path, fallback=lambda new: pytest.fail("fallback"))
    camp = opener(False)
    assert camp.name == name and "катування" in camp.engine.ctx.intent
    assert camp.title == g.camp.title and camp.intro == g.camp.intro


def test_assistant_off_gives_no_suggestions(tmp_path):
    g, _ = make(tmp_path, MINIMAL + "assistant: off\n")
    assert g.camp.assistant is False
    g.start_turn("Озираюся.")
    g.wait_idle(20)
    assert not [e for e in g.events_after(0) if e["type"] == "suggestions"]


def test_classic_dialogue_from_the_package(tmp_path):
    g, _ = make(tmp_path, MINIMAL + "dialogue: classic\n")
    assert g.eng.dialogue == "classic"


def test_loose_canon_is_told_to_the_narrator(tmp_path):
    g, _ = make(tmp_path, CANON + "canon: loose\n")
    assert g.eng.canon_guard is None and "background" in g.eng.ctx.intent


# -- HTTP ------------------------------------------------------------------------------------

def server(tmp_path, monkeypatch):
    stack = fake_stack()
    from app.campaigns import open_campaign
    import app.campaigns as campaigns
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")
    fallback = lambda new: open_campaign(stack, root=tmp_path, new=new)  # noqa: E731
    g = Game(newgame.opener(stack, root=tmp_path, fallback=fallback), pace=0.0)
    g.open_package = lambda pkg: newgame.open_package(stack, pkg, root=tmp_path, canon_db=False)
    return g, TestClient(create_app(g))


def test_check_endpoint_returns_summary_or_errors(tmp_path, monkeypatch):
    _, c = server(tmp_path, monkeypatch)
    r = c.post("/api/package/check", json={"text": EXAMPLE})
    assert r.status_code == 200 and r.json()["ok"]
    assert r.json()["summary"]["set"]
    r = c.post("/api/package/check", json={"text": "version: 3\n"})
    body = r.json()
    assert r.status_code == 200 and not body["ok"]
    assert {"field", "problem", "fix"} <= set(body["errors"][0])


def test_start_endpoint_starts_the_package_game(tmp_path, monkeypatch):
    g, c = server(tmp_path, monkeypatch)
    old = g.camp.name
    r = c.post("/api/package/start", json={"text": "weather: 1\n"})
    assert r.status_code == 400 and r.json()["errors"]
    assert g.camp.name == old
    r = c.post("/api/package/start", json={"text": EXAMPLE})
    assert r.status_code == 200, r.text
    st = r.json()
    assert st["transcript"][0]["kind"] == "intro"
    assert st["transcript"][0]["text"].startswith("Ранок третього дня")
    assert g.camp.name != old
    # a restart of the app continues the package campaign
    st2 = c.get("/api/state").json()
    assert st2["title"] == st["title"]


# -- the instruction document for external AIs -----------------------------------------------

def test_instruction_examples_are_valid_and_the_full_one_is_the_example_file():
    import re
    doc = (ROOT / "docs" / "new_game_instruction.md").read_text(encoding="utf-8")
    blocks = re.findall(r"```yaml\n(.*?)```", doc, re.DOTALL)
    examples = [b for b in blocks if "..." not in b]  # the schema block has placeholders
    assert len(examples) == 3
    assert examples[0] == EXAMPLE
    for b in examples:
        assert parse(b).warnings == []
    # every canon start point is described in the document
    for cid in newgame.start_points():
        assert f"`{cid}`" in doc


# -- review fix round 1 ----------------------------------------------------------------------

@pytest.mark.parametrize("text", [
    MINIMAL + "extra: &a [*a]\n",
    MINIMAL + "inks: {a: &b [*b]}\n",
    "version: &a [*a]\nworld: witcher\nplayer: {description: x}\n",
    MINIMAL + "a: &a [x, x]\nb: &b [*a, *a]\nc: &c [*b, *b]\nd: [*c, *c]\n",  # billion laughs
])
def test_yaml_aliases_are_refused_with_a_readable_error(text):
    got = issues(text)
    assert got[0].field == "файл" and "посилання" in got[0].problem.lower()


def test_oversized_file_is_refused_before_parsing():
    got = issues(MINIMAL + "notes: |\n" + ("  " + "а" * 1000 + "\n") * 300)
    assert got[0].field == "файл" and "завеликий" in got[0].problem


def test_unknown_fields_and_notes_are_capped():
    big = MINIMAL + "extra: [" + ", ".join(["слово"] * 5000) + "]\n" + \
        "".join(f"x{i}: {'б' * 200}\n" for i in range(100))
    pkg = parse(big)
    assert len(pkg.data["notes"]) <= newgame.MAX_NOTES + 100


def test_notes_and_tone_may_be_lists():
    pkg = parse(MINIMAL + "tone: [похмуро, з гумором]\nnotes: [перше, друге]\n")
    assert pkg.data["tone"] == "похмуро; з гумором" and "перше" in pkg.data["notes"]


def test_endpoints_turn_any_parser_failure_into_a_file_issue(tmp_path, monkeypatch):
    _, c = server(tmp_path, monkeypatch)

    def boom(_text):
        raise RuntimeError("unexpected")
    monkeypatch.setattr(newgame, "parse", boom)
    r = c.post("/api/package/check", json={"text": MINIMAL})
    assert r.status_code == 200 and r.json()["errors"][0]["field"] == "файл"
    r = c.post("/api/package/start", json={"text": MINIMAL})
    assert r.status_code == 400 and r.json()["errors"][0]["field"] == "файл"


def test_limits_reach_npc_prompts(tmp_path):
    g, stack = make(tmp_path, EXAMPLE)
    assert "жорстокість до дітей" in g.eng.ctx.limits and "докладні тортури" in g.eng.ctx.limits
    assert "Ольдрих" not in g.eng.ctx.limits                     # not the whole intent
    g.start_turn("*показую торговці гребінець* Ви знаєте цього хлопця?")
    g.wait_idle(20)
    names = {p.name for c, p in g.eng.profiles.items() if c.startswith("npc_")}
    npc_calls = [m for _, m in stack.provider.calls
                 if any(m[0]["content"].startswith(f"You are {n}") for n in names)]
    assert npc_calls
    for m in npc_calls:
        assert "жорстокість до дітей" in m[0]["content"] and "докладні тортури" in m[0]["content"]


def test_classic_dialogue_survives_a_restart(tmp_path):
    g, stack = make(tmp_path, MINIMAL + "dialogue: classic\n")
    g.eng.close()
    camp = newgame.opener(stack, root=tmp_path, fallback=lambda new: pytest.fail("x"))(False)
    assert camp.engine.dialogue == "classic"


def test_player_knowledge_is_a_belief_not_world_truth(tmp_path):
    g, _ = make(tmp_path, EXAMPLE)
    texts = [r[0] for r in g.eng.conn.execute("SELECT content FROM facts")]
    rumour = [t for t in texts if "старого палацу" in t]
    assert rumour and all(t != "У місті кажуть, що біля старого палацу щось неладне і люди "
                          "туди не ходять уночі." for t in rumour)
    assert all("believes" in t for t in rumour)


def test_pointer_is_written_only_after_a_successful_build(tmp_path, monkeypatch):
    stack = fake_stack()
    newgame._pointer(tmp_path).write_text("old")
    monkeypatch.setattr(newgame, "_free_world", lambda *a: (_ for _ in ()).throw(RuntimeError()))
    with pytest.raises(RuntimeError):
        newgame.open_package(stack, parse(EXAMPLE), root=tmp_path, canon_db=False)
    assert newgame._pointer(tmp_path).read_text() == "old"


def test_the_game_stays_responsive_while_a_package_builds(tmp_path):
    import threading
    stack = fake_stack()
    g = Game(lambda new: newgame.open_package(stack, parse(MINIMAL), root=tmp_path,
                                              canon_db=False), pace=0.0)
    gate, entered = threading.Event(), threading.Event()

    def slow(pkg):
        entered.set()
        gate.wait(5)
        return newgame.open_package(stack, pkg, root=tmp_path, canon_db=False)
    g.open_package = slow
    t = threading.Thread(target=g.start_package, args=(parse(EXAMPLE),))
    t.start()
    assert entered.wait(5)
    got = []
    reader = threading.Thread(target=lambda: got.append(g.state()))
    reader.start()
    reader.join(2)
    assert got, "state() blocked while the new campaign was being built"
    gate.set()
    t.join(10)
    assert g.camp.intro.startswith("Ранок третього дня")


def test_a_huge_request_is_refused_readably(tmp_path, monkeypatch):
    _, c = server(tmp_path, monkeypatch)
    r = c.post("/api/package/check", json={"text": MINIMAL + "notes: " + "я" * 500_000 + "\n"})
    assert r.status_code == 200 and r.json()["errors"][0]["field"] == "файл"
    assert "завеликий" in r.json()["errors"][0]["problem"]
