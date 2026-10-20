# Task 19: Outcome-first fast/slow turn loop, evaluation harness, long-run NPC foundations

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `docs/pending_decisions.md` (agreed with the user, not yet in decisions.md; items 2, 4, 14, 15 matter here), `reports/research/18A_infrastructure.md`, `reports/research/18B_design.md`, `docs/tools.md`, the merged task 16/17 code (`harness/canon/`, `harness/world/`).

## 1. Outcome before prose (user decision)
- The player decides what the character does and attempts; the world judges per situation whether it works, before any prose is written. No dice, no stats: one judgment (decider first, LLM escalation per the existing rule) that may say "no" or "partly", with the reason stored as a record. Narration then tells that outcome.
- Real failure has consequences in world state. Death of the player character ends the campaign (a final chronicle screen in the app; the campaign becomes read-only).
- A campaign flag `player_unbounded` (the Vizima pilot demon): the player's own acts always happen; only reactions are judged.
- NPC acts toward the player (attack, theft, arrest) are judged the same way.

## 2. Fast/slow turn loop (Hidden Door pattern, 18A)
- Fast lane: outcome judgment, narration, NPC lines, the checks that must run before text is shown.
- Slow lane, while the player reads: extraction, salience/attitudes, off-screen world updates, name learning, next-turn briefs (prefetch of likely context). The next turn waits for the slow lane only if it needs its results; measure how often that happens.
- Keep the event log deterministic (single writer, fixed order).
- Report seconds to first word and to full turn, live, before vs after.

## 3. Prompt layout for caching
- Order every prompt as static rules → character file → dynamic scene, use OpenRouter `session_id` for sticky routing, and measure cache hits and cost before/after on a 15-turn live session.

## 4. Evaluation harness from our own log
- Record/replay of provider calls so a session can be re-run offline as a regression test.
- Automatic checks over a played log: isolation (no NPC states what it had no channel for, including through goal/intent notes), fact and commitment survival over 20+ turns (things said or promised are still respected later), canon drift (task 16 check), metaphor-as-state errors in extractor output ("took his hand" must not add a hand to inventory).
- LLM judging only with reference answers; report agreement with your own grading on a sample.
- A `pytest -m eval` (or a script) that runs these on stored sessions.

## 5. Long-run NPC foundations (18B "change now")
- Split every NPC profile into an immutable core (voice, drives, values; set once) and mutable layers (memories, attitudes, state). Context always includes the core verbatim.
- Non-canon NPC names, traits and quirks come from code: seeded, period- and region-appropriate tables for the Witcher world (Nordling, Nilfgaardian, elven, dwarven, halfling naming), not from the model. Never reuse a name already in the campaign.
- Age, birth year and mortality for every NPC the player knows: aging and natural death are computed in code from tables, the LLM only narrates. Hooks only for marriage/children (no feature yet).

## 6. Integration of tasks 16 and 17
- The narrator currently sees collectives' rumour versions and authority reactions as plain campaign facts (task 17 report) and invents guards at places they have not reached. Filter the narrator's context by what the player character could perceive or has been told, exactly like NPC contexts.
- Wire `harness/world/canon_adapter.py` to the real `harness/canon/api.py` from task 16 (task 17 guessed the function names and assumed `ScheduledEvent.t` in campaign minutes); replace placeholder collective ids and the Velerad/king chain with task 16's canon characters.
- The app campaign gets the Vizima map and starts at situation A (tavern «Під Лисом», day 3 evening) with the limitless-demon player flag, ready for the pilot test plan (`docs/pilot_vizima_test_plan.md`).
- "Seek the person" orders go to the incident place; when the men find nobody, they ask around and follow the trail per situation (judged), so authorities can actually reach the player.

## Known flaky test
`app/tests/test_app_t12.py::test_narration_streams_before_the_first_npc_word_and_second_npc_hears_the_first` failed once in about five full-suite runs on 2026-10-20 (passes alone). Find the race (parallel turn, thread order) and make it deterministic.

## Tests and budget
All tests pass (report the count); tests per item with fake providers. Live checks under 0.50 USD.

## Output
Full report in the final message (what changed, latency before/after, cache hit numbers, eval results on a real session, spend, open questions, branch and worktree as absolute paths).
