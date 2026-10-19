# Bake-off (task 7)

Run from the repo root inside `nix develop`:
- `python3 experiments/bakeoff/build_judgments.py`, `build_texts.py` — write `testset/*.json` (gold included).
- `python -m experiments.bakeoff.run_text` / `run_decide` — raw outputs to `raw/` (needs `OPENROUTER_API_KEY` in `.env`).
- `grade_prep.py` makes the blind packets; grades are in `grades_*.json`; `analyze_text.py`, `analyze_decide.py`, `analyze_npc_check.py`, `laya_compact.py`, `timing_turn.py` produce the numbers in `reports/bakeoff/SUMMARY.md`.
- Laya: `setup_laya.sh` once, `serve_laya.sh` to serve on 127.0.0.1:8765.
No keys and no book text are stored here.
