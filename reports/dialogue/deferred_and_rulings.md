# Living dialogue: deferred minor findings and lead rulings (from the SDD ledger, 2026-10-22)

| T2 vs T3/T4 | T2 counts code_choices from notes T3/T4 create later | ordering gap -> Ruling 1 |
| T5 self | test_app_turn_without_narration listed in tests/test_exchange.py but is an app test | Ruling 2 |
| T7 self | start_turn no longer 409 conflicts with existing app test expecting 409 | Ruling 3 |
Ruling 1: T2 defines `CODE_CHOICE_KINDS` (a set of note kinds) in harness/decisions.py; T3/T4 must log their code choices as engine notes with kinds added to that set — counts are complete only after T4 — cost if wrong: a few uncounted code choices in the report.
Ruling 2: test_app_turn_without_narration goes in app/tests/test_app_dialogue.py (created in T5, extended in T7) — cost if wrong: none.
Ruling 3: T7 updates the existing test expecting 409 on a second start_turn to the new interrupt-then-run behaviour (spec: sending mid-exchange cuts in) — cost if wrong: a stale test.
Task 1: minor (deferred): empty dash paragraph counted as narration gap (profile.py:161-165)
Task 1: minor (deferred): obscure runs.append idiom (profile.py:166)
Task 1: minor (deferred): is_question misses "?!"/"?.." (profile.py:98)
Task 1: minor (deferred): distance() includes narration/run metrics that are 0 for engine output — Ruling: Task 6 compares speech metrics only (carried into T6 dispatch) — cost if wrong: misleading distance numbers
Task 1: minor (deferred): load_profile/CLI untested; from_dict defaults silently
Task 2: minor (deferred): two count sources (Game marks vs slow.result.decisions) may drift; Game count includes after_settle hook calls
Task 3: minor (deferred): prompt (shape_instruction defaults) vs fit (profile bounds) mismatch — Ruling: Task 4 drives prompt and fit from one bounds value (shape_instruction gains optional bounds and name args) — cost if wrong: model told 10-25 words while checker enforces 8-15
Task 3: minor (deferred): _FROM_BINS ignores bin keys; LONG upper 80; no profile-bounds fit test
Task 3: minor (deferred): language line duplicated — Ruling: fixed in Task 4 alongside the bounds change
Task 3: minor (deferred): "The character" replace hack; weak test_shape_instruction_per_shape; comment misalignment
Task 3: minor (deferred): GESTURE output dashless — Ruling: Task 4 handles GESTURE by shape (stores beats as the NPC's action, no utterance)
Task 4: Ruling: app stays classic until Task 7 switches it to living (Task 7 dispatch carries this) — cost if wrong: the user plays classic if Task 7 slips
Task 4: minor (deferred): fake_next_floor in judge.py does not filter PLAYER/NOBODY on step 0; app/stacks.py Question rebuild depends on constructor signature
Ruling: plan amended with Tasks 9-11 (play-test bugs: absent canon character in scene, challenge not removing content, dash-in-speech parsing, name gender) — same turn loop, so on this branch after Task 8 — cost if wrong: the user waits longer for these fixes
Task 5: review Needs fixes — Important: skipped turn can be empty (first step NOBODY/PLAYER or no NPCs). Important 2 (wasted next/shape on narrated turns) — Ruling: accepted trade-off per plan ruling 1; latency measured in Task 8 — cost if wrong: ~0.4 s per narrated turn
Task 5: minor (deferred): narration_skipped counted as code choice; fake_needs_narration brittle; import noise; scripted() helper readability
Task 5: minor (deferred): on_narration("") now called for a non-skipped empty narration — Ruling: Task 7 app guards empty narration — cost if wrong: an empty bubble
Task 6: minor (deferred): app test d-is-None vacuous; __import__ hack; long lines; session_lines reset on reopen (document); prior coupled to bin names
Task 7: minor (deferred): empty-turn test does not produce an empty turn; thinking/narrating-phase cut-in untested; unsaid-intent on typing path unchecked
Task 7: minor (deferred): slow-lane retract after cut-in lands in the new turn (carry a turn id) — flag for final review
Task 7: minor (deferred): fixed-sleep test; challenge race during wait; double send; feed click skips during text selection; duplicate #dockBusy rule
Ruling: Tasks 9-11 run in parallel on branches ld-t9/ld-t10/ld-t11 off bd9986a (user asked for parallel work; 9-11 are independent of each other and of Task 8's measurement files), merged back into living-dialogue one by one after review — cost if wrong: merge conflicts in pipeline.py between 9 and 10
Task 10: minor (deferred): candidate-stage JudgeError fail-open (logged)
Ruling: plan amended with Task 12 (after 9–11 merge): fix the '~2' extractor source bug; calibrate shape distribution toward the profile (long lines too); beats by profile share — cost if wrong: dialogue stays clipped
Ruling: A/B pairs will be regenerated after Task 12 (dialogue changes again); fix round now = honest verdict, drop pair 7, caveat format tells and glitches in SUMMARY; engine glitches (label-as-speaker prefix, duplicated name) + script-switch output check go to Task 12 — cost if wrong: the user gets the A/B page later
Task 8: minor (deferred): narration-skip count inconsistency; speed ratio wording; hardcoded paths; cassette doesn't record streams; scene medians 5-10 vs book 16-22.5 not called out; no script tests
Task 8: fix 4fa112d (glitch actually pair 6 classic side, removed; 9 pairs). Flaky: test_send_during_exchange_via_http_does_not_return_409 failed 2/3 full runs -> Ruling: Task 12 makes it deterministic (blocker for merge to main)
Task 9: minor (deferred): last-resort re-admit skips name masking in actions; remove_people regex may remove nothing (logged removed=[]); pronoun-only sentences stay; both-ends-elsewhere heuristic
Final fix wave: 095eca8..42e9cfc (6 items, 5 full runs green, Vizima first-word 9.28s on/off). ui_check: controller ran it, OK (implementer's failure = timing flake) -> minor (deferred). Scoped re-review dispatched
