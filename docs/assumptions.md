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

## Playable app (task 11)

47. **Stack.** Starlette + uvicorn, SSE for the stream, POSTs for actions, plain JS (recorded in `docs/tools.md`). Only packages from the locked nixpkgs; `flake.nix` gained `starlette`, `uvicorn`, `playwright` and the Playwright browsers.
48. **No engine changes.** The engine streams NPC words through `on_word`, but narration is only returned after the turn. The app gets narration by wrapping the engine instance's `log.append` for the duration of a turn: when the NARRATION event is written, its text is streamed word by word from the turn thread. This relies on the narration being written before the NPC lines (true today) and on `Engine._event` going through `self.log.append`. If task 9's parallel turn changes that order, only `Game._run` in `app/game.py` needs adjusting.
49. **Narration interrupt.** The engine only has a live interrupt for NPC speech. Pressing the button during narration stops the display of the narration (the rest is "never said" for the player) but does not touch the engine: the full narration stays in the event log, so facts from the unseen tail can still be stored. Making the engine treat a narration cut like an NPC cut is not decided.
50. **Pace.** Default 0.25 s per word (about 4 words a second), set by `--pace`. The pacing is done by the app, not by `Engine.pace` (kept at 0), so it can wait while the page is in the background.
51. **Background.** The client reports page visibility; the server holds the stream while the last report says hidden. With two clients open (phone and laptop) the last report wins. A phone that sleeps without reporting leaves the stream waiting until it reports visible again. Turn-based time only; flowing time is not built.
52. **Language.** Until task 9's output-language setting exists, `app/campaigns.py: Recorder` appends a "write in Ukrainian" line to the narrator and NPC system prompts. Records, extractor facts and judgment questions are untouched, so the player's panel prose (taken from known facts) can contain English engine sentences, e.g. the interruption fact ("Рагнар interrupted Ельза after 4 words ..."). Remove the Recorder hint after task 9.
53. **Panel prose.** "A few sentences" are the last four facts the player character knows, as stored. No LLM call. Near-duplicate facts show up as near-duplicate sentences (seen in the live check). A proper summary is a later feature.
54. **Panel content.** Chips are the player's live state (own body is perceived, so hidden elements are shown with an empty dot, "known only to you"); NPC-only facts cannot appear because the panel is read from the player's own derived memory.
55. **Storage.** One function, `app.campaigns.open_campaign`, builds a fresh in-memory campaign (SQLite `:memory:` with `check_same_thread=False`; the app guarantees one thread uses it at a time, and the panel and debug data are cached snapshots). The transcript lives in the server process, so a server restart starts a new game. "Continue" works across page reloads and phone/laptop switches, not across restarts, until task 9's file-backed campaigns are plugged in.
56. **Models for `--live`.** Defaults are the task 7 choices (`gpt-6-luna` narrator, NPC and escalation judge; `deepseek-v4.1-flash-1017` extractor). The first judge is still Jev 1.14, because `liquid/d1-ultra` needs task 9's decision client. Until task 9's price-based policy is merged, `harness/policy.py` still has the old allowlist, so `--live` needs `HARNESS_EXTRA_ALLOWED=openai/gpt-6-luna,deepseek/deepseek-v4.1-flash-1017`.
57. **Scene.** Reuses the prototype's names (Горст, Ельза, Корчма «Вовче Гніздо»). The player's character description is the first plain paragraph of `data/Ragnar.md` (first 300 characters) if the file exists, else a placeholder. The file is read at campaign start and never written or copied.
58. **Network.** Default bind is 127.0.0.1:8765. For the phone, `--host 0.0.0.0` and TCP 8765 must be allowed from the LAN in the firewall (not done here). There is no authentication: anyone on the LAN who can reach the port can play and see the debug view.
59. **Errors.** A failed model call rolls the turn back in the engine; the app shows a message and restores the player's text into the input. The message names the HTTP status or exception class, never keys.

## Record language experiment (task 10)

