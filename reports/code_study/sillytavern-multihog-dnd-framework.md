# SillyTavern-MultihogDnDFramework

- Repo: https://github.com/MultihogAurelius/SillyTavern-MultihogDnDFramework (cloned, HEAD `d6aab00`, 2026-09-27)
- Language: plain JavaScript (ES modules), a SillyTavern UI extension, about 58k lines. `index.js` 13k, `router.js` 6k.
- **License: GPL-3.0** (`LICENSE`).
- Paths below are relative to the repo root.

## What it is

An RPG engine inside SillyTavern. One narrator LLM writes prose. Background passes (State Tracker, Lorebook Agent "router", Map Updater, Map Evolution, World Progression) read that prose and maintain structured state. Everything is stored in SillyTavern settings and World Info (lorebook) entries, not in an external database.

## 1. How world and character state is represented and stored

There are three separate state stores, and they are not unified.

1. **State Memo.** A single free-text string of `[TAG]...[/TAG]` blocks (`[CHARACTER]`, `[PARTY]`, `[INVENTORY]`, `[COMBAT]`, `[TIME]`, `[QUESTS]` and so on). It lives in `settings.currentMemo`. The memo is the mechanical "source of truth" and is injected into every narrator prompt. The only parsing is regex over tags (`memo-processor.js:444-545` `mergeMemo`, `:407-430` `deduplicateMemo`). Quests are parsed out of the text and back in (`:1115-1327`).
2. **Lorebook (World Info).** NPCs, factions, locations and events are lorebook entries. `router.js` (the Lorebook Agent) creates and updates them. NPC records have `[CORE]` identity fields plus appended, timestamped chronicle/EVENT lines. Entries are scanned by name in the latest narration (`router.js:4624-4692` `scanRecentOutputForPresentNpcs`) and injected as "Present Now".
3. **Dungeon/settlement map documents.** The only truly structured store. `dungeon-reality.js` normalizes a JSON document of `areas` (id, name, knowledge, geometry, connections) and `assets` (id, kind, name, location, state, knowledge, detail, count, duration, cause, actor, `changed_at`), `dungeon-reality.js:39-40`, `:790`. The document is persisted inside a lorebook entry (`router.js:527`, `:733` `persistArchitectDungeonMap`).

Histories are bounded snapshots in settings: 20 log entries, 5 lorebook rollback snapshots (`src/state/history-retention.js:3-4`). The memo and map histories are stored as compressed files through SillyTavern's file API (`README.md`, "Memo and map history storage").

There is **no event log**. State is current-value-overwrite, with snapshots kept for undo.

## 2. How state changes are extracted from model output

Three extraction styles are used. The structured one is the useful one.

- **State Tracker (text diff of sections).** The prompt is `src/state/defaults.js:415-440`. It tells the model to "Output ONLY the changed sections (or NO_CHANGES_DETECTED)", with `[TAG]REMOVED[/TAG]` for deletion. Rule 5 requires re-emitting a whole list block when any item changes. `mergeMemo` then replaces matching blocks wholesale. An empty block is treated as removal (`memo-processor.js:483-492`). If no closed tag is found the output is treated as no-change (`:467-476`).
  - The repo documents that weaker models drop unchanged-but-true blocks in delta mode. It therefore ships a "Full Review Mode" that dumps all modules every pass (`docs/multihogDnDdoc.md`, "Local / weaker State Tracker models").
  - There is no schema validation of the content inside a block. Validation is only structural (tags present).
