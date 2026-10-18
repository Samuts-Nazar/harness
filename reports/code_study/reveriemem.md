# ReverieMem (arXiv 2606.25632)

"Staying In Character: Perspective-Bounded Memory For Book-Based Role-Playing Agents", Tang, Zhang, Yang, Tang, Li, Lai, Yang (UNSW, Sydney, Alibaba Tongyi Lab), cs.CL, 24 Jun 2026. https://arxiv.org/abs/2606.25632

## Availability

- **No code was found.** The arXiv HTML and PDF contain no repository link (I searched the full text for `github`, `code`, `release`). A GitHub search for "reveriemem" returned 0 repositories on the date of this study. Per the task, this report studies the paper itself.
- References therefore use **paper sections, tables and appendices**, not file paths and line ranges. Anything not stated in the paper is marked "not specified".
- **License:** the paper is under the arXiv perpetual non-exclusive license (stated on the HTML page). No code license exists. The ideas and the algorithm are free to re-implement. Do not reproduce its prompts verbatim (the prompts are in Appendix F, Tables 11-13).

## What it is

A memory architecture for character agents built from novels. It targets two failures: **Factual Overreach** (a character uses true facts it could not know) and **Stylistic Monotony** (a character flattened to one voice). Memory is built **offline** from the full book, per focus character, in three layers, and queried at inference with every retrieval restricted to the facts the speaking character may see.

## 1. State representation and storage (section 3.2)

- **Episodic layer:** per character, a corpus of first-person scene summaries, one per scene the character was present for, written in that character's voice (what they did, felt, perceived, inferred). Indexed by dense embedding.
- **Semantic layer:** a knowledge graph of facts as **SPOCV tuples**: subject, predicate, object, **C** (in-narrative cause, when explicit) and **V** (the visibility set: the set of characters allowed to know the fact). Table 8 of Appendix B shows six example tuples that cover the four visibility routes.
- **Personality layer:** per character, (a) a set of situation-dependent behaviour *patterns* (a short description plus canonical excerpts, for example "Lestrade in cautious deference to Holmes"), and (b) an emotion-transition record derived from per-utterance annotations, with inferred intent.
- Storage backend is not specified (dense retrieval is mentioned, no database).
- It is a **static** memory built from a finished book. There is no write path during play. The paper does not address updating memory as events happen.

## 2. How state is extracted (section 3.3, Source-to-Memory)

All extraction is by an LLM from the source text, offline, with human input limited to a focus-character list and aliases.

1. *Scene preparation:* LLM-guided partition into scenes, each with metadata (location, time, atmosphere) and a roster that marks each focus character as present and active, present but silent, or only referenced.
2. *Episodic summarisation:* a first-person retrospective per character per scene, **generated scene by scene without access to later narrative**, so a summary cannot contain the future.
3. *Knowledge-graph extraction:* two stages, extract entities (7 types), then relations with causes. Aliases are unified across scenes and facts are deduplicated.
4. *Visibility assignment (V), two phases:*
   - Local: direct experience for the fact's subject and object; observation for characters present at the scene of the fact; common knowledge for world-level background.
   - Propagation: **organisational sharing**, tracing each fact through a character-organisation membership graph derived from the same scenes.
5. *Personality clustering:* utterances annotated with an emotion triple and intent, scenes clustered by behavioural similarity into patterns, each with a one-line embedded description and exemplar excerpts.

No schema validation or repair loop is described. Quality of V depends on the LLM-written scene roster.

## 3. Per-character knowledge separation (sections 1, 3.1, 3.4)

This is the paper's core and the closest match to our design principle.

