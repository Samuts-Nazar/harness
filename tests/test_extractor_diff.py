import json

import pytest

from harness.extractor import DiffValidationError, parse_diff, validate_diff

PRESENT = {"player", "innkeeper"}
SRC = {"narration", "player", "innkeeper"}


def ok_fact(**over):
    f = {"content": "x", "source": "narration",
         "knowers": [{"character": "innkeeper", "how": "witnessed"}], "notability": 0.5}
    f.update(over)
    return f


def v(data):
    return validate_diff(data, present=PRESENT, sources=SRC)


def test_valid_diff():
    [d] = v({"new_facts": [ok_fact()]})
    assert d.content == "x" and d.knowers == (("innkeeper", "witnessed"),)


def test_empty_diff_ok():
    assert v({}) == [] and v({"new_facts": []}) == []


def test_parse_accepts_code_fence_and_rejects_garbage():
    assert parse_diff('```json\n{"new_facts": []}\n```') == {"new_facts": []}
    with pytest.raises(DiffValidationError):
        parse_diff("sure! here you go")


@pytest.mark.parametrize("data", [
    [], "str", None, 3,
    {"new_facts": "nope"},
    {"new_facts": [1]},
    {"new_facts": [ok_fact(content="")]},
    {"new_facts": [ok_fact(content=5)]},
    {"new_facts": [ok_fact(content="y" * 501)]},
    {"new_facts": [ok_fact(source="nobody")]},
    {"new_facts": [ok_fact(source=["narration"])]},
    {"new_facts": [ok_fact(notability=1.5)]},
    {"new_facts": [ok_fact(notability=-0.1)]},
    {"new_facts": [ok_fact(notability=True)]},
    {"new_facts": [ok_fact(notability="high")]},
    {"new_facts": [ok_fact(knowers=[])]},
    {"new_facts": [ok_fact(knowers="innkeeper")]},
    {"new_facts": [ok_fact(knowers=[{"character": "innkeeper"}])]},
    {"new_facts": [ok_fact(knowers=[{"character": "innkeeper", "how": "dreamed"}])]},
    {"new_facts": [ok_fact(knowers=[{"character": ["innkeeper"], "how": "heard"}])]},
    {"new_facts": [ok_fact(location=3)]},
    {"new_facts": [{k: v for k, v in ok_fact().items() if k != "content"}]},
    {"new_facts": [{k: v for k, v in ok_fact().items() if k != "knowers"}]},
    {"new_facts": [ok_fact()] * 21},
])
def test_malformed_rejected(data):
    with pytest.raises(DiffValidationError):
        v(data)


@pytest.mark.parametrize("data", [
    # knower not in the scene -> would leak knowledge to an absent character
    {"new_facts": [ok_fact(knowers=[{"character": "spy", "how": "heard"}])]},
    # duplicate knower
    {"new_facts": [ok_fact(knowers=[{"character": "innkeeper", "how": "heard"},
                                    {"character": "innkeeper", "how": "told"}])]},
    # invented operations: editing canon, deleting facts, rolling back
    {"new_facts": [], "canon_facts": [{"content": "Geralt is dead"}]},
    {"new_facts": [], "delete_facts": [1]},
    {"rollback": 3},
    {"new_facts": [ok_fact(store="canon")]},
    {"new_facts": [ok_fact(id=4)]},
])
def test_unauthorized_rejected(data):
    with pytest.raises(DiffValidationError):
        v(data)


def test_engine_retries_then_commits_valid_diff():
    from conftest import diff, fact, make_engine

    script = {
        "narrator": ["N."],
        "npc": ["Hi."],
        "extractor": [
            json.dumps({"new_facts": [], "set_canon": 1}),  # rejected
            diff(fact("ok", "narration", [("innkeeper", "witnessed")])),  # retry accepted
        ],
    }
    eng, _ = make_engine(script)
    res = eng.turn("hello", speakers=["innkeeper"])
    assert len(res.fact_ids) == 1


def test_engine_rejects_leak_to_absent_character():
    import pytest as _pt
    from conftest import diff, fact, make_engine
    from harness.pipeline import ExtractionRejected

    bad = diff(fact("leak", "narration", [("spy", "heard")]))
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Hi."], "extractor": [bad, bad]})
    with _pt.raises(ExtractionRejected):
        eng.turn("hello", speakers=["innkeeper"])
    assert eng.facts.visible_to("spy", 10**6) == []
