# Concordia (google-deepmind/concordia)

- Repo: https://github.com/google-deepmind/concordia (cloned, HEAD `4b7e02a`, 2026-10-16)
- Language: Python, about 59k lines in `concordia/`.
- **License: Apache-2.0** (`LICENSE`). All files carry the Google header.
- Paths below are relative to `concordia/` inside the repo unless stated.

## What it is

A library for generative-agent simulations. Entities (players) are built from *components*. A Game Master (GM) is itself an entity built from components. An *engine* loops: pick who acts, ask them for an action, treat that action as a "putative event", let the GM resolve it into a real event, and deliver observations to the entities. State is held by components and can be checkpointed.

## 1. How world and character state is represented and stored

- **Entity = bag of components** with a phase machine `READY -> PRE_ACT -> POST_ACT -> UPDATE -> READY` (`typing/entity_component.py:39-80`). Every component implements `get_state()` / `set_state()` returning a JSON-like mapping (`:34`, `:119`, `:128`; entity-level `:220`, `:225`). This gives a whole-simulation checkpoint (engines call a `checkpoint_callback` every step, `environment/engines/sequential.py:231`, `:297-299`, `:361-362`).
- **Memory** is an `AssociativeMemoryBank` (`associative_memory/basic_associative_memory.py:30`): a pandas DataFrame with exactly two columns, `text` and `embedding` (`:52`). It is an append-only list of strings. Duplicates are dropped by hash unless `allow_duplicates` (`:87-114`). **No timestamp, no tags, no importance, no participants** are stored, although the docstring of `add` still says "(time, text, tags, importance)" (`:88-93`). Tags are embedded in the text itself, for example `[observation]`, `[putative_event]`, `[event]` (`components/agent/observation.py:29`, `components/game_master/event_resolution.py:36-37`) and retrieved by string-matching `scan(selector_fn)` (`:200`).
- **World state** in the GM is `WorldState`: a flat `dict[str, str]` of `name|value` variables that an LLM rewrites after each event (`components/game_master/world_state.py:35-173`). There is also `Locations` (same file, `:176`) and `inventory.py`, each LLM-maintained.
- Characters have no structured state. Identity is a list of strings (formative memories, `components/game_master/formative_memories_initializer.py`) plus whatever question-components derive from recent memories.

So state is **text rows and string maps**, and LLMs write the maps. Code only stores them.

## 2. How state changes are extracted from model output

- The player's output is wrapped as a putative event: the engine calls `game_master.observe(f'{PUTATIVE_EVENT_TAG} {putative_event}')` (`environment/engines/sequential.py:163`).
- `EventResolution.pre_act` (`components/game_master/event_resolution.py:132-247`) scans memory for the latest `[putative_event]` for the active player (`:151-190`), then runs a configurable **chain of thought** (`run_chain_of_thought`, `:1282-1309`). Each step is a function `(InteractiveDocument, premise, player) -> str`, for example `attempt_to_result`, `determine_success_and_why`, `result_to_causal_statement`, `result_to_who_what_where`, `result_to_effect_caused_by_active_player` (definitions at `:588-794`). The last step's string is the real event.
- State components then update from the event text in `post_act`: for instance `WorldState.post_act` asks an open question to emit `name|value,...` pairs and splits on `,` and `|` (`world_state.py:108-145`). Malformed pairs are silently ignored (`if len(split_variable) == 2`). There is no schema, no type check, no retry. A value containing a comma or `|` corrupts the parse.
- `InteractiveDocument` is the prompting primitive: `statement`, `open_question`, `multiple_choice_question`, `yes_no_question` (`document/interactive_document.py:112-345`). `yes_no_question` returns a bare `bool` (`:338`). Language models expose `sample_choice(prompt, responses)` returning `(index, response, info)` (`language_model/language_model.py:79`). The docstring notes the sampling may not reflect log-probabilities. So there are **typed choice judgments but no probabilities**.
- The interrupt-driven GM parses entity output with a small tagged-text parser (`components/game_master/interrupt_response_parsing.py`, 129 lines) that yields `action_text`, a mask, and a timer.

## 3. How per-character knowledge is separated

This is the part most relevant to our design, and it is **filtered at event-delivery time, by an LLM judgment, into per-entity queues**.

- Each entity's own memory contains only what that entity observed or did. The GM's memory is separate and sees everything (the putative events are written to the GM's memory, not to others').
- Delivery: after resolving an event, `EventResolution` (with `notify_observers=True`) clones the resolution prompt and asks `"Which entities are aware of the event? Answer with a comma-separated list of entity names."` (`event_resolution.py:219-236`). Each named entity gets the event string appended to its queue with `make_observation.add_to_queue(name, event_statement)` (`:233-236`).
- The alternative path, `SendEventToRelevantPlayers.post_act` (`:451-505`), asks a yes/no question for each player: `"Is {name} aware of the latest event above?"` (`:478`). It also strips text the player already saw (`:484-486`).
- `MakeObservation` holds an `ObservationQueue` with `add(entity, event)`, `get_and_clear(entity)`; the entity name `all` fans out to every player (`components/game_master/make_observation.py:41-83`). When an entity is asked what it observes, queued events are returned verbatim and the queue is cleared (`:205-209`). Only if the queue is empty and `allow_llm_fallback` is true does an LLM invent an observation, with the instruction `"Only include information of which they are aware"` (`:32`, `:210-222`).
- The entity then stores each observation in its own memory (`ObservationToMemory.pre_observe`, `components/agent/observation.py:48-58`).
- In the interrupt-driven variant, attention is controlled by a prefix mask on event tags per entity (`interrupt_scheduling.py:70-125`, `get_entities_to_poll` at `:385-425`); events that match no mask are held in a pending list and delivered later as a catch-up summary ("Events missed while focused", `interrupt_make_observation.py:75-95`). Timers are non-maskable and private (`:399-405`).