- **Lorebook Agent (tool-calling loop).** The model emits `Action: tool({json})` lines. `parseTextAction` extracts a balanced-paren JSON argument (`router.js:260-306`). Tools include `grep_lore`, `inspect_book`, `read_entry`, plus write actions such as `UPDATE_CORE`, `UPDATE_APPEARANCE`, `UPDATE_EQUIPMENT` (`applyAction`, `router.js:2842`). Pass rollback exists (`rollbackRouterPass`, `:3661`; `reapplyRouterPass`, `:3768`).
- **Map Updater (typed transactions, validated, with a correction loop).** This is the most relevant part.
  - Prompt: `map-updater-prompt.js:2-` (output contract). It demands exactly one JSON object `{operation_id, operations[1..24], chronicles[]}` or `{"noop":true}`.
  - Each operation is flat: `ADD_ASSET`, `SET_ASSET`, `MOVE_ASSET`, `REMOVE_ASSET`, `ADD_AREA`, `SET_AREA`, `SET_CONNECTION`. Each must carry `cause` (an in-world reason) and an `evidence` level of `CONFIRMED | IMPLIED | AUTONOMOUS | EVOLVED`. DEAD/DESTROYED also requires `actor`.
  - Validation is in code, not prompt: `applyDungeonMapTransaction` (`dungeon-reality.js:2035-`). It rejects unknown fields (`UNKNOWN_FIELD`), bad operation ids by regex (`:2046-2049`), more than 24 operations, duplicate areas/assets, unknown area references, `AUTONOMY_NOT_ALLOWED`, and mutation of the player's current area by autonomous evolution (`PLAYER_BUBBLE_FROZEN`, `:2073-2077`). Errors are structured objects (`mapError(code, path, value, hint, {allowed})`).
  - The apply runs on a clone (`:2038`, `:2062`) and commits only if there are no errors.
  - Correction loop: up to `MAX_CORRECTION_ATTEMPTS = 2` retries. Each retry calls `correctionPrompt(...)` with the previous output and the error list (`map-updater.js:59`, `:350`, loop at about `:500-590`). The same `operation_id` is reused on a retry so the commit is idempotent.
  - The prompt includes worked examples per operation, a durable-vs-transient rule ("never write transient combat into detail"), and a rule that absolute timestamps (`duration`) fire when the authoritative clock passes them.

## 3. How per-character knowledge is separated

**It is not separated per character.** The framework has one omniscient narrator and one omniscient lore store.

- The one place where knowledge is modelled is **player knowledge of the map**: areas are `UNREVEALED | DISCOVERED | VISITED`, assets are `UNREVEALED | SUSPECTED | KNOWN` (`dungeon-reality.js:39-40`). The hidden "reality" map and the player-facing view are one document, filtered at render time by `formatDungeonMapForPlayer` (`:1102-`) and `renderDungeonMapReadableHtml` (`dungeon-map-graph.js:383`). The filter works by `isPlayerVisibleAsset` = KNOWN or SUSPECTED. Hidden assets never appear in the companion's text.
- Knowledge only ratchets up through rules in the Map Updater prompt (a streetscape observation raises landmark assets to KNOWN; a GM-authored rumour yields SUSPECTED; "Player speculation is not evidence", `map-updater-prompt.js:64`).
- NPC records have no "who knows this". "Present Now" injects an NPC's whole lorebook entry whenever the name appears in the last narration, matched by name tokens (`router.js:4693-`). There is no retrieval by witness. The main narrator sees all NPC entries.
- `sysprompt.txt` contains an anti-sycophancy section and bans metagaming on the player side, but this is a prompt instruction, not retrieval isolation.

So filtering happens **at render time to a single viewer (the player)** and there is no filtering at retrieval for NPC contexts.

## 4. How long histories are compressed or retrieved

- The README says outright that **a separate summarizer extension is mandatory** (Summaryception). The framework does not compress the chat itself.
- Lore is compressed by the Lorebook Agent with redundancy handling: bigram Jaccard similarity to find redundant lines (`router.js:4861-4910`), `deduplicateContent` (`:4800`), `protectCoreBlock` to stop the model overwriting `[CORE]` (`:4821`), a "consolidation" pass (`runWorldProgressionConsolidationPass`, `:5839`), and a map "evolution compress" prompt (`map-evolution-compress-prompt.js`).
- Retrieval for the agent is `grep_lore` over books with a "keyring" (`src/state/lorebook-keyring.js:59-81`), plus keyword activation for the narrator. No embeddings.
- `memoForTrackerContext` and `memoForGmContext` (`memo-processor.js:1080-1113`) give different views of the memo to the tracker and to the narrator. This is the only role-specific view.

## 5. Canon / rule consistency checks

