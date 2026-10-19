# Task 7: Model bake-off (2026-10-19)

Total API spend: **at most $0.13** of the 1 USD budget (`experiments/bakeoff/spend.py`).
Everything below is measured on our own Ukrainian test set (Witcher setting, Рагнар). Gold answers were written before any run. Text outputs were graded blind (shuffled, labelled A–F) by the Claude Code agent. Small samples: treat gaps under ~0.3 points or ~8 percentage points as noise.

## Recommended stack

| Role | Model | Why |
|---|---|---|
| Narrator | `openai/gpt-6-luna` | Ukrainian 4.4/5, no flags in 9 scenes |
| NPC lines | `openai/gpt-6-luna` | Ukrainian 4.8/5, leaks 8% (others 33–58%) |
| Extractor | `deepseek/deepseek-v4.1-flash-1017` | recall 95%, valid JSON 10/10, fewest bad state ops |
| Judge (first) | `liquid/d1-ultra` | 93.8%, $0.004 per 1000, 0.36 s |
| Judge (escalation, below 0.8) | `openai/gpt-6-luna` as LLM judge | 95.8%, $0.02 per 1000 |
| Fallbacks | `deepseek/deepseek-v4.1-flash-1017` (text), `perplexity/pplx-decider-v1.2` (judge) | one other vendor each |

Cost of play: **about $0.013 per hour** (40 turns/hour, assumption). Text $0.012, judgments $0.001. Context in the test is short; real campaigns send longer prompts, so scale the text part.
Time per turn: **9.3 s sequential, 7.0 s parallel** (measured, real calls). Time until the first NPC line is ready: about 4.5 s either way.

Free (`:free`) models were not tested (see assumptions). Recommended roles all have a paid fallback from a different vendor.

## Text roles (top 3 each)

Scores: Ukrainian quality 0–5 (natural, no calques or Russianisms; 0 = not Ukrainian or unusable).

### Narrator (9 scenes)
| # | Model | UK | Flags* | s/call | $ per call |
|---|---|---|---|---|---|
| 1 | gpt-6-luna | 4.44 | 0 of 9 | 2.8 | 0.00011 |
| 2 | deepseek-v4.1-flash-1017 | 4.22 | 2 of 9 | 3.2 | 0.00013 |
| 3 | gemini-3.5-flash-lite | 3.33 | 0 of 9 | 2.1 | 0.00075 |

Also: glm-5.3-flash 3.33 (5 flags, once wrote NPC speech); qwen3.8-omni-flash 2.44 (2 of 9 answered in English, 6.5 s); command-a-plus 2.22 (2 of 9 unusable).
*Flags = narrator decided the player character's actions/feelings, or a canon/scene error. NPC speech in narration: only glm (1 of 9).

### NPC line (12 situations)
| # | Model | UK | In character | Leaks | s/call | $ per call |
|---|---|---|---|---|---|---|
| 1 | gpt-6-luna | 4.83 | 4.83 | 1 of 12 | 2.2 | 0.00005 |
| 2 | deepseek-v4.1-flash-1017 | 4.25 | 4.42 | 5 of 12 | 1.9 | 0.00006 |
| 3 | qwen3.8-omni-flash | 3.67 | 3.58 | 4 of 12 | 4.8 | 0.00010 |

Others: gemini 3.17 (7 leaks), glm 2.83 (7 leaks, 2 broken lines), command-a-plus 2.75 (reasoning text leaked into the line).
Leak = the line asserts something the character had no channel to learn, including invented specifics. Model choice matters more than the output check (see below).

### Extractor (10 passages)
| # | Model | Recall | Precision | Valid JSON | Facts in Ukrainian | Bad state ops |
|---|---|---|---|---|---|---|
| 1 | deepseek-v4.1-flash-1017 | 95% | 100% | 10/10 | 2/10 | 22% |
| 2 | qwen3.8-omni-flash | 91% | 100% | 10/10 | 4/10 | 56% |
| 3 | gpt-6-luna | 86% | 100% | 10/10 | 9/10 | 50% |

