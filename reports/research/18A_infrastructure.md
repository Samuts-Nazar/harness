# Task 18A: prior art, infrastructure and techniques (2026-10-19)

> Lead spot-check (2026-10-19): Hidden Door fast/slow post (2026-10-16; slow lane up to 20 calls; 0.5% of turns waited) and NCP-Bench arXiv 2608.08160 (best model 42% commitment survival after 20 turns) confirmed. Note: the "about 21 s per turn" figure is from task 6; after task 9/12 a live turn is about 16 s with parallel NPC chains.

Method: live web search and page fetches on 2026-10-19; no code changes, no paid API calls. Page summaries came from a fetch tool that sometimes saw only an abstract; such claims are marked (abstract). I read `docs/decisions.md`, `docs/tools.md`, `reports/code_study/SUMMARY.md`, `reports/canon_pilot/SUMMARY.md`, `docs/HANDOFF.md`, `reports/decision_gaps.md`. I did NOT read `design/schema.md`, `ideas/*`, or the pilot test plan in full, so schema-level statements are hedged.

## Verdict
The core design (code owns state, append-only log, visibility filter at retrieval, typed judgments, validated extractor diffs, two times per record, origin links) matches or exceeds the best 2026 prior art. The closest independent match is Hidden Door's engine (Oct 2026). Nothing found says the core must be redone. The risks are around it: (1) book time/place quality, (2) retrieval and memory behaviour over years, (3) latency, (4) no regression harness for isolation and commitments, (5) how NPCs treat player claims, (6) pretraining knowledge overriding the isolation prompt.

## Ranked recommendations

### Change now (before building more)
1. **Saga-wide canonical timeline before ingesting more books.** Pilot: 24 of 80 events had the wrong story day, no places. Every strong book-memory system anchors on story time (Living the Novel, E2RAG, DREAM). Store dates as interval plus confidence plus basis ("day 7 of arc", "March 1193"), place per event, and source offsets. Ingestion is cheap (extrapolated below); a schema change later is not. Cost now: small. Later: re-run plus migration.
2. **Fast/slow turn loop.** Hidden Door: the fast path answers the player; the slow path (5-20 model calls) runs while the player reads and prepares a brief for the next turn; only 0.5% of turns waited on it. Our 21 s/turn sequential pipeline should move extraction, off-screen updates, salience and next-turn briefs to a background lane, with parallel NPC calls. Adopt the idea (no library). Cost now: pipeline shape; later: rewrite of the turn loop.
3. **Evaluation harness from our own log.** Three automatic checks: isolation (KBF-style questions: what each NPC witnessed or not), commitment/fact survival (NCP-style, 20+ turns with a player pushing), canon drift. Public numbers show why: the best model keeps narrative commitments in 42% of 20-turn runs; persona first failure after about 10 turns. Use LLM judges only with reference answers and a human-agreement check. Add record/replay of provider calls for offline regression. Cost now: low; later: you will not know what regressed.
4. **Memory structured-first with immutable evidence.** Raw event/text atoms are never rewritten; facts are derived with origin links; summaries are derived views, never the source of truth. Evidence: structured fact stores 0.70-1.00 vs embedding retrieval 0.30-0.95 task success; curated-summary memory fell 96% to 72% by week nine while a provenance-typed graph rose to 90%. This is already our direction; keep it.
5. **Decide who resolves the truth of a player claim.** Where Winds Meet shipped NPCs that accept invented quest completion. Our decisions say player info is like anyone's; the pipeline needs a code-side resolution step (Concordia-style proposal then resolution) so NPCs can only believe, doubt or check, never "know". It is an open gap in decisions already.
6. **Prompt layout for caching.** Order: static world and style rules, then character file, then dynamic scene. DeepSeek cache hit is about 1/50 of a miss; OpenRouter `session_id` pins routing (10 min). Cost now: none.

