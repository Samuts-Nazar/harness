# Task 3: Core skeleton

Work fully autonomously. Do not ask questions. When something is ambiguous, choose the most reasonable option, record the assumption in `docs/assumptions.md`, and continue.

## Context

Read `docs/decisions.md` first and implement only what it decides. If `reports/code_study/SUMMARY.md` or `reports/experiments/SUMMARY.md` exist, read them and use what applies; they may not exist yet.

## Scope

A Python library with tests and a minimal command-line demo. No UI, no mechanics, no media.

1. Event log
   - Append-only store (SQLite) of typed events with in-game time, location, participants, witnesses, and notability.
   - Current state is derived from the log; snapshots are allowed for speed.
   - Rollback of the last utterance event and of every state change derived from it.

2. Facts and visibility
   - A fact is free-text content plus metadata: source event, in-game time, location, the set of characters who know it and how (witnessed, heard, told), notability.
   - Two stores: immutable canon and mutable campaign.
   - A query API: "facts visible to character C at time T", filtered in code.

3. Context assembly
   - Build an isolated context for one character from its visible facts, its own memory, and its pending intents.
   - Build the narrator context from the full scene state.
   - Unknown facts are excluded, never annotated as unknown.

4. Turn pipeline
   - Narrator call, then one call per speaking NPC with that NPC's isolated context, then an extractor call that returns a JSON diff, then validation in code, then commit to the event log.
   - Behind a provider interface with an OpenRouter implementation and a fake implementation for tests.
   - A slot for typed judgments behind its own interface (Jev later), with a stub implementation.

5. Interruption
   - Streaming output with a cut position.
   - Live interrupt and retroactive interrupt, limited to the last NPC utterance.
   - On cut: the tail is removed from the record, state derived from it is rolled back, an interruption event visible to everyone present is recorded, and the tail is stored as the NPC's private intent.

6. Agents
   - A character becomes a persistent agent after its first interaction with the player.
   - An off-screen update hook with a stub implementation.

## Quality bar

- pytest suite covering: visibility filtering (no leaks across characters), rollback correctness, retroactive interrupt limits, intent retention, and extractor-diff validation (rejects malformed or unauthorized changes).
- Type hints throughout. A README with architecture notes and how to run the demo.
- The demo runs a short scripted scene with the fake provider by default and with OpenRouter when `OPENROUTER_API_KEY` is set.
- Commit in small, working steps.

## Rules

- `data/` stays in `.gitignore`.
- Do not implement anything listed as undecided in `docs/decisions.md`.
