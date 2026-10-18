# Code study: summary

Reference material for `docs/decisions.md`. Per-project reports are in this folder. Date of study: 2026-10-19.

## Availability

| # | Project | Code studied? | Notes |
|---|---|---|---|
| 1 | MultihogDnDFramework | Yes (cloned, `d6aab00`) | JavaScript, SillyTavern extension |
| 2 | Concordia | Yes (cloned, `4b7e02a`) | Python |
| 3 | rolememo (DualMem) | **No. Repository unavailable** (404; clone asks for credentials). Paper studied. | Authors say code is planned for release. |
| 4 | ReverieMem (arXiv 2606.25632) | **No code released** (none linked, no repo found). Paper studied. | |
| 5 | lorevault-extension | Yes (client only, `c3d0529`) | Server is closed; inferred only. |

Reports: [sillytavern-multihog-dnd-framework.md](sillytavern-multihog-dnd-framework.md), [concordia.md](concordia.md), [rolememo-dualmem.md](rolememo-dualmem.md), [reveriemem.md](reveriemem.md), [lorevault-extension.md](lorevault-extension.md).

Assumption recorded: the task names `reports/code_study/<project>.md`. I used the project's repository or paper name for the file name.

## Comparison table

| Question | Multihog DnD | Concordia | DualMem (paper) | ReverieMem (paper) | LoreVault (client) |
|---|---|---|---|---|---|
| License | GPL-3.0 | Apache-2.0 | paper: arXiv; code unreleased | paper: arXiv; no code | README says MIT; no LICENSE file; server proprietary |
| State representation | `[TAG]` text memo + lorebook entries + JSON map documents | Per-entity string memory (text + embedding); GM `name\|value` strings | One bank of fact and insight entries; schema not given | SPOCV tuples (subject, predicate, object, cause, visibility set) + first-person scene summaries + personality patterns | Server-side LLM-extracted event rows: type, summary, location, characters involved |
| Event log / append-only | No (overwrite + snapshots); map ops carry `cause`/`actor` | Memory is append-only text; state components overwritten | Incremental, append | Static, built offline | Append-style, server-side |
| Extraction | Delta text blocks (tracker); tool-call JSON (lore agent); **typed JSON transactions with validation + retries (map)** | LLM chain-of-thought steps on putative events; `name\|value` parse, silent on failure | Trained 4B model emits facts then insights; null insight allowed | Offline LLM passes over a whole book | Hosted LLM extraction, prompts unknown |
| Code validation | Strong for map (structured errors, clone-apply-commit, max 2 corrections); weak for memo | Almost none | Format reward only | Not described | Unknown |
| Per-character knowledge | Not separated. Only player-view filter on map (UNREVEALED/SUSPECTED/KNOWN) | **Per-entity memory + per-entity delivery queue**; who-knows decided by an LLM question | None (persona-conditioned interpretation only) | **Visibility set per fact, hard filter at retrieval**; 4 routes | One `pov_character` string; Pro feature; server-side |
| Where filtering happens | Render time, for the player | Event delivery time | n/a | Retrieval time, in code | Retrieval time, on server |
| Long history | External summarizer required; lore dedupe/consolidation; grep tool | Embedding top-k; recent-memory question components | Chunked incremental build, top-10 | Offline scene summaries + fact graph; probe loop | Server summarisation + embeddings + token budget |
| Canon / rule check | Map invariants; dice commitment; no canon store | None | None | None (built from canon) | None |
| Rollback | Snapshot restore on swipe, 5 lore snapshots | Whole-simulation checkpoint | n/a | n/a | Unknown (client skips swipe duplicates) |
| Fit with our decisions | Typed transaction + validation pattern fits; omniscient narrator conflicts | Entity isolation + proposal/resolution split fits; LLM-written world state conflicts | Fact vs attitude split fits | Closest to the epistemic design | Same principle, closed, not reusable |

## Ranked patterns for this engine

Ranked by (importance to `docs/decisions.md`) x (evidence it works) x (cost to adopt). All are re-implementations of ideas. GPL-3.0 code (Multihog) must not be copied; no code is copied from anywhere (task rule).

