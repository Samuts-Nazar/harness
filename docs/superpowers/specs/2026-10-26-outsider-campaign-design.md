# Outsider campaign: engine capabilities

Status: draft for the builder check and the user's approval. Nothing here is built.
Source: the lead brief "engine capabilities for an outsider campaign" and the user's answers in chat on 2026-10-26.

## Intent

The user wants to play himself: a person from our world (ML/computer engineer, athletic) who lands at Yennefer's feet on the road to the temple of Melitele in Ellander, in the period of «Кров ельфів», and arrives at the temple with her. He carries one backpack of modern and near-future equipment, has a latent magical Source nobody knows about, and over months wants to collect data about magic, train models on it, and build an "artificial magical intelligence". A slow romance with Yennefer is part of the arc.

The engine today cannot hold this campaign: the start inventory is capped at 8 observable and 6 hidden items; there is no way for a character to read an item; there is no sense of magic; devices have no charge or wear; nothing records practice or datasets; the canon store covers only «Останнє бажання».

## Names (canonical forms, from `worlds/witcher/glossary.json` and the text)

Цірі, Йеннефер, Неннеке, Мелітеле (the temple is «храм Мелітеле»), Елландер. The user's spellings «Цирі» and «Єніфер» are listed as wrong forms in the glossary; the engine uses the canonical ones. The glossary has no entries for Неннеке, Мелітеле and Елландер yet (counts in the text: 144, 70, 53); they are added.

## Closed decisions this must fit

No stats, no dice, no success tables; one judgment per situation. Code owns state. Epistemic isolation. Records are open-ended facts with two times. Cheap models only over the API (`docs/decisions.md`). `data/` is never committed or quoted at length. Every design below is built from existing mechanisms; where a mechanism is missing it is named.

## Goals / non-goals / anti-goals

Goals: the campaign above is playable end to end: start, backpack, reading the saga file, Yennefer noticing his Source, devices with charge, recorded data, growth from practice.
Non-goals: local models for devices (deferred, the provider stays swappable); images; voice; ingesting the whole saga; new rules for combat or magic power.
Anti-goals: any number that decides an outcome; devices voiced by the narrator; the character knowing anything from the file before he reads it; any feature the user did not ask for (no content-check machinery).

## What the code looks like today (verified 2026-10-26)

- Live state is a replay of `STATE_CHANGE` events; key is the exact tuple `(category, item)`; categories are fixed (`harness/models.py:29`); ops are add/remove/reveal/hide (`harness/state.py`). A one-character difference in the text drops the change.
- Start state comes from `derive_traits` (one cheap call, caps in `app/character.py:27`) and `seed_player_state` (`app/campaigns.py:306`), called from `app/newgame.py:851`.
- **The player panel has no self-awareness filter today**: it lists every element of the player's own state, hidden ones included (`app/game.py:326`). The Source cannot be hidden from its owner until this changes.
- There are no timed effects: no expiry field, nothing ticks state (`harness/world/world.py:691` `tick` is where it would go).
- Perception: a scene is one room, present characters see and hear; observations of observable state go through `_observe` and one salience judgment per NPC (`harness/pipeline.py:1166`).
- Channels accepted by the unknown-claim check and "how does he know that": FACT, NAME, SEEN, STATE, BACKGROUND (`harness/knowledge.py:277`). Source `own life` is a literal string.
- Content limits are prompt rules only; no output check exists (`docs/assumptions.md` GP-4).
- Canon ingestion reads `data/witcher_books.txt` lines 7–694 only (`harness/canon/ingest.py:29`). «Кров ельфів» is lines 15505–22101 (the next book starts at 22101). Canon starts are built by `pilot.CanonStart` with `builder: vizima` (`worlds/witcher/start_points.yaml`).

## Design

### D0. Foundations (needed by everything below)

1. **Item identity.** Every explicit item gets a stable id (`item:<slug>`, unique in the campaign). State changes for such items match by id, not by text, so a 25-item backpack does not depend on the extractor repeating a string exactly. The extractor still proposes text; code resolves it to an id by a cheap normalised match, and an unresolved text is dropped as today. Text-keyed items for characters without an explicit list keep working unchanged.
2. **Location as state.** A state element may have `location`: `worn`, `in_hand`, `in:<container id>`, `on:<place>`. New op `move`. Observability is derived, not stored: worn and in-hand items are observable; an item inside a closed container is hidden from everyone but the owner; opening a container (an event) makes its contents observable under normal perception and runs the usual `_observe`.
3. **Self-awareness.** Each element has `aware` (default true). The player panel and the player-character context show only aware elements. Unaware elements stay in the engine and in other characters' perception. An event `realize` flips `aware` (the channel is recorded: told by someone, instrument reading, spontaneous manifestation). Debug view shows everything.
4. **Timed effects.** An element may carry `until` (in-world time). `World.tick` and time skips remove or change expired elements by an ordinary state event, so rollback works. Used by charge, wear, spells, and the Source's manifestations.