- No canon store and no contradiction check against source text. Consistency is by (a) injecting the memo as truth, (b) the prompt "NPC profile persistence": reuse a named NPC's stored combat profile verbatim (`sysprompt.txt`), (c) `protectCoreBlock`.
- **RNG commitment** is a nice anti-hallucination device. Either a pre-seeded dice queue is injected into the prompt, or the narrator must call a `RollTheDice` tool and declare a DC before seeing the result (README, "Hybrid RNG"). The code owns the randomness, not the model. The mechanics themselves are undecided in our design (`docs/decisions.md`, "Mechanics"), so the principle matters, not the dice.
- Map validation (section 2) is the strongest rule-check. It is a real invariant checker (duplicates, containment, frozen player bubble).

## 6. Rollback

- Swipe rollback for the Map Updater: after a successful pass the triggering message is stamped with `extra.rpgMapUpdaterRanForSwipe = swipe_id` and a deep clone of the whole locations book is kept (`map-updater.js:175-181`). If the message's swipe changes, `maybeRollbackMapUpdaterForSwipe` restores the clone (`:411-423`).
- Lorebook rollback is a stack of up to 5 snapshots (`history-retention.js:4`), with created-book deletion logic (`router.js:3661-`).
- Both are snapshot-restore. This is a coarse substitute for the event-log rollback our design requires.

## 7. Fit with `docs/decisions.md`

| Our decision | This project |
|---|---|
| Code owns state, LLM never writes state directly | Partly. Map Updater: model proposes a transaction, code validates and applies. State Memo and lorebook: the model rewrites text and code merges blocks. |
| Append-only event log | No. Overwrite plus snapshots. The map has `cause`/`actor`/`changed_at` per asset and `chronicles`, which is the nearest thing to an event. |
| Epistemic isolation at retrieval | No. Only player-view filtering of the map. |
| Open-ended fact records | Memo is open-ended text. Maps are a fixed schema. |
| Canon store vs campaign store | No. |
| Mechanics undecided | The project is mechanics-heavy (D&D hybrid). Conflicts if adopted. |
| Interruption / retroactive cut | None. Swipe is the nearest analogue. |

## 8. What is reusable

**Directly reusable as design (re-implement; GPL-3.0 means do not copy code into a differently licensed engine):**
- Typed transaction contract: `{operation_id, operations[], cause, evidence}` with an idempotent id and a flat op vocabulary (`map-updater-prompt.js`, `dungeon-reality.js:2035`).
- Validate on a clone, return structured errors with machine-readable `code`, `path`, `hint`, `allowed`, then feed errors back to the extractor for at most two retries (`map-updater.js:59`, `:350`). This maps onto "code validates and stores".
- `evidence` levels and the rule "narrator facts are CONFIRMED, strong entailments IMPLIED, autonomous only with an explicit trigger, never from speculation or an unresolved player attempt". Useful for deciding what the extractor may write.
- "Durable vs transient" filter in the extractor prompt.
- Absolute-timestamp expiry rule evaluated by code against the authoritative clock.
- `noop` as a legal output, so the extractor never invents changes.

**Ideas only:**
- Multi-valued knowledge states (UNREVEALED/SUSPECTED/KNOWN). Our design wants per-character witness sets rather than one viewer enum, but SUSPECTED (rumour vs witnessed) is a useful third state between "knows" and "does not know".
- Separate memo views per consumer (`memoForTrackerContext` vs `memoForGmContext`).
- Role-split models (narrator strong, tracker cheap) and a combat-specific faster model.
- Dedupe of lore by bigram Jaccard.
- Dice commitment before outcome (only if mechanics get decided).

**Conflicts with our decisions / not to adopt:**
- Free-text `[TAG]` memo with regex merge. Fragile (documented failures with weaker models), no typed validation, not an event log.
- Single omniscient narrator that gets every NPC's full entry whenever a name is mentioned. This is exactly the leak our design forbids.
- Snapshot-based rollback.
- Reliance on SillyTavern (World Info, settings storage). We are a standalone app.
- Fixed D&D mechanics baked into prompts.

## 9. License

GPL-3.0. Reading and re-implementing ideas is fine. Copying code into the engine would force the engine to be GPL-3.0 (and task rules forbid copying anyway). Quote only short excerpts.

## Assumptions / limits

- I read the extraction, validation, rollback, knowledge-filter and prompt code paths. I did not read UI, portrait, theming or character-creator code. The 13k-line `index.js` was not read in full, and the runtime flow that triggers the passes (`index.js`, `immersion.js`) was not traced.
- Line numbers are from HEAD `d6aab00`. They were taken from the cloned source.
