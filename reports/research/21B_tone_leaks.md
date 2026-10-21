# 21B: prose tone and invented-fact leaks

Date of research: 2026-10-21. Branch `worktree-agent-aefb1f06d7751ae62`. Spend: 0.024 USD of 0.30 (ledger files outside the repo). No engine code touched. No book text committed (probe prompts used `data/` at runtime; outputs stayed outside the repo).

## Verdict in six lines

1. **No hosted base model is available cheaply right now.** The live OpenRouter catalog (468 models, fetched 2026-10-21) has none; Hyperbolic, the one public host of Llama 3.1 405B Base, now says "base completion models ... aren't available". The only real route to a base model is local or rented GPU (Gemma 4 base checkpoints exist, Apache 2.0). I could not test one: my download of a 8 GB GGUF to the 1TB disk was refused by the permission layer, so I stopped there.
2. **The strongest evidence for removing assistant voice is fine-tuning on the author's own corpus**, not prompting: Chakrabarty et al. (arXiv 2510.13939, v4 2026-03-17) fine-tuned GPT-4o per author (median 81 USD) and expert readers then preferred the AI text for style and quality; detectors flagged 3 percent instead of 97. But the route we would copy is closing: OpenAI is retiring fine-tuning of 4o/4.1 on 2027-01-14 and `gpt-6-luna` cannot be fine-tuned; Together AI has discontinued serverless LoRA serving (adapters need a dedicated endpoint).
3. **Our own probe (5 NPC moments, 2 runs, blind-graded by me) found nothing that beats the current luna prompt**: dropping the rule list for a "book page" frame made luna slightly worse, `gemma-4-31b-it` worse, `mistral-nemo` unusable in Ukrainian, a rewrite pass about equal. The one clear tone defect I measured was ours: **the manner notes seed stock phrases** ("fair measure", "a bad draft", "bad for business") that then appear in most outputs of every model.
4. `gpt-6-luna` accepts **no sampling parameters** (no temperature, top_p, min_p; its supported list is reasoning, verbosity, structured output). Sampler tricks (min_p, XTC, antislop) need another model or a local server.
5. **Leak check**: claim splitting works for recall (24 of 25 leaks caught on our 68 graded lines with one luna call per line) but over-flags (20 to 32 of 43 clean lines at the settings I tried). Cheapest path likely to work: claim split once, then judge each claim with the typed decider against the knowledge, accept lines whose only unsupported claims are few and cheap to retry; plus a generator-side cite-or-omit step. Test set exists already (68 lines, 25 leaks).
6. Ukrainian AI-text detectors are not usable as a quality gate (no robust public Ukrainian detector; best evidence is a 87 to 88 percent academic-text classifier). Use a home-made stylometric distance to the author's own text instead.

## 1. Tone: what removes assistant voice (evidence with links)

### 1.1 Why it happens (measured)
- Human stories show 2 to 4 times the token-level entropy of model continuations; instruction tuning widens the gap, base models are closest to human; gap is 25 to 30 percent larger in creative writing. 28 LLMs. Mistral-Small-24B had the smallest gap, Gemma-3 the largest. https://arxiv.org/html/2602.16162v1 (2026-02).
- Instruction tuning, and DPO most, cuts output diversity in all five models tested; remedy "conformative decoding" mixes base and instruct log-probs (gamma 0.5) and raised diversity without loss in most models. Needs a base and instruct pair with the same tokenizer and local logits, so it cannot run through OpenRouter. https://arxiv.org/html/2507.20956v1 (2025-07).
- Persona leakage: assistant traits are upweighted across all personas the model plays (Anthropic alignment blog, "Persona Selection Model", 2026). Context dilution of a system prompt over long chats is the other known mechanism. https://alignment.anthropic.com/2026/psm/ ; https://futureagi.com/blog/evaluating-llm-personas-style-2026/ (secondary).

