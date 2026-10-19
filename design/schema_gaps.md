# Schema gaps

Companion to `design/schema.md` (section numbers below refer to it). Evidence only: `docs/decisions.md` is not edited, and nothing here is a decision. Written 2026-10-19 on branch `design-schema`.

Contents: **A.** what the task 4 code would have to change; **B.** places where the decisions cannot be satisfied cleanly by a record model, or are silent in a way the schema had to fill (G-1 … G-13); **C.** the number of judgment calls each mechanism costs, as a count, not a price; **D.** suggested order of work.

Sizes: **S** < half a day, **M** 1–3 days, **L** > 3 days (same scale as `reports/decision_gaps.md`). They are estimates from reading the code, not measurements.

---

## A. What the current code would need to change

Code read: `harness/` on `worktree-task4-core-revision` (identical to `main`), 2,660 lines, 115 tests on `main`.

### A.1 Storage and log

| Module (lines) | Today | Needed | Size |
|---|---|---|---|
| `db.py` (61) | tables `events`, `rollbacks`, `facts` (with `store` column), `fact_knowers`; triggers on events/facts only; `connect()` returns one in-memory DB | `design/schema.sql` (envelope, `record_link`, `rollback`, `stale`, `judgment`, ext tables, an update/delete-blocking trigger pair on every table, `link_requires_alive` guard); `canon.sqlite` opened `mode=ro` and attached; `connect()` returns campaign + canon; WAL for a file-backed campaign (the prototype is `:memory:` by default, `connect()` default) | M |
| `models.py` (91) | `Event`, `Fact`, `Knower` dataclasses; event-type constants; `STATE_CATEGORIES` (5 values) and `OPS` | one `Record` dataclass plus a **kind registry** (kind -> ext table, required links, allowed writers); typed read models for fact/knowledge/state/intent; categories become default tags, `OPS` disappears (a change is a new record in a register) | S–M |
| `eventlog.py` (130) | `append(type, game_time, …, cause_id)`; `cause_id` is **one** parent; rollback cascades through `cause_id`; `active()`, `descendants()`; `recent_dialogue` filters on an event's `witnesses` list | `RecordLog.put(kind, body, t_from, …, ext, links)` writing envelope + ext + links in one transaction with the resurrection guard (R5); multi-parent `record_link`; `rollback(seeds, reason, by, mode)` with closure, span-aware cut seeds (R3), `supports`/`stale` (R4), dry run; `current(kind, slot, T)` register reader; `alive()`; recent text via `text_unit.audience`. Replaces `cause_id` everywhere | M |
| `facts.py` (141) | `FactStore` mixes truth and knowledge (`fact_knowers`); `visible_to`; `search_canon` is token overlap over `store='canon'` rows in the same DB; canon knowers are passed in by the caller | split into `Facts` (truth, narrator-only), `Knowledge` (holder-scoped; produces the snapshot of §6.2), and `Canon` (separate file; FTS5/embeddings; typed lookup; seeding from `canon_knower`). `status established/asserted` | M–L |
| `state.py` (100) | live state = replay of `STATE_CHANGE` events, `(category,item) -> observable`, ops add/remove/reveal/hide, 5 categories, no expiry, no awareness | registers of `state_elem` (`present`, `observable`, `perceptibility`, `self_aware`, `expires_at`); `check_change` validates a proposed record against the register's current value; ops derived from the diff; all categories of the decisions as tags | S–M |
| `attitudes.py` (90) | attitudes and notices are **events** with `cause_id` = the fact's source event; attitude points to `fact_id` | `attitude` ext (points to `knowledge_id` and `about`); notices become `knowledge.salience`; "shown" becomes `surfaced` records | S |
| `agents.py` (85) | `Intents` are `INTENT_SET`/`INTENT_RESOLVED` events; promotion is an `AGENT_PROMOTED` event | `intent` ext with `type` (unsaid/tellable/plan), `utterance_id`, `from_word`; resolution `requires` the saying utterance; promotion as a register record | S |

### A.2 Perception, extraction, narration

