# Gaps: current code vs. the new `docs/decisions.md`

Checked against `main` after merging tasks 4 and 5 (115 tests). Size: **S** < half a day, **M** 1–3 days, **L** > 3 days.
No engine code was changed for this list. Items that are "undecided" in decisions.md and correctly not built are not gaps.

## Already matches (no action)
- Model allowlist, forbidden markers, `--live` flag, offline-by-default demo (`harness/policy.py`, `harness/demo.py`).
- Narrator never speaks for NPCs; speech rejected and regenerated (`pipeline._narrate`).
- Per-NPC isolated calls, output check for unlearnable claims, perception computed in code, append-only log with cascading rollback, Jev-first judging with 0.8 escalation, `relationship_magnitude` direct to the LLM, batching of per-state questions, live and retroactive interruption with private intent, per-character wikilinked memory files.

## Gaps

| # | Area | File(s) | What differs | Size |
|---|------|---------|--------------|------|
| 1 | Two times per record | `harness/db.py`, `models.py`, `facts.py`, `pipeline._commit` | Events and facts have only `game_time`; there is no separate log time. `_commit` always stamps facts with the current scene time, so lazily computed records about the past (heard on day 12, written on day 40) cannot be expressed. Needs a `logged_at` column and an `in_world_time` that may differ. | S–M |
| 2 | Open records / free-text facts with metadata | `facts.py` | Facts carry content, time, location, notability, knowers; "source" exists only per knower. No record-level origin link for facts derived from other facts (only `source_event_id`). Derived-from-text links cover the event but not fact→fact derivation (needed for attitudes/summaries/ingested book facts). | S |
| 3 | Live-state scope | `models.py` (`STATE_CATEGORIES`), `state.py`, `pipeline._OBSERVED` | Only injury, clothing, inventory, equipment, internal. Missing: timed effects (expiring), body details (fatigue, hunger, thirst, illness, poison, intoxication, pain as first-class), appearance (dirt/blood/marks), equipment condition, inventory location and money, companions, standing (wanted, disguised, reputation by place), posture/action. Decisions say all in scope from v1. | M |
| 4 | Player panel | none | No player-facing state panel (chips + prose through the epistemic filter). Only the dev-view print in `demo.py`. | M |
| 5 | Canon vs campaign check | `facts.search_canon`, `pipeline` | No check that narration contradicts canon, no "justified drift" vs "hallucination" decision. Canon retrieval is a token-overlap placeholder (no embeddings), and no canon-pull-proportional-to-deviation logic. | L |
| 6 | Book ingestion | none | Not built (task 6 only measures cost). Needs a chunker, extraction schema, canon store loader, and canon knowers by perception rather than the caller-supplied list. | L |
| 7 | Information spread by notability | `perception.py`, `pipeline` | Loud events reach only characters "outside" the room in the same scene. Nothing travels over distance/time, nothing reaches unvisited places; collectives (towns, factions) do not exist as holders of a version of events. | L |
| 8 | Belief and trust | `belief.py` | `neutral_belief` returns a constant. Decisions say belief depends on trust/relationship with the source; the model is undecided, so this is an acknowledged placeholder, but trust/relationship values are not stored anywhere yet. | S (store) / ? (model) |
| 9 | Two-level simulation | `agents.py` | `StubOffscreenUpdater` does nothing; no cheap world-level simulation (records + judgments without agents). Promotion on interaction exists. Off-screen detail level awaits the task 6 cost numbers. | L |
| 10 | Model-error action | none | No "model error" button flow: player states what was wrong, only the last world output regenerated, turn kept, explanation stored per campaign and fed into later prompts. | M |
| 11 | Choices final / debug-only rewind | `pipeline.rollback` | `Engine.rollback` is a public method with no normal-play vs debug-view gate. Needs a mode flag so rollback is unavailable in normal play (interruption and model-error regeneration use internal paths). | S |
| 12 | Time modes | `pipeline.py` | Only turn-based (`minutes_per_turn`). Flowing mode (silence counts as time) and "world stops in background" not built. Both are to be built and compared. | M |
| 13 | Turn assistant | none | Not built: situation-fit options, accept/feedback/edit/own/modify flow, verbatim-keep of praised parts, player-knowledge-only context, drafts outside the log, optional editable play-style note. | L |
| 14 | Settings | none | No content-limit conversation at campaign start; no pause / veil / skip controls. | M |
| 15 | Interaction extras | `streaming.py` | Streaming at speaking pace exists (`pace`), but quick reactions while an NPC speaks and tappable names/items are not prototyped. Marked "to be prototyped", so low priority. | M |
| 16 | App shell | none | No application (phone-first UI, persistence to disk, hosting). Engine is an in-memory library plus a CLI demo (`connect()` defaults to `:memory:`). Decisions require an own app, mainly phone. | L |
| 17 | Dev/debug view | `demo.py` | Debug info is printed by the demo only; no queryable dev view that separates it from normal play (judgments log and `devlog` exist as data). | S |
| 18 | Cost safeguards | `providers.py`, `judge.py` | Spend is tracked as a total only; no per-call log of role, model, tokens, cost, latency. Added for the task 6 measurement in `experiments/cost/` (outside the engine). Engine itself still lacks it. | S |
| 19 | Streaming usage (closed in task 9: usage is read from the final chunk) | `providers.OpenRouterProvider.stream` | Streaming requests do not ask for `usage`, so streamed calls would not be counted in `Spend`. The engine currently uses `complete` for NPC lines, so it is latent. | S |

## Not gaps (decided as undecided)
Mechanics (dice, stats), belief model internals, user-facing chronicle, hosting, off-screen update detail, music/voice/images.
