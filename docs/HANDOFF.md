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
  - the model switch: narrator `xiaomi/mimo-v2.6-pro`, NPC `xiaomi/mimo-v2.6-flash`, temperature 0.8. The user's blind grading was mimo-pro 4.0, mimo-flash 3.6, luna 3.0.
- **In progress: the interactive book UI.**
  - Spec: `docs/superpowers/specs/2026-10-22-interactive-book-ui-design.md` (approved). Plan: `docs/superpowers/plans/2026-10-22-interactive-book-ui.md`. Mockups: `docs/design/ui-mockups/`.
  - Branch `book-ui`, worktree `.claude/worktrees/book-ui`, ledger `.claude/worktrees/book-ui/.superpowers/sdd/2026-10-22-interactive-book-ui/progress.md`.
  - Task 1 is complete (tokens, inks, `/api/cast`, `/api/people`).
  - Task 2, the turn assistant, is implemented (f96f3f2) but NOT yet reviewed. Next step: its task review (package 625cb29..f96f3f2, built with the skill's `review-package` script), then Task 3.
  - Tasks 3 (client page) and 4 (places and a live check) remain, then the final review and the merge.
- **Next, after the UI:** active play tests by the user on the Vizima pilot (`docs/pilot_vizima_test_plan.md`, `app/static/checklist.html`). Start: `nix develop --command python -m app --live --host 0.0.0.0 --budget 0.5`; phone at `http://192.168.1.109:8765/`.
- **Later projects agreed with the user:**
  - project 2, a decision layer against averaging (`reports/research/21A_decisions.md`);
  - project 3, prose tone (`21B`);
  - a bake-off of models on the known failures.
- **Open user questions:**
  - whether a bake-off may test models above the price ceiling (the user said no to Gemini 3.8 Flash for now);
  - an 8 GB Gemma 4 E4B local download for a base-model tone test (not answered).
- **Known test-data defects:** `experiments/bakeoff/testset/npc.json` c07 lists Marta as Roche's rumour source, and the old tests predate names-as-knowledge. Fix them when touching these sets.
