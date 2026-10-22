# Character Portraits Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Important NPCs behave from a portrait (core paradox, stances by relationship × situation, switches, hidden layer with leaks, voice rules, own example lines), so cheap models stop guessing who the character is. Yennefer in Rinde is playable early.

**Architecture:**
- `harness/portrait.py` loads YAML portraits and turns them into a slice of about 250 words for one NPC call, choosing the stance in code.
- `harness/relations.py` keeps the NPC→player relationship (ladder rung, warmth, trust) as events in the log. Switches move it on the slow lane through typed judge questions.
- The NPC prompt, the director and the outcome judge read the slice or relationship line instead of the model guessing.

**Tech Stack:** Python 3 (nix dev shell), PyYAML 6.0.3 (already in the shell), SQLite event log, pytest with fake providers, Playwright `app/tests/ui_check.py`.

**Spec:** `docs/superpowers/specs/2026-10-22-character-portraits-design.md` (approved 2026-10-22). Research: `reports/research/characters_yennefer.md`, `reports/research/characters_methods.md`.

## Global Constraints

- **Cheap models only.** NPCs on `xiaomi/mimo-v2.6-flash` (harness/policy.py). No new paid model.
- **Slice size:** at most 260 words per NPC call. The whole portrait never goes into a prompt.
- **No new model call on the fast lane.** Stance selection is code. Relationship updates run on the slow lane.
- **Knowledge stays the knowledge layer's job.** The slice passes through `ctx.mask(character, …)`, and a portrait never adds facts the NPC has not learned (names are knowledge).
- **Portraits are for NPCs only.** The player's character sheet is unchanged.
- **Never commit `data/`, `campaigns/` or `.env`.** No book excerpts beyond a few words. Portraits and example lines are our own paraphrase.
- **Canon names as in the glossary:** Йеннефер (never «Єніфер»), Ґеральт, Рінде, Визім.
- **Paid API calls** happen only in the live checks named in a task, under the budget that task states. The key is in `/home/cock/projects/harness/.env` (`load_dotenv`), and it is never printed.
- **Tests run with fake providers:**
  - `nix develop --command pytest -q` must exit 0, with the real exit code captured;
  - UI changes also need `nix develop --command python app/tests/ui_check.py`;
  - when a prompt change breaks `tests/test_eval_sessions.py`, re-record with `nix develop --command python -m harness.evalkit.record_fake`.
- **Commit messages end with:**
  `Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>`
  `Claude-Session: https://claude.ai/code/session_01CWLHKUxozeDSLq8FyEpMnW`

## Review Focus