Properties of this scheme against our requirements:

- Good: isolation is structural. A character's context is built only from that entity's own memory, so there is no "you do not know X" instruction.
- Weak: the decision *who knows* is one LLM question with no metadata on the event (no loudness, distance, or notability), so there is no propagation over time and distance. The fallback LLM observation (`make_observation.py:205-222`) is a leak path: the GM model is asked to write what the entity observes with the full GM context in the prompt, and only an instruction guards it.
- Weak: no second-hand knowledge. An entity cannot "hear later" about an event because delivery is one-shot at event time.
- Memory has no provenance field, so "witnessed" versus "was told" cannot be distinguished.

## 4. How long histories are compressed or retrieved

- Retrieval is `retrieve_associative(query, k)`: embed the query, dot-product with every stored embedding, sort, take top k (`basic_associative_memory.py:133-198`). There is no recency or importance weighting in the bank. Recency is a separate call, `retrieve_recent`.
- `QuestionOfRecentMemories` pulls `num_memories_to_retrieve=25` recent memories, optionally conditioned on other components, and asks a fixed question (self-perception, situation perception, options, and so on) (`components/agent/question_of_recent_memories.py:25-80`). The answer is injected into the next prompt and optionally added back to memory (`add_to_memory`).
- Compression is by these derived-answer components, not by summaries of history. There is no hierarchical summary or forgetting.

## 5. Canon / rule consistency

- No canon store, no contradiction check. Consistency relies on the GM's chain of thought (`determine_success_and_why`, `AccountForAgencyOfOthers`, `Conversation`, `event_resolution.py:588`, `:833`, `:948`) and on injecting `WorldState`.
- `get_action_category_and_player_capability` (`:1053`) and `maybe_inject_narrative_push` / `maybe_cut_to_next_scene` (`:1144`, `:1204`) steer pacing, not canon.
- Scene specs and `script.py` constrain what is allowed per scene. No validator.

## 6. Interruption / rollback

- "Interrupt" in Concordia means *an entity's attention mask and timers* (`interrupt_*` components). It does not mean cutting a speaker mid-utterance. Nothing in the code supports the "retroactive interruption" in `docs/decisions.md`.
- Rollback is whole-simulation checkpoint (`get_state`/`set_state` on every component, saved by the engine's checkpoint callback). There is no per-event undo.

## 7. Fit with `docs/decisions.md`

| Our decision | Concordia |
|---|---|
| Code owns state, LLM never writes it | No for GM state. The LLM rewrites `WorldState` strings. Code stores. |
| Append-only event log | Memory bank is append-only text, but with no metadata; state components are overwritten. |
| Isolation at retrieval, not by instruction | Largely yes: per-entity memory plus delivery queue. Leaks through the GM-written fallback observation. |
| Open-ended facts with when/where/who/how loud | No. A fact is a bare string. |
| Notability-driven spread | No. |
| Separate call per NPC line with isolated context | Yes, that is exactly the entity-act model. |
| Two-level simulation | No. All entities are full agents. |
| Typed judgments (Jev) | Partly: `yes_no_question`, `multiple_choice_question`, `sample_choice`, but no probabilities. |
| Canon store / drift check | No. |
| Interruption | No (different meaning). |

## 8. What is reusable

**Directly reusable as design (Apache-2.0 allows reuse with attribution and a NOTICE, but we are not copying code per task rules):**
- Entity = isolated component set with `pre_act / post_act / update` phases and `get_state / set_state` on every component. This is a clean template for "each NPC line from a separate call with that NPC's isolated context".
- Observation queue per entity with a catch-up delivery and explicit `drain` (`make_observation.py:41-83`, `interrupt_make_observation.py:75-95`).
- GM-side `putative event -> resolution -> real event` split. The player's or NPC's output is a *proposal*, not a fact. This maps onto the extractor emitting a diff that code validates.
- "Missed events" digest for characters returning from being busy, which fits off-screen NPC cheap updates.

**Ideas only:**
- The two-step awareness decision (`Which entities are aware...` / `Is X aware...`). Replace the free-form LLM question with a code-side rule over event metadata (loudness, location, witnesses), with a typed judgment only for borderline cases.
- Chain-of-thought event resolution as an ordered list of step functions.
- Tag prefix mask for what an agent attends to.
- `QuestionOfRecentMemories`-style derived context (what situation is X in) as an NPC-agent step.

**Conflicts / not to adopt:**
- Memory rows as bare strings with tags embedded in text.
- LLM-written `name|value` world state with silent parse failure.
- GM fallback observation generated by an omniscient model.
- Dot-product over all rows in pandas (fine for a prototype, not for a long campaign).
- Whole-simulation checkpoints as the only rollback.

## 9. License

Apache-2.0. Permits use, modification, redistribution including commercial, with notice preservation and a patent grant. We still do not copy code (task rule); ideas are free.

## Assumptions / limits

- I read the memory bank, observation delivery, event resolution, interrupt scheduling and resolution, world-state, entity-component and sequential engine paths. I did not read the prefabs (`prefabs/`), `contrib/`, the language-model backends, or the example scenarios in detail.
- I did not run the code.
