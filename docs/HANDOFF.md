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

## State on 2026-10-19
- main: core engine (task 4, 115 tests), idea sessions A/B (`ideas/`), decisions replaced, cost report (`reports/cost/`), gaps list (`reports/decision_gaps.md`, 19 gaps).
- Pending: cleanup/merge of `ui-prototype` (phone UI prototype, `prototype/ui/`) and `design-schema` (`design/schema.md`, `design/schema_gaps.md`) if not yet done; task 7 model bake-off (`docs/tasks/task7_model_bakeoff.md`) if not yet run.
- Known issues: NPC output check too strict (falls back on correct lines); engine retries extraction only once; scene tests were in English, play will be Ukrainian.
- Open questions from design-schema for the user (ask in plain Ukrainian): who decides if an NPC's claim is true; whether to check narrator text for leaks too; when the retroactive-interrupt window closes; how much to verify the book ingestion; whether normal play needs "forget this record and everything derived from it".
- User answers so far are reflected in decisions.md (open simulation, player is sole truth for Ragnar, canon pull proportional, phone first, full live state in V1, world pauses when app backgrounded, rewind only in debug, model-error button with required explanation stored per campaign, turn assistant with action options, no music/voice/images in V1).
