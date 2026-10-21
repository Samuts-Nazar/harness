"""`pytest -m eval`: replay every stored session offline and run the automatic checks on it.

Stored sessions: tests/fixtures/eval/*.jsonl (committed, recorded on the offline fake stack) and
every *.jsonl in $HARNESS_EVAL_DIR (your own live recordings; hashes and replies only, prompts are
not stored, but keep them out of git anyway). A replay must give the same story with no miss (a
miss means a prompt changed since the recording), and the isolation and metaphor checks must find
nothing. The fact-survival check uses a gap of 20 turns on sessions that long, else the session's
own length (`HARNESS_EVAL_GAP` overrides)."""
import os
from pathlib import Path

import pytest

from harness.evalkit import session
from harness.evalkit.__main__ import stored
from harness.evalkit.replay import load

pytestmark = pytest.mark.eval
PATHS = stored()


@pytest.mark.parametrize("path", PATHS, ids=lambda p: p.name)
def test_stored_session_replays_and_passes_the_checks(path: Path):
    header, _ = load(path)
    game, info = session.replay(path)
    assert not info["misses"], f"prompts changed since the recording: {info['misses'][:2]}"
    assert all(r["error"] is None for r in info["rows"]), info["rows"]
    assert info["same_story"], "the replayed story differs from the recorded one"
    gap = int(os.environ.get("HARNESS_EVAL_GAP", min(20, max(len(header["turns"]) - 1, 1))))
    reports = session.check(game, min_gap=gap)
    bad = {k: [f.detail for f in r.findings] for k, r in reports.items() if not r.ok}
    assert not bad, session.summary(reports)
    assert reports["isolation"].stats["npc_lines"] >= 0
