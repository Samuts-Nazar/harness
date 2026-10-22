# Character portraits — rulings and deferred items

From the SDD ledger of plan docs/superpowers/plans/2026-10-22-character-portraits.md (merged 2026-10-23).

## Rulings
- Ruling: T2 package seeding of rung happens in T2 via profile/package attitude, moved to Relations in T3 — keeps Yennefer playable after T2 — costs a small rework in T3 if wrong.
- Ruling: ladder fallback goes down first, then up — matches the brief's example — costs a stance mismatch for rival/enemy edge cases if wrong.
- Ruling: merge Tasks 1–2 into main now so the user can play Yennefer while Tasks 3–5 continue on the branch — the user asked to test actively — costs a second merge later.
- Ruling: brief's default (0.0/0.2) vs example (-0.2) — get() falls back to SEED_VALUES by rung — the brief was inconsistent — costs a slightly colder stranger start if wrong. Fix round 1/5 dispatched (FIX_BASE 0e70092).
- Ruling: regen keeps cause on player utterance, lines = this NPC only, revert then re-ask one NPC after regen (success or restore) — the player's act stays in the story so its effect must too — costs one cheap judge call per correction.
- Ruling: pacing per reviewer numbers (largest positive + all negatives; positive cap +0.3/+0.3; repeat dampening per scene; rung multipliers 1.0/0.75/0.5/0.35; close needs ally across ≥1 scene change; lover needs close across ≥2 scene changes and ≥3 distinct positive switches; decay 0.05 toward entry warmth on a scene with no positive hit) — "possible but earned" — costs slower romance if too strict.
- Ruling: drop only when the turn's warmth delta is negative; enemy→stranger only at warmth ≥ −0.4 after ≥1 scene change — avoids flapping and cheap forgiveness — costs grudges lasting longer.
- Ruling: helpless_nearby trigger excludes her and the player; judge state header "what the player did or said this turn (toward her or others present)".
- Ruling: scene key also advances on a new game day or ≥120 game minutes since last judged — one-room games must allow scene changes — costs faster dampening reset if wrong. Task 4 fix commits eb4d6b5..6e857bb; scoped re-review dispatched. Known flake: test_stream_and_state_answer_while_slow_translations_run ~1/8 (pre-existing).
- Ruling: keep the stopped implementer's uncommitted tests and have the new implementer check them against the brief — they match the brief's shape — costs a reviewer catching a wrong test if they drifted.
- Ruling: commits end with the Co-Authored-By line only, no Claude-Session line — the old session link no longer applies — costs nothing.
- Ruling: package people without portrait_text get a short portrait only when they become named/recurring (knows_player makes them named on first settle) — matches "invented NPCs who matter" — costs one extra call later instead of at start if wrong.
- Ruling: crowd/court stances limited to [stranger] — the ladder must show where they actually live — costs a too-open innkeeper in a full room if wrong.
- Ruling: at most 2 short portraits per settle, run in parallel, the rest next settle; guarded like _apply_switches — keeps turn 2 fast — costs a late portrait for the 3rd+ named NPC.
- Ruling: the ~9-word standing line stays outside the 260-word slice cap — the plan means the NPC to see its standing — costs 9 words per call.
- Ruling: no rewrite of the 5 commits with the old Claude-Session trailer — rewriting pushed history is worse — costs nothing.
- Ruling: the decisions.md entry is written by the controller at merge.

## Deferred minors (final review: all can wait unless fixed in the final wave)
- Task 1: minor (deferred): non-dict switch entry raises AttributeError; `when` values not validated; blank required strings pass; last-resort truncation drops voice/never; no tests for PortraitError attrs/malformed YAML/load_world_portraits
- Task 2: minor (deferred): negation looks one word back («не дуже дружня»); «друга» matches friend; vitals.age may still reach prompts elsewhere; situation() scans log twice; power/stakes branches rarely fire; DANGER matches 'drawn'; bundled_packages title/pitch uncapped
- Task 3: minor (deferred): stored non-seedable rung keeps label with stranger numbers; import order in pipeline.py
- Task 4: minor (deferred): regen re-judge uses current scene time, not the turn's (narrow day/120-min boundary window); pending slow lane may extract facts from a regenerated line (pre-existing); relation_changed noted on no-change turns
- Task 5: minor (deferred): promote_short_portraits no per-settle cap and rescans log; ladder coverage not enforced; one bad stance drops whole portrait; portraits block repeated in 7 start points; ensure_character saves setup twice; overlong header line; glossary-named free-text person generated as invented NPC
- Task 5: minor (deferred): corrupt cached portrait entry is never regenerated; import order in app/tests/test_newgame.py

## Final review minors not fixed
- standing line (~9 words) outside the 260-word slice cap (ruled acceptable)
- promote state survives a failed slow lane; relation reads rescan the log; 5 commits carry the old Claude-Session trailer
- short-portrait prompt asks 4–5 stances / 3–5 switches (spec: 3–4 / 3)
- live check: in a full tavern the innkeeper played the crowd stance at stranger rung (now crowd only at stranger); a question addressed to nobody got no speaker (director, not portraits)
