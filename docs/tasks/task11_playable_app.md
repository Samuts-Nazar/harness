# Task 11: Playable minimum (phone app on the real engine)

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `docs/tools.md` (open roles: web framework, streaming transport, frontend), `prototype/ui/` (README, app.js, screenshots), `harness/pipeline.py` (`Engine`), `harness/streaming.py`, `harness/demo.py`.

## Goal
The user has not played the project yet. Build the smallest app in which they can play one scene from their phone (and laptop browser) on the real engine, then keep playing to give feedback. This is the base later features plug into, so keep it simple and clean, not throwaway.

## Parallel work
Another worker (task 9) is changing `harness/` at the same time: new models, parallel turn, file-backed campaigns, output language. Put your code in `app/` (server, static frontend, tests). Do not modify `harness/` except a thin, clearly separated hook if streaming or interrupt truly cannot be done from outside; list any such change in the report. Use the in-memory engine for now and keep campaign storage behind one function so the file-backed version from task 9 can be plugged in.

## Choose the stack (tool freshness rule)
- Pick web framework, streaming transport and frontend from the candidates in `docs/tools.md` (re-check versions live, they move fast). Criteria: least code, works well on a phone browser, survives the app going to background (the world pauses when the app is backgrounded, `docs/decisions.md`), supports a server-to-client word stream and a client-to-server interrupt.
- Record the choice in `docs/tools.md` (move the entries from "open" to chosen, with reason and date). Only use packages available in nixpkgs or installable in the flake dev shell; add them to `flake.nix`.

## Features (minimum)
1. Start or continue a campaign: a Witcher inn scene with Рагнар as the player character and two NPCs, reusing the demo setup. The player character file is local (`data/Ragnar.md` is never committed); if it is missing, use a short placeholder.
2. Player types an action or line; the turn runs; narration and NPC lines stream word by word at speaking pace, NPC lines labelled with the speaker.
3. Interrupt button while text streams (uses the engine's live interruption).
4. Player character panel: live state as chips plus a few sentences (as in the prototype), only what the character perceives.
5. Debug view (hidden behind a toggle): event log, judgments, model calls with cost and latency for the last turn.
6. Clear errors: if a model call fails, show a message and keep the player's input.
Not now: turn assistant, retroactive cut, model-error button, quick reactions, tappable names. Reuse prototype styling where it is cheap.

## Running
- One command in the dev shell, e.g. `nix develop --command python -m app --live`. Fake provider without `--live` (scripted Ukrainian text, so the UI can be tested offline).
- Bind to `127.0.0.1` by default; a `--host 0.0.0.0` flag for phone access over the LAN. Do not touch `/etc/nixos` or the firewall; say in the report which port must be opened.
- Write `app/README.md` in Ukrainian: how to start, how to open on the phone.

## Tests
- Server tests with the fake engine (turn, stream, interrupt, panel).
- A Playwright check at phone size (390x844) like `prototype/ui/test_ui.py`: play two turns offline, interrupt once, open debug view; save screenshots under `app/screenshots/`.
- One live check: 3 turns in Ukrainian; report seconds until first word and per turn.

## Budget
Under 0.30 USD.

## Output
Final report: chosen stack and why, how to run, test results, live numbers, spend, any `harness/` changes, branch name and worktree path as full absolute paths.
