"""Play a scripted session on a stack, record it, and replay it offline as a regression test.

The scenario is the app's Vizima campaign without canon (`app.vizima`, deterministic: a fixed
campaign name and seed make the code-made NPCs identical every run). The cassette header holds the
scenario, the turns and the model names; the footer holds the player-visible transcript, so a replay
checks that the same answers produce the same story, and any prompt change shows up as a replay
miss.
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any, Sequence

from app.campaigns import Stack
from app.game import Game
from app.vizima import open_vizima
from harness.pipeline import ModelConfig

from .checks import Report, run_all
from .replay import Cassette, RecordingJudge, RecordingProvider, ReplayJudge, ReplayProvider, load

SCENARIO = "vizima_nocanon"
NAME, SEED = "eval-vizima", "eval-seed-1"


def _models_dict(m: ModelConfig) -> dict[str, Any]:
    return dict(vars(m))


def play(stack: Stack, turns: Sequence[str], root: Path | str, *, timeout: float = 240.0
         ) -> tuple[Game, list[dict[str, Any]]]:
    """Run the turns through the app's Game (threads, slow lane) and collect per-turn timing."""
    game = Game(lambda new: open_vizima(stack, root=root, new=True, name=NAME, canon_db=False,  # type: ignore[arg-type]
                                        seed=SEED), pace=0.0)
    rows: list[dict[str, Any]] = []
    for i, text in enumerate(turns, 1):
        t0 = time.monotonic()
        game.start_turn(text)
        game.wait_idle(timeout)
        d = game.debug
        err = next((e for e in game.events_after(0) if e["type"] in ("error", "retract")), None)
        rows.append({"turn": i, "error": err and err.get("message"), "wall_s": round(time.monotonic() - t0, 2),
                     "first_word_s": d.get("timing", {}).get("first_word_s"),
                     "fast_s": d.get("timing", {}).get("total_s"),
                     "slow_s": d.get("timing", {}).get("slow_s"),
                     "waited_s": d.get("timing", {}).get("waited_s"), "cost": d.get("cost"),
                     "calls": len(d.get("calls", []))})
    return game, rows


def record(stack: Stack, turns: Sequence[str], path: Path | str, *, keep_prompts: bool = False
           ) -> tuple[Game, list[dict[str, Any]]]:
    """Play on `stack` (live or fake) and write the cassette."""
    cas = Cassette(path, {"scenario": SCENARIO, "turns": list(turns),
                          "models": _models_dict(stack.models), "name": NAME, "seed": SEED})
    rec = Stack(RecordingProvider(stack.provider, cas, keep_prompts=keep_prompts),
                RecordingJudge(stack.judge, cas), stack.models, stack.spend, stack.live)
    game, rows = play(rec, turns, tempfile.mkdtemp(prefix="eval-rec-"))
    cas.write({"k": "f", "transcript": game.transcript})
    return game, rows


def replay(path: Path | str, *, strict: bool = True) -> tuple[Game, dict[str, Any]]:
    """Re-run a recorded session offline. Returns the game and {misses, same_story}."""
    header, recs = load(path)
    prov = ReplayProvider(path, strict=strict)
    judge = ReplayJudge(path, strict=strict)
    stack = Stack(prov, judge, ModelConfig(**header["models"]), None, False)
    game, rows = play(stack, header["turns"], tempfile.mkdtemp(prefix="eval-rep-"))
    footer = next((r for r in recs if r["k"] == "f"), None)
    same = footer is not None and footer["transcript"] == game.transcript
    return game, {"misses": prov.misses + judge.misses, "same_story": same, "rows": rows}


def check(game: Game, *, judge: Any = None, min_gap: int = 20) -> dict[str, Report]:
    from harness.world.places import vizima
    eng = game.eng
    common = [p.name for p in vizima().places.values()]
    reports = run_all(eng, judge=judge, min_gap=min_gap)
    from .checks import check_isolation
    reports["isolation"] = check_isolation(eng, common)
    return reports


def summary(reports: dict[str, Report]) -> str:
    return "\n".join(str(r) for r in reports.values())


def to_json(reports: dict[str, Report]) -> str:
    return json.dumps({k: {"ok": r.ok, "stats": r.stats,
                           "findings": [vars(f) for f in r.findings]} for k, r in reports.items()},
                      ensure_ascii=False, indent=1)
