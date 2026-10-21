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

## State on 2026-10-19 (evening)
- main has tasks 4-15 merged: engine on chosen models (luna narrator/NPC, deepseek extractor, d1-ultra decider), parallel turn, saved campaigns, phone app (`app/`, port 8765 open on the LAN, run `nix develop --command python -m app --live --host 0.0.0.0`), prose narration + scene director, names as knowledge, "how does he know that" with spoiler, actions in *asterisks*, player looks from the local character file, Sapkowski style sheet + NPC beats + manner notes, one glossary, canon ingestion pilot (`harness/canon/`, `reports/canon_pilot/SUMMARY.md`).
- Running (background workers, own worktrees under `.claude/worktrees/`, briefs in `docs/tasks/`): task 16 canon in play, task 17 world beyond the scene, task 18A/18B prior-art research (reports go into the final message; write them to `reports/research/`). If a session dies, check each worktree's branch (`git log main..<branch>`), resume or start a new worker on the same branch with the same brief, then review, merge, push, verify with `git ls-remote origin`, delete branch and worktree.
- Next after 16+17: Vizima pilot scene, situation A (tavern «Під Лисом», day 3 evening), player = limitless demon; test plan `docs/pilot_vizima_test_plan.md`. Adjust the plan if 18A/18B recommend changing the core first.
- All decisions agreed in chat up to 2026-10-20 are in `docs/decisions.md` (written 2026-10-20). Pilot setup (not a design rule): Vizima situation A, tavern «Під Лисом», day 3 evening; player = limitless demon (own creature in the spirit of Master Mirror, not O'Dimm); Ragnar will be replayed from scratch once the harness is ready; checklist page `app/static/checklist.html`.
- User feedback to remember: the first NPC lines read as "neural-network style", not Sapkowski; this drove task 15. The A/B style page `/static/ab.html` awaits the user's verdict. Ragnar's chronicle will be replayed from scratch once the harness is ready.
- Open user question: none pending.

## Checkpoint 2026-10-21 (session paused at usage limit)
- Living-dialogue plan (`docs/superpowers/plans/2026-10-21-living-dialogue.md`, spec in `docs/superpowers/specs/`) runs with superpowers subagent-driven-development; the ledger is `.claude/worktrees/living-dialogue/.superpowers/sdd/2026-10-21-living-dialogue/progress.md` (read it first; tasks marked complete are done).
- Branches: `living-dialogue` (tasks 1-8 + 10), `ld-t9`, `ld-t11` (pending review/merge). Nothing of these is on main yet.
- Research done and on main: `reports/research/21A_decisions.md`, `21B_tone_leaks.md`.
- Open user questions: model bake-off above the price ceiling?; approve an 8 GB local Gemma 4 E4B download for a base-model tone test?
