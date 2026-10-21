# 21A: the decision layer against averaging (2026-10-21)

Method: live web search and page fetches on 2026-10-21, the live OpenRouter catalog, one probe run (1981 calls, **0.052 USD of 0.30**). No engine code touched. Page summaries came from a fetch tool, so numbers are "as reported by the page"; where two sources disagreed I say so. Book-derived data (16 decision points, raw rows) is in `campaigns/21A/` (git-ignored). Code: `experiments/decisions21a/`.

## Verdict (read first)

1. **The user's idea is half right.** A dedicated decision model is cheap and fast, but it is not the cure for averaging. In our probe the deciders were *more* concentrated than the LLM (one option gets nearly all the mass in almost every point), and nothing we tried (state line, verbalized sampling) moved the book-like pick beyond noise. Who writes the options matters more than which model picks.
2. **The biggest finding is about options.** When I wrote the options from the book, the book option won 12 of 16 points even with the scene removed, because the book action was the longest, most specific option (longest in 12 of 16). After a blind rewrite to equal length it fell to ~0.35 probability with no scene at all. Any "option list written by a model that has read the books" has the same leak; any list written by a generic model lacks the rare real choices (see the open-generation result).
3. **Fine-tuning a hosted decider is not available.** d1/d1-ultra, Jev, pplx-decider: no fine-tune offered. OpenAI is shutting its fine-tuning down. Fine-tuning is possible through Together/Fireworks (open models, about 0.5 USD per million training tokens) or locally on a small open decision model; the real obstacle is training data, not price.
4. **Cheapest next step:** do not fine-tune yet. Build the options from the world's own text (extractor records of what characters did at comparable moments), pick by sampling from the decider's probabilities, and put the person's concrete state into the question. Test it on the harness below with equalised options.

## 1. Decision models usable now

Live OpenRouter catalog (`GET /api/v1/models?output_modalities=decisions`, 2026-10-21): 27 decision entries. Prices are per million input tokens, output free. All answer on `POST /api/v1/systemone`.

