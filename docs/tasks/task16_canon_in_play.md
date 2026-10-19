# Task 16: Canon in play — fix the pilot ingestion and wire it into the engine

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md` (Canon), `docs/pilot_vizima_test_plan.md`, `reports/canon_pilot/SUMMARY.md` (section "Must improve before extending"), `reports/canon_pilot/gold_notes.md`, `harness/canon/`, `docs/tools.md`.
Task 17 runs at the same time and builds the world beyond one scene in `harness/world/` (places, world clock, travel, spread of news, collectives, off-screen events). Interface between you: canon provides **scheduled canon events** (who, where, when, what, who learns it) and **character background knowledge**; task 17 executes events and spreads news. Agree on it by writing `harness/canon/api.py` first (dataclasses + functions, documented) and committing it early; task 17 reads it from your branch name `worktree-agent-*` if needed, or codes against the same shape from this brief.

## 1. Fix the ingestion (pilot arc only: book file lines 7–694)
Items 1–6 of "Must improve" in the pilot report:
- Day tracking: code check (monotonic days, cue words), second-model vote on the timeline, day ranges for vague cues. Target: wrong-day events ≤ 5% against `gold_notes.md`.
- Places: every event linked to a place entity.
- Knowers: present participants auto-added; "informed by" for officials stating facts they did not witness; tellers are not "witnessed". Target: missing knowers ≤ 5%.
- Retrieval: Ukrainian gist per event (or embeddings via OpenRouter if FTS on gists is not enough; check current options live and record in `docs/tools.md`), relevance cutoff (return nothing rather than noise), persons resolved before collectives. Re-run the 10 retrieval questions; target ≥ 9/10 useful and 10/10 no leak.
- Reactions: separate pass with "none".
- Re-check every record against the text as in task 13; report counts.

## 2. Canon in the engine
- **Campaign from canon**: a campaign can start at a canon moment (story day + time + place). Everything before it is the world's past: NPCs created from canon characters carry what they knew as of that moment (knower rows), as knowledge records with source and time. Names known to each other per canon (`Engine.acquaint`).
- **Background knowledge from life** (user decision, pending in decisions.md): a canon or invented NPC knows what follows from their life (role, years, place, standing). Computed lazily when a topic comes up (one cheap judgment: "would this person plausibly know X?"), stored as a knowledge record with source "own life", so it stays consistent. Canon secrets never come through this channel.
- **Scheduled canon events**: the events after the start moment, with time, place, participants, knowers, as the list task 17 executes when nothing has changed them.
- **Canon drift check** (decisions: narrated output contradicting canon is checked against the campaign store; justified drift accepted, otherwise regenerate): implement for narrator and NPC output using retrieval on the pilot arc. Proportional canon pull: a scheduled canon event whose preconditions the player changed is re-judged (still happens / happens differently / does not happen), one judgment with the reason stored.
- Tests with fake providers; one live check: start at situation A, 5 turns, show what the innkeeper and a guard know and from where.

## Budget
Under 0.60 USD.

## Output
Full report in the final message: ingestion error counts before/after, retrieval results, what canon now does in play, spend, open questions, branch and worktree as absolute paths.