| Module (lines) | Today | Needed | Size |
|---|---|---|---|
| `perception.py` (51) | `perceivers(scene, kind, notability, speaker)` over `Scene.present/outside`; kinds speech/action/description; channels witnessed/heard/told | read presence **as of a time** and observer state (asleep blocks sight), add kind `covert` (actor only), channels `overheard`/`sensed`; return `knowledge` rows. Joss-asleep and Zoltan-examines cases are new | S–M |
| `extractor.py` (148) | `Diff` of `FactDraft` and `StateChange`; validated against present characters and sources | each item carries a **word span** inside its segment; `hidden` segments; state diff has `present`/`observable`/`self_aware`/`perceptibility`; status (established/asserted) derived by code from segment kind; `match_fact` step for speech claims. **Risk G-13:** span accuracy is unmeasured | S–M |
| `narrator.py` (90) | JSON `{description, observable_actions, speakers}` | add `hidden` (covert events, never displayed); optionally `movements` (presence proposals) | S |
| `context.py` (172) | builds NPC context from `CharacterMemory`; narrator context from `FactStore.all_campaign` and `LiveState.snapshot` | NPC/assistant context from the snapshot only; narrator context labels claims vs established, shows hidden state with flags, collectives' versions with operators, open divergences, corrections; extractor prompt with segment kinds and spans | M |
| `memory.py` (183) | `MemoryDeriver.derive` reads the old stores; `MemoryWriter` regenerates Markdown with wikilinks | rewire to the snapshot and registers; files for collectives; wikilinks from `source`, `place`, `about`; cache key `(max id, rollback count)` | M |
| `belief.py` (15) | `neutral_belief` constant | no change (slot kept); reads `knowledge` + `belief_update` | — |

### A.3 Pipeline, judgments

| Module (lines) | Today | Needed | Size |
|---|---|---|---|
| `pipeline.py` (558) | `turn()` appends events with a single `cause_id`; `_commit` writes facts + `fact_knowers`; `_observe` writes observation *facts*; `Scene` is session state, not in the log; time is `scene.time += minutes_per_turn`; `interrupt_retroactive` rolls back the whole utterance and **re-extracts** the kept prefix; `rollback` is public and ungated; no model-error flow | output-cycle root (narration) with every derived record linked; `_commit` writes facts then `knowledge` from perception; observations as knowledge about state records; `enter_scene`/`leave_scene` write `presence` records (scene derived from the log); `time_passes` records (both time modes); `interrupt_retroactive` = interruption record + `unsaid` intent + `cut_seeds` rollback (no re-extraction); `report_model_error(text)` = correction + rollback of the output cycle + regeneration; `rollback(..., mode)` gate (R7); `materialise(holder, upto)` for lazy records before a scene (T6); prefetch with the resurrection guard | L |
| `judge.py` (321) | `JudgmentLog` writes JSONL; tags: salience, unknown_claim, attitude_direction, relationship_magnitude, narrator_speech | log into `judgment` table (batch, escalated, inputs, cost); new tags and closed vocabularies: `match_fact`, `reach`, `reach_eta`, `version_derivable`, `version_heard`, `symptom`, `examination`, `duration`, `reaction`, `drift`, `explains`; a memo helper for T5 | S–M |
| `streaming.py`, `providers.py`, `policy.py` | — | no change | — |
| `demo.py` (188) | prints the dev view | rewrite for the new API; add scenarios 1–5 as offline demos on the fake provider | S |

### A.4 New modules

| Module | Purpose | Size |
|---|---|---|
| `store.py` | envelope writer, kind registry, link invariants, registers, as-of queries, dry-run | M |
| `snapshot.py` | holder-scoped views -> per-call snapshot DB (§6.2) | S |
| `spread.py` | physical bound from a map graph, `reach`/version/`version_heard` judgments, back-dating guard (T4), memoisation | M–L (the map graph is world data: a small hand-written graph is enough for the first world) |
| `canon.py` | open `canon.sqlite` read-only, typed lookup + FTS5, seeding of knowledge, drift check, divergence ledger | M–L |
| `ingest/` (separate tool) | chunker, windowed extractor, entity resolver, vocabulary mapper, loader, content hash | L (cost measured in task 6) |
| `corrections.py` | store and retrieve corrections for prompts | S |

### A.5 Tests

Of the 115 tests, the ones that touch storage shapes need rewriting: `test_rollback.py`, `test_visibility.py`, `test_live_state.py`, `test_interruption.py`, `test_perception.py`, `test_memory.py`, `test_extractor_diff.py` (roughly 60% of the suite). `test_judge.py`, `test_narrator.py`, `test_output_check.py`, `test_agents.py` need small edits. New tests: closure and dry run; span cut; `supports`/`stale`; guard trip; back-dating rules (T4); snapshot isolation (the attempts of §6.2); as-of registers; canon load and seeding; the five scenarios of §8 as end-to-end offline tests (the build script already asserts their key properties).

### A.6 How this relates to `reports/decision_gaps.md`

That table's rows 1 (two times), 2 (derived-from links), 3 (live-state scope), 7 (information spread), 10 (model error) and 11 (choices final) are closed by the schema; rows 5–6 (canon check, ingestion) are given a concrete format and flow (§7) but remain **L** engineering; rows 4, 12–17 (panel UI, time modes, assistant, settings, app shell) are not record-model matters.

