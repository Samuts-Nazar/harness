import json

import pytest

from harness.extractor import DiffValidationError, parse_diff, validate_diff
from harness.state import StateChange

PRESENT = {"player", "innkeeper"}
SRC = {"narration", "player", "innkeeper", "action1"}


def ok_fact(**over):
    f = {"content": "x", "source": "narration", "notability": 0.5}
    f.update(over)
    return f


def ok_change(**over):
    c = {"character": "innkeeper", "category": "injury", "op": "add", "item": "cut lip",
         "source": "action1"}
    c.update(over)
    return c


def v(data, state=None):
    return validate_diff(data, present=PRESENT, sources=SRC, state=state)


def test_valid_diff():
    d = v({"new_facts": [ok_fact()], "state_changes": [ok_change()]})
    assert d.facts[0].content == "x" and d.facts[0].source == "narration"
    assert d.changes == [StateChange("innkeeper", "injury", "add", "cut lip", True, "action1",
                                      id="item:cut-lip")]  # the id is minted in code


def test_empty_diff_ok():
    d = v({})
    assert d.facts == [] and d.changes == []
    assert v({"new_facts": []}).facts == []


def test_parse_accepts_code_fence_and_rejects_garbage():
    assert parse_diff('```json\n{"new_facts": []}\n```') == {"new_facts": []}
    with pytest.raises(DiffValidationError):
        parse_diff("sure! here you go")


@pytest.mark.parametrize("knowers", [
    [{"character": "innkeeper", "how": "witnessed"}],
    [],
    "innkeeper",
])
def test_knower_lists_are_rejected(knowers):
    """Perception is computed in code; the extractor may not assign knowers at all."""
    with pytest.raises(DiffValidationError, match="knowers"):
        v({"new_facts": [ok_fact(knowers=knowers)]})


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
    {"new_facts": [ok_fact(location=3)]},
    {"new_facts": [{k: v for k, v in ok_fact().items() if k != "content"}]},
    {"new_facts": [ok_fact()] * 21},
    {"state_changes": "nope"},
])
def test_malformed_rejected(data):
    with pytest.raises(DiffValidationError):
        v(data)


@pytest.mark.parametrize("data", [
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


def test_state_changes_validated_against_existing_state():
    """An invalid change is dropped (with its reason); it never rejects the diff."""
    state = {"innkeeper": {("equipment", "dagger"): False}}
    # cannot remove what is not there
    d = v({"state_changes": [ok_change(category="equipment", op="remove", item="sword")]}, state)
    assert d.changes == [] and "does not have" in d.dropped[0]["reason"]
    # cannot add twice
    d = v({"state_changes": [ok_change(category="equipment", item="dagger")]}, state)
    assert d.changes == [] and "already has" in d.dropped[0]["reason"]
    # reveal only a hidden element, hide only an observable one
    assert v({"state_changes": [ok_change(category="equipment", op="hide", item="dagger")]},
             state).changes == []
    assert v({"state_changes": [ok_change(category="equipment", op="reveal", item="dagger")]},
             state).changes
    # changes inside one diff see each other: add then remove is fine, remove then remove is not
    add_rm = [ok_change(), ok_change(op="remove")]
    assert len(v({"state_changes": add_rm}).changes) == 2
    d = v({"state_changes": [ok_change(), ok_change(op="remove"), ok_change(op="remove")]})
    assert len(d.changes) == 2 and len(d.dropped) == 1
    # validation does not mutate the caller's state
    assert state == {"innkeeper": {("equipment", "dagger"): False}}


@pytest.mark.parametrize("bad", [
    ok_change(category="mood"), ok_change(op="steal"), ok_change(item=""),
    ok_change(character="nobody"), ok_change(source="nobody"), ok_change(observable="yes"),
    ok_change(extra=1), "not an object", 7,
])
def test_one_bad_change_is_dropped_the_rest_stands(bad):
    """The first live session lost whole turns to one invented change (revealing an item in the
    wrong category). Now only that change goes; facts and the other changes are kept."""
    good = ok_change(item="bruise")
    d = v({"new_facts": [ok_fact()], "state_changes": [bad, good]})
    assert [c.item for c in d.changes] == ["bruise"] and len(d.facts) == 1
    assert len(d.dropped) == 1 and d.dropped[0]["change"] == bad and d.dropped[0]["reason"]


def test_engine_retries_then_commits_valid_diff():
    from conftest import diff, fact, make_engine

    script = {
        "narrator": ["N."],
        "npc": ["Hi."],
        "extractor": [
            json.dumps({"new_facts": [], "set_canon": 1}),  # rejected
            diff(fact("ok", "narration")),  # retry accepted
        ],
    }
    eng, _ = make_engine(script)
    res = eng.turn("hello", speakers=["innkeeper"])
    assert len(res.fact_ids) == 1


def test_engine_rejects_diff_with_knowers():
    import pytest as _pt
    from conftest import make_engine
    from harness.pipeline import ExtractionRejected

    bad = json.dumps({"new_facts": [{"content": "leak", "source": "narration",
                                     "notability": 0.5,
                                     "knowers": [{"character": "spy", "how": "heard"}]}]})
    eng, _ = make_engine({"narrator": ["N."], "npc": ["Hi."], "extractor": [bad, bad]})
    with _pt.raises(ExtractionRejected):
        eng.turn("hello", speakers=["innkeeper"])
    assert eng.facts.visible_to("spy", 10**6) == []
