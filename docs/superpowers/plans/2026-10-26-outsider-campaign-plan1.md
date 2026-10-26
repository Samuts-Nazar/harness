# Outsider campaign, Plan 1: playable start

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The outsider campaign starts and plays: a 20+ item backpack with containers, a panel that hides what the character does not know, reading the saga file, Yennefer perceiving his Source by the magic sense, and canon plus a start point for the road to Ellander.

**Architecture:** Extend the event-sourced live state with optional fields (id, location, aware, until, channel) that default to today's behaviour, so old logs replay unchanged. Reading is an ordinary action that runs term expansion, grep and a reader call, and writes knowledge records with a new READ channel. Canon for «Кров ельфів» is extracted by Claude Code subagents into JSON that the existing ingestor validates and loads.

**Tech Stack:** Python, pytest via `nix develop --command pytest`, the fake provider and `FakeJudge` for tests, YAML packages, SQLite canon store.

**Spec:** `/home/cock/projects/harness/docs/superpowers/specs/2026-10-26-outsider-campaign-design.md` (sections D0, D1, D2, D5 observation path, D7).

## Global Constraints

- No stats, dice or success tables; no number decides an attempt.
- Code owns state; LLMs never write state directly.
- Old saves and recorded sessions replay unchanged: new payload fields are optional with defaults (no id, no location, `aware` true, no `until`, channel `sight`).
- Canonical names: Цірі, Йеннефер, Неннеке, Мелітеле, Елландер.
- `data/` and `.env` are never committed; no long excerpts of `data/witcher_books.txt` in code, tests, reports or commits. The user's own character file is never committed; tests use a generic fixture player.
- Cheap models only over the API (input ≤ 0.60 USD, output ≤ 2.50 USD per million tokens); no Anthropic models in the engine; tests use the fake provider.
- Canon ingestion uses no API money; subagents do the extraction; stop autonomous work at about 90% of the 5-hour usage window.
- Tool freshness: any model chosen for a new role is checked against the live catalog and recorded in `docs/tools.md` (role, tool, alternatives, reason, date).
- One record text per item is at most 80 characters for names, 400 for notes; a stored read record at most 600 characters; one read returns at most 2 000.
- Run `nix develop --command pytest` before every merge; check the real exit code. Known flake: `app/tests/test_app_final_review.py::test_stream_and_state_answer_while_slow_translations_run`, rerun alone.

## Review Focus

- Opening the same container twice, or opening an empty one: no duplicate observations, no error.
- A container placed inside itself or in a cycle: rejected, not an infinite loop.
- A read query with no hits in the file, or `data/witcher_books.txt` missing on this machine: a clear "nothing found / no file" result, no crash, no invented knowledge.
- A very common search term (a pronoun, «і»): result capped, no 60 000-line dump.
- The narrator or an NPC mentioning an unaware element (the Source) because an observable action hinted at it: the context never contains it for the player character.
- A recorded old session replays to the same state after the changes.

---

## File Structure

- `harness/state.py`, `harness/models.py`: optional fields, ops `move` and `realize`, viewer-filtered `of`.
- `harness/items.py` (new): item ids, locations, container rules, id resolution.
- `harness/readable.py` (new): term expansion, grep, reader, read records.
- `harness/knowledge.py`: READ channel.
- `harness/pipeline.py`, `harness/context.py`, `harness/extractor.py`, `harness/memory.py`: wiring.
- `harness/world/world.py`: expiry in `tick`.
- `app/newgame.py`, `app/campaigns.py`, `app/game.py`: package inventory, seeding, panel.
- `harness/canon/ingest.py`: line range arguments and a `--from-json` load path.
- `worlds/witcher/`: glossary entries, portraits, start point; package fixtures under `app/tests/fixtures/`.

---

### Task 1: Optional state fields and old-log replay

**Files:**
- Modify: `harness/models.py:29-32`, `harness/state.py:123-185`
- Test: `tests/test_state_foundations.py`

**Interfaces:**
- Produces: `StateChange(character, category, op, item, observable=True, source=None, id=None, location=None, aware=True, until=None, channel="sight")`; `OPS` gains `"move"` and `"realize"`; `payload()` writes new keys only when they differ from defaults; `Element` carries the same fields; `LiveState.snapshot()` still returns `character -> {key: Element-or-bool}` readable by old callers via `LiveState.of(character)` and `.observable(character)`.

