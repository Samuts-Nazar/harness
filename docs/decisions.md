# Harness: Decisions So Far

Status: closed decisions only. Anything not listed here is undecided. Do not design or build undecided parts; if a task needs one, use the smallest placeholder that keeps it swappable and record the assumption.

## Goal

- A world-agnostic engine for single-player AI role-playing games. The Witcher (book canon) is the first world.
- An AI game, not an AI chat. The target is a world simulation, not a game interface with a fixed parameter sheet.
- The long-term target: the player plays only their own character and can live that character's whole life in Sapkowski's world, doing no less than what the saga contains.
- Open simulation: the player can attempt anything a person could do in that world. No action is a special mechanic or a dedicated feature (starting a rumour, bribing, lying are ordinary actions).
- World behaviour follows reality, judged per situation by scale and circumstances, not by fixed rules. Examples: news may arrive before the hero or never arrive; rumours may distort while the truth and several versions coexist; whether a rumour has a concrete source, and how fast a reputation fades, depends on how big the event was and what happened since.
- Own application. Not built on SillyTavern or another chat frontend.
- Played mainly from the phone; laptop also supported. Hosting location is not decided.
- The player sees only the story and the player-facing interface (own character panel, controls). Background processes (state updates, judgments, checks) are invisible in normal play and visible only in a dev/debug view.
- Quality beats latency. Model-agnostic; several models may serve different subtasks.
- Other users later: their own hardware or their own API key.
- Prototype language: Python.

## Model and spending policy

- Paid API calls use cheap models only: input price at most 0.60 USD and output at most 2.50 USD per million tokens. Flagship-class models are never called over the API.
- No Anthropic models in the engine.
- The model for each role is chosen by a bake-off on our own tasks, from the live OpenRouter catalog, never from memory. The bake-off is re-run when notable new models appear. Current choices live in `docs/tools.md`.
- Free (`:free`) models may be tested and used, but never as the only option for a role, because they disappear.
- Strong-model judging in development is done by the Claude Code agent itself, never over the API.
- Tests and demos use the fake provider by default; network only with `--live`.

## Core architecture