### 1.2 Base (non-instruct) models: availability, checked live
| Route | Finding | Link |
|---|---|---|
| OpenRouter catalog | 468 models, none is a base model; `openai/gpt-3.5-turbo-instruct` is instruct-tuned and costs 1.5/2.0 (over our ceiling) | `GET https://openrouter.ai/api/v1/models`, 2026-10-21 |
| Hyperbolic | Llama 3.1 405B Base BF16 announced 2024-08-27, but the current docs list only chat models (glm-5.3-flash, deepseek-v4.1-flash, mimo-v2.6-flash ...) and say base completion models "aren't available"; prices current 2026-10-20 | https://www.hyperbolic.ai/blog/llama-3-1-405b-base-bf16 ; https://www.hyperbolic.ai/docs/inference/overview |
| Together AI | fine-tune list shows only instruct (IT) variants, no base | https://docs.together.ai/docs/fine-tuning-models |
| Local weights | Gemma 4 (released 2026-03-31) has base checkpoints `google/gemma-4-E4B`, `-E2B`, `-12B`, `-26B-A4B`; Apache 2.0; "pre-trained on 140+ languages"; official GGUFs of the base at `ggml-org/gemma-4-E4B-GGUF` (Q8 8.0 GB) and `ggml-org/gemma-4-26B-A4B-GGUF` (Q8 26.9 GB) | https://huggingface.co/google/gemma-4-E4B ; https://ai.google.dev/gemma/docs/releases ; https://huggingface.co/ggml-org/gemma-4-E4B-GGUF |
| Ukrainian-tuned | MamayLM (INSAIT, Gemma 3 based; v2.0 12B and 27B) ranks second on the Ukrainian LLM leaderboard (2026-05-06) behind Gemma-4-26B-A4B-it; these are instruct models | https://huggingface.co/collections/INSAIT-Institute/mamaylm-v10-gemma-3 ; https://benchmarklist.com/benchmarks/ukrainian_llm_leaderboard/ |

Fit for 8 GB VRAM shared with the compositor: E4B Q4 about 3 to 5 GB of GPU weights is plausible; 12B Q4 (about 7 GB) is not; 26B-A4B needs CPU offload of experts. Not measured by me. A base model also has no chat template, so the engine's "NPC call" would become a completion with a hand-built book-page prompt, and the knowledge-boundary rules would have to live in that prompt text (CHARM below says models override such rules).

### 1.3 Style fine-tuning on one author's corpus
- Chakrabarty, Ginsburg, Dhillon, arXiv 2510.13939 (first 2025-10-15, v4 2026-03-17): 50 authors, MFA writers vs ChatGPT/Claude/Gemini, 28 MFA-trained and 516 general readers, blind. In-context prompting lost to the experts; fine-tuning GPT-4o on each author's complete works reversed it for both style and quality; detectors flagged 3 percent vs 97 percent; median cost 81 USD per author; two books were enough. https://arxiv.org/abs/2510.13939 ; summary https://the-decoder.com/ai-models-can-mimic-famous-authors-writing-styles-using-just-two-books-for-training/ . Caveat: English, whole-passage writing tasks, closed model, no dialogue-in-a-simulation test.
- Availability of the route today:
  - OpenAI: SFT for 4o/4.1 models; all, **including fine-tuned versions, stop 2027-01-14**; `gpt-6-luna` cannot be fine-tuned; tuned 4.1-mini inference 0.80/3.20 is above our ceiling. https://datanorth.ai/news/gpt-4o-and-gpt-4-1-leave-openais-api-on-14-january-2027-fine-tuned-versions-included
  - Together AI: LoRA SFT 0.34 to 5.60 USD per M tokens depending on size (minimum charge 4 to 22 USD per job); models include Gemma 4 31B/26B, Qwen3.8 27B, Llama 3.3 70B; **serverless LoRA inference discontinued**, adapters run on a dedicated endpoint (hourly GPU). https://www.together.ai/pricing ; https://docs.together.ai/docs/lora-training-and-inference
  - Fireworks: SFT 0.50 USD per M tokens up to 16B, 3.00 up to 80B; a search summary says tuned LoRA is served at base-model serverless price (not confirmed on the official page I could fetch). https://www.fireworks.ai/pricing
  - Tinker (Thinking Machines): per-token training (Qwen3-8B 0.40 USD per M tokens in July 2026), exports standard PEFT adapters usable in vLLM/SGLang. https://www.beam.cloud/blog/tinker-model-pricing
  - Local QLoRA: 8 GB is the stated minimum for a 7B QLoRA (third-party guides); Unsloth supports Gemma and Qwen families (its requirements page was 404 for me; check before starting). https://machinelearningplus.com/gen-ai/unsloth-fine-tuning/