- **T10-1. Temperature.** The engine sets no temperature; runs used the experiment client's default 0.7 and reasoning off (retry with low effort on HTTP 400), as in task 7.
- **T10-2. Language line.** The added output-language line is Ukrainian and sits in the system message of narrator and NPC prompts ("Відповідай українською мовою..."). The extractor gets "facts in English" or "facts in Ukrainian" appended to the user message. The template scaffolding (field labels, JSON schema) stays English in all variants, as in task 7; only the context content changes language.
- **T10-3. English variant details.** Hand-translated by the agent. Latin names (Ragnar, Vesemir, Jaskier...), English profiles, English times ("Day 3, 19:00"). The player's lines and the player-facing "The player does/says" line stay Ukrainian. Roles are Guard, Merchant, Smith, Girl.
- **T10-4. Third variant added.** EN+UKNAMES (English text, Ukrainian names/places/titles) was added after the first grading showed mangled names; it has 3 samples (narrator) and 2 (NPC) and was graded in a separate batch, so it is not blind to the variant (only to the model). The brief asked for two variants; this is an addition within budget.
- **T10-5. Grading.** One grader (the Claude Code agent). Scales as in task 7; leaks count invented specifics and, for the Philippa item, any asserted trait or scheme beyond "powerful sorceress, mentor". Leak rates are therefore higher than in task 7 and only comparable across variants. Flags: ru = calque, Russianism or wrong grammatical form; en = Latin letters, English words or mangled names in the Ukrainian text; pc = narrator decides the player character's actions/feelings or makes a scene error (including "гравець" meta-words); x = foreign-script fragment.
- **T10-6. Extractor input.** Passages and the current-state list stay Ukrainian in both variants (they are player/narrator text); only the language of the output facts differs. State-item language was not constrained, which is what produced the mixed items.
- **T10-7. Fixed gold from task 7** was reused for extractor scoring. Recall is over facts plus state changes; precision is over emitted facts only.
- **T10-8. Report file.** The brief asks for `reports/language/SUMMARY.md`; the session's file tool refused to write a report file, so the report text is in the worker's final message and must be saved by the lead.

## Engine on the chosen models (task 9)

