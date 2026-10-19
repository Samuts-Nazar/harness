# Task 13: Canon ingestion pilot — "Останнє бажання", story "Відьмак"

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md` (Canon section), `design/schema.md` and `design/canon.sql` (canon ingestion schema: events, participants, knowers, reactions with a closed vocabulary, pivots), `design/schema_gaps.md` (G-4, G-6, G-12), `ideas/A/03*` (canon reaction index), `reports/cost/SUMMARY.md` (ingestion probe), `docs/tools.md`.
Another worker runs task 12 at the same time (app, narrator, director, glossary in `harness/` and `app/`). Put your code in a new package (`harness/canon/`), touch shared engine files only where unavoidable, and list those changes.

## Why
The user wants to judge book ingestion on one small arc first: ingest it carefully, check every record, then play inside it and see whether the world behaves like a real simulation. Only when that is good does it extend to the rest of book 1, then the saga (cost).

## Scope
- Text: `data/witcher_books.txt`, book "Останнє бажання": the frame chapter "Голос розуму-1" and the story "Відьмак" (lines 7–694 of the file; check the boundaries yourself). Nothing else.
- Never commit book text beyond short quotes (a sentence). The canon database with passages lives under `campaigns/canon/` (git-ignored). Commit code, schema, gold notes and the report.

## Steps
1. **Ingest** into the canon store following `design/canon.sql` (implement the subset needed; record deviations): events with in-world time, place, participants, who knew what and how (knowers with channel), reactions (closed vocabulary), character entries (who they are, role, standing, what they would know from their life), places, and passages for retrieval (FTS5, per `docs/tools.md`).
2. **Models:** run the ingestion with 2–3 cheap models chosen from the live catalog under the price policy (start from `docs/tools.md` Models; check for newer ones live). Record the choice in `docs/tools.md`.
3. **Check every record** yourself against the text (not a sample): wrong facts, missing important events, wrong knowers (someone "knows" what they could not), wrong time order, invented details, distorted names. Count per type and per model. Quote short examples.
4. **Names:** produce the glossary of canonical Ukrainian forms for this arc (characters, places, titles) for task 12's glossary format (`harness` glossary; if it is not merged yet, a JSON file the lead can plug in).
5. **Starting situations:** read `data/Ragnar.md` (the player character; never commit it or quote more than a sentence). Propose 2–3 starting situations that place Ragnar in this arc (place, in-world time relative to the story events, who is around, what Ragnar plausibly knows), consistent with both texts. The user picks one; do not build the scene yet.
6. **Retrieval check:** for 10 questions a character in this arc might face, show what the canon retrieval returns, filtered by that character's knowledge, and whether it is right.

## Budget
Under 0.60 USD.

## Output
- Report readable on a phone (verdict first): per model, error counts by type, cost, time; the recommended ingestion model; the starting situations; what must improve before extending to more stories.
- Put the full report text in your final message; also try to write it to `reports/canon_pilot/SUMMARY.md`, and say if the file could not be written.
- Branch name and worktree path as full absolute paths.
