# A2. Belief and trust (sourced knowledge, the player character as a normal being)

Source legend: **[V]** = found via search on 2026-10-19; **[M]** = from memory, link not opened.

## 1. Seed

> "Every piece of knowledge has a source. How much a character believes it depends on trust and relationship with the source. The player character is a being of the world like any other, not a special case."

Closed in `decisions.md`: a character's context contains only facts it witnessed or plausibly heard; no "you do not know this" instructions; salience is a separate judgment; the world is simulated with records plus Jev judgments.

## 2. Completed idea

**2.1 Knowledge record vs. fact.** A "fact" is what is true in the world (narrator/code only). A "knowledge record" is `holder + content + source + channel + t_learned + stance`. Stance is not a boolean. Minimum useful set: *knows firsthand* (witnessed), *believes*, *suspects*, *doubts*, *rejects*, *knows it's a lie but pretends otherwise*. Stance can change when new records arrive (corroboration, refutation).

**2.2 Source is a chain, not a label.** "Heard from X, who heard from a trader" — the chain length matters for trust (and links to distortion hop-count in A1). Store only the immediate source plus a pointer to the source's own knowledge record where it exists; the chain is recovered by following pointers. Where the source is a place ("everyone in the market says"), the source is a *collective* with its own attributes.

**2.3 What trust actually depends on.** From the seed ("trust and relationship") plus what real credulity depends on:
1. The source's **track record** with this holder (were they right before?).
2. **Relationship** (affection, kinship, debt, fear) — which can bias belief *against* the track record.
3. **Plausibility** against what the holder already knows (a claim contradicting a firsthand record needs strong source).
4. **Interest**: does the source gain from the holder believing this? (motive judgment)
5. **Stakes and cost of being wrong** for the holder.
6. **Corroboration**: independent sources agreeing.
7. **Holder's disposition** (credulous, paranoid) — a character property, a few sentences of free text, not a stat.
8. **Source's manner**: confidence, evidence shown. (The narrator produces this in the scene; the extractor records it.)
The seed names 1 and 2. 3–6 are what make belief non-trivial in play and should be at least judged even if not stored.

**2.4 Lying is a first-class action.** If knowledge has sources, someone can be the source of something they know is false. An NPC's line carrying a lie needs its own record pair: (a) what the NPC knows (truth) and (b) what the NPC asserted (claim), flagged `asserted_false_by_speaker=true` at write time by a Jev judgment on the NPC's intent. Without this, a "lie" is just an NPC hallucination and cannot be audited.

