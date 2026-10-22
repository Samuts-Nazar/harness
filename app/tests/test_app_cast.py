"""Character tokens, inks and the cast endpoint (no network)."""
from __future__ import annotations

import tempfile

import pytest
from starlette.testclient import TestClient

from app import campaigns
from app.campaigns import open_campaign
from app.game import Game
from app.inks import PALETTE, assign_ink, token_for
from app.server import create_app
from app.stacks import fake_stack
from harness.director import NEXT_TAG
from harness.models import PLAYER


@pytest.fixture(autouse=True)
def _no_local_character_file(monkeypatch, tmp_path):
    monkeypatch.setattr(campaigns, "DATA_FILE", tmp_path / "missing.md")


def make(root=None, floors=("horst", "elza", "player")) -> Game:
    stack = fake_stack()
    stack.judge.rules["director_narration"] = False
    if floors:
        stack.judge.rules[NEXT_TAG] = list(floors)
    root = root or tempfile.mkdtemp(prefix="harness-app-")
    return Game(lambda new: open_campaign(stack, root=root, new=new), pace=0.0)


def play(g: Game, text="Що кажете?") -> None:
    g.start_turn(text)
    g.wait_idle(20)


def test_cast_hides_real_ids_and_unlearned_names():
    g = make()
    play(g)
    c = TestClient(create_app(g))
    r = c.get("/api/cast")
    assert r.status_code == 200
    cast = r.json()
    assert {x["tok"] for x in cast} >= {g.camp.tok("horst"), g.camp.tok("elza")}
    raw = r.text
    assert "horst" not in raw and "elza" not in raw
    assert "Горст" not in raw and PLAYER not in {x["tok"] for x in cast}
    assert all(set(x) == {"tok", "label", "ink", "present"} for x in cast)
    assert all(x["ink"] in PALETTE and x["label"] for x in cast)


def test_token_and_ink_stable_when_name_learned():
    g = make()
    play(g)
    tok = g.camp.tok("horst")
    before = next(x for x in g.cast() if x["tok"] == tok)
    assert before["label"] != "Горст"
    g.eng.names.learn(PLAYER, "horst", how="introduced", scene=g.eng.scene, source="horst")
    g.eng.ctx  # noqa: B018
    g._cast = g._compute_cast()  # what the end of the next turn does
    after = next(x for x in g.cast() if x["tok"] == tok)
    assert after["label"] == "Горст"
    assert after["tok"] == before["tok"] and after["ink"] == before["ink"]
    assert token_for("a", "horst") == token_for("a", "horst") != token_for("b", "horst")
    assert len(token_for("a", "horst")) == 8


def test_auto_ink_distinct_then_reuses_least_recent():
    toks = [f"t{i}" for i in range(10)]
    inks: dict[str, str] = {}
    recency: list[str] = []
    for i, t in enumerate(toks):
        others = [x for x in toks if x != t]
        inks[t] = assign_ink(others, inks, recency)
        recency.append(t)
        if i < 8:
            assert inks[t] not in [inks[x] for x in toks[:i]]
    assert len(set(inks[t] for t in toks[:8])) == 8
    # the 9th reused the colour of the least recently active (t0), the 10th that of t1
    assert inks["t8"] == inks["t0"] and inks["t9"] == inks["t1"]
    # a token that spoke again is no longer the least recent
    recency2 = [t for t in toks[:8] if t != "t0"] + ["t0"]
    only8 = {t: inks[t] for t in toks[:8]}
    assert assign_ink(toks[:8], only8, recency2) == only8["t1"]


def test_ink_change_persists_across_reopen():
    root = tempfile.mkdtemp(prefix="harness-app-")
    g = make(root)
    play(g)
    c = TestClient(create_app(g))
    tok = g.camp.tok("horst")
    other = next(p for p in PALETTE if p != next(x["ink"] for x in g.cast() if x["tok"] == tok))
    with c.stream("GET", "/api/events?until_idle=1") as _:
        pass
    assert c.post("/api/ink", json={"tok": tok, "ink": other}).json() == {"ok": True}
    assert any(e["type"] == "ink" and e["tok"] == tok and e["ink"] == other
               for e in g.events_after(0))
    assert c.post("/api/ink", json={"tok": "nope", "ink": other}).status_code == 404
    assert c.post("/api/ink", json={"tok": tok, "ink": "red"}).status_code == 400
    g2 = make(root)
    assert next(x for x in g2.cast() if x["tok"] == tok)["ink"] == other
    assert next(x for x in g2.cast() if x["tok"] == tok)["label"]


def test_events_and_transcript_carry_tokens_not_ids():
    g = make()
    play(g)
    evs = g.events_after(0)
    for e in evs:
        if e["type"] in ("speaker", "word", "npc_act"):
            assert "who" not in e and "name" not in e and e["tok"]
    sp = [e for e in evs if e["type"] == "speaker"]
    assert sp and all(e["label"] and e["label"] != "horst" for e in sp)
    npc = [t for t in g.transcript if t["kind"] == "npc"]
    assert npc and all("who" not in t and "name" not in t and t["tok"] and t["label"] for t in npc)
    rebuilt = [t for t in g.camp.transcript() if t["kind"] == "npc"]
    assert [(t["tok"], t["label"]) for t in rebuilt] == [(t["tok"], t["label"]) for t in npc]
    assert "horst" not in str(g.state()["transcript"])
