from pathlib import Path

import pytest
import yaml

from harness.portrait import (
    Situation, PortraitError, load_portrait, select_stance, slice_text,
)


def stance(id, rung, **kw):
    d = {"id": id, "rung": rung, "does": "Does a thing.", "sounds": "Sounds flat."}
    d.update(kw)
    return d


def base(**kw):
    d = {
        "id": "p1", "character": "c1", "name": "Mira", "phase": "early",
        "core": "A careful ferrywoman.",
        "stances": [stance("s1", ["stranger"])],
        "switches": [{"id": "w1", "trigger": "Did the player help her?", "warmth": 0.2, "trust": 0.1}],
        "hidden": "Owes money.", "leaks": ["Glances at the purse."],
        "voice": "Short sentences.", "never": "Never begs.", "relations": {"c2": "ally"},
    }
    d.update(kw)
    return d


def write(tmp_path: Path, data) -> Path:
    p = tmp_path / "p.yaml"
    p.write_text(yaml.safe_dump(data, allow_unicode=True), encoding="utf-8")
    return p


def test_load_valid_portrait(tmp_path):
    p = load_portrait(write(tmp_path, base()))
    assert p.stances[0].rung == ("stranger",)
    assert p.switches[0].warmth == 0.2
    assert p.relations == {"c2": "ally"}


def test_missing_core_is_a_portrait_error(tmp_path):
    d = base()
    del d["core"]
    with pytest.raises(PortraitError) as e:
        load_portrait(write(tmp_path, d))
    assert e.value.field == "core"


def test_select_stance_prefers_matching_situation(tmp_path):
    d = base(stances=[
        stance("plain", ["stranger"]),
        stance("pub", ["stranger"], when={"audience": True}),
    ])
    p = load_portrait(write(tmp_path, d))
    assert select_stance(p, "stranger", Situation("self", True, "low")).id == "pub"
    assert select_stance(p, "stranger", Situation("self", False, "low")).id == "plain"


def test_select_stance_falls_back_down_the_ladder(tmp_path):
    d = base(stances=[stance("a", ["stranger"]), stance("b", ["close"])])
    p = load_portrait(write(tmp_path, d))
    sit = Situation("even", False, "low")
    assert select_stance(p, "ally", sit).id == "a"
    assert select_stance(p, "lover", sit).id == "b"
    assert select_stance(p, "enemy", sit).id == "a"


def test_slice_is_capped_and_trims_examples_first(tmp_path):
    long = " ".join(["word"] * 300)
    d = base(stances=[stance("s1", ["stranger"], does=long, examples=["Ex one.", "Ex two."])])
    p = load_portrait(write(tmp_path, d))
    out = slice_text(p, p.stances[0], "Glances at the purse.")
    assert len(out.split()) <= 260
    assert "Ex one." not in out and "Ex two." not in out


def test_slice_keeps_examples_when_room(tmp_path):
    d = base(stances=[stance("s1", ["stranger"], examples=["Ex one.", "Ex two.", "Ex three."])])
    p = load_portrait(write(tmp_path, d))
    out = slice_text(p, p.stances[0], None)
    assert "Ex one." in out and "Ex two." in out and "Ex three." not in out


def test_slice_contains_leak_only_when_given(tmp_path):
    p = load_portrait(write(tmp_path, base()))
    assert "Glances at the purse." in slice_text(p, p.stances[0], "Glances at the purse.")
    assert "Glances" not in slice_text(p, p.stances[0], None)