### Plan for later
- Embeddings for canon/memory: `qwen/qwen3-embedding-8b` on OpenRouter ($0.01/M) is the best-documented multilingual option; best Ukrainian retrieval backbone in a 2026 UNLP shared-task paper, with a reranker adding recall. Keep FTS5 + typed lookup first; test embeddings on the 10 pilot questions.
- Background consolidation ("sleep-time"): Letta and Hidden Door's slow lane. Derived views over the log, never deletion. Forgetting (FadeMem) as retrieval decay only.
- Small local models: Qwen3.5-9B Q4_K_M reaches about 55 t/s on an RTX 3070 (32K), but VRAM is shared with the compositor; narrow subtasks only. Hidden Door's LoRA on Qwen3-1.7B beat a 120B model on one narrow rewrite (97% vs 94%). Candidates: speaker picker, perspective rewrite, looks extraction. Verify Ukrainian first.
- Grounding checker for NPC lines: small NLI models (MiniCheck family) answer "is this claim supported by this context" in about 200 ms; English-centred, test on Ukrainian before trusting.
- Structured output: use `json_schema` where supported, but for narration prefer "think freely, then format" (constrained decoding hurts open-weight writing/reasoning; a 2026 follow-up reports up to +27% from free-then-constrain).
- Bi-temporal validity ("valid from / until") for facts and states as in Graphiti; we already have two times, an end-of-validity is cheap.
- Speculative prefetch (ICLR 2026): up to 55% next-action accuracy, up to 20% latency cut. Small gain; after fast/slow.

### Ignore
Mem0/Zep/Letta as dependencies (vendor benchmark disputes; they model one user, not many isolated characters); full GraphRAG and any graph database (Kuzu archived 2025-10-10, successor LadybugDB 0.x, FalkorDB; SQLite recursive CTEs cover our needs); million-agent frameworks (OASIS, AgentSociety, Light Society); AI Town; NPC SaaS (Inworld moved to a voice stack; Convai/ACE are voice-first); stuffing full history into context (does not scale to years; context rot); RL fine-tuning pipelines.

## Where we are likely to hit their failures
- Midpoint contradictions: errors cluster mid-narrative (ConStory). Mitigation: canon/campaign check on every narration.
- Delta-only extractors drop still-true items with weaker models (Multihog, already in the code study).
- Parametric override: models recognise out-of-scope questions but answer anyway (CHARM: compliance failure, not awareness). Our post-check is the right fix; measure its false-reject rate (known too strict).
- Hidden Door shipped a spoiler bug where a character motivation text revealed a secret: any text the writer sees is a leak surface, including NPC goal/intent notes. Put them in the isolation tests.
- Literal reading of metaphors ("took his hand" added a severed hand to inventory): the extractor needs a semantic filter on state ops.
- Sycophancy: narrators accept player actions; Hidden Door lets world rules decide death and authored playbooks decide what follows. Same lesson for our judgments.

## Findings with sources