1. **Visibility as a hard, code-side filter on every fact, applied before ranking.** Source: ReverieMem, paper section 3.2 (SPOCV tuples), section 3.4 (every retrieval bounded to the visible subset), Table 1 and Table 2 ([reveriemem.md](reveriemem.md)). Measured: shared-store RAG refuses 8.7-11.3% of out-of-perspective questions; the visibility-bounded system reaches 81.2%. Directly supports "isolation at retrieval, in code". Extend with a "heard" route plus time/distance, which none of the projects have.
2. **Typed state-change transaction, validated in code on a clone, with structured errors fed back for at most N retries.** Source: Multihog Map Updater: contract in `map-updater-prompt.js`, validation `dungeon-reality.js:2035-`, retry loop `map-updater.js:59`, `:350` ([sillytavern-multihog-dnd-framework.md](sillytavern-multihog-dnd-framework.md)). Fields worth keeping: `operation_id` (idempotent), mandatory `cause`, `evidence` level (CONFIRMED / IMPLIED / AUTONOMOUS), `noop` as a valid output, machine-readable error codes with `path` and `allowed`. This is the extractor-to-code contract for "code validates and stores".
3. **Per-entity observation delivery with a catch-up digest.** Source: Concordia `components/game_master/make_observation.py:41-83` (queue per entity), `interrupt_make_observation.py:75-95` (missed-events digest) ([concordia.md](concordia.md)). Fits "each NPC line from a separate call with that NPC's isolated context" and "off-screen NPCs receive cheap periodic updates". Replace the LLM "who is aware" question (`event_resolution.py:219-236`) with a rule over event metadata (witnesses present, loudness, distance), and keep a typed judgment only for borderline cases.
4. **Proposal -> resolution split.** An NPC line or a player action is a *putative event*; only the resolved, validated event enters the log. Source: Concordia `environment/engines/sequential.py:163`, `components/game_master/event_resolution.py:132-247` ([concordia.md](concordia.md)). This is also the natural place for the canon-drift check (accept if a campaign event explains it, else regenerate).
5. **Separate shared facts from per-character attitudes, linked by fact ids, with null allowed.** Source: DualMem, paper section 4.1-4.3 ([rolememo-dualmem.md](rolememo-dualmem.md)). Implements "different characters hold different attitudes toward the same event" and "salience is a separate judgment". Retrieval returns an attitude with its grounding facts.
6. **Refusal-by-absence plus an isolation regression test.** Source: ReverieMem, Memory-Fusion constraints (Table 13) and the KBF metric (section 4) ([reveriemem.md](reveriemem.md)). The prompt for an NPC contains no fact they cannot know, so "I don't know" is natural. Build a small recall/refusal question set from the campaign log (what each NPC witnessed or not) and score it with the harmonic mean, to detect leaks when prompts or models change.
7. **Scene-anchored retrieval for an NPC agent.** Source: ReverieMem Anchor + Self-Probe loop (section 3.4, Appendix C, Table 11). First retrieve the NPC's own first-person episode summaries, then use them to form fact probes inside the visible set. Written at event time rather than offline, the "summaries without access to later events" property is automatic. Costs several LLM calls per line, which `docs/decisions.md` accepts ("quality beats cost") but a budget is needed.
8. **Evidence levels and durable/transient filtering in extractor prompts.** Source: Multihog `map-updater-prompt.js` ("DURABLE vs TRANSIENT", "Never mutate from speculation or from an unresolved player attempt"). Prevents recording what was only attempted, intended or cut off. Important for interruption rollback: an interrupted utterance is an unresolved attempt.
9. **Full-review fallback for weak extractor models.** Source: Multihog `docs/multihogDnDdoc.md` (Local / weaker State Tracker models), `src/state/defaults.js:415-440`. Delta-only extraction makes weaker models drop still-true items; full-state output is more reliable. Our event-log design avoids full dumps, but the failure mode is real for any "emit a diff" extractor and should be tested.
10. **Provenance routes beyond presence.** Source: ReverieMem organisational-sharing propagation via a membership graph (section 3.3). Use for faction/guild knowledge spread in the Witcher world.
11. **Knowledge states with a "suspected" level.** Source: Multihog `dungeon-reality.js:39-40`. A rumour/hearsay level between "knows" and "does not know" suits notability-driven spread.
12. **Commit-before-outcome for randomness (only if mechanics are decided later).** Source: Multihog Hybrid RNG (README, `sysprompt.txt`). Mechanics are explicitly undecided, so this is parked.

## Gaps none of the projects fills (for our design)

- **Append-only event log with rollback by event.** Multihog uses snapshot restore; Concordia uses whole-simulation checkpoints. Neither supports "everything after the cut point was never said; roll back extracted state".
- **Interruption.** Concordia's "interrupt" means attention masks; nothing cuts an utterance. No project has retroactive interruption or "unsaid remainder as private intent".
- **Notability-driven information spread** (quiet stays local, loud travels). Not present anywhere. ReverieMem's V is static, Concordia's delivery is one-shot, LoreVault is a witness list at best.
- **Canon store vs campaign store with justified-drift check.** No project has it. Multihog's closest piece is its map invariants.
- **Two-level simulation** (cheap world records, persistent agents only after interaction). Concordia makes all entities full agents; Multihog's World Progression / Map Evolution is cheap off-screen simulation of places, not of knowledge.

## What conflicts with `docs/decisions.md` (do not adopt)

- Free-text `[TAG]` memo merged by regex (Multihog): fragile, not an event log.
- Omniscient narrator that receives every NPC's full record on a name mention (Multihog): the leak our design forbids.
- LLM-written `name|value` world state with silent parse failure (Concordia `world_state.py:108-145`).
- LLM-written fallback observation for a character from the omniscient GM context (Concordia `make_observation.py:205-222`).
- Hosted memory service that receives all text and controls the filter (LoreVault): conflicts with "own hardware or own key" and with the code-owned state principle.
- Offline, one-shot memory built from a finished text (ReverieMem, DualMem): no write path during play.
- Hard-coded D&D mechanics (Multihog): mechanics are undecided.

## Licenses at a glance

| Project | License | What it allows |
|---|---|---|
| MultihogDnDFramework | GPL-3.0 | Study and re-implement ideas freely. Copying code would force the engine under GPL-3.0. |
| Concordia | Apache-2.0 | Reuse with notice and patent grant. We still copy nothing. |
| rolememo | unknown (unreleased) | Ideas only. |
| ReverieMem | paper under arXiv non-exclusive license; no code | Ideas only. Do not copy its prompts verbatim. |
| lorevault-extension | README says MIT, no LICENSE file; server proprietary | Nothing to reuse. |

## Method and limits

- All "from the code" statements cite files and line ranges at the HEAD commits above. I did not run any of the projects.
- Multihog is 58k lines and Concordia 59k; I read the paths relevant to state, extraction, knowledge separation, retrieval, validation and rollback, not the whole codebases (see each report's "Assumptions / limits").
- For the two papers, claims are from the paper text, not from verified code, and the headline numbers are the authors' own (LLM-judged where stated).
- The clones live in the session scratchpad, outside the repository. Nothing from `data/` was used.
