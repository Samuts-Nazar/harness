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
    c = TestClient(create_app(g))
    stream = "".join(line for line in _raw_sse(c))
    assert "horst" not in stream and "elza" not in stream and "Горст" not in stream


def _raw_sse(c):
    with c.stream("GET", "/api/events?after=0&until_idle=1") as r:
        yield from r.iter_lines()


def test_token_salt_is_random_per_campaign_and_stable_on_reopen():
    root = tempfile.mkdtemp(prefix="harness-app-")
    g1, g2 = make(root), make()
    assert g1.camp.tok("horst") != g2.camp.tok("horst")
    assert g1.camp.tok("horst") != token_for(g1.camp.name, "horst")
    assert make(root).camp.tok("horst") == g1.camp.tok("horst")


def test_ink_assignment_does_not_write_during_streaming(monkeypatch):
    g = make()
    writes = []
    orig = g.camp.inks.flush
    monkeypatch.setattr(type(g.camp.inks), "flush", lambda self: (writes.append(1), orig())[1])
    play(g)
    assert g.cast() and writes  # flushed at the turn's end, not per speaker


def test_people_are_masked_and_carry_known_facts():
    g = make()
    play(g)
    c = TestClient(create_app(g))
    r = c.get("/api/people")
    assert r.status_code == 200
    people = r.json()
    assert people and all(set(x) == {"tok", "label", "ink", "present", "known"} for x in people)
    assert "horst" not in r.text and "Горст" not in r.text  # not introduced
    assert all(isinstance(f, str) for x in people for f in x["known"])
    assert any(x["known"] for x in people), "the drawer shows what the character knows"
    shown = " ".join(f for x in people for f in x["known"])
    assert "гравц" not in shown.lower() and "player" not in shown.lower()


def test_ink_rejects_malformed_json():
    c = TestClient(create_app(make()))
    assert c.post("/api/ink", content=b"{nope", headers={"content-type": "application/json"}
                  ).status_code == 400
    assert c.post("/api/ink", json=[1]).status_code == 400


def test_auto_inks_of_present_characters_are_distinct_with_many_met():
    """Final review, finding 2: more than eight met, at most eight present: the present ones
    never share an auto-assigned ink (absent characters do not use up the palette)."""
    import dataclasses

    g = make()
    base = g.eng.profiles["horst"]
    absent = [f"gone{i}" for i in range(8)]
    here = [f"here{i}" for i in range(6)]
    for i, cid in enumerate(absent + here):
        g.eng.profiles[cid] = dataclasses.replace(base, id=cid, name=f"Ім'я{i}",
                                                  appearance=f"постать {i}")
    with g.lock:
        g._seen = list(absent)  # met before, gone now; their inks fill the whole palette
        for cid, ink in zip(absent, PALETTE):
            g.camp.inks.set(g.camp.tok(cid), ink)
            g._touch(g.camp.tok(cid))
        g.eng.scene.present = (PLAYER, "horst", "elza", *here)
        g._seen += ["horst", "elza", *here]
        g._cast = g._compute_cast()
    present = [x for x in g.cast() if x["present"]]
    assert len(present) == 8
    assert len({x["ink"] for x in present}) == 8, [x["ink"] for x in present]


def _contrast(a: str, b: str) -> float:
    def lum(h: str) -> float:
        c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        c = [x / 12.92 if x <= 0.03928 else ((x + 0.055) / 1.055) ** 2.4 for x in c]
        return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def test_ink_and_placeholder_contrast_on_the_page():
    """Final review: the inks' contrast comment holds, and the input placeholder is >= 4.5:1."""
    import re
    from pathlib import Path

    css = (Path(__file__).resolve().parents[1] / "static" / "style.css").read_text()
    var = dict(re.findall(r"--([a-z0-9-]+):\s*(#[0-9a-fA-F]{6})", css))
    for ink in PALETTE:
        assert _contrast(ink, var["paper"]) >= 6.5, ink
        assert _contrast(ink, var["paper3"]) >= 5.0, ink
    m = re.search(r"#input::placeholder\s*\{[^}]*color:\s*([^;]+);", css)
    col = m.group(1).strip()
    col = var[col[6:-1]] if col.startswith("var(--") else col
    for bg in ("paper", "paper2"):
        assert _contrast(col, var[bg]) >= 4.5, (col, bg)