### Engines and frameworks
- **Hidden Door** (licensed literary worlds). Oct 2026 blog. Fast/slow architecture: fast writer gets a limited brief (prevents premature secrets), slow lane runs long-horizon planning, NPC goals, scene readiness; 5-20 calls per turn; 0.5% of turns delayed. https://www.hiddendoor.co/blog/fast-slow-architecture-latency-turn-based-narrative (2026-10-16). Agentic harness: strong tool-using model, four tool groups (world context, history, quality assessment, authored playbooks), "much less enforced structure than our previous ones, more small clear tools"; fractal memory. https://www.hiddendoor.co/blog/agentic-story-harness-narrative-ai-context-model (2026-10-02). LoRA: https://www.hiddendoor.co/blog/lora-low-rank-adaptation-narrative-game-dev-storytelling (2026-09-10). Bugs: https://www.hiddendoor.co/blog/favorite-bugs-fixes-january-2026-product-changes . Death/consequences: https://www.hiddendoor.co/blog/death-narrative-worldbuilding-game-player-choices . We differ: they let a strong model call tools; we keep code authority and typed judgments. Their post supports our isolation of the writer; copy the slow lane.
- **Concordia** (DeepMind). v2.4.0 2026-03-06 added an asynchronous engine; v2.3.0 scene-aware event delivery. https://github.com/google-deepmind/concordia/releases . Already studied in `reports/code_study/concordia.md`.
- **Orchestrated Reality** (arXiv 2606.16014, 2026-06-14): PDVA pipeline (plan, diff, validate, apply content-hashed JSON deltas) over canonical JSON state. Work in progress, no quantitative results. Same idea as our extractor diff plus validation. https://arxiv.org/abs/2606.16014
- Small open projects with the same shape: Omnia https://github.com/sortedcord/omnia-legacy ; NarrativeEngine-P https://github.com/Sagesheep/NarrativeEngine-P ; RPG-MCP https://glama.ai/mcp/servers/@Mnehmos/rpg-mcp/blob/ea933ed6a4b58565dd0d6f34b777961f0509410e/README.md . Convergent design; none with epistemic isolation.
- **Project Sid / PIANO** (Altera, arXiv 2411.00114, Nov 2024): 10-1000+ agents, concurrent modules with a cognitive controller (abstract only). Not needed at our scale.
- **OASIS** keeps its simulation in SQLite at up to a million agents: SQLite is fine. https://camel-ai.org/blogs/oasis
- **Intra** (Ian Bicking, 2025-07): tool use made the model worse at creative narration; normalised action intent before resolution; NPC events filtered by room; unbounded event history loses critical memories; serial events are expensive. https://ianbicking.org/blog/2025/07/intra-llm-text-adventure . Supports a no-tools narrator plus code validation.
- **SEP "AI dungeon master with real memory"**: event log + vector DB + knowledge graph; reactive retrieval failed ("storyteller invents new narratives"), proactive retrieval before narration worked; 20+ hours with minor breaks. https://sep.com/blog/building-an-ai-dungeon-master-with-real-memory/ . We already retrieve before generation.
- **Kathaaverse** (book to text adventure, HN 2025-07): characters lose context, Gandalf appears without cause, sycophancy; commenters recommend an object-state DB and programmatic constraints. https://news.ycombinator.com/item?id=44725202
- **Where Winds Meet, Vaudeville, RyzaChat** (Arcanum, 2026): NPCs accept player testimony; a separate Game Master AI validating input before the character answers is the shipped fix. https://arcanumrpgs.com/blog/games-with-ai-npcs/ . Why AI NPCs are rare: cost grows with play, novelty fades, "feels like AI" (Frisson Labs, 2026-05-21) https://www.frisson-labs.com/ai-npcs-2026 .
- Index of 63 papers on AI RPG memory, NPC fidelity, state: https://arcanumrpgs.com/research/ (verified 2026-09-25). Useful for 18B too.

### Memory, knowledge, belief
- **ReverieMem / "Staying In Character"** (2606.25632, 2026-06): visibility-tagged facts, +34.6 points knowledge-boundary fidelity; KBF-QA 4,386 questions over 8 novels. In the code study already. https://arxiv.org/abs/2606.25632
- **MemIR, provenance-role collapse** (2605.25869, 2026-05): typed atoms separate evidence, cues and truth-bearing claims. https://arxiv.org/abs/2605.25869 . **Eywa** (2605.30771): "evidence before belief", zero LLM calls inside retrieval. https://arxiv.org/abs/2605.30771
- **BeliefMem** (2605.05583): keep several candidate conclusions with probabilities (Noisy-OR) instead of one; avoids self-reinforcing errors. Fits rumours and coexisting versions. https://arxiv.org/abs/2605.05583
- **SymbolicToM** (2023): explicit per-character nested belief graphs. https://arxiv.org/abs/2306.00924 . **Sotopia-ToM** (2605.02307): ToM prompting cut privacy violations 9.9% to 2.2% (GPT-4o). https://arxiv.org/html/2605.02307v2 . Decrypto: newer reasoning models often assume the opponent sees their private info. https://arxiv.org/abs/2506.20664
- **CHARM** (2609.01352, 2026-09): role-play hallucination is mainly compliance failure; "verified parametric overrides". https://arxiv.org/abs/2609.01352 . **Living the Novel** (2512.07474): story-time-aware knowledge graph prevents spoiler leaks. https://arxiv.org/abs/2512.07474 . **Tricking LLM NPCs into spilling secrets** (2508.19288, abstract only). https://arxiv.org/abs/2508.19288
- **When Does Memory Help?** (2609.05441, 2026-09): 23,440 episodes, $42.57; fact stores 0.70-1.00, embeddings 0.30-0.95; "full replay is never economical". https://arxiv.org/abs/2609.05441
- **Ground Truth First** (2607.21962, 2026-07): longitudinal memory test; curated map 96% to 72% by week 9, provenance graph rises to 90%; weakly written facts fail 24% vs 2%. Library Veracium. https://arxiv.org/abs/2607.21962 . The only test I found that looks at weeks, not hours.
- **Benchmarks are shaky:** LoCoMo answer key 6.4% wrong, judge accepted up to 63% of deliberately wrong answers https://dev.to/penfieldlabs/we-audited-locomo-64-of-the-answer-key-is-wrong-and-the-judge-accepts-up-to-63-of-intentionally-33lg ; vendors dispute each other https://mem0.ai/blog/ai-memory-benchmarks-in-2026 ; BEAM at 10M tokens: Mem0 48.6%. Do not choose a memory product from leaderboards.
- **Graphiti/Zep** (bi-temporal, episodic/semantic/community layers): idea worth borrowing; graphiti-core 0.30.2 (2026-09-08), churn and backend breakage in issues (FalkorDB 6 rewrite). https://pypi.org/project/graphiti-core/ ; https://github.com/getzep/graphiti/issues
- **Letta MemFS** (git-backed markdown memory, "dreaming"): close to our per-character linked files; confirms the approach is viable and diffable. https://docs.letta.com/concepts/memfs . Basic Memory (markdown plus wikilinks): https://jimmysong.io/ai/basic-memory .
- **Long-Lived Characters, Local Inference** (2609.18935, 2026-09-16): incremental NPC memory updates without re-reading history; relevant only to local KV-cache setups. https://arxiv.org/abs/2609.18935
- **FadeMem** (2601.18642, forgetting) https://arxiv.org/abs/2601.18642 . **Rumour simulation** (2502.01450): personas and network shape spread from none to 83% of agents; supports spread by notability and attitude. https://arxiv.org/abs/2502.01450