---

## B. What the schema cannot satisfy cleanly, or had to fill because the decisions are silent

Each item: what the decisions say, what the schema does, what is left over. Nothing here is proposed as a decision change; the user may read these as questions.

**G-1. Is what an NPC says a fact?** The decisions say the extractor "proposes new facts" from a turn and that a fact has "who knows it and how". Read literally, an NPC's line becomes a world fact known to everyone present. Then a lying or mistaken NPC rewrites reality, and "the truth persists while distorted versions circulate" cannot hold for speech-born content. *Schema:* speech yields `asserted` facts (`asserted_by`); only narration, action, hidden text, canon and world judgments yield `established` ones (§5.2). *Left over:* nothing in the decisions says **who settles an asserted claim and when**. Candidates: the narrator when it next narrates the matter; a judgment on first need; never (stays a claim). Each changes narrator behaviour and cost.

**G-2. No commit point for derived records.** "Said means delivered", and the retroactive window lets the player cut the last NPC utterance after it finished. So everything derived from that utterance is provisional until the window closes, yet the engine wants to prefetch reactions (A6) during that time. *Schema:* closure rolls back prefetched records correctly (scenario 3, Hubert's plan). *Left over:* external side effects cannot be rolled back (a notification, an outbound request, a message to another process). The decisions do not say when the window closes (at the next player action? after a timeout?). That moment is the commit point; prefetched results should have no side effects before it.

**G-3. "Each element is either observable or hidden" vs perception by examination.** The decisions say hidden state is not perceived until it becomes observable. A healer who identifies a poison by examining is a per-observer discovery: the element does not become observable to the room. *Schema:* keeps the binary on `state_elem.observable`, adds optional `perceptibility` (`{"examination":0.8}`) and records the healer's discovery as the healer's own `knowledge` (`channel='sensed'`), not as a global flip (§5.5, scenario 4). Satisfies the intent, exceeds the letter. *Left over:* the wording; a third state ("discoverable by examination") may deserve a place in the decisions. Also `self_aware` (known/suspected/unaware) is a second axis the decisions do not name but the panel rule needs.

**G-4. "Every record carries two times" vs canon.** The books give no absolute dates; log time for a canon record is the ingestion time, which is not a story time. *Schema:* canon records have an `order_key` and `t_prec`; `t_from` may be an estimate with `t_prec='unknown'`; pre-campaign history is negative minutes before the epoch (§7.2). *Left over:* the decision's wording does not hold for ingestion records; reading it as "campaign records" is what the schema assumes.

**G-5. Transitive rollback vs records with several sources.** The decisions: rollback removes everything derived from removed text, directly or transitively. A reputation or a town's talk is derived from many stories; strict cascade kills it as soon as any one story is cut, although the ideas (A1 2.4) want "the story is forgotten, the reputation stays". *Schema:* `supports` links (soft): the record dies only when all its supports die, otherwise it is `stale` and re-derived (R4). *Left over:* this is a deviation from the strict reading. The strict alternative is one line (treat `supports` as `requires`) at the price of reputations that flicker out when an old story is cut. Which is right depends on how often a summary is derived from a *cut* utterance versus an old one; no data yet.

**G-6. Immutable canon vs ingestion errors.** A3 notes that extraction errors become permanent canon. The decisions make canon immutable. *Schema:* canon is a read-only file pinned by hash; a fix means a new canon version, and a running campaign cannot adopt it without a migration. A workaround inside the decisions: a campaign-store `erratum` record linked `about` the canon record, read by retrieval; I did not add it because the decisions do not ask for it.

**G-7. Model errors found late.** "Model error" regenerates only the last world output. A bad fact that has already persisted for three turns cannot be removed in normal play ("choices are final"). *Schema:* the correction is stored and fed forward, but the wrong records stay alive; only the debug view can remove them. *Left over:* a gap in the interface decision, not in the model; the record model would support "retract this record and what depends on it" with a `by_record` reason if the interface wanted it.

**G-8. The player saw text that was "never said".** After a retroactive cut, the player has read the removed words; the character has not heard them. The schema rolls back every record derived from them, but cannot remove the knowledge from the player's head. If the player then types something that uses it, the character says it as an ordinary PC utterance, perceived like any other. That is consistent with "information from the player character is treated like anyone else's"; it also means the unknown-claim check does not apply to the player's words. No change proposed; stated so it is not mistaken for a leak in the schema.

**G-9. Output checks exist only for NPC lines.** The decisions check NPC lines for claims without a channel. Nothing equivalent covers the **narrator's** player-facing text, which (a) sees hidden state and may name a hidden cause ("the poison burns"), (b) may state the player character's inner life (scenario 5: "hands shake with fear", which the decisions reserve to the player), (c) may assert what an NPC knows ("Marta, who knows what happened at the mill"). The panel's epistemic filter can be bypassed by prose. *Schema:* has everything needed for a symmetric check (the PC's known rows, `self_aware`, NPC knowledge) but the check is an additional judgment per narration, not a decided feature. Today the only remedy is the model-error button. This is the largest silence found.