Others: glm 86%, gemini 73%, command-a-plus 9% (only 1 of 10 valid JSON).
Finding: the engine prompt has no language instruction, so most models write facts in English. Either say "write facts in English" on purpose (see language section) or add the instruction. "Bad state ops" are ops the validator would reject (removing an item that is not there, wrong direction).

## Decision models (60 judgments, 96 calls each)

| Model | Acc | EN | UK | ECE* | Below 0.8 | Acc if ≥0.8 | s/call | $ per 1000 |
|---|---|---|---|---|---|---|---|---|
| gpt-6-luna (LLM judge) | 95.8% | 97 | 94 | .035 | 4% | 96% | 1.32 | 0.021 |
| liquid/d1-ultra | 93.8% | 97 | 86 | .040 | 10% | 98% | 0.36 | 0.004 |
| elorian/glimpse (chat) | 92.7% | 92 | 92 | .022 | 0% | 93% | 0.36 | 0.225 |
| perplexity/pplx-decider-v1.2 | 91.7% | 94 | 89 | .056 | 10% | 95% | 0.52 | 0.003 |
| deepseek-v4.1-flash (LLM judge) | 89.6% | 94 | 86 | .037 | 4% | 94% | 0.46 | 0.019 |
| typesafe/jev-1.14 (old baseline) | 87.5% | 86 | 86 | .094 | **41%** | 100% | 0.36 | 0.016 |
| perplexity/pplx-decider-flash-v1.2 | 81.2% | 86 | 78 | .092 | 19% | 86% | 0.31 | 0.001 |
| laya (English) | 52.1% | 56 | 56 | .298 | 41% | 47% | 0.68 | 0 (local CPU) |
| laya (multilingual) | 49.0% | 47 | 50 | .362 | 29% | 52% | 0.29 | 0 (local CPU) |

*ECE = calibration error, lower is better. EN/UK columns are the 36 items that exist in both languages.
- Types: perception 92–100%, canon-vs-drift 96–100%, unknowable claim 92–100% (d1, luna), narrator speech 92–100%, salience weakest (58–92%).
- **d1-ultra** is the best dedicated decider: more accurate and better calibrated than Jev 1.14, 10% escalation instead of Jev's 41%, same speed.
- **glimpse** is a chat model, not a decider (no decision endpoint). Its output price $3.00 per M is above the $2.50 ceiling, so it is excluded by policy. It also never reports doubt (0% below 0.8).
- Escalation costs almost nothing: 10% of d1 calls go to luna, which is cheaper than Jev's 41%.
- All hosted deciders (Jev, pplx, d1) share one schema, `POST https://openrouter.ai/api/v1/systemone` (the old `/api/alpha/decisions` path also works). The existing `JevJudge` client works for all three by changing only the model name.
- The flash decider returned HTTP 429 under sequential load; the client needs retry with backoff.

### Laya (local, Apache 2.0)
- Installed `laya[serve]` into `/home/cock/1TB/AI/laya/venv` (CPU torch, 6 threads), served on 127.0.0.1:8765. English and multilingual checkpoints.
- Zero-shot it is at chance: 52% and 49% on the 60 judgments, 66% and 56% on the real NPC-check state where "always no" scores 63%. Wire format (list, string, `{"document":...}`) made no difference.
- Context: the engine's NPC-check state is 325 tokens on average in Ukrainian for the English model (512 limit, 4 of 68 truncated) and 232 for multilingual (1024 limit, none truncated). It fits, but accuracy does not.
- Fine-tune estimate (not measured): the model card reports 0.766 for its own typed-decisions checkpoint after RL fine-tuning on four workflows. For our five judgment types expect 300–1000 labelled examples per type (1.5–5k total), labelled by the Claude Code agent, then a GPU run. The likely best case is below d1-ultra (94%) at $0.004 per 1000 decisions. **Not worth it** unless the game must run fully offline.