- [ ] **Step 1: Write failing tests** `test_old_payload_replays_with_defaults` (an event payload with only the old keys yields `aware is True`, `location is None`, `channel == "sight"`), `test_new_fields_roundtrip_through_payload`, `test_recorded_session_replays_same_state` (replay `tests/fixtures/eval/` session before and after, compare `snapshot()` of observable items).
- [ ] **Step 2: Run** `nix develop --command pytest tests/test_state_foundations.py -v`; expect FAIL.
- [ ] **Step 3: Implement** the fields, the two ops (`move` changes `location`, `realize` sets `aware=True`), and validation in `check_change` (`move` needs an existing item; `realize` needs an unaware item). Keep the key `(category, item)`; the id is an attribute, not the key.
- [ ] **Step 4: Run** the new tests and `tests/` state and extractor tests; expect PASS.
- [ ] **Step 5: Commit** `feat: optional state fields and move/realize ops`.

### Task 2: Item ids, locations and containers

**Files:**
- Create: `harness/items.py`
- Modify: `harness/pipeline.py:1143-1215` (`_apply_change`, `apply_state_change`), `harness/extractor.py:71-170`, `harness/context.py:625-661`
- Test: `tests/test_items.py`

**Interfaces:**
- Consumes: Task 1 fields.
- Produces: `items.mint_id(name: str, taken: set[str]) -> str` returning `item:<slug>` unique; `items.resolve(text: str, character: str, state) -> str | None` (id of the best normalised match among the character's items, `None` if none); `items.is_observable(element, state) -> bool` (worn and in-hand: yes; inside a closed container: no; `on:<place>`: yes); `items.open_container(engine, character, container_id) -> list[str]` (marks the container open, returns the ids that became observable and runs `_observe` for them once); `items.check_location(state, item_id, location)` raising `StateError` on a missing container or a cycle.

- [ ] **Step 1: Failing tests:** `test_backpack_contents_hidden_until_opened`, `test_opening_makes_contents_observable_once` (second open produces no new observation), `test_open_empty_container_is_noop`, `test_container_cycle_rejected`, `test_extractor_add_mints_id`, `test_unresolved_remove_dropped_but_unresolved_add_creates_item`, `test_text_keyed_items_without_ids_unchanged`.
- [ ] **Step 2: Run** them; expect FAIL.
- [ ] **Step 3: Implement** `harness/items.py`; observability is derived at read time, never stored; the extractor prompt lists `id` beside each item and tells the model to refer to ids for `remove`, `move`, `reveal`, `hide`; extractor `add` of new text mints an id in code.
- [ ] **Step 4: Run** `tests/test_items.py tests/test_extractor*.py tests/test_pipeline*.py`; expect PASS.
- [ ] **Step 5: Commit** `feat: item ids, locations and containers`.

### Task 3: Self-awareness filter

**Files:**
- Modify: `harness/state.py` (`LiveState.of`), `harness/memory.py:48`, `app/game.py:326`
- Test: `tests/test_self_awareness.py`, `app/tests/test_panel_awareness.py`

**Interfaces:**
- Consumes: Task 1 `aware`.
- Produces: `LiveState.of(character, viewer: str | None = None, debug: bool = False)`: when `viewer == character` and not `debug`, unaware elements are dropped; every other call keeps today's result. `MemoryDeriver.derive` uses the filtered view for the player character; the debug view passes `debug=True`.

- [ ] **Step 1: Failing tests:** `test_unaware_element_absent_from_own_view`, `test_unaware_element_present_in_debug_view`, `test_realize_makes_it_appear`, `test_panel_chips_exclude_unaware`, `test_player_context_prompt_has_no_unaware_text` (build the player's narrator, assistant and outcome contexts with a fake provider and assert the Source text is in none of the captured prompts).
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the filter in the single state accessor so panel, narrator context, assistant and outcome prose all inherit it; update `_compute_panel` comment that said "hidden or not".
- [ ] **Step 4: Run** the new tests plus `app/tests/`; expect PASS.
- [ ] **Step 5: Commit** `feat: panel and player context hide unaware state`.

### Task 4: Timed effects

**Files:**
- Modify: `harness/world/world.py:691` (`tick`), `harness/pipeline.py` (`advance_offscreen`)
- Test: `tests/test_timed_effects.py`

**Interfaces:**
- Consumes: Task 1 `until`.
- Produces: `World.expire_state(now: int) -> list[StateChange]` appending ordinary `remove` events for elements whose `until <= now`, called from `tick` and from the skip paths; rollback of the cause restores the element.

- [ ] **Step 1: Failing tests:** `test_element_removed_when_until_passes`, `test_expiry_runs_on_day_skip`, `test_rollback_restores_expired_element`, `test_expiry_of_observable_element_is_observed_by_present` (others present get "no longer has").
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** `expire_state` and call it each `tick` step and in `skip_days`.
- [ ] **Step 4: Run** `tests/test_timed_effects.py tests/test_world*.py`; expect PASS.
- [ ] **Step 5: Commit** `feat: timed state effects`.

### Task 5: Package inventory and seeding

**Files:**
- Modify: `app/newgame.py:78-83,380-460,851-861`, `app/campaigns.py:303-330`, `docs/new_game_instruction.md`, `docs/game_package_example.yaml`
- Test: `app/tests/test_package_inventory.py`, fixture `app/tests/fixtures/outsider_generic.yaml`

**Interfaces:**
- Consumes: Tasks 1–3.
- Produces: `PLAYER_KEYS` gains `inventory`; `parse` validates each entry `{name, where, condition, notes, container, open, hidden}` (at most 80 entries, name ≤ 80, notes ≤ 400; bad entries yield Ukrainian `Issue`s like the other fields); `campaigns.seed_player_inventory(eng, items: list[dict])` mints ids, sets locations, applies through `eng.apply_state_change`; with an explicit list `derive_traits` still runs but its `equipment`/`inventory` items are skipped.

- [ ] **Step 1: Failing tests:** `test_parse_accepts_25_items`, `test_parse_rejects_81_items_with_issue`, `test_where_must_name_a_container_or_known_place`, `test_seed_puts_laptop_in_backpack_hidden`, `test_worn_jacket_observable_to_npc_on_entry`, `test_package_without_inventory_unchanged`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** parsing and seeding; update the instruction and the example file with an `inventory` block.
- [ ] **Step 4: Run** `app/tests/`; expect PASS.
- [ ] **Step 5: Commit** `feat: explicit starting inventory in game packages`.

### Task 6: Readable items and the READ channel

**Files:**
- Create: `harness/readable.py`
- Modify: `harness/knowledge.py:277-310`, `harness/pipeline.py` (turn loop), `harness/context.py:223`, `app/newgame.py` (`player.knows` source), `docs/tools.md`
- Test: `tests/test_readable.py`

**Interfaces:**
- Consumes: Task 2 item ids.
- Produces: `readable.expand_terms(judge_or_model, request: str) -> list[str]` (cheap typed call; at most 12 terms); `readable.grep_file(path: Path, terms: list[str], context_lines: int = 3, cap_chars: int = 2000) -> list[Passage]` (case-insensitive, Ukrainian endings via the stem logic in `harness/glossary.py`, merged overlapping hits, hard cap); `readable.read(engine, character, item_id, request) -> ReadResult(text: str, minutes: int, records: list[str])`; knowledge kind `READ` accepted by the unknown-claim check and `challenge_line`; records have knower source `read: <item_id>` and the in-world time; `player.knows` records get source `own life, from another world` rendered «(з власного життя, з іншого світу)». A `read_intent` yes/no judgment in the turn loop decides whether the player's action reads an item that has `content`.

- [ ] **Step 1: Failing tests:** `test_expand_terms_includes_forms_and_aliases` (fake provider scripted), `test_grep_finds_declined_forms`, `test_grep_cap_on_common_word`, `test_missing_file_returns_nothing_found`, `test_no_hits_creates_no_knowledge`, `test_read_creates_knowledge_with_read_source`, `test_read_advances_clock_by_amount`, `test_claim_from_unread_text_still_rejected`, `test_other_reader_gets_own_read_channel`, `test_own_life_other_world_rendering`. Tests use a tiny invented file in `tmp_path`, never `data/`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the module and wiring. Model for term expansion and the reader: check the live OpenRouter catalog, pick the cheapest model within the price caps that passes a 5-case Ukrainian check on invented text, and record role, choice, alternatives, reason and date in `docs/tools.md`. Duration comes from the existing duration judgment with the amount as input; no per-request table.
- [ ] **Step 4: Run** `tests/test_readable.py tests/test_knowledge*.py tests/test_output_check.py`; expect PASS.
- [ ] **Step 5: Commit** `feat: readable items and the READ knowledge channel`.

### Task 7: Magic sense observation

**Files:**
- Modify: `harness/pipeline.py:1166-1260` (`_observe`, `enter_scene`), `harness/state.py` (channel), `harness/context.py` (noticed items)
- Test: `tests/test_magic_sense.py`

**Interfaces:**
- Consumes: Tasks 1, 3.
- Produces: character attribute `senses: tuple[str, ...]` (default `("sight",)`), settable from a canon portrait or package person (`senses: [magic]`) and granted by an item with `grants_sense: magic` when worn; `_observe` filters elements by `channel` against the observer's senses; an element with `channel == "magic"` is invisible to sight-only observers.

- [ ] **Step 1: Failing tests:** `test_sorceress_notices_unaware_source_on_entry`, `test_sight_only_npc_does_not`, `test_source_stays_out_of_player_panel_until_realize`, `test_realize_after_told_by_sorceress`, `test_medallion_grants_sense_when_worn`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the channel check in `_observe`; the noticed fact reaches the NPC context as "(just noticed)" like any other observation.
- [ ] **Step 4: Run** `tests/test_magic_sense.py tests/test_perception*.py`; expect PASS.
- [ ] **Step 5: Commit** `feat: magic sense observation channel`.

### Task 8: Canon extraction for «Кров ельфів» by subagents

**Files:**
- Modify: `harness/canon/ingest.py:29,408` (line-range and chapter arguments, `--from-json DIR`)
- Create: `reports/canon_be/README.md` (scope, ranges, counts; no excerpts)
- Test: `tests/test_canon_from_json.py`

**Interfaces:**
- Produces: `python -m harness.canon.ingest --source data/witcher_books.txt --lines A-B --from-json DIR --out X.db` validates each JSON file against `canon/vocab.py`, drops invalid records and counts them, loads the rest; JSON schema is the one the current ingest passes already emit (entity, timeline, events, knowers, reactions); then `Refiner` runs for time, places, knowers, gist and FTS (embedding step skipped if no embedding model is configured offline; FTS works alone).

- [ ] **Step 1: Failing test:** `test_from_json_loads_valid_and_counts_dropped` using a hand-made invented JSON.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** the load path and range arguments.
- [ ] **Step 4: Run** the test; expect PASS. Commit `feat: ingest from subagent JSON`.
- [ ] **Step 5: Scope.** Read the chapter table of lines 15505–22101 (headings only), pick the chapters that carry Yennefer's journey to Ellander, the temple, Неннеке and Цірі there, and write the ranges to `reports/canon_be/README.md`.
- [ ] **Step 6: Extract.** Dispatch Claude Code subagents, one per window of about 400 lines, in parallel, each writing JSON files to `campaigns/canon/raw_be/` (git-ignored). Then run the loader and the refiner into `campaigns/canon/be.db`; record dropped counts in the report.
- [ ] **Step 7: Verify** by sampling 10 records against the text yourself; commit the report.

### Task 9: Glossary, portraits, places and start point

**Files:**
- Modify: `worlds/witcher/glossary.json`, `worlds/witcher/start_points.yaml`, `harness/world/pilot.py:92-135`, `app/newgame.py:153-165`
- Create: `worlds/witcher/portraits/yennefer_temple.yaml`, `nenneke.yaml`, `ciri_temple.yaml`; `app/tests/fixtures/outsider_generic.yaml` already from Task 5
- Test: `tests/test_ellander_start.py`

**Interfaces:**
- Consumes: Tasks 7, 8.
- Produces: glossary entries Неннеке (latin Nenneke), Мелітеле (Melitele), Елландер (Ellander), with wrong forms and cases; three portraits in the existing format (`id, character, name, phase, core, stances, hidden, leaks, voice, never`; Yennefer's has `senses: [magic]`); start point `ellander_road` with a general builder beside `builder: vizima`, `here: [yennefer]`, places "road to Ellander", "temple of Melitele", "temple grounds"; start text: a stranger falls at Yennefer's feet on the road.

- [ ] **Step 1: Failing tests:** `test_glossary_fixes_wrong_forms`, `test_start_point_loads_and_binds_portraits`, `test_ellander_start_scene_has_yennefer_and_player`, `test_vizima_start_points_unchanged`.
- [ ] **Step 2: Run**; expect FAIL.
- [ ] **Step 3: Implement** entries, portraits (written from the extracted canon, Ukrainian, Sapkowski's tone per `worlds/witcher/style.md`), the general builder and the start point.
- [ ] **Step 4: Run** `tests/test_ellander_start.py app/tests/`; expect PASS.
- [ ] **Step 5: Commit** `feat: Ellander start, glossary and portraits`.

### Task 10: Live check and records

**Files:**
- Modify: `docs/decisions.md` (one entry), `docs/assumptions.md` (new section), `docs/HANDOFF.md` (state)
- Create: `reports/outsider/SUMMARY.md`

- [ ] **Step 1:** Run the full suite `nix develop --command pytest`; record the real exit code.
- [ ] **Step 2:** Live check with the generic fixture package on `ellander_road`, 3 turns, budget 0.1: the Source is absent from the panel, Yennefer reacts to it, a read of an invented item returns knowledge, a backpack opens. Write the result to `reports/outsider/SUMMARY.md`.
- [ ] **Step 3:** Update `docs/decisions.md` once, `docs/assumptions.md`, `docs/HANDOFF.md`; save rulings and deferred items to `reports/outsider/deferred_and_rulings.md`.
- [ ] **Step 4:** Merge into main, push, verify `git ls-remote origin`, delete branch and worktree.

---

## Self-review notes

- Spec coverage: D0 items 1–4 → Tasks 1–4; D1 → Task 5; D2 → Task 6; D5 observation path → Task 7; D7 → Tasks 8–9. D3, D4, D5 manifestation/masking, D6 are Plans 2 and 3.
- Names match across tasks: `items.mint_id`, `LiveState.of(character, viewer, debug)`, `World.expire_state`, `readable.read`.
- Plan 1 leaves the player's own character file out of the repo by design.