**G-10. Quality beats latency; cost is undecided.** The schema multiplies derived records (per-observer salience, attitudes, version generation). Counts per mechanism are in section C; prices need the task 6 measurements. The schema keeps cost bounded by being lazy (nothing computed for Vergen until someone needs it) and memoised (`reach`), but cannot decide how detailed off-screen updates are (also undecided in the decisions).

**G-11. Flowing time and hidden-condition progression.** The symptom design (one batched judgment per active hidden condition per time advance) is cheap in turn-based play and unbounded in flowing play. *Schema:* progression is written at the time advance that the player or an observer triggers, never by a timer, and conditions are evaluated lazily at observation points (panel open, turn end). *Left over:* the decisions leave the time mode open; the schema works with both, but the flowing mode needs an explicit minimum interval between symptom judgments.

**G-12. Ingestion with cheap models only.** The decisions allow only cheap models over the API and put strong judging in the Claude Code agent's hands during development. The books are about 9 MB of Ukrainian text (roughly 2–3 million tokens by the A3 estimate). A cheap model producing events, reactions and entity resolution at that size will have a real error rate; the canon file is immutable (G-6). The review step in §7.2 (agent samples, `review` field) bounds this but does not remove it. Unknown until task 6's measurement.

**G-13. Word spans are an assumption about the extractor.** Exact interruption (R3) needs each extracted item to name the words it was read from. E3 showed extractors are unreliable at witness lists; spans may also be unreliable. *Schema:* an item with no span is treated as derived from the whole text and dies on any cut; the engine may then re-extract the kept prefix as the task 4 code does. A quick experiment (cheap model, 30 utterances with gold spans) would say whether spans are usable; not run, since this task allows no paid calls.

---

## C. Judgment calls per mechanism (counts, not prices)

Jev calls are batched per state; "LLM" means an allowed cheap model. Retries (regeneration after a failed check) are not counted.

| Mechanism | Calls | When |
|---|---|---|
| Turn base | narrator 1 LLM, NPC line 1 LLM per speaker, extractor 1 LLM | every turn |
| Narrator speech check | 1 Jev | every narration (exists today) |
| Unknown-claim check | 1 Jev per NPC line | every line (exists today) |
| Salience | 1 batched Jev per observable change (one question per observer) | when an observable state changes or someone enters |
| Attitude | 1 batched Jev (direction, one question per NPC knower) + 1 LLM per NPC knower (magnitude) | only facts with notability >= 0.6 |
| Match speech claim to a fact | 1 Jev per claim that has candidates | when an NPC repeats something |
| Duration | 1 Jev | per time advance |
| Symptom/progression | 1 batched Jev per active hidden condition | per time advance |
| Examination | 1 Jev | when an observer examines |
| Reach + ETA | 1 batched Jev (2 questions), memoised | first time a place's NPC is met after a loud event |
| Versions | per version: 1 LLM (text) + 1 Jev (derivable); then `version_heard` 1 Jev + attitude 1 Jev + 1 LLM per individual | first meeting; memoised per place |
| Drift check | 1 Jev (flag) + up to k Jev (explains) | only when retrieval returns canon relevant to the output |
| Model error | the output's narrator + NPC + extractor calls again, plus their checks | per report |
| Reaction / plan prefetch | 1 Jev per prefetched NPC | optional |

---

## D. Suggested order of work (not a plan, a dependency order)

1. `store.py` + `schema.sql`; re-base `eventlog`, `facts`, `state`, `attitudes`, `agents` on it with the existing behaviour and tests passing (storage swap, no new features).
2. `knowledge` + new `perception` + `snapshot`; NPC and unknown-claim contexts from the snapshot.
3. Spans in the extractor + the cut rollback; measure span accuracy (G-13) before relying on it.
4. Model-error flow and the mode gate (small, independent).
5. `time_passes`, `presence`, lazy materialisation, `spread`, back-dating rules.
6. Hidden channel and symptoms (scenario 4).
7. Canon file, retrieval, seeding, divergence ledger, drift check.
8. Ingestion tool (needs task 6's cost numbers).
