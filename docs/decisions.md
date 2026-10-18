# Harness: Decisions So Far

Status: closed decisions only. Anything not listed here is undecided. Do not design or build undecided parts; if a task needs one, use the smallest placeholder that keeps it swappable and record the assumption.

## Goal

- A world-agnostic engine for single-player AI role-playing games. The Witcher (book canon) is the first world.
- An AI game, not an AI chat. The target is a world simulation, not a game interface with a fixed parameter sheet.
- Own application. Not built on SillyTavern or another chat frontend.
- Played from phone and laptop. Hosting location is not decided.
- The player sees only the story. Background processes (state updates, judgments, checks) are invisible in normal play and visible only in a dev/debug view.
- Quality beats cost and latency. A hallucination over a long campaign costs more than extra seconds or extra API spend.
- Model-agnostic. Several models may serve different subtasks. Prototypes use OpenRouter.
- Other users later: their own hardware or their own API key.
- Prototype language: Python.

## Core architecture

- Code owns world state. LLMs never write state directly.
- Turn loop: a narrator LLM writes the story; an extractor LLM emits a JSON diff of new facts and changes; Jev (TypeSafe's decision model: typed yes/no, choice, or score with probabilities, no text generation) answers narrow typed judgments; code validates and stores.
- State is an append-only event log; current state is derived from it. This is required for rollback (see Interruption).
- Records are open-ended: a fact is free text plus metadata (when, where, who witnessed or heard it, how loud/notable it is). No fixed attribute sheet. The world should remember everything a real world would remember.

## Knowledge and characters

- Epistemic isolation is enforced at retrieval, in code: a character's context contains only facts that character witnessed or plausibly heard. Never pass a fact with an instruction like "you do not know this"; models leak such facts (CHARM benchmark: awareness does not imply compliance).
- Information spreads by notability: quiet events stay with witnesses; loud events travel with time and distance and reach places the player has not visited. Different characters hold different attitudes toward the same event.
- An NPC must not comment on something it had no channel to learn, and should not comment on something it would not care about (salience is a separate judgment).
- Two-level simulation: the world as a whole is simulated cheaply (records plus Jev judgments, no agents). A character becomes a persistent agent once the player has interacted with it. In a scene the agent is fully active (own memory, goals, character). Off-screen it receives cheap periodic updates rather than full simulation.
- For the quality target, each NPC line in a scene comes from a separate call with that NPC's isolated context; the narrator sees everything.

## Canon

- Two stores: an immutable canon store (source texts, world rules, pre-campaign history) and a mutable campaign store (events of play).
- A narrated output that contradicts canon is checked against the campaign store. If a campaign event explains the deviation, it is justified drift and accepted. Otherwise it is a hallucination: reject and regenerate.
- The canon store is too large for any single context; canon reaches judgments and narration through retrieval of relevant passages.

## Interaction

- Interruption is a button. Narration streams at speaking pace so interruption points are meaningful.
- Retroactive interruption: after an NPC finishes, the player may pick a point inside that NPC's last utterance and interrupt there. The window is the last NPC utterance only.
- On interruption, everything after the cut point was never said. Any state extracted from the removed part is rolled back. The event "player interrupted X at words Y" is recorded and is visible to everyone present under normal visibility rules.
- The NPC keeps the unsaid remainder as a private intent (it remembers what it meant to say and may return to it later).
- Time: two modes will be built and compared in play: turn-based (world waits for the player) and flowing (silence counts as time passing).

## Mechanics

- Not decided. Do not implement dice, stats, or success rules.
