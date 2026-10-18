# RoleMemo / DualMem (role2026/rolememo)

"From Facts to Insights: A Persona-Driven Dual Memory Framework and Dataset for Role-Playing Agents", arXiv 2605.25693, 26 May 2026. https://arxiv.org/abs/2605.25693

## Availability

- **The repository is unavailable.** The abstract links `https://github.com/role2026/rolememo`. On the date of this study `git clone` fails (it asks for credentials, which GitHub does for a non-existent or private repo), the page returns **HTTP 404**, and `api.github.com/repos/role2026/rolememo` returns "Not Found". A repository search for "rolememo" finds only an unrelated project. The paper's Ethics Statement says the authors "plan to open-source the dataset and code under permissive licenses", so the code is probably not yet released.
- This report therefore studies the paper (arXiv HTML). References are **paper sections, tables and appendices**, not files and line ranges. Statements about code behaviour are not possible.
- **License:** the paper is under the arXiv perpetual non-exclusive license. The code license is unknown ("permissive" is only promised). Ideas are free to re-implement.

## What it is

A dataset (RoleMemo: 2,052 synthetic personas, 23 domains, 26,636 insights, 20,244 queries over 32k-256k token histories, section 3) and a memory framework (DualMem) that stores two kinds of memory entries:

- **factual cognition:** objective events and details from the conversation;
- **insight cognition:** a persona-conditioned *interpretation* of facts (for example "late-night gaming" -> "behavioural fatigue" for a psychologist persona), each insight linked to the facts that ground it.

A small model (4B, Qwen3-4B base) is trained by SFT and RL to build this memory; a separate fixed role-playing agent answers using retrieved cognitions.

The scenario is **long chat with a persona** (companionship, advice), not a world simulation. Its relevance to us is the fact/interpretation split.

## 1. State representation and storage (section 4.1, 4.2)

- One "unified memory bank" containing both factual and insight entries. The paper does not specify the storage format or schema beyond: each insight *references its grounding facts* (provenance links). Retrieval of an insight also pulls its linked facts (section 4.2, "Notably, during retrieval...").
- Incrementally built: history is split into fixed-size chunks processed sequentially. At step t the construction model sees the persona, the chunk and the **prior memory**, and emits facts first, then insights from the new facts and "relevant history" in memory (section 4.2, Eq. 1).
- Persona is an input profile (values, personality, background, expertise, goals/conflicts, work and hobbies, Appendix B.2 / C.2). Insights per persona (20 each) are the dataset's ground truth (Appendix B.2 prompt).

## 2. How state changes are extracted

- By the memory-construction LLM, in two ordered steps per chunk (facts, then insights), with chunk-level prompts. Prompts are given in Appendix B; the construction prompts for DualMem itself are in the appendices on training (D).
- **Null insights as a trained behaviour:** SFT includes manually built negative samples where evidence is insufficient and the target insight is set to null, "to mitigate forced interpretation hallucinations" (section 4.3). In RL, the reward combines Format Compliance and In-Character Quality, judged by GPT-5.1 (section 4.3).
- No schema validation by code is described beyond a format reward. There is no retry loop. The extractor is a trained model, not a prompt contract.

## 3. Per-character knowledge separation

**None.** The memory belongs to one persona ("the agent") and records one conversation. Persona-conditioning means *interpretation*, not *access control*. There is no concept of what the character could not know. The nearest relation is that insights are stored from the persona's perspective, so a different persona over the same history would hold different insights.

## 4. Long histories

Chunked incremental construction over 32k-256k-token histories (section 3.2: blocks of 24 turns; evidence blocks interleaved with casual conversation at varied density). Retrieval of the top 10 entries (Recall@10 in Appendix G.1, matched semantically). Appendix F compares retrieval strategies. The authors note multi-million-token histories remain untested (Limitations).

Results (section 5.2, 5.3): fact recall 0.77 (RL) and 0.76 (SFT) against 0.69-0.74 for non-hierarchical baselines and 0.37-0.42 for hierarchical frameworks (HiMem, Mirix); insight recall 0.73 (RL) and 0.65 (SFT) against at best 0.41 for baselines; role-play quality 4.16 overall for DualMem-RL against 3.94-4.01 for persona-agnostic frameworks, judged by LLM. Key mechanism claimed: strong baselines have comparable *fact* recall but fail to translate it into role-play quality because nothing tells the agent how to read the facts from the persona's view.

## 5. Canon / rule consistency

None. The benchmark is synthetic conversation. Consistency is only "interpretive traceability": every insight carries links to the facts that justify it, so an insight can be audited.

## 6. Fit with `docs/decisions.md`

| Our decision | DualMem |
|---|---|
| Facts as records with metadata | A fact entry is text; no where/who/when schema is described in the paper. |
| Epistemic isolation | Not addressed. |
| NPC agent with own memory, goals, character | Conceptually adjacent: a persona-owned memory with interpretation. |
| Two-level simulation (cheap off-screen updates) | Chunked incremental construction could serve as the "cheap periodic update", but needs a trained model. |
| Code owns state, validated | Not addressed; trained model emits entries. |
| Salience as a separate judgment | Related: insight construction decides what a fact *means* to this character, which is an input to whether they would care. |
| Model-agnostic | The trained 4B constructor is model-specific; the prompts (Appendix B) are model-agnostic in principle. |

## 7. What is reusable

**Directly reusable as design:**
- **Keep facts and interpretations in separate records, and link each interpretation to the fact ids it is derived from.** In our engine: world facts are shared records (with visibility), while an NPC's *attitude* toward an event is a separate per-NPC record pointing at the event. This matches the decision "Different characters hold different attitudes toward the same event". Retrieval returns an attitude together with its grounding facts, never an attitude alone.
- **Allow "no insight".** An interpretation record may be null when evidence is insufficient. In our setting this guards against NPCs inventing opinions about events they have no basis to judge.
- Order of construction: extract facts first, then derive interpretation from facts plus prior state, in a separate step.
- Evaluation idea: a query type set (interpretive attribution, contradiction revelation, value judgment, decision guidance) usable as NPC regression tests.

**Ideas only:**
- Training a small constructor model with SFT/RL for memory writing. Possible later; not now (undecided, and no compute budget in the brief).
- Separately scoring "fact recall" and "insight recall" to diagnose whether failures are in extraction or interpretation.

**Conflicts / not to adopt:**
- Single unified bank of free-form entries without visibility.
- Quality judged by an LLM judge (GPT-5.1) that is also the RL reward; the authors check cross-judge agreement in section 6.1, but the dataset is single-generator (DeepSeek-V3.2), which the Limitations section admits.
- Persona-conditioned insights are confident psychological claims; the Ethics Statement itself warns about "confident psychological or interpretive statements without sufficient evidential grounding".

## 8. License

Paper: arXiv perpetual non-exclusive license. Code and dataset: unreleased at the time of study, license unknown (authors say "permissive").

## Assumptions / limits

- The repository could not be cloned. Everything here is from the paper's HTML text (sections 1-8, Appendix B.2 and the results tables as text). I did not read Appendices C-Q in detail, nor Figures. Numbers in section 4 come from the prose of section 5.2-5.3, not from the tables.
- If the repository appears later, re-check how entries are stored (the key open question: the schema of the unified bank and the fact-insight link).
