# Harness: Decisions So Far

Status: closed decisions only. Anything not listed here is undecided. Do not design or build undecided parts; if a task needs one, use the smallest placeholder that keeps it swappable and record the assumption.

## Goal

- A world-agnostic engine for single-player AI role-playing games. The Witcher (book canon) is the first world.
- An AI game, not an AI chat. The target is a world simulation, not a game interface with a fixed parameter sheet.
- Own application. Not built on SillyTavern or another chat frontend.
- Played from phone and laptop. Hosting location is not decided.
- The player sees only the story. Background processes (state updates, judgments, checks) are invisible in normal play and visible only in a dev/debug view.
- Quality beats latency. Model-agnostic; several models may serve different subtasks.
- Other users later: their own hardware or their own API key.
- Prototype language: Python.

## Model and spending policy

- Paid API calls (OpenRouter) use cheap models only. No exceptions. Allowed: Jev (`typesafe/jev-1.13`, `typesafe/jev-1.14`), `anthropic/claude-haiku-5.5`, `google/gemini-3.1-flash-lite`, `deepseek/deepseek-v4-flash`, `qwen/qwen3.5-9b`, and models of similar or lower price. Sonnet-, Opus-, GPT-5.x-full-class and similar models are never called through the API.
- In development and experiments, any strong-model judging or grading is done by the Claude Code agent itself (reading outputs and judging them in the session), never by a strong model over the API.
- Tests and demos run on a fake provider by default. Network calls happen only when explicitly requested (a `--live` flag).

## Core architecture

- Code owns world state. LLMs never write state directly.
- Turn loop: a narrator LLM writes description; each speaking NPC's line comes from a separate call with that NPC's isolated context; an extractor LLM proposes new facts as a JSON diff; typed judgments decide narrow questions; code validates and stores.
- The narrator never writes NPC speech. It outputs description and which characters speak next. NPC lines come only from NPC calls. A narrator output that contains NPC speech is rejected and regenerated.
- State is an append-only event log; current state is derived from it. This is required for rollback.
- Records are open-ended: a fact is free text plus metadata (when, where, who knows it and how, its source, notability). No fixed attribute sheet.

## Judgments

- Narrow judgments go to Jev first (typed yes/no, choice, or score with probabilities). If Jev's probability for its answer is below 0.8, the same question is escalated to a cheap LLM from the allowed list. Relationship-magnitude judgments go to the LLM directly (Jev was weak there).
- Several questions about the same state are batched into one Jev call.

## Knowledge and characters

- Epistemic isolation is enforced at retrieval, in code: a character's context contains only what that character perceived or was told.
- Every NPC line is checked before it is shown: does it contain a claim this character had no channel to learn? If yes, it is regenerated. This also catches knowledge the model brings from pretraining (the model has read the books).
- Who perceived an event is computed in code from scene state (who is present, what is visible or audible to them), not taken from the extractor. The extractor proposes only the fact text. Characters present perceive observable actions described in narration (a drawn sword), not only spoken lines.
- Every piece of knowledge records its source ("heard from X"). The player character is a being of the world like any other: information from the player character is treated exactly like information from anyone else. How much a character believes something depends on that character's trust and relationship with the source; the belief model itself is not decided yet.
- Information spreads by notability: quiet events stay with witnesses; loud events travel with time and distance and reach places the player has not visited. Different characters hold different attitudes toward the same event. Attitudes are stored separately from facts and point to the facts they are about.
- An NPC must not comment on something it had no channel to learn, and should not comment on something it would not care about (salience is a separate judgment).
- Two-level simulation: the world as a whole is simulated cheaply (records plus judgments, no agents). A character becomes a persistent agent once the player has interacted with it. In a scene the agent is fully active (own memory, goals, character). Off-screen it receives cheap periodic updates.

## Character memory and live state

- Each character has its own memory, stored as per-character files linked to each other (Obsidian-style wikilinks between characters, places, events). These files are the AI's memory only, written and read by the engine, not a user-facing document. They are derived from the event log, which stays the source of truth for rollback.
- A user-facing chronicle or database, if any, is a separate thing adapted for the player and is not decided.
- Each character has a live state carried from scene to scene: wounds and injuries, clothing and its condition, inventory and equipment, and internal changes. Each element is either observable or hidden. A state element persists until an event changes it (a drawn sword stays drawn until sheathed).
- When characters share a scene, each perceives the others' observable state (a man walking into an inn with a bloody drawn sword is seen by everyone there). Whether a given observer reacts is a salience judgment per observer. Hidden state is not perceived until it becomes observable.

## Canon

- Two stores: an immutable canon store (source texts, world rules, pre-campaign history) and a mutable campaign store (events of play).
- A narrated output that contradicts canon is checked against the campaign store. If a campaign event explains the deviation, it is justified drift and accepted. Otherwise it is a hallucination: reject and regenerate.
- The canon store is too large for any single context; canon reaches judgments and narration through retrieval of relevant passages.

## Interaction

- Interruption is a button. Narration streams at speaking pace so interruption points are meaningful.
- Retroactive interruption: after an NPC finishes, the player may pick a point inside that NPC's last utterance and interrupt there. The window is the last NPC utterance only.
- On interruption, everything after the cut point was never said. Any state extracted from the removed part is rolled back. The event "player interrupted X at words Y" is recorded and is visible to everyone present under normal perception rules.
- The NPC keeps the unsaid remainder as a private intent (it remembers what it meant to say and may return to it later).
- Time: two modes will be built and compared in play: turn-based (world waits for the player) and flowing (silence counts as time passing).

## Mechanics

- Not decided. Do not implement dice, stats, or success rules.