## Language of judgments: English or Ukrainian?
- On the 36 items that exist in both languages, English beat Ukrainian for 4 of 5 hosted deciders (d1 97 vs 86, pplx 94 vs 89, flash 86 vs 78, luna 97 vs 94); Jev tied. Pooled over the five hosted deciders, 12 items were right only in English and 2 only in Ukrainian (sign test p ≈ 0.01).
- Checks of Ukrainian text (NPC lines, narrator output) work fine with an English question and a quoted Ukrainian line: d1 100% on narrator-speech, 100% on unknowable claims.
- **Recommendation:** keep internal state, judgment questions and probably records in English; keep only player-facing text in Ukrainian. Not measured: whether English records in the NPC and narrator prompts hurt Ukrainian style. Test this before switching storage.

## Parallelism and time per turn (gpt-6-luna + d1-ultra, 4 runs each)
Step latencies: narrator 2.8 s, NPC line 2.2 s, extractor 2.2 s, a decision 0.4 s.
| Plan | Whole turn | First NPC line ready |
|---|---|---|
| Sequential | 9.3 s | 4.5 s |
| Parallel | 7.0 s | 4.5 s |
Parallel plan: after the narrator, run the speech check, both NPC chains (line then check) and the extractor concurrently; the NPC-line extraction and the salience judges follow. Calls in a turn are independent enough to parallelise; the decider client retries on HTTP 429 (not counted separately).

## NPC output check: too strict, and also too loose
On 68 graded NPC lines (43 correct, 25 with a leak) with the engine's exact question:
| Checker | Wrong rejects of correct lines | Leaks caught |
|---|---|---|
| d1-ultra, threshold 0.5 (engine now) | 11.6% | 64% |
| d1-ultra, threshold 0.7 | 4.7% | 56% |
| pplx-decider-v1.2, 0.5 | 9.3% | 40% |
| Jev 1.14, 0.5 | 9.3% | 56% |
| d1-ultra, revised question, 0.5 | 2.3% | 40% |
| gpt-6-luna as LLM judge | 2.3% | 8% |
- A wrong reject only matters when every retry is rejected. If rejects were independent across 2 retries, 11.6% per try gives about 0.2% fallbacks. They are not independent: the same character and situation tends to produce the same small invention, so the fallbacks seen in task 6 are more likely correlated (not measured here).
- Proposed fix (not applied; engine code untouched): (1) reject only at p ≥ 0.7; (2) when all retries fail, show the candidate with the lowest suspicion instead of the fixed fallback line; (3) rely on the generator: gpt-6-luna leaks 8% against 33–58% for the rest, which beats any checker we tested; (4) test a claim-splitting check (extract atomic claims, judge them in one batched decider call).
- Caveat: n = 68, one grader, and my "leak" label is strict (it counts invented specifics). Treat the rates as rough.

## What was not done / caveats
- Free `:free` models were not tested. Candidates and reasons for the three extra text models are in `docs/assumptions.md`.
- One sample per prompt at temperature 0.7, one grader (Claude Code agent), 9 / 12 / 10 text items. Rankings of close models are not significant.
- `~perplexity/pplx-decider-latest` was skipped (alias, not in the catalog).
- `harness/policy.py` still has the old allowlist (Anthropic Haiku is the default extractor and escalation target). Needs a code task.

## Where things are
- Test set, runner scripts, raw outputs, blind grades: `/home/cock/projects/harness/.claude/worktrees/task7-bakeoff/experiments/bakeoff/` (after merge: `/home/cock/projects/harness/experiments/bakeoff/`).
- Catalog snapshot: `experiments/bakeoff/catalog_2026-10-19.json`.
- Metrics JSON: `reports/bakeoff/decide_metrics.json`, `text_metrics.json`, `npc_check_metrics.json`.

Spend: ledger `experiments/results/spend.jsonl` (gitignored) $0.117, hosted decider runs $0.002, unrecorded decider calls at most $0.005; total at most $0.13.
