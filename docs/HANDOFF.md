# Handoff for the lead session

You are the lead ("brain") for the harness project. The user talks to you; Sonnet worker subagents do the hands-on work. Read this file, `docs/decisions.md`, `CLAUDE.md`, `docs/assumptions.md`, `reports/` and `design/` before anything else.

## How to work with the user
- He writes in Ukrainian; answer in Ukrainian, short, plain words, explain jargon in one clause. No analogies for technical things.
- Most of what he says is a raw idea. Expand and complete it, do not take it literally, and do not question it as if it were a finished spec.
- Ask only about the engine, cost and interface. World behaviour follows reality and is judged per situation by scale and circumstances; never turn it into game-rule questions. No action is a special mechanic.
- Resolve open questions in chat first; update `docs/decisions.md` once at the end, not incrementally. Never put open questions inside decisions.md.
- Never invent facts about him or his situation. Verify anything current (models, prices, tools) live before stating it; do not pick models from memory.
- Do not dramatize, do not remind him about time.

## Division of labour
- You decide, plan, write briefs, review diffs and talk to the user. Workers (Sonnet) do implementation, experiments, bulk reading and web research.
- Do small things yourself when delegating costs more than doing: a few-line edit, reading one or two files, a single command, a quick check. A worker starts cold and re-reads context, and you must review its output anyway.
- For broad read-only exploration of the repo, use the Explore subagent and take its summary instead of reading everything yourself.
- Independent tasks go to several workers in parallel in the background.

## Tool freshness (hard rule)
- Your training data and the workers' end around mid-2026; the tool landscape changes weekly. Never choose a model, library, framework, service or method from memory.
- Before adopting or keeping any tool for a role: search what is current (OpenRouter catalog, Hugging Face, GitHub releases, release notes from the last 3 months), list the real alternatives, and pick with a short written reason. Prefer newer versions when they are better and not more expensive; never keep an older or weaker option without a reason.
- Record every choice in `docs/tools.md`: role, chosen tool and version, alternatives checked, reason, date checked. Re-check an entry when it is older than a month, when starting work that depends on it, or when the user names something new.
- When the user names a tool you did not know, verify it and evaluate it seriously; treat it as a sign the last check missed something and widen the next search.

## Spending and models
- Paid API (OpenRouter) only for cheap models; flagship-class never over the API. No Anthropic models in the engine. Model per role chosen by bake-off on our own tasks from the live catalog.
- Strong judging/grading is done by you or a worker reading outputs, never by a strong model over the API.
- Measured cost (task 6, older model set): about $0.04-0.08 per hour of play; cost is not the bottleneck. Speed (~21 s/turn, sequential calls) and quality are.
- Decision models (typed answers with probabilities): Jev is the old baseline; candidates include elorian/glimpse, perplexity/pplx-decider(-flash)-v1.2, liquid/d1-ultra, and Laya (local, Jev-compatible API).

## Repo hygiene (past failures)
- Workers claimed "pushed" when nothing reached GitHub, and left work in hidden nested worktrees under `.claude/worktrees/`. After every worker task: check the diff yourself, merge into main, push, verify with `git ls-remote origin`, delete the branch and worktree.
- Every report to the user gives full absolute paths.
- Never commit `.env`, `data/`, `campaigns/`, character files. Repo is public for now.

## How we work now (since 2026-10-21)
- The superpowers plugin is installed. New features go through the following, without exceptions for "small" features:
  - `superpowers:brainstorming`: questions one at a time, playbacks, a visual companion for anything visual;
  - a design doc in `docs/superpowers/specs/`, then a builder check by a fresh subagent, then the user's approval;
  - `superpowers:writing-plans`, with the plan in `docs/superpowers/plans/`;
  - `superpowers:subagent-driven-development`: one implementer per task, a task reviewer after each, scoped re-reviews of fixes, a final whole-branch review on opus.
- The ledger and workspace of each plan live in `<worktree>/.superpowers/sdd/<plan>/progress.md`, git-ignored. Read it first after a restart; tasks marked complete are done.
- Before merging, run pytest yourself and check the real exit code. Run the Playwright check `app/tests/ui_check.py` for UI changes. Then merge into main, push, verify with `git ls-remote`, and delete the branch and worktree. Save the ledger's rulings and deferred items to `reports/<area>/deferred_and_rulings.md`.
- The user's preferences learned so far:
  - choices about taste (models, UI) are made by the user's blind grading, never by agent grading;
  - they distrust OpenAI models;
  - they reject outdated models;
  - they want parallel work when tasks are independent;
  - they dislike Telegram-like UI;
  - they want the game to read like Sapkowski's book.
- Every money spend needs the user's OK when it exceeds what a brief already allows. They refused a $2 Gemini comparison; small budgets (≤ $0.20) per task are fine.