1. **NPC without a portrait:** prompt and behaviour are unchanged. `core` and `manner` are used as today. Pinned in Task 2.
2. **Rolled-back cause:** after «Помилка моделі» or a challenge rolls back the line that moved a relationship, the relationship returns to its earlier state, because relation events are caused by the turn's event. Pinned in Task 4.
3. **Restart:** the relationship state and the portrait binding survive `open_campaign` / reopen of a package game. Pinned in Tasks 2 and 3.
4. **Names in the slice:** a name in the portrait that this NPC has not learned (for example the player's name in an example line) is masked, and an example line never leaks the player's real name. Pinned in Task 1 (slice) and Task 2 (masked in `character_view`).
5. **Example lines copied into play:** a reply sharing 6 or more consecutive words with an example line is logged as `portrait_copy`. It is not blocked. Pinned in Task 2.

---

### Task 1: Portrait schema, loader and slice

**Files:**
- Create: `harness/portrait.py`
- Create: `worlds/witcher/portraits/README.md` (the schema, short, for portrait writers)
- Test: `tests/test_portrait.py`

**Interfaces:**
- Produces:
  - `RUNGS = ("stranger", "client", "ally", "close", "lover", "rival", "enemy", "subordinate")`
  - `@dataclass(frozen=True) class Situation: power: str  # "self"|"other"|"even"; audience: bool; stakes: str  # "low"|"high"|"mortal"`
  - `@dataclass(frozen=True) class Stance: id: str; rung: tuple[str, ...]; when: dict  # optional keys power/audience/stakes; does: str; sounds: str; tail: str = ""; examples: tuple[str, ...] = ()`
  - `@dataclass(frozen=True) class Switch: id: str; trigger: str  # an English yes/no question about what the player just did; warmth: float; trust: float; note: str = ""`
  - `@dataclass(frozen=True) class Portrait: id: str; character: str  # profile id; name: str; phase: str; core: str; stances: tuple[Stance, ...]; switches: tuple[Switch, ...]; hidden: str; leaks: tuple[str, ...]; voice: str; never: str; relations: dict[str, str]  # other character id -> rung (static NPC->NPC)`
  - `load_portrait(path: Path) -> Portrait` raises `PortraitError(path, field, problem)` on schema errors
  - `load_world_portraits(world: str) -> dict[str, Portrait]`, keyed by portrait id, from `worlds/<world>/portraits/*.yaml`
  - `select_stance(p: Portrait, rung: str, sit: Situation) -> Stance`: the first stance whose `rung` contains `rung` and whose `when` keys all match `sit`. Otherwise the first stance for that rung with no `when`. Otherwise the nearest rung by ladder order (`stranger < client < ally < close < lover`; `rival`/`enemy`/`subordinate` fall back to `stranger`).
  - `slice_text(p: Portrait, stance: Stance, leak: str | None) -> str`: core, the stance's does/sounds/tail, at most 2 of its examples, voice, never, and the leak line if given. Hard cap 260 words, trimmed in this order: examples, tail, leak.

- [ ] **Step 1: Write the failing tests** in `tests/test_portrait.py`:
  - `test_load_valid_portrait` (a tmp YAML with all fields loads; `stances[0].rung == ("stranger",)`);
  - `test_missing_core_is_a_portrait_error` (`PortraitError.field == "core"`);
  - `test_select_stance_prefers_matching_situation` (two stranger stances, one with `when: {audience: true}`: `Situation("self", True, "low")` gets it, `Situation("self", False, "low")` gets the other);
  - `test_select_stance_falls_back_down_the_ladder` (a portrait with only stranger and close stances: rung `ally` gets the stranger stance, rung `lover` gets close);
  - `test_slice_is_capped_and_trims_examples_first` (a portrait with a 300-word stance: `len(slice_text(...).split()) <= 260` and the examples are gone);
  - `test_slice_contains_leak_only_when_given`.
- [ ] **Step 2: Run** `nix develop --command pytest -q tests/test_portrait.py`. Expected: FAIL with `ModuleNotFoundError: harness.portrait`.
- [ ] **Step 3: Implement** `harness/portrait.py` with `yaml.safe_load`, and write the schema README with one minimal example (an invented character, not a canon one).
- [ ] **Step 4: Run** `nix develop --command pytest -q tests/test_portrait.py`. Expected: PASS. Then run the full suite, exit 0.
- [ ] **Step 5: Commit** `harness/portrait.py worlds/witcher/portraits/README.md tests/test_portrait.py`.

### Task 2: Portraits in the NPC prompt, and a playable Yennefer in Rinde

**Files:**
- Modify:
  - `harness/models.py` (`CharacterProfile.portrait: str = ""`, a portrait id);
  - `harness/context.py` (`character_view`; `ContextBuilder.portraits: dict[str, Portrait]`; `ContextBuilder.portrait_section(character, scene) -> str`);
  - `harness/pipeline.py` (engine loads `load_world_portraits(world)` when a world is set, passes them to the context, keeps the binding in campaign settings);
  - `harness/stylehits.py` or `harness/portrait.py` (`copy_overlap(line, examples, n=6) -> bool`);
  - `app/newgame.py` (person key `portrait`, validated against the world's portraits, with a Ukrainian Issue on an unknown id);
  - `app/static/app.js` and `app/server.py` (the new-game sheet lists bundled packages, GET `/api/packages` returning `[{id, title, pitch}]` from `worlds/witcher/packages/*.yaml`; a tap fills the text box);
  - `docs/new_game_instruction.md` (the `portrait` person field, one line);
- Create:
  - `worlds/witcher/portraits/yennefer_rinde.yaml`;
  - `worlds/witcher/packages/yennefer_rinde.yaml` (free start in Rinde: the room Yennefer rents in a merchant's house, the player a stranger come to ask for help; `who_is_here` has Йеннефер with `portrait: yennefer_rinde`, `knows_player: false`; `canon: loose`);
- Test: `tests/test_portrait_context.py`, `app/tests/test_newgame.py`, `app/tests/ui_check.py`.

**Interfaces:**
- Consumes: Task 1 (`Portrait`, `select_stance`, `slice_text`, `Situation`, `load_world_portraits`).
- Produces:
  - `ContextBuilder.portrait_section(character: str, scene: Scene) -> str` (empty when the profile has no portrait);
  - `ContextBuilder.rung_of(character: str) -> str` (Task 2 returns the package or static seed, else `"stranger"`; Task 3 replaces the body with the relations store);
  - `ContextBuilder.situation(character: str, scene: Scene) -> Situation` (power `"even"` unless outcome or state says otherwise; `audience` = anyone present besides the NPC and the player; stakes `"low"` unless the turn's outcome is mortal or the scene state says danger);
  - a devlog note `portrait_copy` with `npc` and `line`.

- [ ] **Step 1: Write the failing tests.**
  - `test_portrait_replaces_core_and_manner` (an NPC with `portrait` set: the system and sections contain the stance's `does` text, and not the profile's `core` line «Who you are (fixed…)»);
  - `test_npc_without_portrait_is_unchanged` (the prompt is byte-equal to the same view built with no portraits loaded);
  - `test_slice_is_masked_for_the_npc` (an example line containing the player's name «Рагнар», which the NPC does not know, is masked in the prompt);
  - `test_copy_overlap_logged` (a fake NPC reply that repeats 6 words of an example line gives a `portrait_copy` note);
  - `test_portrait_binding_survives_reopen`;
  - `test_package_person_portrait_unknown_id` (Ukrainian Issue, field `who_is_here[0].portrait`);
  - `test_bundled_packages_listed` (`/api/packages` includes `yennefer_rinde` with a Ukrainian title).
  - ui_check: the new-game sheet shows the bundled list; tapping «Йеннефер у Рінде» fills the box; the summary card shows Йеннефер.
- [ ] **Step 2: Run** these tests. Expected: FAIL (no `portrait` field, no `/api/packages`).
- [ ] **Step 3: Implement** the code above. In `character_view`, when a portrait exists, `portrait_section` replaces `core_text` and the style `manner` notes. Everything else stays. The NPC system prompt keeps the style sheet and limits.
- [ ] **Step 4: Write the Yennefer Rinde portrait** from `reports/research/characters_yennefer.md` (§3) and the local book. It is agent work, no API calls.
  - Core paradox.
  - Stances for every rung (stranger: test → bargain; client; ally; close; lover; rival/enemy: cold fury with politeness), fitted to the Rinde phase. She is not used to closeness, wants a cure for infertility, uses people and trusts no one.
  - 6–8 switches from §3.2: warm-ups (unpaid attention to her need, sincerity for sincerity, courage without flattery, shared laugh at a third, someone helpless nearby) and setbacks (pity, flattery or pathos, pressure, touching her wound, the word «мутант» about someone she cares for). Each has a yes/no `trigger` question and warmth/trust deltas in [-0.5, 0.5].
  - Hidden: infertility, origin, loneliness. Leaks: an address-form change, lines dropping to 1–2 words, a secret act of care, the star pendant gesture.
  - Voice from §3.3: median about 15 words; politeness as a weapon in cold anger; one-word apologies; test questions about concrete things; at most one signature per line. Never: names her wound, begs, explains herself, looks up only from papers.
  - 2 own example lines per main stance. Only a few words may echo the book.
- [ ] **Step 5: Run** the full suite (exit 0) and ui_check (exit 0).
- [ ] **Step 6: Live check, budget $0.05:** start the bundled Yennefer package in a temp campaign dir under the scratchpad, play 4 turns, save the transcript to the scratchpad. Report: whether she stays in a stranger stance, any `portrait_copy`, whether any line names her wound, first-word time. Do not grade prose; the user does that in play.
- [ ] **Step 7: Commit** the files above plus regenerated screenshots, with explicit paths.

### Task 3: Relationship state, and judges that see it

**Files:**
- Create: `harness/relations.py`
- Modify:
  - `harness/models.py` (`RELATION = "relation"` event type);
  - `harness/context.py` (`rung_of` reads `Relations`; `director_state` adds a line per present portrait NPC);
  - `harness/outcome.py` (`OutcomeJudge._context` adds the same lines);
  - `harness/pipeline.py` (seeding at campaign creation: from a package person's `attitude`/`knows_player`, mapped to `stranger` or `client`/`ally`; from a portrait's `relations` for NPC→NPC);
- Test: `tests/test_relations.py`

**Interfaces:**
- Consumes: Task 1 `RUNGS`; Task 2 `ContextBuilder.rung_of`, `situation`.
- Produces:
  - `@dataclass(frozen=True) class Relationship: npc: str; other: str; rung: str; warmth: float  # -1..1; trust: float  # 0..1; reason: str; event_id: int | None`
  - `class Relations: __init__(log: EventLog); get(npc, other) -> Relationship` (default `stranger`, 0.0, 0.2, "", None); `set(npc, other, rung, warmth, trust, reason, scene, cause_id: int | None) -> Event`, logged as a RELATION event caused by `cause_id`, so a rollback of the cause reverts it;
  - `ContextBuilder.relation_line(npc: str) -> str`: `"Йеннефер → the player: stranger, warmth -0.2, trust 0.2; stance: test"`, with the NPC's name as the omniscient judges see it.

- [ ] **Step 1: Write the failing tests.**
  - `test_default_relationship_is_stranger`;
  - `test_set_and_get_latest`;
  - `test_rollback_of_cause_reverts_relationship` (Review Focus 2: set with `cause_id`=an utterance id, `log.rollback(id)`, `get` returns the previous state);
  - `test_survives_reopen` (Review Focus 3);
  - `test_package_attitude_seeds_rung` (`knows_player: true` with a friendly attitude seeds `ally`; an absent attitude seeds `stranger`);
  - `test_director_and_outcome_see_relation_line` (on a fake stack, the prompts sent to the judge contain `relation_line`).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code above. The relation line goes only to judges and the NPC itself, never to the narrator or player-facing text.
- [ ] **Step 4: Run** the full suite. Expected: exit 0. If `test_eval_sessions` breaks, re-record the eval cassettes.
- [ ] **Step 5: Commit.**

### Task 4: Switches move the relationship; leaks are rationed

**Files:**
- Modify:
  - `harness/pipeline.py` (slow lane, after the existing post-turn judgments: one batched `judge.ask` per present portrait NPC that the player interacted with this turn, one yes/no per switch `trigger`, sent with the turn's dialogue as context);
  - `harness/relations.py` (`apply(rel, switches_hit) -> Relationship`, with ladder thresholds);
  - `harness/context.py` (`portrait_section` passes a leak only when `trust >= 0.4` and no leak was used for this NPC in the current scene, tracked by a `portrait_leak` devlog note keyed by scene entry);
- Test: `tests/test_switches.py`

**Interfaces:**
- Consumes: Task 3 `Relations`, `Relationship`; Task 1 `Switch`.
- Produces:
  - `apply(rel: Relationship, hits: Sequence[Switch]) -> Relationship`. It sums deltas, clamps warmth to [-1, 1] and trust to [0, 1], and moves the rung:
    - `stranger → client` at trust ≥ 0.3;
    - `client → ally` at warmth ≥ 0.3 and trust ≥ 0.45;
    - `ally → close` at warmth ≥ 0.6 and trust ≥ 0.65;
    - `close → lover` at warmth ≥ 0.85 and trust ≥ 0.8;
    - down one rung when warmth falls below the rung's entry warmth − 0.3;
    - to `enemy` at warmth ≤ −0.7.

    `reason` lists the switch ids.
  - Devlog `relation_changed` with npc, from, to and switch ids.

- [ ] **Step 1: Write the failing tests.**
  - `test_apply_clamps_and_climbs` (a sequence of warm-up hits climbs stranger→client→ally, never skipping a rung in one turn);
  - `test_setback_drops_a_rung`;
  - `test_enemy_threshold`;
  - `test_switch_batch_runs_on_slow_lane_only` (with fakes, the fast lane's first output happens before any switch question is asked);
  - `test_leak_needs_trust_and_one_per_scene`;
  - `test_no_switch_questions_for_npc_without_portrait`;
  - `test_rollback_reverts_switch_effect` (Review Focus 2 through the full turn path: model_error on the NPC line rolls back the relation event).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code above.
- [ ] **Step 4: Run** the full suite and ui_check. Expected: exit 0.
- [ ] **Step 5: Live check, budget $0.08:** the Yennefer package, 8 turns: first rude, then honest attention to what she needs. Report the relationship trace per turn (rung, warmth, trust, switches hit), any leak, first-word time and slow-lane time.
- [ ] **Step 6: Commit.**

### Task 5: Short portraits for invented NPCs and package people; canon portraits for the Vizima cast

**Files:**
- Modify:
  - `harness/npcgen.py` (`short_portrait(spec, style) -> Portrait | None`: one cheap extractor-role call at creation, only for NPCs that are named, recurring or in a package; result cached in the campaign; failure logs and falls back to manner);
  - `app/newgame.py` (a person's free-text `portrait_text` is converted once at start by the same function);
  - `docs/new_game_instruction.md` (how to write `portrait_text`: core, how they treat strangers vs. close people, what warms or angers them, what they hide, how they talk);
- Create:
  - `worlds/witcher/portraits/` entries for the Vizima-arc cast that the start points place in scenes: `innkeeper_vizima.yaml`, `velerad.yaml`, `geralt_vidmak.yaml` (the phase of «Відьмак»), `foltest.yaml`, written from the book as in Task 2 Step 4;
  - and bind them in `worlds/witcher/start_points.yaml` (`portraits: {<character id>: <portrait id>}`);
- Test: `tests/test_npc_portraits.py`, `app/tests/test_newgame.py`.

**Interfaces:**
- Consumes: Tasks 1–4.
- Produces: `short_portrait` with the Portrait schema; `start_points.yaml` `portraits` binding read by the start builder.

- [ ] **Step 1: Write the failing tests.**
  - `test_short_portrait_parsed_from_fake_reply` (a fake extractor YAML gives a valid Portrait with ≥3 stances, ≥3 switches, a voice);
  - `test_background_extra_gets_no_portrait_call`;
  - `test_portrait_text_in_package_converted_once`;
  - `test_canon_start_binds_portraits` (the `vidmak_A_tavern` innkeeper has `portrait == "innkeeper_vizima"`);
  - `test_all_world_portraits_load_and_fit` (every YAML in `worlds/witcher/portraits` loads, and every stance slice is ≤ 260 words).
- [ ] **Step 2: Run** the tests. Expected: FAIL.
- [ ] **Step 3: Implement** the code above and write the four canon portraits.
- [ ] **Step 4: Run** the full suite and ui_check. Expected: exit 0.
- [ ] **Step 5: Live check, budget $0.06:** one Vizima start, 5 turns. Report the innkeeper's stance and lines (still answers direct questions, item 6 of the smoke report), `portrait_copy` hits and first-word time.
- [ ] **Step 6: Commit.**