- Code owns world state. LLMs never write state directly.
- Turn loop: the outcome of what the player attempts is judged first (see Outcomes); then a narrator LLM writes description; each speaking NPC's line comes from a separate call with that NPC's isolated context; an extractor LLM proposes new facts as a JSON diff; typed judgments decide narrow questions; code validates and stores.
- Player-facing text must not follow a visible pattern. Narrator and NPC calls write free prose only, with no JSON contract on creative calls. Who speaks next and which observable actions happened are derived by separate steps (a scene director using typed judgments, and the extractor).
- The narrator never writes NPC speech. NPC lines come only from NPC calls. A narrator output that contains NPC speech is rejected and regenerated. An NPC call may write that NPC's own small actions and manner around its speech (a glance, a lowered voice), never anyone else's actions or speech, and never the player character's.
- State is an append-only event log; current state is derived from it. This is required for rollback.
- Records are open-ended: a fact is free text plus metadata (when, where, who knows it and how, its source, notability). No fixed attribute sheet; panel categories are tags on open records, not a schema.
- Every record carries two times: in-world time (when it happened or became true) and log time (when it was written). Records computed lazily about the past (what an NPC heard on day 12, written on day 40) are legal.
- A record derived from another record or from a piece of text stores a link to its origin. Rollback removes everything derived from removed text, directly or transitively.
- The language of records is an engine detail. Names, places and titles are never distorted: one canonical form per name (the Ukrainian translation's form for the Witcher), applied in code when records are written and when context is rendered, so every model always sees one form.

## Judgments

- Narrow judgments go to a typed decision model first (yes/no, choice, or score with probabilities). If its probability for its answer is below 0.8, the same question is escalated to a cheap LLM. Relationship-magnitude judgments go to the LLM directly.
- Several questions about the same state are batched into one call.
- Decision models cannot write text; open questions are re-expressed as choices from a closed list.

## Outcomes

- The player decides what the character does and attempts. Whether it works is judged by the world per situation, before any prose is written. No dice, no stats, no success tables: one judgment that may say yes, partly or no, with its reason stored.
- Failure is real and has consequences in world state. The death of the player character ends the campaign.
- A campaign may mark the player character as unbounded (used for the Vizima pilot): then the player's own acts always happen as declared, and only the world's reactions are judged.

## Player character

- The player character is the player's persona. Only the player decides what the character says, does, believes and intends. No component writes these for the player.
- The world sets the character's body (wounds, pain as a physical signal, poison, fatigue, intoxication, illness), senses (what is seen and heard, including hallucinations) and external facts (being wanted, robbed). Emotions, how an event affected the character, trauma, attitudes and meaning belong to the player only; the narrator never assigns them, and the character's inner state in the panel comes only from what the player wrote. NPCs react to the character's observable behaviour, not to an assumed inner state. The turn assistant suggests actions, not feelings.
- Mind magic (a sorceress's control, a djinn's wish) is a world law like poison: only from an explicit in-world cause, recorded as a timed effect. Whether the character resists is judged per situation (the caster's power, the target's nature, circumstances), not by a fixed rule. While under it, the player still writes, as attempts to resist and remnants of the character's own mind; how much breaks through depends on the spell's strength (under a strong spell the body follows the caster and the narrator describes it). Feelings induced by the spell are part of the effect; after it ends, the character's attitude is the player's again.
- Toward everyone else, the player character is a being of the world like any other: information from the player character is treated exactly like information from anyone else.
- The player character's observable appearance and hidden traits come from the player's character file at campaign start, as live state.
- Player input: text in `*asterisks*` is an action (observable under normal perception rules), the rest is speech. The player's words are kept verbatim.

## Knowledge and characters

- Epistemic isolation is enforced at retrieval, in code: a character's context contains only what that character perceived, was told, or knows from their own life. The same applies to collectives (towns, factions): they react to their version of an event, not to the truth. The narrator speaks from the player character's perception and gets the same filter.
- Background knowledge from life: a character knows what follows from their life (age, occupation and years in it, place, standing, connections). A child knows little; an innkeeper of ten years knows locals, prices and many rumours, often distorted; an aristocrat knows the court and politics. It is computed lazily when a topic comes up and stored as a knowledge record with source "own life" and an in-world time, so the answer stays consistent. Rumour versions come from what reached that place. Secrets never come through this channel.
- A name is knowledge like any other: a character knows another's name only through a channel (introduction, overhearing, being told, prior acquaintance, canon). Until then the person is rendered by what can be observed.
- Every NPC line and every narration is checked before it is shown: does it contain a claim or a name the speaker had no channel to learn? If yes, it is regenerated. This also catches knowledge the model brings from pretraining (the model has read the books).
- What an NPC says is stored as "X said Y" (an asserted claim), never as world truth; the truth is a separate record. If the world has not decided the matter yet, the truth is settled lazily when it matters, by plausibility (what is known about the speaker, their source, the regional situation).
- Who perceived an event is computed in code from scene state (who is present, what is visible or audible to them), not taken from the extractor. The extractor proposes only the fact text. Characters present perceive observable actions described in narration (a drawn sword), not only spoken lines.
- Every piece of knowledge records its source ("heard from X"). How much a character believes something depends on that character's trust and relationship with the source; the belief model itself is not decided yet.
- Information spreads by notability: quiet events stay with witnesses; loud events travel with time and distance and reach places the player has not visited. Different characters hold different attitudes toward the same event. Attitudes are stored separately from facts and point to the facts they are about.
- An NPC must not comment on something it had no channel to learn, and should not comment on something it would not care about (salience is a separate judgment).
- Two-level simulation: the world as a whole is simulated cheaply (records plus judgments, no agents). A character becomes a persistent agent once the player has interacted with it. In a scene the agent is fully active (own memory, goals, character). Off-screen it receives cheap periodic updates; how detailed these are depends on measured cost.

## Character memory and live state

- Each character has its own memory, stored as per-character files linked to each other (Obsidian-style wikilinks between characters, places, events). These files are the AI's memory only, written and read by the engine, not a user-facing document. They are derived from the event log, which stays the source of truth for rollback.
- A user-facing chronicle or database, if any, is a separate thing adapted for the player and is not decided.
- Each character has a live state carried from scene to scene: body (wounds, scars, fatigue, hunger, thirst, illness, poisons and toxicity, intoxication, pain), timed effects, appearance (clothing and condition, dirt and blood, visible marks), equipment and its condition, inventory with location and money, companions, standing (wanted, disguised, reputation by place), posture and action, inner state. All of it is in scope from the first version, because NPCs must be able to react to it.
- Each element is either observable or hidden. A state element persists until an event changes it (a drawn sword stays drawn until sheathed).
- When characters share a scene, each perceives the others' observable state. Whether a given observer reacts is a salience judgment per observer. Hidden state is not perceived until it becomes observable.
- The player's panel shows the player character's state as the character perceives it (the same epistemic filter applied to the own body), as short chips plus a few sentences of prose.
- Character portraits: an NPC who matters has a portrait (core, stances by relationship rung, switches, a hidden thing and its leaks, voice, bans). Canon people have hand-written portraits in the world folder, bound per start point; invented NPCs who become named or recurring, and package people with free-text `portrait_text`, get a short generated portrait (one cheap call, cached in the campaign, never remade). Background extras keep the cheap profile.
- Each NPC call gets a slice of the portrait, at most 260 words, passed through the speaker's knowledge mask; a portrait never adds facts the NPC has not learned. Stance choice is code on the fast lane.
- Relationship with the player: a ladder stranger → client → ally → close → lover (and enemy), with warmth and trust, stored as events in the log (rolls back with its cause). Switches are yes/no questions judged on the slow lane; code supplies the size, with pacing so closeness is earned (caps per turn, repeat dampening, scene changes required for close and lover, slow decay, grudges that last). Hidden things leak only at enough trust, rationed per scene.

## Canon

- Two stores: an immutable canon store (source texts, world rules, pre-campaign history) and a mutable campaign store (events of play).
- Canon is the world's starting state and its gravity, not a script. Canon events happen while their preconditions hold; when the player changes them, the event is re-judged (as written, differently, or not at all). The further from the player, the longer the world follows the books. Because of the butterfly effect, most of what happens alongside the saga, and everything after it, is the campaign's own invention.
- A narrated output that contradicts canon is checked against the campaign store. If a campaign event explains the deviation, it is justified drift and accepted. Otherwise it is a hallucination: reject and regenerate.
- The canon store is too large for any single context; canon reaches judgments and narration through retrieval of relevant passages.
- Canon pull is proportional to the deviation: small acts do not change big events; large or logically connected changes can, when the consequence is logical and fitting.
- The books get a one-off structured ingestion (who, what, when, where, who knew and how, how others reacted) to make later play cheaper and more accurate. It is piloted on one arc first (book "Останнє бажання": "Голос розуму-1" and the story "Відьмак"), checked record by record and played; only when the result satisfies the user does it extend to the rest of book 1, then the whole saga.

## Outsider campaign (plan 1, 2026-10-27)

Spec `docs/superpowers/specs/2026-10-26-outsider-campaign-design.md`; plans 2 and 3 are not built.

- Explicit inventory: a package may list the player's items (up to 80) with `where` (worn, in hand, pocket, or a container's name), condition, notes, `container`, `open`, `content`. Each listed item has a stable id (`item:<slug>`) and changes match by id; location is state (`worn`, `in_hand`, `in:<container id>`, `on:<place>`, op `move`), and observability is derived: what lies in a closed container is perceived only by its owner until it is opened (op `open`, then the usual observation). Without a list, the derived items and their caps stay.
- Self-awareness at retrieval: a state element may be unaware to its owner (`aware: false`). The one function that renders a character's state for any composer leaves it out for the owner (panel, own context, assistant, outcome prose) and keeps it for everyone else's perception and for the debug view. A `realize` event makes it aware.
- Timed effects: an element may carry `until` (in-world time); `World.tick` removes it by an ordinary state event, so rollback works.
- Reading is an ordinary action. When the player holds an item with `content`, a judgment per turn decides whether he reads it; a file is grepped for terms that one cheap call expands from the request (short inline text is read whole), and one cheap reader call says what it says, close to the text. The clock moves by the duration judgment. The result becomes the reader's own records with source `read: <item id>` (channel READ, accepted by the unknown-claim check and "how does he know that"), and the player sees it as its own block «Прочитано · <item>». Nobody else present learns what was read.
- Magic sense: a character (portrait or profile) or the wearer of an item may have the `magic` sense. Elements perceptible only by magic (an aura, a spell, a latent Source) are observed only by those who have it, through the same observation and salience path. A package's `player.latent` is such an element, unaware to the player.
- Canon starts go through a general builder (`builder: canon`: any canon place and store; the Vizima builder stays). A canon event whose participant is in the player's scene at another site is deferred until that person is at the event's place, in story order per person, at most 6 released per world step, and retired unfired after 14 story days.
- Canon extraction for further books is done by Claude Code subagents in development, by `reports/canon_be/EXTRACTION.md`, with no API spend; the ingestor validates and loads their JSON.
- The player is free to go anywhere. Canon deferral never forces or restricts him; it only delays book scenes whose people are with him elsewhere.
- A label is never a name form: a canon person a character has not learned the name of is shown by a description (a portrait's `look`, or an alias that describes), never by an alias that is a variant or misspelling of the name.
- A person the narration describes who is already present is not admitted again: by all distinctive words of their label in code, else by a typed `cast_same_person` choice; generic words never merge two people, and without a verdict the newcomer is admitted.
- Taking an item out of a closed container opens it (a `move` out of it implies `open`); a `remove` means the item is gone and is never reinterpreted.
- A read's request is the lookup topic of the turn (`lookup_topic`), not the turn's physical actions.
- Only an outsider remembers another world: a package's `player.knows` gets the other-world source when `player.outsider: true` or `latent` is set; any other package keeps «own life».
- An item's condition, notes and power are shown to its owner only, as a short suffix (at most 160 characters) on the owner's own state lines for the narrator and the assistant; observations and other people's prompts keep the bare name.
- The extractor is told which elements are unaware to their bearer; `realize` only when the text shows the bearer told of it or perceiving it himself.
- A content file comes from the project's `data/` only (never the campaign folder).

## Interaction

- Interruption is a button. Narration streams at speaking pace so interruption points are meaningful.
- "Said" means delivered to the player (displayed or heard), not generated.
- Retroactive interruption: after an NPC finishes, the player may pick a point inside that NPC's last utterance and interrupt there. The window is the last NPC utterance only, and it closes as soon as the next event starts (the player sends a turn, another NPC speaks, or the world acts). Until then that utterance is not final: its facts are stored but can be rolled back.
- On interruption, everything after the cut point was never said. Any state extracted from the removed part is rolled back. The event "player interrupted X at words Y" is recorded and is visible to everyone present under normal perception rules.
- The NPC keeps the unsaid remainder as a private intent (it remembers what it meant to say and may return to it later).
- Choices are final: rewind and "what if" exist only in the debug view.
- Model errors are not the player's consequences. A "model error" action in normal play requires the player to say what was wrong; only the last world output is regenerated with that explanation, the player's turn stays. The explanation is stored per campaign and fed to later generations so the error is not repeated.
- "How does he know that?": the player can mark an NPC line as knowledge the character could not have. The engine checks the speaker's channels. No channel: the line is treated as a model error (regenerated, explanation stored). A channel exists: the player is told how the character knows it; in play only the kind of channel and a rough time are shown, the full event is behind a "show (spoiler)" tap and in the debug view.
- A model error found later in an old record is fixed by a correction, not a rewind: the record is marked wrong, records derived from it become stale and are recomputed lazily; the player's choices and what already happened stay.
- Scene modes. Base mode: no queue or rounds; after each event a scene director decides who, if anyone, speaks or acts, from character, situation, who was addressed and interest; silence is possible; the world waits for the player as long as needed. Live scene: a toggle that can be switched on or off mid-scene; real time runs and nobody waits; characters may arrive, leave on their business or get distracted; the player presses "Говорю" to speak or act; silence when addressed is the character's silence in the world, and NPCs react to it. While the player types after "Говорю", the world gives a natural pause (an impatient NPC may cut in); its length is tuned in play.
- In both modes the world stops when the app is in the background.
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
