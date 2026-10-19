# Task 6: Merge branches, update decisions, measure cost

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md` and continue.

## 1. Merge
- Merge into `main`: `worktree-task4-core-revision`, `worktree-task5-session-a`, `worktree-task5-ideas-b`. Resolve conflicts; all tests must pass on `main` afterwards.
- Before pushing, confirm no `.env`, `data/`, campaign directories or character files are tracked in any commit. Do not push if they are; report instead.

## 2. Decisions
- Replace `docs/decisions.md` with the version provided with this task. Read it in full.
- Do not change engine code to match it in this task. List every place where the current code contradicts the new decisions in `reports/decision_gaps.md` (file, what differs, rough size of the change).

## 3. Cost measurement
Goal: the user needs numbers to decide how much to spend per hour of play.
- Budget: under 1 USD total. Allowed models only (see decisions). No strong model over the API.
- Run the live demo for a scripted scene of at least 10 player turns, including at least one NPC dialogue with 2 NPCs and one second-hand-knowledge case. Log per call: role, model, input tokens, output tokens, cost, latency.
- Report per turn: number of calls by role, tokens, cost, latency. Use actual OpenRouter usage figures, not estimates.
- Extrapolate cost per hour of play assuming 30 and 60 turns per hour.
- Off-screen agents: estimate cost per in-game day for 10, 50 and 200 persistent agents at three detail levels: (a) one batched Jev tick per agent per day, (b) Jev tick plus one cheap-LLM summary per agent per day, (c) lazy only: nothing until the player meets them, then one catch-up call. Base estimates on measured per-call costs; state assumptions.
- Also estimate the one-off structured ingestion of the books (~9 MB Ukrainian text) with Haiku and with the cheapest allowed model: tokens, cost, time. Measure on one chapter, extrapolate. Do not ingest the whole corpus.

## Output
- `reports/cost/SUMMARY.md`: a short table the user can read on a phone (cost per hour, per in-game day for each agent option, ingestion cost), then details.
- Final report: merge result, test count, gaps file summary, cost table, total API spend.