60. **Defaults.** Narrator and NPC `openai/gpt-6-luna`, extractor `deepseek/deepseek-v4.1-flash-1017`, first judge `liquid/d1-ultra`, escalation `openai/gpt-6-luna`; fallbacks per role as in `docs/tools.md` (extractor fallback `qwen/qwen3.8-omni-flash`, first-judge fallback `perplexity/pplx-decider-v1.2`). The fallback applies when a call raises `ProviderError` (after the client's retries) or, for the decider, `JudgeError`; JSON/format failures are not a reason to switch models. `ModelConfig()` keeps its old placeholder names for tests; `ModelConfig.live()` gives the real ones.
61. **Price rule.** Worst-case price counts: the base price or any surcharge tier ("overrides") in the catalog, whichever is higher. Variable (negative) prices are refused. A model not in the catalog is refused. `:free` models pass at price 0. Anthropic = id contains `anthropic/` or `claude`. Deny list: OpenRouter routers (`openrouter/auto` and kin) plus `HARNESS_DENY` (comma-separated). `HARNESS_EXTRA_ALLOWED` is removed (the rule replaces it). The decision client accepts only the explicit decision list. The cache lives in `.cache/openrouter_models.json` (git-ignored; override with `HARNESS_CACHE_DIR`); the catalog endpoint is public, so the fetch sends no key. If a refresh fails the older cache is used; with no cache the model is refused.
62. **Parallel plan, as built.** After the narrator: its speech check and each NPC chain (line, then check) start together; the extractor does NOT run beside them. It needs what was actually said (an interrupted line is cut), so it runs once, after delivery. The task 7 timing script also ran an extractor in the first wave, but its wall time equals narrator + longest chain + extractor, which one post-delivery extractor reproduces; two extractor calls would only cost more. After extraction the salience and attitude judgments run as one concurrent wave. NPC chains start speculatively on the candidate narration; if the speech check then rejects it, the provisional narration/action events are rolled back, the chains are dropped (their spend is lost) and the narrator is called again.
63. **Consequence of parallel NPC chains.** Two NPCs speaking in one turn no longer see each other's line from that turn (both are generated before either is delivered). Sequential mode still does. Fake providers run sequentially (`parallel_ok` is False) so scripted tests stay deterministic; `Engine(parallel=...)` overrides. Not measured: how much this hurts dialogue quality. In the live smoke run the second speaker's lines stayed coherent with the scene but did not answer the first NPC's line of the same turn.
64. **Deterministic logs.** Workers do no database access and write no logs of their own: notes and judgments are collected per worker and merged by the main thread in a fixed order (speech check, then NPCs in narrator order). Salience judgments for state changes are now asked after all state changes of the diff are applied (one wave), not interleaved per change; the result is the same in both modes.
65. **NPC output check.** Suspicion = the decider's probability for "yes" (the claim is unknowable). Reject at p >= 0.7 (`Engine(npc_reject_p=...)`, `settings.NPC_REJECT_P`). If no judge answers, the line is accepted (as before). `FALLBACK_LINE` is kept as a constant but is no longer shown. Ties between candidates go to the earliest.
66. **Languages.** Output language default Ukrainian is an instruction appended to the narrator prompt ("Write the description and the observable actions in X") and the NPC prompt ("Speak in X."). Observable actions are player-facing, so they follow the output language. Record language default is None = no instruction (what the extractor writes now: mixed Ukrainian and English in the live run); setting it adds one sentence to the extractor prompt. Judgment questions stay English. Both live in `harness/settings.py` and as `Engine` arguments, and are stored with a saved campaign.
67. **Saved campaigns.** One database per campaign, `campaigns/<name>/campaign.db`; the scene (location, present, outside, time), characters and settings are stored in a `campaign_meta` table and rewritten whenever the scene changes (`refresh_memory`, `advance_offscreen`). Everything else (events, facts, live state, agents, intents, attitudes) is derived from the log. Models, judge and provider are not stored; they are passed on open. Connections for campaigns are opened with `check_same_thread=False` so a server can use them; the caller must serialise turns. `synchronous=NORMAL` with WAL.
68. **Decision-model backend label.** Judgments from a hosted decider now carry the model id as `backend` (was `"jev"`), so the debug view shows which decider answered, including after a fallback.
69. **Stream usage.** `OpenRouterProvider.stream` adds the final chunk's usage to `Spend` once; if a stream breaks, usage is not counted (not reported by the API). The engine itself still uses `complete`.

## Canon ingestion pilot (task 13)

- **T13-1. Arc boundaries.** File lines 7-694: frame chapter "Голос розуму-1" (7-17) and the story "Відьмак" (19-694). The last lines (Velerad at the bedside) belong to the story; "Голос розуму-2" starts at 695 and is excluded. Footnote markers like `[1]` stay in the passage text.
- **T13-2. Schema subset.** Implemented: canon_meta, canon_source, canon_passage (+FTS5), canon_event (+FTS5 over body and quote), canon_participant, canon_knower, canon_reaction, canon_vocab, canon_evidence, canon_relation (only `member_of`), entity, record. Not implemented: canon_embedding, canon_pivot, canon_rule, review workflow. Additions to design/canon.sql: `canon_knower.learned_t/learned_prec/learned_line` (when and where a holder learns a past event; needed for "as of" filtering), `canon_event.day/part/quote/lines/local_id`, `canon_passage.line_from/line_to`, `canon_character` (profile: who, role, standing, knows) and `canon_alias`. FTS tables are not contentless in the pilot so text can be inspected.
- **T13-3. Closed vocabularies.** 27 reactions (`harness/canon/vocab.py`), 9 channels (the `knowledge.channel` list), 18 event kinds, 4 attitudes. The extractor chooses reactions from the list inside the same call; the separate "map free text to the vocabulary with a choice judgment" step of design/canon.sql section 7.2 was skipped in the pilot (items outside the list are dropped and counted).
- **T13-4. Record language.** Event text is asked in English with Ukrainian names (task 10 result). Models drift: several wrote Ukrainian or translated place names. v2 prompt repeats the rule.
- **T13-5. Story time.** Day 1 = arrival, minutes from day 1 00:00; past events negative (years_before x 525600); unknown carries the last known time forward with `t_prec='unknown'`. The text gives no absolute dates. The fight night is "after the full moon", four days after day 2, so day 6 or 7 are both accepted as correct.
- **T13-6. Placement of the fight.** The text says "до повного місяця ще чотири дні. Після повні." and the strzyga is "наїдена після останньої повні"; read as the night after the full moon. Not certain.
- **T13-7. Evidence.** Events cite paragraph (line) numbers; the passage containing the line becomes `canon_evidence`. Each event carries one verbatim Ukrainian quote of at most 15 words; code checks it is a substring of the arc (normalised for quotes, dashes and case). A failing quote is a cheap, mechanical hallucination signal.
- **T13-8. Retrieval is filtered at the event level.** `Canon.recall(holder, query, as_of)` returns only canon events with a knower row for the holder or a collective the holder belongs to, learned at or before `as_of`. Raw passages are never returned to a character (`passages_unfiltered` exists for narrator and judgments and is named so). A knower row for a past event learned in conversation gets the time of the telling, derived from the story day of the nearest day-timed event at or before the knower's line, unless the model gave one.
- **T13-9. Ragnar and Geralt.** The chronicle makes Geralt and Ragnar the same age (born 1174, both 18 in 1193) and brothers in arms, while the book's Geralt is an experienced witcher with a reputation. The pilot does not resolve this; the starting situations treat Geralt as the same person and leave his age open. Ragnar's chronicle also says the adult mind of a former reader sits in him, so he may know the plot; whether he does is the player's choice (decisions: only the player decides what the character knows and believes).
- **T13-10. Cost.** The two v2 runs, v1 runs and replays together stay under the 0.60 USD budget (see the report for the exact figure). Replays from saved raw replies cost nothing.

## App on the new engine, prose narration, glossary (task 12)

70. **Prose is the default.** `Engine(narration="prose")`: narrator and NPC calls return plain text. The task 3 JSON narrator stays as `narration="json"` (tests, comparison). The `app` uses prose. The prompt asks for no JSON, no lists, no fixed pattern, and (after the live run) no quotation marks and no dialogue dashes.
71. **Scene director** (`harness/director.py`, `Engine.direct`). Speakers: ONE batched decider call: a choice over the present NPCs plus "nobody", and one yes/no "would X also speak" per other NPC; order = first choice, then the yeses by probability; at most `max_speakers` (2). If the decider fails the NPCs named in the narration speak (else the first NPC), noted as `director_unavailable`. Observable actions: one cheap LLM call (the extractor role, plain lines, "none" allowed), run concurrently with the decider and the speech check; its sentences are written in the record language. `speakers=` on `turn` overrides the decider.
72. **First-speaker wording.** The first wording ("...or nobody if the moment calls for silence") picked the wrong speaker in 7 of 27 prose narrations (Lambert for Vesemir, nobody for the innkeeper). The wording now used ("answering the player or reacting to the narration... nobody only if no one at all would say anything") got 23 of 27 on the same set (`experiments/prose/director_acc.py`, expected speakers from the task 7 notes). Remaining misses: the innkeeper in n02 (narration ends before the reply) and one Vesemir/Lambert swap.
73. **NPCs hear each other.** In the parallel turn each NPC chain waits for the lines of the NPCs before it (generated and checked, not yet delivered) and gets them under "Recent conversation"; the output check knows them too. If an earlier line is then cut by an interruption, later speakers never speak anyway. `Engine(hear_each_other=False)` restores the task 9 all-at-once behaviour. Sequential (fake provider) mode always had this. Only speech is heard: everyone `present` hears everyone (perception model unchanged).
74. **Narration hook.** `Engine.turn(on_narration=...)` is called once, with the accepted narration, before the first NPC word (a rejected speculative narration is never announced). `EventLog.subscribe(fn)` replaces the app's `log.append` monkeypatch for the debug event list.
75. **Dialogue-dash speech.** Ukrainian prose writes speech as "— Текст, — каже вона." Neither the quote heuristic nor the d1-ultra speech check caught it in the first live session (2 of 15 narrations carried NPC speech this way). Code now treats a sentence that starts with a dash and a capital letter as speech: rejected and regenerated, stripped as a last resort (`has_dash_speech`). A narration with a mid-sentence dash ("дощ — ніби плаче") is not flagged.
76. **Repetition metric** (`harness/repetition.py`): per output, against the last 8 outputs: share of repeated word trigrams, share of sentences whose first two words were seen before, share of earlier outputs of the same kind with the same paragraph shape (paragraphs, sentences, average sentence length / 5); `score` = mean; up to three quoted examples. Logged per turn (`Engine.reports`, debug view). Measures surface repetition only; the same advice in other words does not register. No regeneration.
77. **Glossary** (`harness/glossary.py`, `worlds/witcher/glossary.json`). Entries: canonical form, Latin forms (replaced whole, case-insensitive, "Horst's" keeps the "'s"), wrong Cyrillic stems (a case ending after them is kept), optional declension stem. Applied (a) to the extractor's parsed JSON (facts, state items; so also to JSON that escapes Cyrillic), (b) to observable actions, (c) to narration and NPC lines before they are stored or shown, (d) to every rendered context, narrator, NPC, extractor, director, with a "use these forms" line listing only the names that occur. Player text is never touched. Forms were checked against the Ukrainian translation in `data/witcher_books.txt` by counting: Ґеральт, Цірі, Йеннефер, Любисток, Трісс, Коен, Нільфгард, Марібор, Каер Морен (not Морхен), Мільва. The task 7/10 test sets use Тріс, Койон, Каер Морхен; those are listed as wrong forms. Горст, Ельза, Брідки, Гостомил, Вернон Роше are not in the books (our names). Generic words ("witcher") and a name's every declension are not handled; unknown distortions are only counted (`near_misses`: a heuristic that also flags legitimate forms such as Горстова, Брідок).
78. **Record language** default is now English (`settings.DEFAULT_RECORD_LANGUAGE`), the extractor is told "state items in English too, names stay Ukrainian". The app's seed facts are English with Ukrainian names. The player's panel (chips, prose) is translated for display by one cheap batched call, cached in the campaign folder (`translations.json`), best-effort.
79. **Fallback on English context: gap recorded.** Rendering the whole context in Ukrainian for deepseek would need every English record translated (an LLM call per fact, or a second extractor field) and is not cheap. Not done. Mitigation in place: Ukrainian names via the glossary (task 10: that recovered most of the loss). Fallback use is already noted as `model_fallback` in the debug notes.
80. **Extractor sources.** With the Ukrainian-names instruction the extractor answered `source: "Ельза"` instead of the id `elza`, which rejected 14 of 15 live turns in the first session. Names are now mapped back to ids before validation. A separate failure remains: an invented state change ("reveal inventory 'steel sword'" when the sword is equipment) rejects the whole turn after one retry (seen once in 30 turns). Not changed here.
81. **App.** `open_campaign(stack, root, new)`: the pointer `campaigns/current.txt` names the campaign a restart continues; "new campaign" creates `inn-<timestamp>` and keeps the old one. The transcript of a reopened campaign is rebuilt from the log (narration the player cut short is shown in full). The Recorder reports `parallel_ok` of the provider it wraps, so the app now runs the parallel turn (it did not under task 11's wrapper). `HARNESS_EXTRA_ALLOWED` and the language hint are gone.
82. **Prose vs JSON narrator** (`experiments/prose/`, luna, 3 samples x 9 items, EN+UKNAMES contexts, blind-graded by the agent): see the report. Grades are mine, the key was read after grading; the prose outputs are longer and multi-paragraph, so the grader could often tell the variants apart.

## Sapkowski style (task 15)

Numbered T15-n so they do not collide with task 14's numbering.

- **T15-1. Where it lives.** `harness/style.py` (wording, sheet loader, exemplar index, NPC beat parser, manner notes, assistant-ism detector); `worlds/witcher/style.md` (the sheet, read by `## section`); `ContextBuilder(style=...)` and `Engine(style=...)` call it. `style=None` keeps the task 12 prompts exactly (tests rely on it). The app turns it on (`Style.load("witcher")`).
- **T15-2. NPC beats.** With a style, an NPC writes book-form dialogue (dash, own beats between dashes). `split_npc_output` splits a text on ` — ` and alternates speech / beat inside a paragraph that starts with a dash; a paragraph that starts without a dash begins with a beat; a text with no dash at all is plain speech (old form). A piece over 40 words is never a beat. Bare speech tags ("каже Горст") are dropped, other beats kept. Known weak spot: a dash used inside a speech ("Млин — ось він") shifts the alternation; mitigated only by the 40-word rule.
- **T15-3. Storage.** The utterance stores the whole text as delivered (needed for display and interruption points) plus `payload["speech"]` (speech only) when dashes were used. Each beat becomes an ACTION event by that NPC (`payload.by`), witnessed by everyone present, `cause_id` = the utterance, so rollback and interruption remove them with it; only beats in the *delivered* part exist. `ContextBuilder._line` prints `speech`, so a gesture is seen once (as "[you see] Горст ...") and not twice.
- **T15-4. Other people's voices.** `foreign_voice`: a `Name:` script line, or a beat that begins with another character's name, rejects the NPC output (regenerated like a failed knowledge check, noted as `npc_line_rejected` with `why`). It does not catch an NPC deciding what the player says inside its own speech ("ти кивнув") nor a beat that names the player later in the sentence; both seen in the bake-off (2 of 360). The narrator checks are unchanged: narration with dash speech is still rejected (`has_dash_speech`), tests cover both directions. The narrator prompt now says gestures during speech belong to the NPC call.
- **T15-5. Manner notes.** One cheap-model call (the extractor role) per NPC profile that has none, made on first use in `_prep_npc` (main thread), stored in `CharacterProfile.manner` and in the saved setup (profiles are saved as 4-tuples; old saves with 3 load fine). On failure the manner is "-" and is not retried. English notes (record language).
- **T15-6. Exemplars.** Runtime only: `data/witcher_books.txt` is found through `HARNESS_BOOKS`, the checkout's `data/`, or the main checkout's `data/` (a worktree has none). Index built in about 0.8 s on first use, 2801 dialogue passages and 1392 speechless prose paragraphs. Passages with several named people are penalised (canon names would leak). **Default off** (`Style(exemplars=False)`): the bake-off showed no measurable gain over the sheet alone (T15 report), at +670 input tokens per NPC call.
- **T15-7. Mistakes in the Ukrainian translation corpus.** The book text contains typos ("усміхнуся", "Заплачу'"); exemplars are used verbatim.
- **T15-8. Dialect words.** The first version of the sheet listed "тутки, тама, ото"; every model then put "ото" into every line. The sheet now asks for a word or two of local speech per speech. Remaining tic in the bake-off: the repeated manner phrase ("справедлива міра", "поганий протяг", "bad for business") across samples of the same NPC; manner notes with a quoted catchphrase should be avoided (the manner prompt does not forbid it yet).
- **T15-9. Bake-off contexts.** The task 7 NPC sets are Ukrainian records; the inn scenes use the app's English seed records with Ukrainian names. The old variant is the engine prompt before this task (same context code, `style=None`). Grading: me, blind, shuffled packets, key read after grading; 360 NPC outputs (10 situations x 3 variants x 4 models x 3 samples), 54 narrator outputs. Differences under about 0.3 are noise.
- **T15-10. Manner notes must not quote.** The first manner prompt let the model quote catchphrases in English ("fair measure", "cash first", "bad for business"); luna then put those English phrases into 4 of 18 Ukrainian lines and repeated one catchphrase in 2 of 18. The prompt now forbids quoting; a re-run of 18 luna outputs (6 situations x 3, `raw/npc2.jsonl`, not graded) had 1 of 18 with Latin text and 0 repeated catchphrases. The graded bake-off tables use the first version of the notes, so they understate luna's Ukrainian a little.