### D1. Explicit starting inventory (brief item 1)

Package gets `player.inventory`: a list of items, each `{name, where, hidden (optional override), condition, notes, container (bool), open (bool), power (optional)}`. `where` is worn / in hand / pocket / «рюкзак» (any other item name that is a container). Limit 80 items; names up to 80 characters; notes up to 400 characters. Notes hold capabilities and contents that the owner knows; other characters perceive only the name, condition and what the item visibly does.
Without an explicit list the derived extraction and its caps stay as they are. With one, derivation still runs for appearance and the label strangers use, but not for items.
Docs updated: `docs/new_game_instruction.md`, `docs/game_package_example.yaml`.

### D2. Readable items and the saga file (brief items 2 and 9)

- An item may have `content`: either inline text (a letter, a note) or a file (`data/witcher_books.txt` for the laptop file) searched on demand. The file is read at play time and never copied into the repo or the campaign store.
- **Read is an ordinary action.** The player says what he looks for. One cheap typed call expands the request into search terms: forms of the word and its aliases and neighbouring concepts (for «джин»: джин, джини, джина, бажання, лампа… and for «елементаль»: елементаль, дух стихії, дух, джин…). Code greps the file for those terms (Ukrainian declension handled the way `harness/glossary.py` handles stems), takes each hit with surrounding sentences, de-duplicates and caps the result. One cheap reader call reads the hits for the question and returns what the passage actually says, close to the text, with nothing added. Not limited to джини or to any set of characters: the terms come from the request.
- **Time.** Reading costs in-world time proportional to the characters read, using the clock's duration buckets (`harness/world/clock.py`); the figure is judged by the duration judgment from the amount, not hard-coded per request.
- **Knowledge.** What was read becomes the reader's knowledge records with source `read: <item id>` and the in-world time. New channel kind READ in `harness/knowledge.py`; the unknown-claim check and "how does he know that" accept it, and keep rejecting anything the character never read. Anyone else who reads or is shown the item gets the same channel under their own name (Yennefer reading her own life is an ordinary event, and the salience judgment and her portrait decide the reaction).
- **His own vague memory** is a different source, `own life, from another world`, written from `player.knows` (extends GP-4b). It never carries details he has not been given. The file is the only place exact details come from.
- Refinement left for later: an index or embeddings over the file if grep is too slow or too noisy.

### D3. Devices (brief items 3 and 4)

- A device is an item with a `device` marker and its own **log**: records linked to the item (typed text, loaded files, lens recordings, what was heard). Not a persistent agent and not an NPC.
- Output (the oracle model, code model, vision model, translator) comes from a separate cheap call that sees only the device's log plus general knowledge of our world, never the Continent unless it is in the log. The output goes through the unknown-claim check with the device's log as the only channel. Output is observable to those who can see the screen or hear the speaker.
- **Translator.** Its log counts what it has heard in each language (records with language and amount). How good it is now is a judgment from those records, not a number. It starts at zero.
- **Charge** is a closed word state on the device: full, high, half, low, empty (a state tag set by judgment, not a score that decides an attempt). Use lowers it by a judgment of duration and kind; the solar panel and power station raise it by a judgment of weather, season, time of day and hours spent (the world clock exists). An empty device cannot be used; the extractor and judgments are told so.
- **Wear.** Condition is free text with judgments on events (water, cold, fall, rough handling); damage is repairable or not by judgment from the means available in the world.
- Local models for devices: out of scope now. The call goes through the existing provider layer, so a local provider can be swapped in later.

### D4. Data and training (brief item 5)

- A **recording** is a fact record with provenance fields in free text plus ids: what was measured, by which device, where, in-world time, during what (which spell, which caster), who labelled it and how reliably.
- A **dataset** is an item on the laptop that lists recording ids and keeps a lazily rewritten summary (how many records, what variety, how reliable the labels), computed by code as plain text from the records, never as a tier.
- **Training** is an in-world process: start event, duration and energy judged from dataset size and device, result event. The trained model is an item that points to its dataset.
- What a trained model can do is judged per situation from the summary and the task asked of it. The records live in the campaign store tagged by item id so retrieval stays cheap in long play.

### D5. Magic perception and the latent Source (brief item 6)

- Characters can have the `magic` sense: sorceresses, mages, a witcher's medallion as an item that grants it to its wearer. Elements can be perceptible through magic only (an aura, an active spell, a Source).
- On scene entry and on change, `_observe` also runs for the magic-sense observers over magic-perceptible elements, with the same salience judgment. Yennefer notices his Source at the first scene through this path, before he does.
- His Source is an element with `aware: false`, magic-perceptible, with a note that it is not of this world and stands out to anyone with the sense. It becomes aware through `realize` events: Yennefer says it, a sensor registers it, or a spontaneous manifestation. Manifestation, practice and growth are judged per situation from his records. Masking is a skill learned later by the same mechanism.
- Chaos in the untrained is a danger judged in the situation, not a rule.

