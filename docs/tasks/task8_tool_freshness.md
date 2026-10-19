# Task 8: Tool freshness audit and `docs/tools.md`

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.

## Goal
Create `docs/tools.md`, the registry of every tool the project depends on or has chosen, each checked against what is current as of today. Your training data is outdated; never judge from memory. Every claim about versions or alternatives must come from a live source (PyPI, GitHub releases, nixpkgs via the nixos MCP tool, official docs, release notes from the last 3 months) with a link.

## Scope
- Everything the repo uses or has decided on, except LLM/decision model choice per role (task 7 covers that; leave a `## Models` section with a placeholder line "filled from task 7").
- Find the list yourself: `flake.nix`, `README.md`, imports in the engine package and tests, `prototype/ui/` (Playwright, shell.nix), `design/` (SQLite schema, `design/tools/`), `experiments/common/llm.py` (HTTP client, OpenRouter usage), `docs/decisions.md`, `docs/assumptions.md`.
- Expected entries at least: Python version, nixpkgs channel/flake inputs, uv, httpx, python-dotenv, pytest, SQLite (and Python's sqlite3 version / any extension used), Playwright, OpenRouter as provider (API features we rely on: structured output, streaming, parallel requests, usage/cost reporting), the local Laya server, anything used for streaming text to the phone UI if decided.
- For roles where the decision is still open (e.g. web framework for the phone app, streaming transport), do NOT choose. List 2-4 current candidates with one line each and mark the entry "open".

## Entry format (one per role)
Role · chosen tool and version (or "open") · alternatives checked · reason · source links · date checked (2026-10-19).

## Rules
- No engine code changes. If a dependency is outdated and upgrading looks clearly better, write the recommendation and the risk in the entry; do not upgrade.
- No paid API calls. Budget 0 USD.
- At the end of `docs/tools.md`, a short "Recommended changes" list, ordered by value.

## Output
- `docs/tools.md` committed on your branch.
- Final report: the recommended changes, anything surprising (a much better tool, a deprecated one), branch name and worktree path as full absolute paths.