### Consistency and evaluation
- **NCP-Bench** (2608.08160, ICML 2026): 100 environments; best model 42% survival after 20 turns; fact conflict rates 40-68%. https://arxiv.org/abs/2608.08160
- **ConStory / Lost in Stories** (2603.05890): contradictions concentrate in factual and temporal dimensions and in narrative midpoints. https://arxiv.org/abs/2603.05890
- **RoleBreak** (2609.16614): first persona failure after 10.4 turns (spoken dialogue). https://arxiv.org/abs/2609.16614
- **WSE-bench** (2608.15654): consistency and richness do not trade off smoothly; scale helps length, not coherence. https://arxiv.org/abs/2608.15654 . **NARRA-Gym** (2605.08503) https://arxiv.org/abs/2605.08503 .
- **IVIE** (2606.13348) and **World-State Transformations** (2605.24719): LLM proposes, symbolic layer validates; small human studies (8 players for the latter). https://arxiv.org/abs/2606.13348 ; https://arxiv.org/abs/2605.24719
- **LLM-as-judge:** position bias flips verdicts about one third of the time; verbosity and self-preference bias; without a reference answer judges over-credit wrong answers and adding one flips verdicts by up to 85% (2607.12885, 2026-07). Check agreement with a human sample before trusting. https://www.alphaxiv.org/abs/2607.12885
- Test tooling: record/replay of LLM calls exists (standin, cendor-cassette, llmvcr). Our fake provider covers unit tests; recorded-live replay would cover prompt regressions. https://pypi.org/project/cendor-cassette/ (small packages; vet first, or write about 50 lines).

