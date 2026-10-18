# Task 2 summary: what the experiments mean for the design

All results: Ukrainian text, 39 / 48 / 20 hand-built cases per experiment, one labeller. Small samples; read every number with the confidence intervals in the individual reports. Total spend about $2.4 of the $3 budget (E1 $2.02, E2 $0.11, E3 $0.28 by the ledger; OpenRouter's key usage grew by $2.45 over the session).

## E1: filtered vs instructed context (see `E1.md`)
- With open (neutral) probes, leaks were rare in both conditions and not distinguishable: both judges agree on a leak in 2/156 replies with the fact in-context-plus-instruction (A) and 6/156 with the fact absent (B). The B "leaks" were all on canon cases, i.e. pretraining knowledge of the saga (0/40 on invented-fact controls).
- With *leading* probes (the player's question already states the fact), models without any instruction went along with the premise much more often than with the instruction (12% vs 4% by the unaudited first judge, upper bound).
- **If the guarantee that matters is "a character cannot reveal what it was never given"**, filtering at retrieval is what delivers it by construction: it cannot leak context it does not have, and it removes the instruction tokens. Instructing is not shown to be worse in this data, but its only demonstrated real leak was the small model, and it relies on the model complying; a design that wants a guarantee should not depend on that.
- **If a canon-known fact must stay unknown to a character** (the saga's secrets), filtering alone does not prevent leakage through pretraining knowledge (about 5% of canon replies in B). That needs an output-side check (a judgment on each NPC line: did this character have a channel?). This is the same check needed for **facts injected by the player's own question**, which no retrieval filter can stop.
- **If you use an LLM judge for leak detection**, use a strict verdict and two judges: the cheap judge's "leak" was right about 56–75% of the time, "hint" almost never.

## E2: Jev vs LLM+JSON (see `E2.md`)
- Jev was reachable with the existing OpenRouter key through `POST /api/alpha/decisions` (`typesafe/jev-1.14`, `jev-1.13`). No blocker.
- Accuracy on 48 narrow judgments: Jev 0.85 (1.14) / 0.91 (1.13); LLMs 0.81–0.97, Sonnet 5.5 best. Not separable from Haiku, Gemini-lite, Qwen-9B or gpt-5.4-mini at this sample size.
- **If latency or cost per judgment matters** (many judgments per turn): Jev p50 0.28 s vs 0.7–1.1 s, $0.019 per 1000 vs $0.034 (Haiku) to $0.675 (Sonnet); batching four questions about one state into one call cut latency 4x and cost 2.7x in a small probe. Only a 9B open model matched Jev on cost, and its confident wrong answers made its probabilities unusable.
- **If you need calibrated confidence to route uncertain cases elsewhere**: Jev's probabilities were informative (64% correct at p<0.8, 94–98% above) and best-calibrated by ECE; Haiku and Sonnet's verbalized probabilities were also informative; Qwen-9B's were not.
- **If you need the best accuracy on subtle judgments** (relationship direction + magnitude, borderline salience): the stronger LLMs (Sonnet, and Haiku on binary types) were ahead; Jev's magnitude scores were no better than small LLMs. Jev's errors were mostly false "yes" at low confidence on low-stakes "no" items.
- Not tested: long retrieved context (Jev's long-context mode starts at ~32 KB), subtle contradictions needing canon retrieval, prompt-tuned LLM baselines.

## E3: state extraction (see `E3.md`)
- All 7 models returned valid JSON on all 20 passages. Fact recall ranged 0.61 (Gemini-lite) to 0.91 (ministral-8B); hallucination (facts the passage does not support) was ≈ 4% for the 4B/8B/9B models, 0.9% for DeepSeek-V4-flash and 0% for Gemini-lite, Haiku and Sonnet.
- **If recall of story facts matters more than a clean store** (cheap, filter later): the small open models (4B-9B) catch 79–91% of gold facts at $0.005–0.021 per 100 turns, but emit 5–6 facts per passage (much scenery) and about 4% invented ones.
- **If a clean, near-hallucination-free store matters** (you will not review it): Haiku 5.5 / Sonnet 5.5 / Gemini-lite had 0% unsupported facts; Gemini-lite is the most precise (0.91) but missed 39% of gold facts; Sonnet had the best F1 (0.81) at roughly 20x Haiku's cost.
- **Witness lists are the weak spot for every model** (exact agreement 0.23–0.55 with my gold; mostly too-short lists). Since epistemic isolation depends on who witnessed what, **if the witness list is the thing the design relies on**, do not take it from the extractor as is: derive it in code from the scene's cast/location state and let the extractor only propose the fact text.
- Inventory and relationship extraction could not be ranked (4 and 1 gold items). Injury extraction was good for all models (F1 0.78–0.95).
- Granularity is a prompt/system question as much as a model question (2.4 to 6.2 facts per passage on the same text).

## Cross-cutting caveats
- Every judge and matcher is an LLM; each report lists the manual spot-check I did and its size.
- Hand-built tiny sets: none of these results replace a test on real engine prompts and a larger labelled set.
- Ledger spend per experiment is in `experiments/results/spend.jsonl` (git-ignored).