- Data volume: the Sapkowski Ukrainian text in `data/` is the training set, for personal use only, never shipped; "any world's own reference text" fits the engine rule, but the tuned adapter is per world and per user, so it is a later feature, not the engine core. Mixed-effort estimate for a first try: 1 to 3 M tokens, about 1 to 10 USD on Together/Fireworks/Tinker class services, then needs a host that serves the adapter (this is the real cost).

### 1.4 Sampling and decoding
- XTC (exclude top choices), arXiv 2608.22758 (2026-08-24): Distinct-2 plus 11 to 15 percent, repeated trigrams minus 27 to 47 percent, blinded study with 150 raters preferred it for creativity 62.3 percent, no overall-quality loss by LLM judges; in llama.cpp, ExLlamaV2, text-generation-webui; cannot fix homogenisation baked in by RLHF; models tested are 12B to 70B open weights. https://arxiv.org/html/2608.22758
- min-p: original ICLR 2025 claims human preference; re-analysis says the evidence does not support quality or diversity gains (Schaeffer et al., arXiv 2506.13681, 2025-06-23). Treat as unproven. https://arxiv.org/pdf/2506.13681
- Antislop (ICLR 2026, arXiv 2510.15061, code github.com/sam-paech/auto-antislop, MIT): sampler that backtracks to suppress 8,000+ phrases; FTPO fine-tuning reaches 90 percent slop reduction; English-only evidence, and it needs a slop list per language and model. https://arxiv.org/abs/2510.15061
- Training-time diversity: DivLM (arXiv 2610.06729, 2026-10-05) CPT on 18M tokens plus GRPO reaches 76.2 percent of human semantic distance vs 42.1 percent baseline on Llama 3.1 8B; temperature alone did not suffice. CreativeInstruct (arXiv 2608.07460, 2026-08-07) 48 percent more semantic diversity; English only. https://arxiv.org/html/2610.06729v1 ; https://arxiv.org/html/2608.07460v1
- **For us**: live check of `supported_parameters` in the catalog: `min_p` appears on 116 of 468 models, `top_a` on 15, `repetition_penalty` 149; `openai/gpt-6-luna` supports none of temperature, top_p, top_k, min_p, penalties. So any sampler lever means leaving luna (for example `google/gemma-4-31b-it` 0.20/0.40 or `deepseek/deepseek-v4.1-flash` support min_p) or going local (XTC in llama.cpp).

