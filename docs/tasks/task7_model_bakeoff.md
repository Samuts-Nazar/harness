# Task 7: Model bake-off on our own tasks

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.

## 0. Fix the previous sessions' output first
- Branches `ui-prototype` and `design-schema` are NOT on GitHub, although their reports said "pushed". They live in local worktrees under `.claude/worktrees/` (the design-schema one is nested inside `.claude/worktrees/task4-core-revision/`). Push both branches to `origin` and verify with `git ls-remote origin`.
- Rule for this and every later report: give full absolute paths for every file or folder you mention, and verify every push with `git ls-remote` before claiming it.

## 1. Model policy (replace the "Model and spending policy" section of `docs/decisions.md` with this)
- Paid API calls use cheap models only: input price at most 0.60 USD and output at most 2.50 USD per million tokens. Flagship-class models are never called over the API.
- No Anthropic models in the engine.
- The model for each role is chosen by a bake-off on our own tasks, from the live OpenRouter catalog, never from memory. The bake-off is re-run when notable new models appear.
- Free (`:free`) models may be tested and used, but never as the only option for a role, because they disappear.
- Strong-model judging in development is done by the Claude Code agent itself, never over the API.
- Tests and demos use the fake provider by default; network only with `--live`.

## 2. Candidates
- Fetch the live catalog from `https://openrouter.ai/api/v1/models` (prices and context from there). Save the snapshot with its date.
- Text roles, mandatory (the user's list): `deepseek/deepseek-v4.1-flash-1017`, `z-ai/glm-5.3-flash`, `qwen/qwen3.8-omni-flash`. Add at most 3 others from the catalog (non-Anthropic, under the price ceiling, or `:free`) only if public quality signals suggest they could beat these; state why with links.
- Decision models, mandatory (the user's list): `elorian/glimpse`, `perplexity/pplx-decider-flash-v1.2`, `perplexity/pplx-decider-v1.2`, `liquid/d1-ultra`, plus `typesafe/jev-1.14` as the old baseline. (`~perplexity/pplx-decider-latest` is an alias; skip it if it resolves to one of the above.) Read each one's API docs; adapt the judge client behind the existing interface.
- Laya (local, Apache 2.0, https://huggingface.co/convaiinnovations/laya): install with `pip install laya` in the dev shell, run `laya-serve` locally (CPU is fine), it exposes the Jev-compatible `POST /v1/systemone`. Test the English and multilingual checkpoints zero-shot. Its context is 1024 tokens (multilingual up to 8192), so measure with the compact state the engine would send. Also estimate how many labelled examples a fine-tune on our judgment types would need and whether it is worth it.

## 3. Test set (Ukrainian)
- Build a fixed Ukrainian test set from the Witcher setting with Рагнар: at least 8 narrator situations, 12 NPC-line situations (including second-hand knowledge and characters who must not know something), 10 extraction passages with gold facts, and 60 typed judgment questions with gold answers (perception, salience, unknowable claim in an NPC line, narrator speaking for an NPC, canon vs drift). Write the gold answers yourself before running any model.
- Use the same prompts as the engine.

## 4. Runs and grading
- Run every shortlisted text model on narrator, NPC line and extractor sets; every decision model on the judgment set.
- You grade text outputs yourself, blind to the model name (shuffle and label). Criteria: Ukrainian quality (natural, no calques or Russianisms), staying in character, no knowledge leaks, no speaking for the player character or for NPCs (narrator), format validity, extraction precision and recall.
- Language of judgment inputs: run every decision model twice, once with state and questions in English, once in Ukrainian. Exception: checks of generated Ukrainian text (NPC lines, narrator output) necessarily contain the Ukrainian text; test those with the question in English and the quoted text in Ukrainian. Report whether English internal state is better, and whether records should be stored in English with only player-facing text in Ukrainian.
- Decision models: accuracy, calibration (does probability track correctness), latency, cost per 1000 decisions; how many fall below 0.8 and would escalate.
- Measure latency per call and check whether calls in a turn can run in parallel; report the expected seconds per turn with the best stack, sequential vs parallel.
- The NPC output check was too strict in task 6 (fallbacks on correct lines). Measure its false-reject rate on the test set with the best decision model and propose a fix; do not change engine code in this task.

## Budget
Under 1 USD total.

## Output
- `reports/bakeoff/SUMMARY.md`, readable on a phone: per role, the top 3 with scores, cost per hour of play and latency; recommended stack; decision-model table.
- Test set and raw outputs committed under `experiments/bakeoff/` (no keys, no book text beyond short quotes).
- Final report: pushed branches verified, recommended stack, total spend, all paths absolute.
