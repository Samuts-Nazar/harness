"""What the player reads is shown as its own block (outsider plan 1, task 6 review): in the live
stream, in the transcript, and again when the campaign is reopened. The shown text is the
reader's Ukrainian text; the English records are never shown. Fake stack, no network."""
from __future__ import annotations

import json

import pytest

from app import newgame
from app.campaigns import Stack
from app.game import Game
from app.newgame import parse
from app.stacks import FakeUk, fake_judge
from harness.pipeline import ModelConfig

LETTER = "Джин живе в мідній лампі торговця. Бажань він дає три, а бере голос."
SHOWN = "У листі сказано: джин живе в мідній лампі торговця і бере за бажання голос."
RECORD = "A djinn lives in the merchant's copper lamp; he takes the wisher's voice."
PKG = f"""\
version: 1
world: witcher
player:
  description: Інженер з іншого світу.
  inventory:
    - name: лист
      where: in hand
      content: "{LETTER}"
start:
  place: ринок
  situation: Ринок.
"""


class ReaderUk(FakeUk):
    def complete(self, model, messages):  # type: ignore[no-untyped-def]
        sys = messages[0]["content"]
        if "passages of a text" in sys:
            with self._lock:
                self.calls.append((model, messages))
            return json.dumps({"found": True, "text": SHOWN, "records": [RECORD]},
                              ensure_ascii=False)
        return super().complete(model, messages)


@pytest.fixture(autouse=True)
def _no_canon_env(monkeypatch):
    monkeypatch.delenv("HARNESS_CANON_DB", raising=False)


def build(tmp_path):
    judge = fake_judge()
    judge.rules["read_intent"] = lambda q, st: "чита" in " ".join(st)
    stack = Stack(ReaderUk(), judge, ModelConfig("narrator", "npc", "extractor", "judge"))
    g = Game(lambda new: newgame.open_package(stack, parse(PKG), root=tmp_path,
                                              canon_db=False), pace=0.0)
    return g, stack


def test_read_is_its_own_block_in_stream_and_transcript(tmp_path):
    g, stack = build(tmp_path)
    g.start_turn("*читаю лист*")
    g.wait_idle(20)
    reads = [e for e in g.events_after(0) if e["type"] == "read"]
    assert len(reads) == 1
    assert reads[0]["label"] == "лист" and reads[0]["text"] == SHOWN and reads[0]["found"]
    kinds = [t["kind"] for t in g.transcript]
    i = kinds.index("read")
    assert kinds[i - 1] == "player"  # shown right after the player's own line
    assert g.transcript[i]["text"] == SHOWN
    # the English record is never the read block's text (the panel's knowledge lines go through
    # the existing translator, `camp.translate`, like every other record)
    shown = json.dumps(reads, ensure_ascii=False) + json.dumps(g.transcript, ensure_ascii=False)
    assert RECORD not in shown
    # a reopened campaign shows the same block
    camp = newgame.opener(stack, root=tmp_path, fallback=lambda new: pytest.fail("x"))(False)
    again = [t for t in camp.transcript() if t["kind"] == "read"]
    assert len(again) == 1 and again[0]["text"] == SHOWN and again[0]["label"] == "лист"


def test_no_read_block_for_an_ordinary_turn(tmp_path):
    g, _ = build(tmp_path)
    g.start_turn("Добрий день.")
    g.wait_idle(20)
    assert not [e for e in g.events_after(0) if e["type"] == "read"]
    assert "read" not in [t["kind"] for t in g.transcript]
