# Assumptions (tasks 3 and 4)

Choices made where `decisions.md` or a task brief was silent. All are easy to swap. Items marked
**(task 4)** are new or changed in the revision to the updated `decisions.md`.

## Carried from task 3

1. **Time** is integer in-game minutes since a campaign epoch. Turn-based mode only (fixed
   `minutes_per_turn`); flowing time is undecided and not built.
2. **Rollback is a marker, not a delete.** The log stays append-only (SQL triggers block
   UPDATE/DELETE). A `rollbacks` table marks events; every derived-state query filters on active
   events. Rollback cascades through `cause_id`. Facts are tied to their source event, so they
   vanish with it. No snapshots: derivation is cheap at this scale. **(task 4)** Live-state
   changes, perception facts, salience notices and attitudes all carry a `cause_id`/source event
   for the same reason, so one rollback removes everything that grew from an event.
3. **Canon visibility.** Canon facts have knowers like campaign facts; a character sees a canon
   fact only if listed. The narrator retrieves canon via a token-overlap placeholder
   (`FactStore.search_canon`), swappable for embeddings. Canon knowers are given by the caller
   (`add_canon(knowers=...)`), not by perception.
4. **One extractor call per turn.** Each diff entry names the segment it came from, which makes
   per-utterance rollback possible. Extraction retries once on an invalid diff; if still invalid
   the whole turn is rolled back and `ExtractionRejected` is raised.
5. **Information spreading by notability** (loud events travelling over distance/time) is decided
   in principle but has no specified algorithm. Notability is stored; the only effect today is
   that a loud event (>= 0.7) is heard by characters *outside* the room (see 15). Nothing
   propagates beyond the scene.
6. **Interruption.** Live: words are delivered one by one; when the handle fires the current word
   is the last one delivered, the rest is kept as the NPC's private intent. Retroactive: allowed
   only for the last NPC utterance overall, once, with a cut point strictly inside it. Because the
   extractor cannot attribute facts to word ranges, all facts and state changes derived from that
   utterance are rolled back and re-extracted from the kept prefix only. If re-extraction fails,
   the cut stands with no facts from the kept part. The interruption fact is perceived by
   everyone present under normal perception rules. Words are whitespace-separated.
7. **Intents** stay pending until explicitly resolved (`Intents.resolve`).
8. **Agent promotion** happens when an NPC speaks in a turn with the player (after the turn
   commits). The off-screen update hook is called for promoted agents not in the scene; the stub
   only records the call.

## Perception (task 4)

9. **Scene model.** A scene is one room: `Scene.present` characters see and hear everything in
   it; `Scene.outside` characters are nearby and hear only loud things (`notability >= 0.7`,
   `perception.LOUD`). No zones, distances or line of sight. A character in neither list perceives
   nothing. Scene composition is session state (`enter_scene`/`leave_scene`), not derived from the
   log, so it is not rolled back.
10. **Perception kinds.** `speech` (listeners are *told by* the speaker, the speaker knows their
    own words first-hand, outside listeners *hear from* the speaker if loud), `action` (present
    characters *witness*, outside *hear* if loud), `description` (nobody: narrator-only knowledge,
    e.g. scenery or a character's hidden thoughts). The extractor segment key decides the kind:
    `player` and NPC ids are speech, `narration` is description, `action1..N` are actions. A
    character id that looks like `narration` or `actionN` would collide; ids must not.
11. **The player's input is treated as speech** ("told by Geralt"). Physical actions of the player
    reach others through the narrator's `observable_actions`, which the narrator is asked to
    write for every visible act, the player's included.
12. **Notability for perception comes from the extractor** (per fact), because it describes how
    loud the content is. Event-level `witnesses` use the present list only.
13. **Narrator description is narrator-only.** If a detail must reach characters, the narrator
    must list it as an observable action. This keeps hidden things hidden by default.

## Source of knowledge, belief, attitudes (task 4)

14. **Schema.** `fact_knowers` gained `source` (NULL = perceived directly, else the character who
    said/told it) and `event_id` (the event the knowledge came from). `how` stays
    `witnessed | heard | told`. NPC context shows `(heard from X)` for any record with a source;
    the player character goes through exactly the same code.
15. **Belief slot.** `belief.BeliefFn(character, fact, knower) -> 0..1`, default constant 0.5
    ("no opinion"). It is called when memory is derived and printed in the memory files; it does
    not change what goes into an NPC prompt yet (there is nothing to change while it is neutral).
16. **Attitudes.** After a turn commits, each new fact with notability >= 0.6 gets, for every NPC
    who knows it, one direction judgment (positive/neutral/negative) and one magnitude judgment
    (0..3, goes to the LLM directly). Neutral or zero-magnitude results are not stored. The
    threshold is a cost control, not a design decision. Attitudes point to the fact id and are
    caused by the fact's source event, so rollback drops them. The player is not assessed (no NPC
    context to feed).