**2.5 The player character (PC) is a being like any other — implications.**
- PC's knowledge is stored in the same structure and is the only thing PC-centred retrieval may expose (this is already the constraint the user has put on the turn assistant in Session B).
- NPCs hold beliefs *about the PC* as ordinary knowledge records; the PC's own self-description has no privilege. An NPC can believe wrong things about the PC and the player may never be told.
- **The sharp edge:** a PC "believes" things only if the *player* believes them. The narrator must not tell the player "you trust him" (that takes away the player's choice), but a PC who heard a claim from an unreliable source still has a knowledge record with that source. Resolution candidates in Options below: the PC's stance is *derived from play* (what the player acts on / says), never asserted by the narrator.
- Consequence for fairness: NPCs should lie to, mislead, and be misled about the PC under the same rules as to each other.

**2.6 Relationship needs history, not a counter.** Closely tied to seed A5's "long-built relationship must not collapse from one bad moment." The relationship between two beings is the *set* of records between them (shared events, favours, betrayals, how each was framed afterwards), plus a short derived summary text refreshed at intervals. One event changes the summary only to the extent a judgment says it is *characteristic* vs *out of character*.

## 3. Options

### Option A — Numeric trust per (holder, source) pair, updated by code
Store `trust ∈ [−1,1]` (or two values: reliability and affinity) for each directed pair. Belief = Jev score (plausibility, interest) combined with trust by a fixed code formula. Update trust when claims are confirmed/refuted.
- *Strengths:* cheap; deterministic; easy to display in debug; scales to many pairs; stable (a single event moves a number by a small bounded amount, giving the "no collapse" property for free).
- *Weaknesses:* it is exactly the "fixed parameter sheet" the Goal section rejects, if it becomes the main driver; numbers hide the *why* (a narrator cannot say "he trusts you because you saved his sister" from `0.62`); formulas are arbitrary; displayed trust can feel gamey.
- *Calls:* 1 Jev (plausibility/interest) per claim received. Update is code-only.

### Option B — Pure records, judged each time (no stored trust)
Trust is *never stored*. When an NPC receives a claim from S, retrieval pulls the top-k records between holder and S (shared events, past claims and how they turned out, relationship summary) and a Jev judgment answers: "given these records, would the holder believe the claim?" (choice: accept / doubt / reject, with probabilities). Probabilities are sampled by code.
- *Strengths:* obeys "records are open-ended, no fixed sheet"; the *reason* is always recoverable from records (good for narration, for debugging, for the assistant that has to say why a character reacted); trust emerges from history without tuning.
- *Weaknesses:* cost (retrieval + Jev per claim); retrieval quality becomes a hidden trust parameter (if the key betrayal is not retrieved, trust is wrong); the same situation can give different probabilities across calls unless judgments are cached on (holder, claim, record-set hash); retrieval ≠ 32K problem: relationship history can grow, so a **relationship summary record** (refreshed at intervals by an LLM, versioned append-only) is required to keep Jev context short.
- *Calls:* 1 retrieval + 1 Jev per claim; plus a periodic summary refresh per important pair (not per turn).

### Option C — Record-based with a small learned ledger (hybrid)  *(candidate default)*
Use Option B for judgment, but keep a **track-record ledger** per (holder, source): counts of claims confirmed and refuted, each pointing to the claim records. The ledger is not a score; it is *evidence*, and it gets retrieved into the Jev context as one line ("S told H 7 things that later proved true, 1 false"). Affinity stays in the relationship summary text. Corroboration is checked by code: other knowledge records of the holder with the same `event_id` and a different source.
- *Strengths:* recorded evidence is short, retrievable, and gives the Option A "stability" without a formula; no hidden numbers in the narrator's reasoning.
- *Weaknesses:* more machinery than B; ledger entries need a "confirmed/refuted" judgment when truth arrives (1 Jev per resolution, only for claims that are later resolved).
- *Calls:* as B, plus resolution judgments occasionally.

### Option D — Narrator-side belief (no engine support)
Let the narrator/NPC call decide belief from its isolated context. Cheapest to build; this is what chat frontends do. Not recommended: nothing is auditable, belief is not stored, and the same claim re-heard later may be believed differently. Listed only as the baseline.

### PC-specific choice (applies on top of A–C)
- *P1 Derived stance:* the PC's stance toward a claim is inferred from what the player does afterwards by an extractor pass ("acted on", "voiced doubt", "ignored") and recorded as a diff. No stance is stored until the player reveals it. Strength: keeps player agency. Weakness: PC knowledge records have no stance for a while, and NPC behaviour that depends on "does the PC believe me" must be judged from observable behaviour only, which is also how NPCs would judge it.
- *P2 Declared by the player:* the interface offers a quiet "do I believe this?" marker. Strength: explicit; weakness: breaks immersion, adds friction.
- *P3 Hidden full model for PC too:* the engine computes a stance for the PC with the same Jev judgments as for NPCs and feeds it only to the narrator for colouring (never forced on the player). Risk: narrator drifts into telling the player what to feel.

## 4. Prior art

- **Crusader Kings III opinion** **[V, secondary]** — every character has a signed opinion of every other, built from modifiers (family, culture, traits, past acts) and used in political decisions https://www.wargamer.com/crusader-kings-3/guide-tips . Shows Option A's strength (transparent modifiers with decay) and its limit (opinion is not knowledge of anything specific). I did not open an official CK3 source.
- **Generative Agents** **[V]** — memories with recency/importance/relevance for retrieval and periodic "reflections" as higher-level summary records https://arxiv.org/abs/2304.03442 . Direct template for the periodic relationship-summary record in Options B/C.
- **Versu** **[V]** — characters are autonomous agents choosing actions by utility within social practices; practices only suggest https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf , https://emshort.blog/2013/02/14/introducing-versu/ . Lesson: relationship consequences (offence, trust) are tied to *what practice was violated*, giving explainable reasons.
- **Prom Week / Comme il Faut / Ensemble** **[V, thin; rest M]** — social physics: thousands of hand-authored "social considerations" drive how characters read each other's actions (search snippet only: https://eis-blog.soe.ucsc.edu/?p=3103 ). Lesson: very strong, but hand-authored; this engine would replace the authored rules with Jev judgments over open records.
- **Theory of mind in LLM multi-agent systems** **[V, abstracts only]** — adding ToM and belief modules does not by itself improve coordination (https://arxiv.org/abs/2603.00142); survey of ToM evaluation and safety (https://arxiv.org/html/2502.06470v1); a benchmark for beliefs diverging from reality (https://arxiv.org/html/2602.13832v1). Lesson: do not assume an LLM will model "what X believes" from a single prompt; supply the belief records explicitly (which is what epistemic isolation at retrieval does).
- **CHARM benchmark** (cited in decisions.md) — awareness does not imply compliance, so "do not use this fact" prompting is unreliable. Supports keeping lies and false beliefs as *records the holder owns*, rather than instructions.
- **Tabletop:** Burning Wheel's Beliefs/Instincts and Fate's aspects make beliefs part of the character, but they are player-declared, not source-based **[M]**.

## 5. Interactions

- **A1 spread:** source/channel/hop-count are produced there. The "attitude" judgment in A1 and the "stance" here are two parts of the same pipeline: reach → version → stance.
- **A3 background decisions:** NPC factions' beliefs about events feed their decisions; a faction's belief is a collective record with a source (its spies).
- **A4 off-screen agents:** an agent returning with "something to tell" tells it with its own stance; the player's trust in what is told then depends on the agent's track record.
- **A5 mechanics:** "relationship must not collapse" is implemented here; "out of character" judgment is shared.
- **Session B interactions (brief not read):** the turn assistant may only use what the PC knows; the knowledge record's `holder=PC` filter is exactly that gate; B1's panel "what the character knows about itself" is the same filter on body-state records.
- **Decisions:** nothing conflicts. Adds requirements for the schema: `source`, `stance`, `asserted_false_by_speaker`, `derived_from`.

## 6. Questions for the user

1. Чи має герой гравця вірити чомусь автоматично (наприклад, що чує від друга), чи віра завжди залишається за гравцем?
2. Чи можуть NPC брехати героєві навмисно, і чи має гравець колись дізнаватися, що це була брехня, якщо сам не перевірив?
3. Чи хочеш ти бачити в налагоджувальному вікні *причину* довіри ("вірить, бо ти врятував його сестру"), чи достатньо результату?
4. Чи може довіра зруйнуватися від однієї великої зради, якщо до того були роки добрих стосунків, і чи від чого це залежить?
5. Чи мають NPC вірити неправдивим чуткам про героя навіть тоді, коли знають його особисто?