- **Where the filter sits:** at retrieval, in code. "Every retrieval restricted to the visibility-allowed subset" (3.4). Facts outside V "cannot be surfaced by any amount of retrieval relevance" (3.2). Nothing tells the model what it does not know; the facts are simply absent from its prompt. This is the same stance as `docs/decisions.md` ("Never pass a fact with an instruction like 'you do not know this'").
- **Refusal by absence:** when the visible pool has no answer, the agent "refuses rather than searches harder" and acknowledges the gap in character (3.1, Memory-Fusion constraint 2 in Table 13).
- **Four visibility routes:** direct experience, observation (present in the scene), organisational sharing (via membership graph), common knowledge. This is a more complete provenance model than any of the other projects. It has no "heard from someone" route, no distance, no time lag, and no loudness.
- **Scene-first recall (Conway's Self-Memory System):** retrieval starts from the character's own first-person scene summaries (Anchor), and these are used to generate probes for the fact pool. The point is that scene context confines the search to the character's lived experience before any fact lookup.

### Inference pipeline (3.4, Algorithm 1 in Appendix C)

1. **Anchor:** similarity search over the speaker's episodic corpus, returning scene memory.
2. **Self-Probe loop:** an LLM turns the scene memory and current situation into one concrete noun-phrase probe (Table 11, JSON output `{refined_query, self_probe}`), runs it as a dense query over the visible fact subset, adds results to a pool, and repeats until the "Sufficient" check passes or a round cap is hit. From round 2 on, sufficiency is decided inside the same Self-Probe call (Appendix C).
3. **Personality track (parallel):** Emo-Gate decides if the turn carries a salient emotional event; if so, Emo-Transition proposes a new emotional state from the character's record; Pattern picks a behaviour pattern by embedding match (Table 12, JSON `{chosen_mode_id, brief_reason}`).
4. **Memory-Fusion:** one call that writes 1-3 first-person sentences from scene memory, visible facts and the chosen pattern's excerpts (Table 13).

Per query this is several LLM calls (probe rounds, gate, pattern, fusion). Anchor and Vis-Retrieve are non-LLM dense retrieval (Appendix C).

## 4. Long histories (sections 3.2, 3.4)

Compression is the offline construction itself: book -> scene summaries plus a fact graph. Retrieval is dense search over the per-character episodic corpus and the visible subset of the graph, in a multi-round loop. It does not handle a growing, live history; the memory is built once from a finished text.

## 5. Canon / rule consistency

No canon check in the sense of our design (no store of canon versus campaign). The system *is* built from canon text. It enforces **what a character may say about canon**, not whether new output contradicts canon. There is no contradiction detection and no drift handling.

## 6. Evidence for the design (sections 4-5)

KBF-QA: 4,386 multiple-choice questions over eight novels (2,442 "KRf" visible-fact items, 1,944 "KR" invisible-fact items), five options including a refusal option. Metric KBF is the sample-weighted harmonic mean of recall and refusal accuracy. gpt-5-mini, greedy decoding, from Table 1:

| Method | recall (KRf) | refusal (KR) | KBF |
|---|---|---|---|
| direct (no retrieval) | 36.4 | 38.2 | 37.2 |
| naive RAG | 63.8 | 10.0 | 18.9 |
| RAPTOR | 66.4 | 8.7 | 16.8 |
| HippoRAG | 65.4 | 11.3 | 20.9 |
| ComoRAG | 33.0 | 45.9 | 37.7 |
| BookWorld | 41.6 | 35.5 | 38.7 |
| ReverieMem | 68.1 | 81.2 | **73.3** |

Take-aways that matter for us:

- **Standard RAG over a shared store has near-zero refusal** (8.7-11.3%). Good retrieval relevance is what causes the leak. This quantifies why epistemic isolation must be at the retrieval layer.
- **Ablation (Table 2):** without the semantic (visibility-tagged fact) layer, recall collapses to 10.8% while refusal is 93.1% (KBF 17.8), meaning the model refuses everything. Without the episodic layer, refusal drops from 81.2% to 47.0% (KBF 60.9). Scene-anchoring matters, not just the filter.
- The narrative-generation win rate against baselines (about 79% per the abstract) is judged by gpt-4o, pairwise, using BookWorld's five-dimension protocol (5.1). It is an LLM-judge result.

Caveat: refusal accuracy is measured on multiple-choice items with an explicit refusal option. Free-form play is easier to leak in. The KBF benchmark measures canon books, where V was assigned by the same pipeline that is evaluated (some circularity: the gold V comes from the paper's own construction, Appendix D).

## 7. Limits stated by the authors (Limitations)

- No stress tests on perspective-heavy works (Rashomon-style multi-witness contradiction, information-asymmetric detective plots, unreliable narrators).
- **No dedicated mechanism for multi-character interaction**: in multi-agent scenes it relies on "simple judgment over the current scene context".

## 8. Fit with `docs/decisions.md`

| Our decision | ReverieMem |
|---|---|
| Isolation at retrieval, never by instruction | Yes, the central mechanism, with measured benefit. |
| Fact = free text + metadata (when, where, who witnessed/heard, loudness) | SPOCV plus V. Has cause and visibility; lacks time, place, loudness (the scene metadata exists at the scene level, not in the tuple). |
| Notability-driven spread (quiet stays, loud travels) | No. V is fixed offline by presence, organisation, and common knowledge. |
| Per-NPC separate call with isolated context | Yes in spirit: one character per query. |
| Salience as a separate judgment (NPC need not comment on what it would not care about) | Partly: the Emo-Gate decides whether a turn carries a salient *emotional* event. This is a different notion. |
| Online, append-only event log, rollback | No. Offline static build. |
| Canon store vs campaign store | Only canon. |
| Code validates | Not described. |

## 9. What is reusable

**Directly reusable as design (re-implement):**
- Visibility as a first-class field on every fact, applied as a hard filter before any ranking. Retrieval relevance must never be able to override it.
- Provenance routes for visibility: *direct*, *observed*, *shared via group membership*, *common knowledge*. Our design needs these plus *heard* (second-hand with distance and time).
- Construct first-person per-character episodic summaries **without access to later events** (online, this is automatic: write the summary at the moment of the scene).
- Refusal-by-absence: when the visible pool is empty, the prompt contains no fact and the model is asked to respond in character about the gap.
- The KBF-style evaluation: a recall item set and a refusal item set scored by a harmonic mean. A cheap regression test for our isolation, built from the campaign's own log (what each NPC witnessed).

**Ideas only:**
- Scene-anchored two-stage retrieval (episodic frame, then probe-driven fact fill) for NPC agents.
- Situation-dependent personality patterns with exemplar excerpts as style anchors (useful for Witcher voices drawn from the books, with `data/` constraints: store excerpts only locally).
- Emotion-transition gating of when to update an NPC's mood.

**Conflicts / not to adopt:**
- Offline-only build; V assigned once by an LLM reading the whole book.
- Multi-round LLM probing per line, which multiplies calls per NPC utterance. Acceptable under "quality beats cost", but needs a budget.
- It treats V as a static set. Our visibility changes with time and distance.

## 10. License

arXiv non-exclusive license for the paper text. No code. Ideas free.

## Assumptions / limits

- Read: the arXiv HTML (sections 1-6, Tables 1-2, Limitations, Appendix C and F prompts). I did not read the appendices on KBF-QA construction (D), pairwise protocol (E), or the per-book statistics (A) in detail, nor the narrative-generation Table 3 beyond the headline claim. Figures were not viewed.
- The 79% win rate is quoted from the abstract (the numeral did not survive HTML extraction in my copy of the text; the web search summary gave "~79%").