## Live state (task 4)

17. **Categories** `injury, clothing, inventory, equipment, internal`; **ops** `add, remove,
    reveal, hide`. Items are matched by exact text. If the extractor spells an existing item
    differently, "remove" is rejected as removing something that is not there, and the whole diff
    is retried once, then the turn fails (this actually happened while building the demo script).
    A fuzzy match is a possible later improvement, deliberately not built.
18. **Setup/scripted changes** go through `Engine.apply_state_change`, validated the same way,
    caused by a `scripted` marker event so they can be rolled back.
19. **What is perceived.** An observable `add`, a `reveal`, and a `remove` of an observable item
    become perception facts ("X is carrying Y", "X no longer has Y") for everyone else present,
    notability 0.4, wording from small per-category templates. `hide` is not perceived (the
    earlier observation stays true of the past). Changes to characters who are not in the room
    wait until they enter. On `enter_scene` the room perceives the entrant's observable state and
    the entrant perceives everyone else's.
20. **Salience.** One batched judgment per observation, one question per NPC observer (the player
    gets the fact but no salience question). A "noteworthy" verdict becomes a `noticed` event and
    appears under "You have just noticed" in that NPC's next *generated line*; it is consumed
    when that NPC speaks (rolled back with the turn if the turn fails). Non-noteworthy
    observations are still known facts. If the judge fails, the verdict defaults to not
    noteworthy and the failure is logged.

## Narrator and NPC output checks (task 4)

21. **Narrator format** `{"description", "observable_actions", "speakers"}`. Speakers may be
    ids, display names, or `id (Name)` (models do all three); unknown or absent ones are dropped
    and logged. `Engine.turn(speakers=[...])` overrides the narrator's list.
22. **Speech detection.** A script-style `Name: words` line is rejected in code. Everything else
    is judged by one yes/no question (every narrator output, since speech also hides in
    paraphrase), because code cannot tell player quotes from NPC quotes. Rejected output is
    regenerated at most 2 times; then speech is stripped (quoted spans and speaker lines), the
    event is logged in `Engine.devlog`, and the turn continues. If the judge is unavailable,
    quotes count as speech.
23. **NPC lines.** The model's text is cleaned in code (stage directions in parentheses/asterisks,
    wrapping quotes, long quoted passages that are other characters' lines), then output-checked
    **before** it is streamed to the player. So the line is complete before the first word is
    shown; "streaming at speaking pace" now means pacing an already-accepted line. This costs
    latency; decisions.md prefers quality.
