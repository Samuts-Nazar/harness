"""The panel translator must not leave English behind (smoke 2026-10-22: a record line whose
masked name had become a Ukrainian description was mostly Cyrillic, so the model returned it
unchanged and the unchanged line was cached for good)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.campaigns import Translator  # noqa: E402
from harness.providers import FakeProvider  # noqa: E402

MIXED = "вартовий без шолома set his tankard on the table twice because it wobbled."


def test_line_returned_unchanged_is_asked_again_and_the_english_one_is_not_cached(tmp_path):
    fixed = "вартовий без шолома двічі поставив кухоль на стіл, бо той хитався."
    prov = FakeProvider(script={"tr": [json.dumps([MIXED, "Шинкар кивнув."]),
                                       json.dumps([fixed])]})
    path = tmp_path / "t.json"
    tr = Translator(prov, "tr", path)
    assert tr([MIXED, "Шинкар кивнув."]) == [fixed, "Шинкар кивнув."]
    assert len(prov.calls) == 2 and "mix" in prov.calls[1][1][0]["content"].lower()
    assert json.loads(path.read_text(encoding="utf-8"))[MIXED] == fixed


def test_a_stubborn_english_answer_is_shown_but_not_cached(tmp_path):
    prov = FakeProvider(script={"tr": [json.dumps([MIXED]), json.dumps([MIXED])]})
    tr = Translator(prov, "tr", tmp_path / "t.json")
    assert tr([MIXED]) == [MIXED]
    assert MIXED not in tr.cache


def test_a_cached_english_leftover_is_translated_again(tmp_path):
    path = tmp_path / "t.json"
    path.write_text(json.dumps({MIXED: MIXED}), encoding="utf-8")
    fixed = "вартовий без шолома двічі поставив кухоль на стіл."
    prov = FakeProvider(script={"tr": [json.dumps([fixed])]})
    assert Translator(prov, "tr", path)([MIXED]) == [fixed]