### Generation and latency
- Structured output engines: XGrammar (default in vLLM/SGLang), llguidance (about 50 microseconds per token, near-zero startup), llama.cpp GBNF. Relevant to local models only; on OpenRouter use `json_schema` where supported. https://arxiv.org/abs/2411.15100 ; https://github.com/guidance-ai/llguidance
- "Thinking Before Constraining" (2601.07525): free reasoning then constrained format, up to +27%. https://www.alphaxiv.org/abs/2601.07525
- Prompt caching, OpenRouter docs: automatic for DeepSeek, OpenAI GPT-5.6+, Gemini 2.5, Grok, Groq, Moonshot, Z.AI; DeepSeek reads 0.1x; `session_id` sticky routing, 10 min idle. https://openrouter.ai/docs/guides/features/prompt-caching
- DeepSeek direct pricing page: V4.1-Flash $0.15-0.3 in (miss), $0.003-0.006 hit, $0.6-1.2 out; off-peak (outside 01-04 and 06-10 UTC Mon-Fri) is half price. Schedule big ingestion off-peak. https://api-docs.deepseek.com/quick_start/pricing . Whether OpenRouter passes the same off-peak rate was not verified.
- Speculative Actions (ICLR 2026) https://arxiv.org/abs/2510.04371 ; Speculate with Memory (2607.12236) https://www.alphaxiv.org/abs/2607.12236
- Ukrainian costs about 2-3x the tokens of English (older estimates; newer tokenizers do better). https://www.frontiersin.org/journals/artificial-intelligence/articles/10.3389/frai.2025.1538165/pdf . Set budgets in Ukrainian tokens.
- Context rot: usable accuracy falls well before the advertised window. https://hamel.dev/notes/llm/rag/p6-context_rot.html . Relevant to ingestion with 1M-context models: keep scene windows.
- Local: RTX 3070 8 GB benchmark, Qwen3.5-9B Q4_K_M 54.9 t/s at 32K (page updated 2026-04-01). https://localllm.in/blog/best-local-llms-8gb-vram-2025

### Book ingestion
- Pilot cost check: the pilot arc (97k characters) cost $0.013 on the v2 pipeline. `data/witcher_books.txt` is 9.06 MB, 797k words (Cyrillic about 2 bytes per character, so roughly 4.5M characters, about 47x the pilot). Linear extrapolation: about $0.6 per pass; even a 10x pipeline stays near $6. Cost is not the constraint; quality is. (Extrapolation, not measured.)
- **E2RAG** (EACL 2026, ChronoQA): entity-event dual graph with temporal-causal consistency, beats GraphRAG variants on causal and character consistency questions. https://aclanthology.org/2026.eacl-long.90 ; https://arxiv.org/abs/2506.05939
- **DREAM** (2608.05170, KDD 2026): event-aware memory graph from novels, temporally ordered and causally linked; abstract gave no numbers. https://arxiv.org/abs/2608.05170 . BookCoref gives coreference data on full books. LitBank and BookNLP are English-only and old; for Ukrainian use the LLM plus our glossary.
- GraphRAG-style indexing is the expensive family (LazyGraphRAG cut it to 0.1%); our targeted event pass is the cheap kind. https://www.beri.net/article/graphrag-vs-vector-rag-indexing-query-cost-lightrag-lazygraphrag-2026
- No Witcher event dataset found: only character co-occurrence network maps and fan chronologies (e.g. https://mina86.com/2022/witcher-chronological-order/). Sapkowski wrote in Polish; the corpus is the Ukrainian translation, so names follow the translator (hence the glossary). Cross-check dates against a fan chronology; licence of wiki-style sources not checked.

### Storage and stack
- SQLite is fine at this scale. sqlite-vec 0.1.11 (2026-07) is pre-1.0; brute force is enough at a few hundred thousand vectors. https://github.com/asg017/sqlite-vec
- Kuzu archived 2025-10-10; fork LadybugDB v0.19.1 (2026-08-12). Do not build on a graph DB. https://oneuptime.com/blog/post/2026-08-12-kuzu-archived-pin-0-11-3-fork-or-migrate/view
- Checks against `docs/tools.md`: nothing found contradicts the entries. Additions: embeddings candidates `qwen/qwen3-embedding-8b` ($0.01/M), `perplexity/pplx-embed-v1-0.6b` ($0.004/M), `nvidia/nemotron-3-embed-1b:free`, from https://openrouter.ai/blog/insights/best-embedding-models-2026/ (updated 2026-09-24). DeepSeek off-peak pricing and 1M context confirmed. Ukrainian quality of these embedders on our canon questions is untested.

## Unverified or weak
- arXiv items were read at abstract level through a summarising fetch tool; numbers come from abstracts, not full papers. DREAM gave no numbers; Orchestrated Reality has none.
- Mem0/Zep numbers are vendor-contested; used only to show the disagreement.
- No public AI-Witcher engine and no fan-community threads on AI Witcher play turned up; that is not proof none exist.
- Project Sid failure details not read beyond the abstract.
