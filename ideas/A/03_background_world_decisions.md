# A3. Background world decisions (many cheap typed judgments + canon retrieval)

Source legend: **[V]** = found via search on 2026-10-19; **[M]** = from memory, link not opened.

## 1. Seed

> "Use many cheap typed judgments (Jev) for how the world develops and reacts: how did the world react to similar events in the original books, how does this campaign differ from the books, will this difference matter. Canon passages reach these judgments through retrieval (the books are about 9 MB of text; Jev's context is about 32K tokens)."

Closed in `decisions.md`: Jev answers narrow typed judgments (yes/no, choice, score with probabilities) and **generates no text**; canon store is immutable and reaches judgments by retrieval; justified drift vs hallucination is decided against the campaign store; the world is simulated cheaply (records plus Jev, no agents).

## 2. Completed idea

**2.1 The three questions in the seed are one pipeline.** For an event E in the campaign:
1. **Analogue:** has something like E happened in canon, and how did relevant parties react? (retrieval + judgment)
2. **Divergence:** how does the campaign's current situation differ from canon at this point? (needs a maintained model of "where the campaign is relative to canon")
3. **Relevance:** does that difference change the analogue's reaction enough to matter? (judgment)
Output: a set of *world reaction records* (who reacts, what kind of reaction, when it becomes visible), written into the campaign store with `derived_from` pointing at the canon passages used.

**2.2 Jev cannot write; reactions must come from a closed list.** Because Jev outputs yes/no, a choice, or a score, "how did the world react?" can only be answered as "which of these reaction types applies". So the engine needs an **enumerated reaction vocabulary** per kind of party (ruler, guild, church, mob, individual) — e.g. *ignore, investigate, retaliate, negotiate, flee, exploit, spread propaganda, hire someone, mobilise, pray/ritual*. Prose for the reaction is produced later by an LLM writer (narrator or an "event writer") from the chosen type plus retrieved passages; a Jev can then check it (consistent with the type? contradicts canon?). The vocabulary can be bootstrapped from the books once (a one-off pre-processing step; not done in this task).

**2.3 Divergence ledger.** Maintain a small, always-short list of campaign-vs-canon differences, each a record: `what differs`, `since when`, `affects which canon threads`. (e.g. "in this campaign X is dead since day 40"; "the PC never visited Y"). This is what lets a judgment answer "how does this campaign differ" without reading the whole campaign. It is the same list that the canon check in `decisions.md` consults to accept justified drift, so one structure serves two purposes.

**2.4 Canon is not a simulation.** The books give *narrated* reactions at *selected* moments, not a complete causal model. Where there is no analogue, fall back to (a) world rules in the canon store (politics, magic, monsters, economy), (b) generic genre analogues, (c) "no reaction" being a legal outcome. The judgment should be allowed to answer *no analogue found* and the pipeline must then say so in the dev view rather than invent one.

**2.5 Triggering and budget.** Not every event deserves this. Trigger when loudness (A1) crosses a threshold, when an event touches a party with a standing interest (faction records), or when a time tick reaches a scheduled canon pivot (e.g. a canonical event that would happen on date D unless the divergence ledger says otherwise). Pivots are the third kind of trigger and are the main source of *canonical pull* on the campaign.

**2.6 Canon pull vs player freedom.** If the campaign diverges, should canon events still try to happen (the war arrives regardless) or fade? This is a design choice with strong consequences, not a technical one. See Options.

**2.7 Retrieval over 9 MB.** About 9 MB of text is on the order of 2–3 million tokens (rough estimate; depends on language and tokenizer — the books may be in Ukrainian, Russian or Polish, which tokenize worse). At ~400–600 tokens per chunk that is several thousand chunks. Budget for Jev's 32K context: ~2K system/typed-schema, ~1–2K event + divergence excerpt, ~4–6 chunks (~3K), leaving a wide margin; a single judgment is therefore easy to fit, the issue is *retrieval quality*, not window size. Two retrieval keys are needed: by *event type* ("a witcher kills a monster in a town") and by *party* ("how did the Nilfgaard court react to …"). Chunk metadata (who, where, when in canon, chapter) should be built at ingestion so retrieval can filter before ranking.

## 3. Options

### Option A — Retrieval-at-event-time ("RAG judgments")
When E triggers: build query from E; retrieve top-k canon chunks; for each chunk, a Jev yes/no "is this an analogue of E?" (relevance filter); for survivors, a Jev choice "which reaction type is described here?" per party; then a divergence/relevance pass with the ledger excerpt.
- *Records:* event, retrieved chunk ids, judgments, reaction records.
- *Calls:* roughly k relevance checks + ≤ m reaction-type picks + 2 ledger passes ≈ 6–15 cheap Jev calls per significant event. All can run in parallel (independent), so latency is one round-trip plus one.
- *Strengths:* no preprocessing; works for any world (world-agnostic goal); canon is not distorted by a lossy summary.
- *Weaknesses:* dependent on embedding/retrieval quality on literary text (references by pronoun, flashbacks, names with many spellings); judgment results may vary across calls (cache by (event, chunk) hash); costs scale with event count.

### Option B — Preprocessed canon reaction index
One-off ingestion pass over the books produces structured canon records: `canon_event(type, who, where, when)`, `canon_reaction(by whom, reaction type, source chunk)`, `canon_relation(party A to party B over time)`. At runtime a *typed lookup* by event type and party returns analogues in code; Jev is only used for the divergence and relevance steps.
- *Strengths:* cheapest at runtime; very good for audit (a canon passage cited for every reaction); the same index supports the canon check (hallucination detection) and A1 distortion operators.
- *Weaknesses:* a significant up-front build with a strong model (not this task; a budget item for later); extraction errors become permanent "canon" unless reviewed; extraction schema decided early becomes hard to change; per-world cost (new world = new ingestion).
- *Calls at runtime:* ~3–5.

