"""Run the checks on stored sessions:

    nix develop --command python -m harness.evalkit [cassette.jsonl ...]

With no argument: every cassette in tests/fixtures/eval/ and $HARNESS_EVAL_DIR. Exit code 1 if a
replay misses or a check finds something."""
from __future__ import annotations

import os
import sys
from pathlib import Path

from . import session


def stored() -> list[Path]:
    out = sorted(Path(__file__).resolve().parents[2].joinpath("tests/fixtures/eval").glob("*.jsonl"))
    extra = os.environ.get("HARNESS_EVAL_DIR")
    if extra:
        out += sorted(Path(extra).glob("*.jsonl"))
    return out


def main(argv: list[str]) -> int:
    paths = [Path(a) for a in argv] or stored()
    bad = 0
    for p in paths:
        game, info = session.replay(p)
        reports = session.check(game, min_gap=int(os.environ.get("HARNESS_EVAL_GAP", "20")))
        print(f"== {p.name}: same story {info['same_story']}, replay misses {len(info['misses'])}")
        print(session.summary(reports))
        bad += (not info["same_story"]) + len(info["misses"]) + sum(len(r.findings) for r in reports.values())
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
