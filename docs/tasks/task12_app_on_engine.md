# Task 12: App on the new engine; free-prose narration; NPCs hear each other; names never distorted

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `docs/tools.md`, `reports/language/SUMMARY.md`, `reports/bakeoff/SUMMARY.md`, `app/README.md`, assumptions 47–69 in `docs/assumptions.md`.
Another worker runs task 13 at the same time (canon ingestion, new code under `harness/canon/` or `harness/ingest/`, data under `campaigns/`); do not touch those.

## User decisions this task implements (not yet in decisions.md; the lead writes them there later)
- Player-facing text must not follow a visible pattern. A rigid JSON contract on creative calls is suspected of making text formulaic.
- Names, places and titles must never be distorted, whatever language records are stored in.
- Characters in one room hear each other.

## 1. App on the task 9 engine
- `app/` uses saved campaigns (`Engine.create_campaign` / `open_campaign`): a server restart continues the game; a "new campaign" button still exists.
- Live defaults come from `harness/policy.py` (d1-ultra first judge etc.); remove the `HARNESS_EXTRA_ALLOWED` workaround from `app/` and its README.
- Parallel turn works with the app's streaming: narration streams first, NPC lines stream in narrator order as soon as each is ready. Replace the `eng.log.append` monkeypatch with a proper engine hook (callback) if the parallel turn makes the patch fragile.
- Use the engine's output-language setting; drop the app-side "write in Ukrainian" hint.

## 2. NPCs hear each other within a turn
- An NPC speaking after another NPC in the same turn gets the earlier line(s) of that turn in its context (only what it could perceive). Keep everything else parallel (checks, extractor, judgments). Measure the latency cost.

## 3. Free-prose narration (no JSON on creative calls)
- Narrator and NPC calls return plain prose only. Who speaks next and which observable actions happened are derived by a separate step: a small "scene director" function using the first-line decider (choice over the present characters plus "nobody") and/or the extractor. Make the director a separate, reusable function: a later task builds a real-time live scene on it (who takes the floor, when, silence).
- Keep the narrator's NPC-speech check (now on prose).
- Compare on the task 7 narrator set (`experiments/bakeoff/testset/narrator.json`): JSON narrator vs prose narrator, luna, 3 samples each, blind-graded by you (Ukrainian quality, variety, flags as in task 7). Report latency added by the director step.

## 4. Repetition metric
- A cheap code metric of repetition across the last N player-facing outputs (repeated n-grams, repeated sentence openings, repeated paragraph shape). Log it per turn in the debug view. Run a 15-turn live session and report the metric, and quote (short) any repetition you see.
- No automatic regeneration on repetition yet; measure first.

## 5. Name glossary
- A per-world glossary of canonical names, places and titles (Ukrainian forms as in the Ukrainian translation; seed it with the names used in the demo scene and the task 7/10 test sets). Applied in code when records are written and when context is rendered, so the model always sees one form. Record language follows `reports/language/SUMMARY.md`: English text, Ukrainian names; extractor told to write state items in English too.
- The deepseek fallback lost quality on English context (task 10): when a fallback model is active for narrator or NPC, render the context in Ukrainian if that is cheap; otherwise record the gap.
- Test: names stay in canonical form over the 15-turn live session (count variants).

## Tests and budget
- All tests pass (`nix develop --command pytest`, report the count); new tests for each item, fake providers only.
- Playwright check of the app at phone size still passes; update screenshots.
- Budget under 0.40 USD.

## Output
Final report: what changed, test count, prose-vs-JSON comparison, repetition and name-consistency numbers, latency per turn, spend, open questions, branch name and worktree path as full absolute paths. Put any report text in the final message; if a report file cannot be written, say so.
