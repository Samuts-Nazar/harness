# Outsider campaign, plan 1: rulings and deferred items

From the ledger `.superpowers/sdd/2026-10-26-outsider-campaign-plan1/progress.md` (git-ignored, in the plan worktree). One line each, grouped by task.

## Pre-flight and general
- Ruling: Task 5 parse accepts optional item key `content` (inline text or `file:`), stored in `inventory_meta`; Task 6 reads it.
- Ruling: Task 7 may edit `harness/portrait.py` to accept optional `senses`.
- Ruling: `data/` is symlinked from the main checkout; canon output goes to the main checkout path (git-ignored).
- Ruling: names follow the glossary (Цірі, Йеннефер, Неннеке, Мелітеле, Елландер).
- Ruling (user): no minors-check feature; no API money for canon extraction (subagents do it).
- Ruling (user): the player is free to go anywhere; canon deferral only delays book scenes, never forces or restricts him.

## Tasks 1–5
- T1→T2: extractor learns move/realize/location/id; `move` requires a location (done).
- T2: item_ids kwarg gates prompt/fuzzy resolution; deferred: mint_id reuse after removal, O(n²) is_observable, no 'no longer visible' observation when moved into a closed container, tests for reveal/hide of a container and extractor realize, engine-level test for fuzzy gating.
- T3: deferred: dead fetch in test_panel_awareness, inline PLAYER aware filter in context.py, extractor sees unaware state (residual risk).
- T4: deferred: removal stamped at step end, tests for simultaneous expiries and re-add.
- T5: deferred: loose `_find_container` substring fallback, cross-module underscore import.

## Task 6 (reading)
- Shown as its own 'Прочитано' block; private to the reader; failures roll back with «Прочитати не вдалося.».
- Deferred: read_intent is a separate judge call every turn (could batch into World.interpret); failure note to the narrator reads like 'found nothing'; reader text language not validated; no app-level test for the failure block.

## Task 7 (magic sense)
- Deferred: no retroactive notice when a sense is gained (Plan 2, medallion); realize wiring from the sorceress telling him (not produced live); a pocket item grants its sense.

## Tasks 8–9 (canon, portraits, start)
- Task 8 split: 8a code + EXTRACTION.md; 8b scope/extraction/load/verify by the controller dispatching workers.
- Ruling: ciri_temple/nenneke close stance also lists lover (ladder coverage test); Ciri has no romance switches.
- Deferral rules: story order per held person, same site (≤5 min), stale after 14 days (retired), cap 6 per step.
- Deferred: only held people block; unmapped places never held; off-map scene drains backlog; no travel time when a person leaves mid-journey; absolute /home/cock paths in tests/scripts (skip safely).
- Canon store: FTS only (no embedder); times and some places are guesses (VERIFY.md).

## Task 10 (live check) and task 11 (fixes)
See `reports/outsider/SUMMARY.md` problems 1–4 and 8: fixed in task 11 (and its review round 1); deferred: 5–7.