## State on 2026-10-22 (for a fresh session)
- **main is the truth.** It has:
  - the engine (tasks 4–19);
  - living dialogue (spec `2026-10-21-living-dialogue-design.md`, plan `…-living-dialogue.md`, report `reports/dialogue/SUMMARY.md`): world profile, response shapes, NPC exchanges, optional narration, cut-in, scene cast, and challenge removal;
  - research reports `reports/research/18A/18B/21A/21B`;
  - the human-writing bake-off (`reports/human_ab/`);
  - the model switch: narrator and NPC both `xiaomi/mimo-v2.6-flash` since 2026-10-22 (narrator was `mimo-v2.6-pro`, too slow to the first word), temperature 0.8. The user's blind grading was mimo-pro 4.0, mimo-flash 3.6, luna 3.0.
- **Interactive book UI: merged 2026-10-22** (spec `docs/superpowers/specs/2026-10-22-interactive-book-ui-design.md`, plan `docs/superpowers/plans/2026-10-22-interactive-book-ui.md`, live report `reports/ui/SUMMARY.md`, rulings `reports/ui/deferred_and_rulings.md`). New game from a file: `docs/new_game_instruction.md` + `docs/game_package_example.yaml`.
- **Next, after the UI:** active play tests by the user on the Vizima pilot (`docs/pilot_vizima_test_plan.md`, `app/static/checklist.html`). Start: `nix develop --command python -m app --live --host 0.0.0.0 --budget 0.5`; phone at `http://192.168.1.109:8765/`.
- **Later projects agreed with the user:**
  - project 2, a decision layer against averaging (`reports/research/21A_decisions.md`);
  - project 3, prose tone (`21B`);
  - a bake-off of models on the known failures.
- **User answers 2026-10-22:**
  - anything may run locally (models, later image generation); put large downloads on `/home/cock/1TB`;
  - models above the price ceiling: first show the user which models they are (names, prices, why), no spend before their OK;
  - speaker names on the page: a setting (on = names visible, off = colours only).
- **Known test-data defects:** `experiments/bakeoff/testset/npc.json` c07 lists Marta as Roche's rumour source, and the old tests predate names-as-knowledge. Fix them when touching these sets.
- **2026-10-22 afternoon:** speaker-names switch in the ☰ drawer (merged). Blind writing test round 2 (`reports/human_ab/README2.md`, page `/static/human_ab2.html`; Єніфер first meeting + 6 Визім moments; glm-5.3, glm-5.3-flash, mistral-large-4-0, mimo-flash, mimo-pro) is waiting for the user's grades. GLM needs `reasoning: {effort: low, exclude: true}` (it refuses reasoning off; that caused round 1's glitches). Next: read the grades, decide narrator/NPC models with the user.
- **2026-10-22 evening:** merged model error on gestures, drawer facts in the player's view, six more canon start points (`worlds/witcher/start_points.yaml`), and fixes from the live smoke play (`reports/ui/2026-10-22_smoke_live.md`, items 1–4: name leaks, English in panel, 20 s fast-call timeout with fallback, judge `p_yes` misread that made the unknown-claim check reject almost every NPC line). Not verified live yet: run a 3-turn live check first. Open from the smoke report: the world writes player actions, mute innkeeper, repeated motifs, broken flash sentences, suggestions quality, empty places for non-Vizima starts (items 5–14). Known: `app/tests/test_app_t19.py::test_vizima_on_the_real_canon_store` fails with `HARNESS_CANON_DB` set (pre-existing).

## Resume here (state on 2026-10-23)
- **Character portraits: merged 2026-10-23** (spec `docs/superpowers/specs/2026-10-22-character-portraits-design.md`, plan `docs/superpowers/plans/2026-10-22-character-portraits.md`, rulings and deferred items `reports/portraits/deferred_and_rulings.md`, design summary in `docs/decisions.md` under "Character memory and live state").
  - In main: portrait slices in NPC prompts; relationship ladder with paced switches and rationed leaks; short generated portraits for named/recurring invented NPCs and package `portrait_text` (max 2 per settle, parallel); canon portraits for innkeeper, Велерад, Ґеральт, Фольтест bound in all 7 start points.
  - Live check (vidmak_A_tavern, 5 turns, $0.01): 0 portrait copies, first word 7–22 s. A question addressed to nobody got no speaker (director, not portraits).
  - **Next:** the user's play test of portraits (Йеннефер in Рінде; Vizima innkeeper getting warmer), then the later projects below.
- **Known flake:** `app/tests/test_app_final_review.py::test_stream_and_state_answer_while_slow_translations_run` fails about 1 run in 8; rerun it alone.
- **Subagents:** the `worker` agent type runs in its own worktree off main; for work on an existing branch worktree use `general-purpose`.
- **User feedback rules** (memory `prose-hates`, `user-preferences-harness`, `claude-usage-limits`):
  - no big blind-grading pages; use 👍/👎 in play (`python -m app.ratings_report`) plus a few finalist pairs;
  - stop autonomous work at about 90% of the 5-hour window; usage is in `~/.claude/usage-cache.json`.
- **Open:** blind test round 2 was graded only for scene w0 (Йеннефер, user notes in memory `prose-hates`). The other scenes are optional now. The live smoke report `reports/ui/2026-10-22_smoke_live.md`: items 1–14 were addressed except the narration name-variant leak («Зоска» vs «Зоська»).
