# Task 1: Study existing implementations

Work fully autonomously. Do not ask questions. When something is ambiguous, choose the most reasonable option, record the assumption in the report, and continue.

## Context

Read `docs/decisions.md` first. It describes the engine being designed. This task produces reference material for that design; it does not build the engine.

## What to do

Clone and study these projects (search GitHub and arXiv for the current URLs if a link is missing or moved):

1. `MultihogAurelius/SillyTavern-MultihogDnDFramework`: an RPG engine inside SillyTavern with a state tracker and mechanics.
2. `google-deepmind/concordia`: generative agent simulation mediated by a Game Master agent.
3. `role2026/rolememo`: code for DualMem (factual memory separated from persona-conditioned insight).
4. ReverieMem, arXiv 2606.25632 ("Staying In Character: Perspective-Bounded Memory For Book-Based Role-Playing Agents"). Look for released code. If none exists, study the paper itself.
5. `HelpfulToolsCompany/lorevault-extension`: a memory extension with per-character knowledge filtering. Only the client is open; document what it sends and what can be inferred about the server.

For each project, answer from the actual code (cite file paths and line ranges), not from READMEs alone:

- How world and character state is represented and stored.
- How state changes are extracted from model output (prompts, schemas, validation).
- How per-character knowledge is separated, if at all, and where in the pipeline the filtering happens.
- How long histories are compressed or retrieved.
- How canon or rule consistency is checked, if at all.
- What is directly reusable for the engine in `docs/decisions.md`, what is reusable as an idea only, and what conflicts with those decisions.
- License of each project and what it allows.

## Output

- One report per project: `reports/code_study/<project>.md`.
- A synthesis: `reports/code_study/SUMMARY.md` with a comparison table and a ranked list of the most useful patterns for this engine, each linked to the project and file it came from.
- Commit after each completed report.

## Rules

- Do not copy third-party code into the engine. Quote at most short excerpts in reports, with paths.
- If a repository is unavailable, say so in the summary and move on.