24. **Output check.** One judgment per line against that NPC's visible knowledge: derived
    knowledge, own condition, noticed items and conversation it witnessed. Unlearnable claim ->
    regenerate, at most 2 retries, then the fixed fallback line "I don't know what to tell you."
    plus a log entry. If the judge fails, the line is accepted and the failure logged. The check is
    only as good as the judge: in the live smoke run Jev/LLM caught invented named characters
    (a bard making up "Margo" and a blacksmith's apprentice) but let through milder embellishment
    ("a week ago", "a blood trail").
25. **A character with no seeded knowledge will have most local detail rejected**; the demo seeds
    a few canon facts per character for that reason. Real campaigns need background knowledge per
    character.

## Judges (task 4)

26. **Jev** `typesafe/jev-1.14`: yes/no -> `noul` (answer = p >= 0.5, probability = max(p, 1-p)),
    choice -> `choice` with `criteria` as an object, score -> `score` with a legend list (answer =
    first legend value + Jev's expected index, probability = largest bin). One HTTP call per batch
    of questions about the same state. Jev's long-context mode (>= 32 KB) is not used.
27. **Escalation.** Probability < 0.8 -> the same questions go to the LLM (default
    `anthropic/claude-haiku-5.5`, best cheap accuracy in E2) and its answer replaces Jev's,
    flagged `escalated`. Tag `relationship_magnitude` skips Jev. If Jev errors, everything goes to
    the LLM. If the LLM errors too, Jev's low-confidence answer is kept when there is one, else a
    `JudgeError` is raised and the caller degrades (see 20, 24). The LLM judge retries once with a
    stricter instruction and tolerates `[name]` keys.
28. **Log.** `Engine.judgments` (and `<campaign>/judgments.jsonl`) hold every judgment: tag,
    question, answer, probability, escalated, backend.
29. **Offline default judge** (`FakeJudge` via `default_fake_judge`): no leaks, no speech, not
    salient, neutral attitudes. Tests script it per tag.

## Memory files (task 4)

30. **One derivation, two renderers.** `MemoryDeriver.derive(character)` (knowledge with
    source/event/belief, attitudes, live state, intents, pending notices) feeds both the NPC
    context and the Markdown files, so they cannot drift. The files are rewritten *completely*
    (stale ones removed) after every committed turn, failed turn, retroactive interruption, scene
    change and `Engine.rollback`. Rolling back through `Engine.log.rollback` directly bypasses the
    refresh; use `Engine.rollback`.
31. **Layout** under `<campaign_dir>/memory/`: `characters/<id>.md` (Knows, Attitudes, Live state,
    Pending intents), `places/place-<slug>.md`, `events/event-<n>.md` (only events some record
    points at). Facts are block anchors (`^fact-<id>`) inside the character file; attitudes link
    to them as `[[<character>#^fact-<id>]]`. `campaigns/` is git-ignored. The SQLite database is
    still in memory; persisting a campaign is not part of this task.

## Models and spending (task 4)

32. **Policy in code.** *(Superseded by 47-48: the allowlist is now a price rule.)* `harness/policy.py` holds the allowlist from `docs/decisions.md`; the
    OpenRouter provider and the Jev client refuse anything else, and `HARNESS_EXTRA_ALLOWED`
    cannot add Sonnet/Opus/GPT-5/Fable-class names. A `Spend` counter reads `usage.cost` and stops
    at a cap (`--budget`, default $0.25 per demo run).
33. **Default live models.** *(Superseded by 47: no Anthropic default; models from the task 7 bake-off.)* Extractor `anthropic/claude-haiku-5.5` (E3: 0% hallucinated facts at
    low cost). Narrator and NPC lines `deepseek/deepseek-v4-flash` (allowed, cheap; writing
    quality was judged only by reading the smoke run, not measured). Judge escalation
    `anthropic/claude-haiku-5.5`. Each is a flag/`ModelConfig` field. Reasoning is switched off in
    requests (retry without it on HTTP 400).
34. **Demo.** Fake provider and fake judge by default; `.env` is read and the network used only
    with `--live`. The fake script deliberately includes a narrator that writes NPC speech and an
    NPC claim the NPC could not know, so both rejection paths show.

## Model bake-off (task 7)

35. **Step 0 was already done.** At the start of the session `git ls-remote origin` already listed `refs/heads/ui-prototype` (edd8f61) and `refs/heads/design-schema` (3e43a39), matching the local worktree heads. Nothing had to be pushed; verified again at the end.
36. **Prompts.** The bake-off uses the narrator, NPC and extractor prompt templates of `harness/context.py` verbatim (copied into `experiments/bakeoff/prompts.py`), filled from fixed test items. The engine prompts contain no language instruction; the test set is Ukrainian and the models were left to choose the output language. Several answered in English (narrator: qwen 2 of 9; extractor facts: mostly English).
37. **Test set.** 9 narrator scenes, 12 NPC situations, 10 extraction passages, 60 yes/no judgments, all written by the agent before any run, from setting knowledge only (no book text, no Ragnar chronicle text). 36 judgments exist in English and Ukrainian; 24 (unknowable claim, narrator speech) contain a quoted Ukrainian line under an English question, as the task allows, and were run once ("mixed"). All judgments are yes/no (`noul`); choice and score types were not benchmarked.
38. **Grading.** One grader (the Claude Code agent), blind to model names (per-item shuffle, key in `raw/blind_key.json`, read only after grading). Scales and flags are defined in the `_doc` fields of the `grades_*.json` files. Extraction precision counts emitted facts that are unsupported by the passage; recall counts gold facts covered (a merged fact can cover two).
39. **Extra text candidates (max 3).** `openai/gpt-6-luna` ($0.10/$0.50; public comparisons at gradually.ai and datalearner.com show it ahead of Gemini 3.5 Flash-Lite on general benchmarks), `google/gemini-3.5-flash-lite` ($0.30/$2.50; within ceiling; Google models are generally strong in Ukrainian), `cohere/command-a-plus` ($0.30/$1.50; multilingual positioning). The OpenRouter roleplay collection ranks DeepSeek V4 Flash first by usage, which supports the mandatory DeepSeek entry (usage, not quality). Public Ukrainian-specific benchmarks for these models were not found; signals are weak. Command-a-plus put its reasoning into the content under the engine's "reasoning disabled" call and was not retried with reasoning on.
40. **Free models not tested.** No `:free` model was run; no role depends on one. Candidates for a later run: `nvidia/nemotron-3.5-super-vl:free`, `thinkingmachines/inkling:free`, `poolside/laguna-s-2.1:free`.
41. **`elorian/glimpse`** is a chat model (the decisions endpoint answers "model does not exist"), so it was run as an LLM judge with the same JSON prompt as the LLM judges. Its output price (3.00 USD per M) is above the 2.50 ceiling, so it is tested because the task lists it but excluded from recommendations.
42. **Decision endpoint.** Jev, pplx-decider and d1-ultra answer both `/api/v1/systemone` and `/api/alpha/decisions` with the same schema. `~perplexity/pplx-decider-latest` is not in the catalog and was skipped. LLM judges give `p_yes` sometimes as confidence in their answer; the harness trusts the `answer` field and flips an inconsistent `p_yes` (as `LLMJudge._parse` does for the answer).
43. **Cost per hour.** 40 turns per hour, one turn = 1 narrator + 1.5 NPC lines + 1 extractor call + about 7 decisions, test-sized contexts. These are assumptions; real contexts are longer.
44. **Laya.** Installed `laya[serve]` with CPU torch into `/home/cock/1TB/AI/laya/venv` (outside the repo and off the root disk); served on 127.0.0.1:8765. Checkpoints English and multilingual only (not `typed-decisions`). The fine-tune estimate (300–1000 labelled examples per judgment type) is a judgment from the model card, not a measurement.
45. **Gap, not fixed here.** *(Closed by task 9, entries 47-48.)* `harness/policy.py` still carries the old allowlist and defaults (`anthropic/claude-haiku-5.5` as extractor and escalation model, `deepseek/deepseek-v4-flash`, forbidden-marker list without the new price ceiling). Aligning it with the new policy in `docs/decisions.md` is a separate engine task (this task did not change engine code).
46. **Branch handling.** The project `CLAUDE.md` asks to merge into `main` and push at the end of a task. This session's background-job rules forbid pushing `main`, so the work stays on branch `worktree-task7-bakeoff` (pushed, verified with `git ls-remote origin`) and the merge is left to the owner.

## Engine on the chosen models (task 9)

47. **Defaults.** Narrator and NPC `openai/gpt-6-luna`, extractor `deepseek/deepseek-v4.1-flash-1017`, first judge `liquid/d1-ultra`, escalation `openai/gpt-6-luna`; fallbacks per role as in `docs/tools.md` (extractor fallback `qwen/qwen3.8-omni-flash`, first-judge fallback `perplexity/pplx-decider-v1.2`). The fallback applies when a call raises `ProviderError` (after the client's retries) or, for the decider, `JudgeError`; JSON/format failures are not a reason to switch models. `ModelConfig()` keeps its old placeholder names for tests; `ModelConfig.live()` gives the real ones.
48. **Price rule.** Worst-case price counts: the base price or any surcharge tier ("overrides") in the catalog, whichever is higher. Variable (negative) prices are refused. A model not in the catalog is refused. `:free` models pass at price 0. Anthropic = id contains `anthropic/` or `claude`. Deny list: OpenRouter routers (`openrouter/auto` and kin) plus `HARNESS_DENY` (comma-separated). `HARNESS_EXTRA_ALLOWED` is removed (the rule replaces it). The decision client accepts only the explicit decision list. The cache lives in `.cache/openrouter_models.json` (git-ignored; override with `HARNESS_CACHE_DIR`); the catalog endpoint is public, so the fetch sends no key. If a refresh fails the older cache is used; with no cache the model is refused.
49. **Parallel plan, as built.** After the narrator: its speech check and each NPC chain (line, then check) start together; the extractor does NOT run beside them. It needs what was actually said (an interrupted line is cut), so it runs once, after delivery. The task 7 timing script also ran an extractor in the first wave, but its wall time equals narrator + longest chain + extractor, which one post-delivery extractor reproduces; two extractor calls would only cost more. After extraction the salience and attitude judgments run as one concurrent wave. NPC chains start speculatively on the candidate narration; if the speech check then rejects it, the provisional narration/action events are rolled back, the chains are dropped (their spend is lost) and the narrator is called again.
50. **Consequence of parallel NPC chains.** Two NPCs speaking in one turn no longer see each other's line from that turn (both are generated before either is delivered). Sequential mode still does. Fake providers run sequentially (`parallel_ok` is False) so scripted tests stay deterministic; `Engine(parallel=...)` overrides. Not measured: how much this hurts dialogue quality. In the live smoke run the second speaker's lines stayed coherent with the scene but did not answer the first NPC's line of the same turn.
51. **Deterministic logs.** Workers do no database access and write no logs of their own: notes and judgments are collected per worker and merged by the main thread in a fixed order (speech check, then NPCs in narrator order). Salience judgments for state changes are now asked after all state changes of the diff are applied (one wave), not interleaved per change; the result is the same in both modes.
52. **NPC output check.** Suspicion = the decider's probability for "yes" (the claim is unknowable). Reject at p >= 0.7 (`Engine(npc_reject_p=...)`, `settings.NPC_REJECT_P`). If no judge answers, the line is accepted (as before). `FALLBACK_LINE` is kept as a constant but is no longer shown. Ties between candidates go to the earliest.
53. **Languages.** Output language default Ukrainian is an instruction appended to the narrator prompt ("Write the description and the observable actions in X") and the NPC prompt ("Speak in X."). Observable actions are player-facing, so they follow the output language. Record language default is None = no instruction (what the extractor writes now: mixed Ukrainian and English in the live run); setting it adds one sentence to the extractor prompt. Judgment questions stay English. Both live in `harness/settings.py` and as `Engine` arguments, and are stored with a saved campaign.
54. **Saved campaigns.** One database per campaign, `campaigns/<name>/campaign.db`; the scene (location, present, outside, time), characters and settings are stored in a `campaign_meta` table and rewritten whenever the scene changes (`refresh_memory`, `advance_offscreen`). Everything else (events, facts, live state, agents, intents, attitudes) is derived from the log. Models, judge and provider are not stored; they are passed on open. Connections for campaigns are opened with `check_same_thread=False` so a server can use them; the caller must serialise turns. `synchronous=NORMAL` with WAL.
55. **Decision-model backend label.** Judgments from a hosted decider now carry the model id as `backend` (was `"jev"`), so the debug view shows which decider answered, including after a fallback.
56. **Stream usage.** `OpenRouterProvider.stream` adds the final chunk's usage to `Spend` once; if a stream breaks, usage is not counted (not reported by the API). The engine itself still uses `complete`.
