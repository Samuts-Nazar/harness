# Task 22: "Writes like a person" bake-off, graded by the user

Work fully autonomously. Do not ask questions. Budget: 0.20 USD (hard). No engine code changes.
Read first: `docs/decisions.md` (model policy), `docs/tools.md` (Models), `reports/bakeoff/SUMMARY.md`, `reports/research/21B_tone_leaks.md`, `worlds/witcher/style.md`, `experiments/style/` (the task 15 NPC moments).

## Why
The user played the engine and found the experience worse than a chat with Gemini in AI Studio: Gemini "writes more humanly and pleasantly". Our narrator/NPC model `openai/gpt-6-luna` was chosen by agent grading on correctness (Ukrainian quality, leaks), never by the user's taste for human, pleasant writing. The user distrusts OpenAI models. This bake-off asks the user directly.

## Candidates (from the live OpenRouter catalog, checked today; never from memory)
- Only the newest models: released or updated within about the last 3 months (use the catalog's `created` field; state each model's date).
- Within the price ceiling (input ≤ 0.60, output ≤ 2.50 USD per M), not OpenAI, not Anthropic. Pick 4–6, favouring families with strong multilingual/creative signals. Include `xiaomi/mimo-v2.6-pro` if it still qualifies (best Ukrainian in 21B). No old generations (the user rejected Gemini 2.5/3.5-era models as outdated).
- Baseline: `openai/gpt-6-luna` (current).
- Record the candidate list with dates and prices in `docs/tools.md`.

## Material
- 6 moments: 4 NPC moments from `experiments/style/` (include the Горст opening and a haggle) and 2 short narration moments from the Vizima situation A (tavern «Під Лисом», day 3 evening). Same prompts as the engine today (style sheet on), output in Ukrainian.
- 1 sample per model per moment (keeps the page short): about 6 × 6–7 = 36–42 texts.
- Filter out glitches automatically (foreign scripts, empty, broken) and note them per model.

## The user's page
- `app/static/human_ab.html` + `app/static/human_ab_data.js` (new files; do not touch `ab.html`/`ab_data.js`, another task regenerates them). Mobile-first, readable, Ukrainian UI.
- Per moment: all candidates' texts shuffled, labelled A, B, C…; the user ranks them or marks each 1–5 for "звучить по-людському, приємно читати"; optional note.
- At the end a copyable result string. Choices kept in the browser (try/catch around storage).
- Key in `reports/human_ab/key.json` (not served).

## Output
- Report in the final message (also try `reports/human_ab/README.md`): candidates with dates/prices, glitch counts, cost, latency per model, how to open the page (`http://192.168.1.109:8765/static/human_ab.html` when the app runs). Do not grade or rank yourself; the user's grading is the result.
- Commit on your branch only; branch and worktree paths as absolute paths.