### Option C — Divergence-first (pivot-driven)
Treat canon as a timeline of pivots (≈ hundreds). Each campaign tick checks only the pivots whose preconditions the divergence ledger touches. Jev judges "do the preconditions of pivot P still hold in this campaign?" and "is its outcome changed?" The reaction to *player-caused* events is handled by A or B; C handles the *canon-caused* ones (the world moves on without the player).
- *Strengths:* gives the world its own momentum, keeps the Witcher flavour (wars, politics) happening; small, structured set.
- *Weaknesses:* needs the pivot timeline (ingestion again) and is canon-centric — poor for worlds without a strong timeline.
- *Calls:* proportional to pivots near the current in-world date; small.

### Option D — Rules-only fallback (no canon analogy)
Reactions come from the world rules and the factions' own goals (A4) via typed judgments, with canon used only as constraint (check) rather than as prompt.
- *Strengths:* simplest; fully world-agnostic.
- *Weaknesses:* loses the main thing the user asked for ("how did the world react in the books").

### Recommendation as conditions
- If you want the fastest path to a working prototype and accept some retrieval noise: **A**, with caching and a "no analogue" outcome.
- If the campaign will be long and canon fidelity is the main selling point: **B** (build later), since it makes audit and runtime cheap; A can be the pilot that discovers which fields B needs.
- If you want the world to keep moving on its own even when the player ignores it: add **C** on top of A or B.
- Do **not** pick D unless canon turns out to be too unreliable to retrieve.
- Also decide separately the **pull policy** (2.6): *strong pull* (canon pivots happen unless blocked by a recorded cause), *weak pull* (pivots happen only if the ledger shows nothing makes them impossible *and* a Jev says "likely"), *no pull* (pivots are just retrievable context). Strong pull reads best for a Witcher story; weak/no pull is better for a sandbox.

## 4. Prior art

- **Caves of Qud history generation** **[V]** — generate historical events and rationalise them after the fact, instead of simulating everything https://www.gamedeveloper.com/design/tapping-into-the-potential-of-procedural-generation-in-caves-of-qud , talk summary https://intfiction.org/t/youtube-video-procedurally-generating-history-in-caves-of-qud/41347 . Lesson: "decide lazily, then make it consistent" is a proven way to get depth cheaply; our version rationalises with canon analogues.
- **RimWorld storyteller (AI director)** **[V]** — a director selects the next event from the situation (https://rimworldwiki.com/wiki/Storyteller). Lesson: a *separate decision layer* choosing "what the world does next" (rather than the narrator improvising) is a well-accepted pattern; Jev judgments over the divergence ledger are the analogue.
- **Blades in the Dark faction clocks and downtime** **[V]** — during downtime the GM rolls factions' progress on project clocks; clocks fill and the thing happens https://gnomestew.com/three-mechanics-from-blades-in-the-dark-i-want-in-all-my-games/ , https://gnomestew.com/background-events/ . Lesson: world development as a few cheap structured steps per faction, resolved lazily at downtime; fits Option C and topic A4.
- **Dwarf Fortress history** **[V]** — the world is simulated for centuries before play and records historical events as the world's memory https://www.dwarffortresswiki.org/index.php/Rumor (event/rumour model). Lesson: events as first-class records, as here.
- **Crusader Kings event system** **[M]** — events fire when conditions on characters/realms hold, with weighted options; it is a hand-authored version of "precondition + reaction type" (Option C and 2.2).
- **LLM game masters** **[V, thin]** — the pattern "deterministic code owns rules and state, the model narrates" https://www.envisioning.com/research/pixels/llm-game-masters.md ; it matches decisions.md but gives no method for canon-anchored world reaction.
- **Retrieval over novels** **[M]** — no mature published recipe I can cite for fiction-specific retrieval of "reactions"; treat Option A as an experiment. The task-2 experiment reports (E1–E3), which I could not see in this worktree, may already contain relevant retrieval/Jev measurements; use them before committing to A vs B.

## 5. Interactions

- **A1 spread:** loudness/kind and the "no analogue" case come from here; reaction records are what the spread carries.
- **A2 belief:** a faction reacts to what it *believes* happened (its version), not to the true event; Option A should run on the faction's knowledge record, which is a significant correctness point: running world-reaction judgments on the true event violates epistemic isolation at the collective level.
- **A4 off-screen agents:** agents' goals are inputs to "who reacts"; their goal progress and the world reactions share the same tick.
- **A5 mechanics:** "will this difference matter" is the same kind of probability judgment as success rolls.
- **A6 time:** pivots are scheduled in in-world time; skipping time must process due pivots in order.
- **Decisions:** needs the canon store to expose chunk metadata and the campaign store to link to canon chunks (`derived_from`). Jev's no-text-generation rule forces the closed vocabulary (2.2).

## 6. Questions for the user

1. Якщо гравець повернув події не так, як у книгах, чи мають великі книжкові події (війна, зради) все одно наближатися, чи світ має йти зовсім новим шляхом?
2. Чи готовий ти один раз заплатити за "розбір" книг у структурований вигляд (хто, що, як відреагував), щоб потім гра була дешевшою й точнішою?
3. Які книжкові події ти вважаєш такими, що мають статися за будь-яких умов (якщо взагалі такі є)?
4. Якщо в книгах нема схожого випадку, чи краще світ нічого не робить, чи вигадує реакцію за загальними законами світу?
5. Українською чи іншою мовою лежать твої тексти книг (від цього залежить якість пошуку по них)?