| Model | Created | Price | Context | Note |
|---|---|---|---|---|
| liquid/d1-ultra | 2026-10-16 | 0.042 | 32k | ours; released 2026-10-15 ([blog](https://www.liquid.ai/blog/d1-ultra)); claims +8 on the Artificial Analysis Decision Index |
| liquid/d1 | 2026-10-01 | 0.02 | 65k | 3.12B, open weights under Liquid licence per [orcarouter](https://www.orcarouter.ai/blog/liquid-ai-d1-3b-vs-lfm2-5-2-6b-base) (secondary), 16 languages |
| perplexity/pplx-decider-v1.2 (27B), -flash-v1.2 (4B) | 2026-10-16 | 0.02 / 0.01 | 262k | |
| openai/gpt-6-luna-decisions | 2026-10-07 | 0.10 | 1.05M | luna through the decisions API; **returned HTTP 502 "OpenAI refused to answer"** on my fight/sex scenes, so it is unusable for violent fiction without a fallback |
| microsoft/microsoft-decision-1 | 2026-10-10 | 0.042 | 32k | weakest in my probe |
| cloudflare/clef-flash (9B, Qwen3.5-9B fine-tune), clef (27B), clef-omni | 2026-10 | 0.038 / 0.24 / 0.15 | | Apache-2.0, 56 quantised builds, [model card](https://huggingface.co/Cloudflare/clef-flash) |
| togethercomputer/tev1-4b-experimental | 2026-09-30 | 0.042 | 32k | Qwen3.5-4B LoRA SFT, **recipe and data code public** ([repo](https://github.com/togethercomputer/Tev1), MIT; 37,840 train examples, rank 8, 1 epoch; "fine-tune your own classifier for 17 USD"); its README says logprobs are preferences, not calibrated confidence |
| jaredpalmer/kev-4b | 2026-09-25 | 0.042 | 8k validated | LoRA r16 + pointer head on Qwen3.5-4B-Base, ECE 0.029 after one temperature, out-of-domain 16 points below Jev ([card](https://huggingface.co/jaredpalmer/kev-4b)) |
| nace-ai/drex-v1.5 (9B), v2.0 (35B MoE) ; upstage/solar-decide(-flash) ; inception/mercury-decide (+ :free) ; respan/span-02 (open weights) ; scaledown/classify-1 ; typesafe/jev-1.13/1.14 | | 0.01-0.06 | | not tested |

New since task 7 and worth a bake-off on our 60 judgments: clef-flash, drex-v2.0, solar-decide, mercury-decide:free. Policy gap: `harness/policy.py` `DECISION_MODELS` lists only five, so none of these can be called (fail closed). Sources: OpenRouter [Jev guide](https://openrouter.ai/docs/guides/community/jev) says "22 decision models from 13 providers" (the catalog now lists 27).

**Which can we fine-tune?** d1 / d1-ultra: no (no mention in the announcement; a search summary states d1 is "not fine-tunable on your own data"; I could not open Liquid's docs page, 404). Jev, pplx, Microsoft, Upstage, Inception: nothing in docs. Open ones can be trained by us: Tev1 (full recipe), Kev (adapter + head), Clef (Apache-2.0), Laya (task 7: zero-shot at chance, needs domain tuning).

**Hosted fine-tuning of ordinary open LLMs** (a tuned LLM that answers with one letter works as a decider; logprobs give a distribution):
- Together: LoRA SFT 0.48 per M tokens up to 16B, 1.50 for 17-69B, minimum charge 4-100 USD per job ([pricing page](https://www.together.ai/pricing), [docs](https://docs.together.ai/docs/fine-tuning-models): Qwen3.5 4B and 9B support LoRA; docs warn some tunable models cannot be deployed as dedicated endpoints, so check deployability first). Per-size numbers via [costbench](https://www.costbench.com/software/fine-tuning-apis/together-ai-fine-tuning/) (secondary).
- Fireworks: LoRA SFT 0.50 per M up to 16B; tuned models served "for the same price as base models" ([pricing](https://fireworks.ai/pricing)).
- OpenAI: supervised fine-tuning only gpt-4.1 / mini / nano, closed to new users, jobs until 2027-01-06, models shut down 2026-10-23 and 2027-01-14 ([docs](https://developers.openai.com/api/docs/guides/supervised-fine-tuning)). Ignore.
- Gemini API tuning: shut down 2025-05-27 (secondary source, aicostcheck). Mistral: fine-tuning page now under "deprecated" in the docs URL.
- Serving through OpenRouter: only "Private Models", invite-only enterprise beta ([docs](https://openrouter.ai/docs/guides/routing/private-models)). So a tuned model is called on the provider's own endpoint; `harness/policy.py` would need a non-OpenRouter route.
- Cost sketch (arithmetic, not measured): 5,000 examples x 600 tokens x 3 epochs = 9M tokens, about 4.5 USD on Together/Fireworks, plus a minimum charge.

**Local on 8 GB shared with the compositor.** Unsloth (PyPI 2026.10.7, 2026-10-19) bf16 LoRA needs 3 GB for Qwen3.5-0.8B, 5 GB for 2B, **10 GB for 4B**, 22 GB for 9B; its guide says QLoRA 4-bit is *not recommended* for Qwen3.5 ([guide](https://unsloth.ai/docs/models/qwen3.5/fine-tune)). So on the RTX 3070 Laptop only 0.8B/2B can be trained, and a 4B/9B training run needs rented GPU (the Tev1 17 USD). Inference of a 4B (about 2.5 GB at Q4) or 9B (about 5.5 GB) decider fits, but competes with `--models-max 1` llama-server. Training speed on this card: **not found, not measured**; I will not guess.

## 2. Research on averaging of decisions (2024-2026), with evidence strength

Measured and relevant:
- **Artificial Hivemind** (NeurIPS 2025 best paper; [arXiv 2510.22954](https://arxiv.org/abs/2510.22954)): 26K open-ended queries; models repeat themselves and each other; reward models and LM judges are worse calibrated on items where annotators disagree.
- **One-Word Census** ([2607.12796](https://arxiv.org/abs/2607.12796)): 105 models, 96 category prompts, each asked 8 times; in 28 of 96 categories one answer takes 80% or more; more concentrated than humans in 18 of 20 shared categories; heavily post-trained assistants worst, lightly post-trained and persona-tuned better. (The first fetch said 44 models; the abstract page says 105.)
- **Base models beat aligned** at randomness and creativity ([2505.00047](https://arxiv.org/abs/2505.00047), COLM 2025); SimBench ([2510.17516](https://arxiv.org/abs/2510.17516)): best model 40.8/100, instruction tuning helps consensus questions and hurts high-diversity ones; "Emulate or Estimate" ([2608.03044](https://arxiv.org/abs/2608.03044)): base models are better at *sampling* individual responses, post-trained at *predicting* a distribution when asked directly.
- **Diversity collapse in game play** ([2607.19523](https://arxiv.org/abs/2607.19523)): reasoning mode narrows action diversity without raising accuracy; narrow-support imitation is a cause; training on several correct moves helps partly.
- **Persona collapse** ([2604.24698](https://arxiv.org/abs/2604.24698)): persona-specific fine-tuning *narrows* populations; no tested model has both coverage and complexity like humans.
- **Description vs history** ([2610.03998](https://arxiv.org/abs/2610.03998)): 845 people, 14 biases; demographic/personality personas recover 53-67% of between-person variation; adding the person's *earlier answers* restores human-level variation but individual prediction reaches only 28% of human test-retest. Supports "state from a specific past", not trait labels.
- **Villains** ([2511.04962](https://arxiv.org/abs/2511.04962), ACL Findings 2026): fidelity falls monotonically as character morality falls (about 3.2 to 2.6 of 5); safety-aligned models worst. Directly our "Geralt kills three men" case.
- **Induced emotion** ([2607.12631](https://arxiv.org/abs/2607.12631)): prompt-induced emotion does not significantly bias LLM choices on average (Iowa Gambling Task); anger shows some effect. A Nature-portfolio paper reports state anxiety changing consumer choices ([link](https://www.nature.com/articles/s44387-026-00122-1), paywalled, not read). Net: a state *sentence* is a weak lever.
- **Selection bias** ([2309.03882](https://arxiv.org/abs/2309.03882), ICLR 2024; follow-ups 2025-26): option order and label tokens shift picks; remedy is permuting options and averaging (PriDe). I used 3 orders for deciders.

Remedies with evidence: Verbalized Sampling ([2510.01171](https://arxiv.org/abs/2510.01171), ICML 2026, v4 2026-07-15): 1.6-2.1x diversity in creative writing, matches a fine-tuned 8B on a donation-dialogue task; limits stated: more calls, needs capable models. A router paper reports it "performs similarly if not worse than baseline" in its setting ([2604.02319](https://arxiv.org/abs/2604.02319), second-hand). Spectrum Tuning ([2510.06084](https://arxiv.org/abs/2510.06084), ICLR 2026) restores steerability by post-training. XTC and min-p are token-level sampling ([2608.22758](https://arxiv.org/abs/2608.22758): 62.3% creativity preference, 150 raters) and cannot act inside a hosted decider, which returns probabilities, not tokens. Idea-generation diversity ([2607.27553](https://arxiv.org/abs/2607.27553)): AI options are less diverse than human ones; pooling vendors, personas and constraints close most of the gap.
What failed or is weak: persona descriptions, fine-tuning on narrow data (CDT paper: plain fine-tuning scored 45.7 vs 61.0 for its codified rules on its benchmark), prompted emotion, reasoning mode for diversity.

## 3. Predicting a fictional character's real choice

- **LifeChoice / CharMap** ([ACL Findings EMNLP 2025](https://aclanthology.org/2025.findings-emnlp.813/); [arXiv 2404.12138](https://arxiv.org/abs/2404.12138)): 2,512 decision points from 470 novels (the 2024 version had 1,462 from 388 books). Reported accuracy conflicts between sources: search summaries give GPT-4o 60.07% (64.22% with CharMap persona-memory retrieval) and Claude 3.5 about 60%, an older version says 49%. I could not read the table; treat "about 60%, +5-6 points from retrieving the character's own past" as the claim. No human ceiling found.
- **Fandom benchmark and Codified Decision Trees** ([2601.10080](https://arxiv.org/abs/2601.10080)): 83 characters, 5,141 scenes, next action scored by NLI (entail 100, neutral 50, contradict 0); CDT 61.0 vs human-written profile 58.3; retrieval ICL 56.0; fine-tuning 45.7. Scores are *entailment of a free action*, a weaker bar than ours.
- CoSER, HER ([2601.21459](https://arxiv.org/abs/2601.21459)), OdysSim 8B ([2606.14199](https://arxiv.org/abs/2606.14199): 93.2% reaction alignment vs 93.5% for real users on an out-of-distribution set, weights released).
- Takeaway: with options given, models are around 60%; nobody reports a human-vs-model gap on *rare but real* choices, which is our question. Our own probe is the first data on that.

## 4. The probe (16 decision points, pilot arc "Відьмак" + the dawn scene)

Setup: 16 points from the ingested arc, each with a situation known before the choice, a short state line, six options including the book's action (book option marked) and one pre-registered "typical" option. Decisions by innkeeper, Velerad, Foltest, Ostrit and Geralt. Metrics: P(book) mean probability on the book option, top = points where the argmax is the book option, H_mean spread of the mean distribution (0 = one option takes all), H_pick spread of individual picks. LLM = `openai/gpt-6-luna`, 5 samples each in shuffled order; deciders: 3 orders. Uniform baseline P(book) = 0.167. With 16 points, differences under about 0.12 or 3 points are noise.

**A. First run, options written from the book (leaky):**
| method | P(book) | top=book |
|---|---|---|
| d1-ultra | 0.655 | 12 |
| d1-ultra, no scene at all | 0.480 | 12 |
| luna closed list | 0.600 | 10 |
| luna, no scene | 0.562 | 9 |

No scene yet the book option wins: the options themselves give it away (book option longest in 12 of 16).

**B. Equalised options (luna rewrote every list blind to 7-9 word clauses; book longest or tied in 8 of 16):**
| method | P(book) | top=book | P(typical) | H_mean | H_pick |
|---|---|---|---|---|---|
| d1-ultra, no scene | 0.349 | 8 | 0.22 | 0.78 | 0.18 |
| luna, no scene | 0.388 | 6 | 0.30 | 0.40 | 0.40 |
| d1-ultra | 0.456 | 8 | 0.24 | 0.57 | 0.11 |
| d1-ultra + state line | 0.445 | 7 | 0.25 | 0.46 | 0.10 |
| pplx-decider-v1.2 | 0.411 | 9 | 0.25 | 0.70 | 0.13 |
| microsoft-decision-1 | 0.311 | 6 | 0.27 | 0.47 | 0.04 |
| luna closed list | 0.450 | 8 | 0.26 | 0.26 | 0.26 |
| luna + state | 0.438 | 8 | 0.18 | 0.14 | 0.14 |
| luna verbalized sampling | 0.463 | 10 | 0.22 | 0.56 | 0.18 |
| luna VS + state | 0.410 | 8 | 0.21 | 0.60 | 0.16 |
| names/world words anonymised: d1-ultra | 0.360 | 7 | 0.22 | 0.67 | 0.10 |
| anonymised: luna | 0.312 | 7 | 0.26 | 0.41 | 0.41 |

(The unequalised anonymised runs gave d1-ultra 0.563 vs 0.655 plain, luna 0.463 vs 0.600.)

Reading (honest, small sample):
- Content of the options alone gives ~0.35 (floor); the scene adds ~0.10; recall of the books adds another ~0.10 (anonymising removes it). So only about 0.10 of the 0.45 is "the model understood the situation". Everything else is option wording and memorisation. The brief's own warning (the model has read the books) is confirmed.
- Concentration: pick spread across orders is 0.04-0.18 for deciders (they pick one option almost always) and 0.14-0.41 for luna. No method covers the spread of options. Luna with a state line is the most concentrated (H 0.14) and has the lowest typical rate.
- **State line and verbalized sampling: no gain** over plain (0.445-0.463 vs 0.456). State lowered "typical" picks for luna (0.26 to 0.18) without raising book picks.
- Deciders disagree with the LLM on single points (p02, p03: luna picks the book option 60%, d1 13-15%), so single-point accuracy is noisy; models split on exactly the cases that are "non-typical-but-human" (innkeeper looks away, Geralt bargains in a corrupt offer).
- Missed by nearly every method with scene: p01 (Geralt lets the stranger go on, answers gently), p07 (neither refuse nor accept, haggle), p10 (Foltest orders the kill if in doubt), p12 (Ostrit goes himself with a bribe), p14 (binds Ostrit as bait). Controls where book = typical (p11, p16, also p09) score 0.8-1.0: the instrument works when the author is conventional.
- Examples of the averaging we are after: p04 (three insulters grab Geralt): the book's lethal draw gets 0.04 from d1-ultra, 0.40 from luna; deciders pick the Sign (stun/throw back) ~35-41% when options include it.

**C. Open generation (no options; luna lists six things; I read the first 3 of 5 lists per point).** Book action present in 8 of 16 points (innkeeper refuses, innkeeper looks away, Foltest forbids killing, Foltest orders kill-if-fail, Ostrit offers the bribe, Ostrit attacks, Geralt frees him only when the slab moves, Geralt lies in the sarcophagus), partly in 5 (p01, p05, p07, p11, p14), absent in 3 (p04 the lethal draw, never listed in 18 lists; p06 the burgomaster turns friendly and tells everything: he interrogates or bargains instead; p08 the body in a palace sarcophagus: custom-burial or chapel instead). The three absent are the author's strongest characterising choices. **A decision layer that only picks from a list cannot recover them; the list writer must.**

Caveats: one human gold per point; options include the answer by construction (a ranking test, not free prediction); the "typical" label is my pre-registration, not measured; 16 points; luna reasoning disabled; one run, no repeats of the equalisation; the equaliser (luna) may itself have flattened the book option; I wrote the options, which is the very leak I describe.

## 5. Where the idea breaks, and what completes it

1. **Same data, same average.** Confirmed: deciders trained on assistant-era data prefer the "reasonable" option; they cover less of the option set than the LLM. They are fast and calibrated, not diverse.
2. **Who writes the options.** Options from a generic model miss the author's rare moves (section 4C); options from the book leak the answer (4A). Source of options must be the world's own corpus without the answer: for each situation, retrieve what *other* characters did at similar structural moments (extractor records: the canon store already has actions, `canon_event`, `canon_reaction`) and add one "characteristic move" slot per character, then pad with generic ones; equalise form with a neutral rewrite.
3. **Illogical choices come from state.** Evidence says a one-line state helps little; behavioural history helps more ([2610.03998](https://arxiv.org/abs/2610.03998)). So condition on the *record* (what this character did before in similar spots, their last three decisions, what they believe falsely) not on adjectives. That is what the event log holds.
4. **Do not make the decider pick the winner; make it produce a distribution and sample.** The decider returns probabilities; take a draw at temperature >1 (or flatten, or exclude the top mass at the option level, XTC-style) and then log the draw. Verbalized sampling from luna is the alternative, 4-5 calls dearer. In my data both left the book pick unchanged, so sampling buys *variety*, not fidelity; fidelity must come from the options and the record.
5. **Fine-tuning** would help only if trained on (situation, what the character did) from the world's text; extraction gives roughly a few thousand pairs from book 1 at about 0.013 USD per arc, i.e. data is cheap but the labels are the author's single draw per situation. CDT paper (fine-tuning lost to rules) and persona-collapse paper (persona fine-tuning narrows) are warnings. Test with a held-out arc before spending.
6. Moderation: luna-decisions refuses violent scenes (HTTP 502); keep d1-ultra primary with fallbacks.

## 6. Recommendations

| Rank | Item | Now | Later |
|---|---|---|---|
| **Adopt** | Option writer separated from the picker; options neutral-rewritten to equal length; permute order and average (3 orders) | S | M if skipped |
| **Adopt** | Sample from the decider's probabilities (not argmax) for tone/emotion/reaction choices; log the draw | S | |
| **Adopt** | Decision-point harness (this probe) as a regression test, with the equalised control and no-scene control; report P(book) minus no-scene floor | S | |
| **Adopt** | Add clef-flash, drex-v2.0, solar-decide, mercury-decide:free, luna-decisions to `DECISION_MODELS` for a bake-off on the 60 judgments | S | |
| **Test next** | Options from the world's own record (similar moves by other characters + per-character characteristic slot); measure open-generation coverage of book moves (target above 8/16) | M | |
| **Test next** | Conditioning on the character's last decisions/beliefs instead of adjectives | S | |
| **Test next** | Local small decider (Tev1-4B / clef-flash 9B Q4) with a LoRA trained on our extracted decision pairs; needs rented GPU for 4B (Unsloth: 10 GB) or 2B locally | M-L | |
| **Test next** | Verbalized sampling for the few high-stakes choices (cost 4-5 calls) | S | |
| **Ignore** | Fine-tuning a hosted decider (d1, Jev, pplx): not offered. OpenAI fine-tuning: being shut down. XTC/min-p for decisions: wrong layer. Laya: at chance. | | |

Measured limits of this report: the probe cannot say which method is "right"; it can say that with equal options and a scene no method beats ~0.46 and that a no-scene control reaches 0.35.

Spend: 0.052 USD (1981 calls; ledger `campaigns/21A/ledger.jsonl`). Next probe design: 40-60 points from the next arc, options built by method 5.2, 3 repeats, blind second option-writer.
