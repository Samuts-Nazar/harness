# Task 9: Engine on the chosen models, faster turns, saved campaigns

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md` (model policy section is new), `docs/tools.md` (Models section and Recommended changes), `reports/bakeoff/SUMMARY.md`.

Goal: the engine plays live on the models chosen in task 7, turns are as fast as the parallel plan allows, and a campaign survives a restart. Another worker builds a phone app on top of `Engine` at the same time (task 11, `app/`); do not touch `app/` and keep `Engine`'s public methods backward-compatible (add parameters with defaults, do not rename).

## 1. Model policy in code (`harness/policy.py`, README, demo)
- Replace the fixed allowlist with the rule in `docs/decisions.md`: a model is allowed if its live OpenRouter price is at most 0.60 USD input and 2.50 USD output per million tokens, it is not Anthropic, and it is not on a small explicit deny list. Decision models (served on the decision endpoint, not in the chat catalog) are allowed by an explicit list: `liquid/d1-ultra`, `perplexity/pplx-decider-v1.2`, `perplexity/pplx-decider-flash-v1.2`, `typesafe/jev-1.13`, `typesafe/jev-1.14`.
- Price lookup: fetch the catalog once and cache it on disk with a date (refresh when older than a day); tests use a fixture, never the network.
- Defaults (from `docs/tools.md`): narrator and NPC `openai/gpt-6-luna`, extractor `deepseek/deepseek-v4.1-flash-1017`, first judge `liquid/d1-ultra`, escalation judge `openai/gpt-6-luna`. Fallbacks per role as in `docs/tools.md`: if a call fails after retries, use the fallback model.
- Remove every Anthropic default from code, README and `docs/assumptions.md` entries that state them (mark old assumptions superseded, do not delete).

## 2. Decision client
- `JevJudge` → generic decision client for Jev, pplx-decider and d1-ultra (same schema; endpoint `POST https://openrouter.ai/api/v1/systemone`). Keep a `JevJudge` alias.
- Retry with exponential backoff on HTTP 429 and 5xx, for both the decision client and the OpenRouter chat client.

## 3. OpenRouter client
- Drop the deprecated `"usage": {"include": True}`; read usage from responses, including the final chunk of a stream, and feed it to `Spend` (closes gap 19).
- Handle a mid-stream `finish_reason: "error"` chunk as an error.

## 4. Parallel turn
- Implement the parallel plan measured in task 7 (`experiments/bakeoff/timing_turn.py`): after the narrator, run the narrator speech check, each NPC chain (line, then its check) and the extractor concurrently; then what depends on them. Threads are fine (the code is sync httpx); keep event-log writes on one thread and in a deterministic order, so results do not depend on timing.
- NPC lines must still be delivered in narrator order.

## 5. NPC output check fix (from `reports/bakeoff/SUMMARY.md`)
- Reject only at p ≥ 0.7 (configurable).
- When all retries are rejected, show the candidate with the lowest suspicion instead of the fixed fallback line; log it.

## 6. Player-facing language
- Add an output-language setting (default Ukrainian) to the narrator and NPC prompts. Do not change the language of records or judgment questions yet; a separate experiment (task 10) decides that. Make the record language a setting too (default: whatever the extractor writes now), so it can be switched in one place.

## 7. Saved campaigns
- File-backed SQLite per campaign under `campaigns/<name>/` (git-ignored), WAL and foreign keys on. `Engine` can open an existing campaign and continue from the log. In-memory stays the default for tests.

## Tests and live check
- All existing tests pass (report the real count from `pytest`), new tests for each item above, fake providers only.
- One short live smoke run (`--live`, 5 turns in Ukrainian, Witcher inn scene with the existing demo setup) to check that it works and to measure seconds per turn sequential vs parallel. Report numbers.
- Update `docs/tools.md` if you choose any new library (follow its format).

## Budget
Under 0.30 USD.

## Output
Final report: what changed, test count, live smoke numbers (s/turn, $), spend, open questions, branch name and worktree path as full absolute paths.