### D6. Growth from practice (brief item 7; user approved 2026-10-26)

Practice records: what was trained, with whom, how long, how hard, in-world time. Written when the extractor sees training and at rests and time skips. At rests and skips one typed judgment per skill asks whether capability has changed since the last summary (no / slightly / noticeably) and a short rationale updates a capability summary record that outcome judgments retrieve with the recent practice. Physical change (stamina, scars, build) is ordinary state events. Source and magic use the same path. No numbers. Source: `ideas/A/05_mechanics_without_numbers.md` section 2.5.

### D7. Canon coverage and the start (brief item 8; scope per the user: what main characters and events need)

- **Ingest** the part of «Кров ельфів» (lines 15505–22101 of `data/witcher_books.txt`) that main characters and events need: Yennefer's journey to Ellander, the temple, Неннеке, Цірі at the temple. The builder reads the table of chapters, proposes the exact line range and shows it to the user before the run. The existing ingestor takes a line range and chapter list (`harness/canon/ingest.py:29`) and gets them as arguments. The extraction is done by Claude Code subagents in development, not by API calls: each reads a window of the text and writes the records as JSON in the same schema the ingestor uses; the existing code validates against the closed vocabularies, drops what fails and loads the store. No OpenRouter spend. Work stops at about 90% of the 5-hour usage window.
- **Glossary** entries for Неннеке, Мелітеле, Елландер.
- **Portraits** (hand-written, in `worlds/witcher/portraits/`): `yennefer_temple` (the existing one is Rinde), `nenneke`, `ciri_temple`, temple people as needed.
- **Places:** the road to Ellander, the temple and its grounds, in the places data for this start.
- **Start point** `ellander_road` in `worlds/witcher/start_points.yaml`: Yennefer on the road, the stranger falling at her feet. `builder: vizima` is generalised to a builder that takes any canon place; the package supplies the player. Canon follows by the existing rule: canon events happen while their preconditions hold and are re-judged when he changes them.

## Order and plans

The campaign cannot start without D0, D1, D2 and D7, so:

- **Plan 1:** D0, D1, D2, D7, plus the magic-sense observation path of D5 (so Yennefer notices the Source in the first scene). After it the campaign is playable; devices are items without a log. The D7 ingestion is the last task of the plan.
- **Plan 2:** the rest of D5 (manifestation, masking, medallion), D3 (log, output, charge, wear).
- **Plan 3:** D4, D6.

Each plan follows the usual workflow: worktree, tasks with reviewers, final review, merge, push, verify with `git ls-remote`, delete branch and worktree.

## Rulings after the builder check (lead's calls unless marked)

- **Old saves replay unchanged.** New fields (`id`, `location`, `aware`, `until`) are optional in the existing `STATE_CHANGE` payload with defaults (no id, no location, aware true, no expiry). A test replays a recorded session before and after.
- **New items.** Code mints ids. An extractor `add` of new text creates an item with a fresh id; the dropped-when-unresolved rule applies only to `remove`, `move`, `reveal`, `hide`. Crafted items, datasets, recordings and trained models are created the same way.
- **The self-awareness filter lives at retrieval**, in the one function that renders the character's state for any composer (`LiveState.of` with a viewer), so the panel, the character context, the assistant and outcome prose all get the filtered view. Only the debug view asks for everything.
- **`until` changes run in `World.tick`**, which also drives time skips. A change to an element another character can perceive goes through the ordinary observation path.
- **The saga file** is the whole `witcher_books.txt`, spoilers included, by the user's intent: the engine tracks only what he has read. A read result is shown to the player as what he read; each stored record is capped at 600 characters and one read returns at most 2 000, so records stay summaries close to the text rather than copies of chapters. `data/` stays out of git.
- **Builder generalisation** of `builder: vizima` keeps the old builder working and adds a general one beside it.
- **Ingestion costs no API money** (user's decision 2026-10-26): see D7.

## Calls made by the lead (not by the user)

- Item ids and the `move` op; the cap of 80 items.
- Charge as five closed words.
- Reader model and term expansion are cheap typed calls; models chosen by a bake-off from the live catalog at build time and recorded in `docs/tools.md`.
- Glossary spellings win over the user's spellings.

## Left to the builder

Exact data layout of `location` and `aware` in the event payload; how the extractor prompt lists container contents; fuzzy id resolution; the reader's context window; the test set for the unknown-claim check with READ and device channels; UI for the panel's inventory.