### 1.5 Rewrite and editor passes
- I found no peer-reviewed 2025/2026 evidence that a generic "remove AI-isms" rewrite makes fiction read like a given author. What exists: practical skill files (3-pass "humanizer" prompts with 36+ banned words, e.g. https://github.com/lguz/humanize-writing-skill ) and older author-style-transfer research (ASTRAPOP, arXiv 2403.08043; AuthorMix, arXiv 2603.23069) that trains adapters. Our own probe (below) shows a prompted rewrite changes little.
- Cheaper, mechanical form: a banned-phrase list built from our own logs (a "slop profile" of the narrator and NPC models in Ukrainian), applied as regenerate-on-hit. This is what Antislop automates in English.

### 1.6 Detectors of AI-isms, Ukrainian
- MULTITuDE (arXiv 2310.13606): 74,081 texts, 11 languages including `uk`, 8 generators; compares zero-shot and fine-tuned detectors. Binoculars/Fast-DetectGPT degrade on fragmented tokenisation in some languages (search summary). https://arxiv.org/abs/2310.13606 ; https://arxiv.org/html/2401.12070v3
- CEAID (arXiv 2509.26051) covers Central European languages; Ukrainian is not in it (per fetch). Ukrainian-specific: a shallow-ANN classifier on IT bachelor theses, 87 to 88 percent (https://journals.nupp.edu.ua/sunz/en/article/view/4113), academic domain, not fiction.
- Detectors flagged 97 percent of prompted literary text but only 3 percent of fine-tuned (above), i.e. detectors are a tone measure only in English-like conditions. **Recommendation**: do not buy a detector. Measure tone by (a) a banned/stock-phrase counter from our logs, (b) type-token and sentence-length distance to the author's own text, (c) blind agent grading.

### 1.7 Our probe (2026-10-21)
Script `experiments/tone21b/probe.py`; same 5 NPC moments as `experiments/style/` (Horst opens, Horst haggles, Roche, innkeeper, Marta). V0 luna with the task 15 rule list and book exemplars; V1 luna with a "Ukrainian translation of the witcher novel" book-page frame and no rule list; V2 `google/gemma-4-31b-it` same frame, temperature 1.0, min_p 0.05; V3 `mistralai/mistral-nemo` same frame, temperature 0.9, min_p 0.05; V4 `gemma-4-31b-it` rewrite of V0 using book exemplars. Run A used the old manner notes, run B the fixed `manners2.json`. 35 outputs per run, shuffled with a key, graded by me: "sounds like Sapkowski in Ukrainian" 1 to 5 and Ukrainian quality 1 to 5. **Limits**: n = 5 moments, one grader (the agent), one sample for most cells; run B used the same shuffle seed as run A, so after seeing run A's key I graded run B from the text but not fully blind. No true base model could be included.

| Variant | n | Sapkowski-likeness (A / B) | Ukrainian (A / B) | Notes |
|---|---|---|---|---|
| V0 luna + rules + exemplars | 5+5 | 3.1 / 3.4 | 4.4 / 4.4 | one answer contained two alternative versions (format fault) |
| V1 luna, book-page frame, no rules | 5+5 | 2.7 / 2.7 | 4.0 / 4.1 | one line wrote the player's reply; narration creeps in |
| V2 gemma-4-31b-it frame, temp 1.0 min_p 0.05 | 10+10 | 2.2 / 2.1 | 3.5 / 3.7 | long narrator-like beats ("голос його звучав глухо"), melodrama (face goes pale, hand trembles), one Latin leak ("apron-фартух") |
| V3 mistral-nemo frame | 10+10 | about 0 | about 0 | 18 of 20 garbled, mixed scripts or English, role-play script format; unusable in Ukrainian |
| V4 gemma rewrite of V0 | 5+5 | 3.3 / 3.4 | 4.5 / 4.4 | near-identical to its input in most cases; one rewrite cleaned a duplicate, one added the filler "звісно" |

Reading: no variant beat luna with rules (the difference V0 vs V4 is inside noise). Removing the rule list does not recover a more author-like voice for luna; a different, larger instruct model with a higher temperature wrote more "narrator" and more melodrama, which is the assistant voice, not less. Temperature plus min_p did not help a 31B instruct model.

Measured homogenisation sources (run A vs B, only outputs of V0, V1, V2, V4):
| Marker | Run A (old manner notes) | Run B (`manners2.json`) |
|---|---|---|
| "поганий протяг" ("a bad draft") in the 10 Horst outputs | 7 of 10 | 0 of 10 |
| "справедлива міра" ("fair measure") in the 10 Horst outputs | 8 of 10 | 0 of 10 |
| "поганий для бізнесу" ("bad for business") in 5 innkeeper outputs | 3 of 5 | 0 of 5 |
| "великим пальцем ... " (thumb-rubbing) in Horst outputs | 8 of 10 | 10 of 10 |

So (1) the task 15 fix of the English catchphrases worked for the phrases, (2) the manner note still seeds one physical tic that every model, every sample repeats (thumb rubbing, wiping the same mug). This is the user's "averaging in content": a note that names a single tic produces that tic every time. Remedy: a note should hold a pool of 5 to 8 small behaviours and the engine should draw one or two per call in code (this matches the living-dialogue direction), not name one.

### 1.8 Ranked recommendations (tone)
| Rank | Action | Cost now | Cost later | Evidence |
|---|---|---|---|---|
| Adopt | Manner notes: pool of behaviours, code picks 1 or 2 per call; ban English catchphrases in the note generator; add a stock-phrase counter built from our own logs to the eval harness | small code | none | probe table above |
| Adopt | Keep luna + rules + exemplars as the NPC and narrator voice; do not switch to a frame-only prompt or to `gemma-4-31b-it` | 0 | 0 | probe |
| Test next | Local base model as a draft voice: `gemma-4-E4B` base (or 26B-A4B with expert offload) via llama.cpp, completion prompt of 2 to 3 book passages plus scene note, 20 moments blind vs luna. Needs the 8 GB download (needs user approval; my attempt was blocked) | 0 USD, a few hours | maybe local serving | 2602.16162, 2507.20956 (theory; no Ukrainian test exists) |
| Test next | Style LoRA on the Ukrainian Sapkowski text for personal use: Together/Fireworks/Tinker training 1 to 10 USD, or local QLoRA of Gemma 4 E4B/12B; first decide where the adapter is served (the part that costs money) | 1 to 10 USD + host | hosting | 2510.13939 |
| Test next | XTC or min_p on a local llama.cpp model or on a catalog model that supports them, after a model is chosen | 0 | 0 | 2608.22758; min-p disputed |
| Ignore for now | Ukrainian AI-text detectors; OpenAI fine-tuning; Together serverless LoRA; generic humanizer prompts | | | sections above |

## 2. Invented-fact leaks

### 2.1 What is known
- This failure class has names: "character hallucination" and "knowledge boundary" in role play. CHARM (arXiv 2609.01352, 2026-09-01, 40 characters, 5 cultural regions, 6 LLMs): hallucination is driven by **compliance failures**: models often recognise that a query is outside the character's knowledge and answer anyway ("verified parametric overrides"). That matches our task 19 session: telling the model not to know is not enough. https://arxiv.org/abs/2609.01352
- RoleKE-Bench (arXiv 2409.11726 v2, 2025-05-20): 21 LLMs, best accuracy under 65 percent at detecting character knowledge errors; a self-recollection plus self-doubt agent (S2RD) lifted detection by 55.6 points on average (GPT-3.5 from 23.8 to 74.1 percent on known-knowledge errors). It retrieves the character's Wikipedia page; our equivalent is the character's knowledge records. https://arxiv.org/html/2409.11726
- TimeChara (11K test examples, 14 characters from four novel series) tests point-in-time hallucination: https://ahnjaewoo.github.io/timechara/ ; also RoleMRC (knowledge-boundary dimension) https://arxiv.org/html/2502.11387v1 . None is in Ukrainian.
- Grounding checkers: MiniCheck (EMNLP 2024; MiniCheck-FT5 matches GPT-4-class on LLM-AggreFact at about 400x lower cost; `Bespoke-MiniCheck-7B` tops that leaderboard) https://arxiv.org/pdf/2404.10774 ; https://huggingface.co/bespokelabs/Bespoke-MiniCheck-7B . English. Vectara HHEM-2.3 supports 11 languages (English, German, French, Spanish, Portuguese, Arabic, Chinese, Korean, Japanese, Hindi, Russian) and **not Ukrainian** (https://www.vectara.com/blog/hhem-expanded-language-support). Multilingual NLI: `MoritzLaurer/mDeBERTa-v3-base-xnli-multilingual-nli-2mil7` (27 languages in training; Ukrainian is not one of XNLI's 15 languages). None are validated on Ukrainian fiction; premises here are short records, not documents, which is a different shape from their training.

### 2.2 Why our two checks missed the cloth seller
The name check only sees names; the first-line decider asks one open question about the whole line ("no channel to learn?"). Measured on 68 graded lines (task 7): whole-line luna judge catches 8 percent, d1-ultra at 0.5 catches 64 percent with 11.6 percent false rejects (`reports/bakeoff/SUMMARY.md`). A scene description ("a tavern scene she never saw") is a claim embedded in colour; a single yes/no question gives it low probability.

### 2.3 Probe: claim splitting (2026-10-21)
`experiments/tone21b/leak_probe.py`: one luna call per line lists specific factual claims and labels each SUPPORTED or UNSUPPORTED against the same context the engine gives the decider (knowledge, recent talk, common sense); a line is flagged when any claim is UNSUPPORTED. Same 68 lines (25 leaks, 43 clean, my strict labels). Cost 0.0047 USD for 68 lines (about 0.00007 per line), a few seconds each.
| Rule | Leaks caught of 25 | Clean lines wrongly flagged of 43 |
|---|---|---|
| any UNSUPPORTED claim | 24 | 28 |
| at least 2 | 23 | 20 |
| at least 3 | 20 | 15 |
| 3-label variant (adds HARMLESS), any | 24 | 32 |
| 3-label variant, at least 2 | 24 | 24 |
| old: d1-ultra whole line, 0.5 | 16 | 5 |
Reading: claim splitting finds almost every leak, as predicted, but luna as claim-verifier is too strict. Part of the "false rejects" are probably my labels being lenient in some lines (for example "Ґеральт сказав, що їде у справах" was marked clean though it is an added specific) and part are real over-flagging of ordinary colour. n = 68, one grader, one prompt; a second prompt that added a HARMLESS label did not help. Do not adopt this as a hard gate.

### 2.4 Cheapest method likely to work for us
1. **Pre-generation (cite-or-omit)**: the NPC call is asked first for a short private plan of "what I assert", each item tagged with the id of a knowledge record or `none` (the claim extractor idea turned around: attributed generation). Code checks the tags exist in that character's channels; `none` items are dropped or must be vague. Free-prose output remains (decisions.md forbids a JSON contract on creative output, so this is a hidden pre-step, the final line is still prose). Costs one extra short cheap call; not tested.
2. **Post-check**: split claims once (the luna prompt above, 0.00007 per line), then send claims, not the line, to the typed decider in one batched `/systemone` call ("is this claim in the character's knowledge or an ordinary consequence of it?"), about 0.004 USD per 1000 claims. Retry only when at least two claims fail or any claim names a person, place, number or event. Not tested as a combined pipeline; the two halves were measured separately (claim splitting above, decider in task 7).
3. **Ground truth for "ordinary consequence"**: the missing piece is a record of what the character plausibly sees from where they stand (the cloth seller sits at a stall: market scene yes, tavern interior no). The living-dialogue world profile would supply place and vantage; the check then reads "can X observe this from X's location".
4. NLI/grounding models: skip. They are English or Russian-supporting, weakest on short fictional premises, and need a hosted GPU or a local 400 MB to 7B model for no gain over a typed decider we already pay for.
5. Latency: luna claim split about 2 s (parallel with other work possible); decider batch about 0.3 s.

### 2.5 Test set (already in the repo)
- `experiments/bakeoff/testset/npc.json` (12 situations with `gold` and `forbidden` notes), `experiments/bakeoff/grades_npc_1.json` and `_2.json` (68 usable lines, 25 leaks), raw outputs `experiments/bakeoff/raw/text_*.jsonl` and key `blind_key.json`.
- Add: (a) the task 19 cloth-seller line and the other leaks the user reported (write the exact line, the character's knowledge records, and the label); the `tests/fixtures/` directory only holds the fake Vizima session, so those need to be exported from the real session log (I could not find the line in the repo); (b) 20 positives written as "clean but colourful" lines, since false rejects were the weak point; (c) a second grader pass on the 28 disputed lines.
- Metrics: recall on leaks, false-reject rate on clean lines, fraction of turns that end on the fallback after retries, cost per turn.

### 2.6 Ranked recommendations (leaks)
| Rank | Action | Cost now | Cost later |
|---|---|---|---|
| Adopt | Add the cloth-seller line and the user-reported leaks to the test set; add vantage ("what this character can observe from here") as a knowledge channel in context | small | none |
| Test next | Claim split (luna prompt in `leak_probe.py`) then typed decider per claim, threshold on count and claim type; compare with d1-ultra whole-line on the enlarged set | about 0.02 USD | about 0.0002 per line in play |
| Test next | Cite-or-omit hidden plan step in the NPC call | one extra cheap call per NPC line | maybe a latency cost of 1 to 2 s |
| Ignore | NLI/grounding models (HHEM, MiniCheck, mDeBERTa) for this use; detectors | | |
| Note | Model choice already dominates: luna leaked 1 of 12 vs 4 to 7 of 12 for the others; keep it as generator | | |

## 3. What I did not do or could not verify
- No base-model probe (none hosted; the local download was blocked). The claim "base models read more like the author" is supported by entropy and diversity papers, not by a Ukrainian test.
- Hyperbolic's current base-model status comes from its docs page; I did not call its API.
- Fireworks' "tuned LoRA at base price" is from a secondary summary; the pricing page itself did not state it.
- Unsloth requirements page returned 404; VRAM figures come from third-party guides.
- Probe grading is one grader with partial loss of blindness in run B; sample sizes are small.
- The luna claim-split result used my strict labels.

## 4. Files
- `experiments/tone21b/probe.py`, `blind.py`, `leak_probe.py`, `leak_probe2.py` (throwaway experiment code).
- No repo changes besides these, this report, and a short `docs/tools.md` entry.
