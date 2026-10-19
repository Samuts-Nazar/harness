# Task 10: Should records be in English? (experiment)

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `reports/bakeoff/SUMMARY.md` (section "Language of judgments"), `experiments/bakeoff/` (test set, prompts, grading method).

## Question
Task 7 found that decision models judge better when state and questions are in English. If records (facts, knowledge, memory files) are stored in English, NPC and narrator prompts will contain English context while they must write Ukrainian. Does that hurt the Ukrainian text? And does it change leaks or staying in character?

## Method
- Reuse the task 7 narrator (9) and NPC (12) situations. Make an English version of each context (facts, character profile, memory, scene state); keep the player's lines and the output-language instruction in Ukrainian. Write the English versions yourself, faithfully.
- Run both variants (Ukrainian context vs English context) with `openai/gpt-6-luna` (chosen narrator/NPC model) and `deepseek/deepseek-v4.1-flash-1017` (fallback). 3 samples per item per variant at the engine temperature, so style differences are not one-sample noise.
- Add an explicit output-language instruction to both variants (the engine prompts had none in task 7).
- Grade blind (shuffle, label, key read only after grading), same criteria as task 7: Ukrainian quality 0–5 with notes on calques, Russianisms and English leaking in (untranslated names of things, English word order), in character, knowledge leaks.
- Also run the extractor (10 passages, `deepseek-v4.1-flash-1017`) asked explicitly for English facts vs Ukrainian facts; compare recall/precision against the task 7 gold.
- Report effect sizes with the sample size; say plainly when a difference is noise.

## Not in scope
No engine code changes. Experiment code under `experiments/language/`, report at `reports/language/SUMMARY.md` (readable on a phone: verdict first, then tables).

## Budget
Under 0.50 USD.

## Output
Final report: verdict (store records in English: yes / no / mixed, with the reason), spend, branch name and worktree path as full absolute paths.
