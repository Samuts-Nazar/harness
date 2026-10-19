# Harness: Decisions So Far

Status: closed decisions only. Anything not listed here is undecided. Do not design or build undecided parts; if a task needs one, use the smallest placeholder that keeps it swappable and record the assumption.

## Goal

- A world-agnostic engine for single-player AI role-playing games. The Witcher (book canon) is the first world.
- An AI game, not an AI chat. The target is a world simulation, not a game interface with a fixed parameter sheet.
- Open simulation: the player can attempt anything a person could do in that world. No action is a special mechanic or a dedicated feature (starting a rumour, bribing, lying are ordinary actions).
- World behaviour follows reality, judged per situation by scale and circumstances, not by fixed rules. Examples: news may arrive before the hero or never arrive; rumours may distort while the truth and several versions coexist; whether a rumour has a concrete source, and how fast a reputation fades, depends on how big the event was and what happened since.
- Own application. Not built on SillyTavern or another chat frontend.
- Played mainly from the phone; laptop also supported. Hosting location is not decided.
- The player sees only the story and the player-facing interface (own character panel, controls). Background processes (state updates, judgments, checks) are invisible in normal play and visible only in a dev/debug view.
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
- Records are open-ended: a fact is free text plus metadata (when, where, who knows it and how, its source, notability). No fixed attribute sheet; panel categories are tags on open records, not a schema.
- Every record carries two times: in-world time (when it happened or became true) and log time (when it was written). Records computed lazily about the past (what an NPC heard on day 12, written on day 40) are legal.
- A record derived from another record or from a piece of text stores a link to its origin. Rollback removes everything derived from removed text, directly or transitively.

## Judgments

- Narrow judgments go to Jev first (typed yes/no, choice, or score with probabilities). If Jev's probability for its answer is below 0.8, the same question is escalated to a cheap LLM from the allowed list. Relationship-magnitude judgments go to the LLM directly (Jev was weak there).
- Several questions about the same state are batched into one Jev call.
- Jev cannot write text; open questions are re-expressed as choices from a closed list.

## Player character

- The player character is the player's persona. Only the player decides what the character says, does, believes and intends. No component writes these for the player.
- The world can fully affect the character (wounds, poison, fear, magic, perception) and through it the player.
- Toward everyone else, the player character is a being of the world like any other: information from the player character is treated exactly like information from anyone else.

## Knowledge and characters

- Epistemic isolation is enforced at retrieval, in code: a character's context contains only what that character perceived or was told. The same applies to collectives (towns, factions): they react to their version of an event, not to the truth.
- Every NPC line is checked before it is shown: does it contain a claim this character had no channel to learn? If yes, it is regenerated. This also catches knowledge the model brings from pretraining (the model has read the books).
- Who perceived an event is computed in code from scene state (who is present, what is visible or audible to them), not taken from the extractor. The extractor proposes only the fact text. Characters present perceive observable actions described in narration (a drawn sword), not only spoken lines.
- Every piece of knowledge records its source ("heard from X"). How much a character believes something depends on that character's trust and relationship with the source; the belief model itself is not decided yet.
- Information spreads by notability: quiet events stay with witnesses; loud events travel with time and distance and reach places the player has not visited. Different characters hold different attitudes toward the same event. Attitudes are stored separately from facts and point to the facts they are about.
- An NPC must not comment on something it had no channel to learn, and should not comment on something it would not care about (salience is a separate judgment).
- Two-level simulation: the world as a whole is simulated cheaply (records plus judgments, no agents). A character becomes a persistent agent once the player has interacted with it. In a scene the agent is fully active (own memory, goals, character). Off-screen it receives cheap periodic updates; how detailed these are depends on measured cost (not decided).

## Character memory and live state

- Each character has its own memory, stored as per-character files linked to each other (Obsidian-style wikilinks between characters, places, events). These files are the AI's memory only, written and read by the engine, not a user-facing document. They are derived from the event log, which stays the source of truth for rollback.
- A user-facing chronicle or database, if any, is a separate thing adapted for the player and is not decided.
- Each character has a live state carried from scene to scene: body (wounds, scars, fatigue, hunger, thirst, illness, poisons and toxicity, intoxication, pain), timed effects, appearance (clothing and condition, dirt and blood, visible marks), equipment and its condition, inventory with location and money, companions, standing (wanted, disguised, reputation by place), posture and action, inner state. All of it is in scope from the first version, because NPCs must be able to react to it.
- Each element is either observable or hidden. A state element persists until an event changes it (a drawn sword stays drawn until sheathed).
- When characters share a scene, each perceives the others' observable state. Whether a given observer reacts is a salience judgment per observer. Hidden state is not perceived until it becomes observable.
- The player's panel shows the player character's state as the character perceives it (the same epistemic filter applied to the own body), as short chips plus a few sentences of prose.

## Canon

- Two stores: an immutable canon store (source texts, world rules, pre-campaign history) and a mutable campaign store (events of play).
- A narrated output that contradicts canon is checked against the campaign store. If a campaign event explains the deviation, it is justified drift and accepted. Otherwise it is a hallucination: reject and regenerate.
- The canon store is too large for any single context; canon reaches judgments and narration through retrieval of relevant passages.
- Canon pull is proportional to the deviation: small acts do not change big events; large or logically connected changes can, when the consequence is logical and fitting.
- The books get a one-off structured ingestion (who, what, how others reacted) to make later play cheaper and more accurate.

## Interaction

- Interruption is a button. Narration streams at speaking pace so interruption points are meaningful.
- "Said" means delivered to the player (displayed or heard), not generated.
- Retroactive interruption: after an NPC finishes, the player may pick a point inside that NPC's last utterance and interrupt there. The window is the last NPC utterance only.
- On interruption, everything after the cut point was never said. Any state extracted from the removed part is rolled back. The event "player interrupted X at words Y" is recorded and is visible to everyone present under normal perception rules.
- The NPC keeps the unsaid remainder as a private intent (it remembers what it meant to say and may return to it later).
- Choices are final: rewind and "what if" exist only in the debug view.
- Model errors are not the player's consequences. A "model error" action in normal play requires the player to say what was wrong; only the last world output is regenerated with that explanation, the player's turn stays. The explanation is stored per campaign and fed to later generations so the error is not repeated.
- Time: two modes will be built and compared in play: turn-based (world waits for the player) and flowing (silence counts as time passing). In both, the world stops when the app is in the background. A world that lives without the player is a future idea.
- Quick reactions while an NPC speaks and tappable names and items in the text are to be prototyped and judged in practice.

## Turn assistant

- A button gives action options fitting the situation; choosing one writes the line and action; the player then accepts, gives feedback, edits by hand, proposes an own option, or modifies a suggested one.
- Parts the player praised stay verbatim unless the player changes them.
- The assistant sees only what the player character knows. Drafts are not part of the log until the player sends them.
- An optional, switchable note learns the player's play style (communication, actions, character), not writing style. The player can read and edit it.

## Settings

- Content limits: set in a conversation at campaign start; during play, buttons pause, veil (happens off-screen) and skip (the scene passes in one sentence).

## Not in the first version

- Music, voice, images.

## Mechanics

- Not decided. Do not implement dice, stats, or success rules.
