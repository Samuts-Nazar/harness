# Task 18: Prior art research (two parallel workers: 18A infrastructure, 18B design)

Work fully autonomously. Do not ask questions. No code changes, no paid API calls (budget 0 USD). Web research only, plus reading this repo.
Read first: `docs/decisions.md`, `docs/tools.md`, `docs/pilot_vizima_test_plan.md`, `README.md`, `reports/decision_gaps.md`, `design/schema.md` (skim), `ideas/A/SUMMARY.md`, `ideas/B/SUMMARY.md`.

## The goal the research serves (user's words, condensed)
An interactive world of Sapkowski's Witcher saga: the player plays only their own character and can live that character's whole life, from start to end, and do no less than what Sapkowski wrote across the saga. Quality may fall short at first, but this is the target. The user believes much is missing that we do not yet know about, and wants to learn from others' results and mistakes now, so the project is not rewritten after it is finished.

## Rules for both
- Your knowledge is outdated; search live. Prefer sources from the last 12 months, but include older foundational work when it is still the best reference. Every claim gets a link and a date.
- Look widely: papers (arXiv, ACL/AIIDE/FDG/CHI), GitHub projects and their issues (what broke), product postmortems and dev blogs, forums (Reddit r/LocalLLaMA, r/SillyTavernAI, r/aigamedev, Hacker News), Discords' public summaries, talks.
- For each relevant finding: what it is, what it does that we do not, what failed for them, and a concrete recommendation for us: adopt / adapt / ignore, with the cost of change now vs later.
- Compare against our current design explicitly (what we already do, what we do differently, where we are likely to hit their failure).
- End with a ranked list: "change now before building more", "plan for later", "ignore". Be honest when our design is fine.

## 18A — infrastructure, tools, techniques (engine side)
Topics (not limited to):
- Existing engines/frameworks for LLM-driven world simulation, RPGs, interactive fiction, multi-agent simulation; what they use for state, memory, retrieval, scheduling.
- Memory and knowledge: event sourcing for LLM worlds, temporal knowledge graphs, per-agent memory (reflection, summarisation, forgetting), epistemic/belief tracking, retrieval at saga scale (millions of words + years of play).
- Structured generation and validation (JSON schema, grammars, constrained decoding), small classifiers/deciders, guardrails for knowledge leaks, LLM-as-judge pitfalls.
- Latency: parallel/speculative generation, prefetch, prompt caching, streaming, small local models for sub-tasks on 8 GB VRAM vs API.
- Book ingestion at scale: entity/event extraction from novels, timelines, coreference, cost control; existing datasets or tools for the Witcher or for literary event extraction.
- Long-run cost and storage for a whole-life campaign; testing/evaluation of interactive narrative systems.
- Tools to consider replacing parts of our stack (our stack: Python, SQLite event log, httpx, Starlette+SSE, OpenRouter cheap models, decision models d1-ultra/Jev). Check `docs/tools.md` entries against what you find.

## 18B — design: what a full world simulation and a whole-life experience need
Topics (not limited to):
- Prior work on emergent narrative and world simulation: simulation-first games (e.g. Dwarf Fortress-style history, The Sims, Crusader Kings, RimWorld storytellers), research systems (social simulation, drama management, story sifting, generative agents and successors), commercial AI RPG/IF products and their postmortems.
- What makes a long life in a simulated world feel meaningful: pacing, long arcs, goals, relationships over years, aging, death, legacy, time skips, boredom, repetition, the "nothing happens" problem, the "everything is about the player" problem.
- Fidelity to a source world: canon adherence vs player freedom, adapting a book world, fan-community views on AI Witcher/Sapkowski-style play.
- Player agency vs world autonomy, NPC lives off-screen, factions, politics, economy, travel, war, magic as world law, the Continent's scale.
- What players of AI RPGs (AI Dungeon, NovelAI, SillyTavern, character.ai, newer AI-native RPGs) complain about most, and which failures our design repeats.
- Produce a list of capabilities we are missing for "live a whole life in Sapkowski's world", each with: why it matters, prior art, how hard, and whether it changes the core design now.

## Output
- Put the full report in your final message (the file tool may refuse report files). Also try to write `reports/research/18A_infrastructure.md` or `reports/research/18B_design.md` and say if it could not be written.
- Readable on a phone: verdict and the ranked recommendation list first, then details with links.
- Branch name and worktree path as absolute paths (only if you committed anything).
