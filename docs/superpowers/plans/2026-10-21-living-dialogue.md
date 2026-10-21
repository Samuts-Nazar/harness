# Living Dialogue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dialogue that follows the rhythm of the source world: varied response shapes, narration only when needed, NPCs talking among themselves, measured against a per-world profile, with a decision counter.

**Architecture:**
- A corpus-derived `WorldProfile` (numbers only) is the prior and the yardstick.
- The scene director grows into a step-by-step exchange loop inside one `turn()`. Each step makes one batched typed decision: who takes the floor next (an NPC, the player, or nobody), and in what shape. Whether the turn needs narration is decided once before the narrator.
- NPC calls get the shape, and code fits the output to it.
- The app keeps input open during an exchange, and a tap skips the speaking-pace delay.

**Tech Stack:** Python 3.14, SQLite event log, Starlette + SSE app, OpenRouter cheap models, first-line decider with LLM escalation (`harness/judge.py`), pytest with fake providers.

**Spec:** `docs/superpowers/specs/2026-10-21-living-dialogue-design.md` (read it first; it carries the why and the user's decisions).

## Global Constraints

- `docs/decisions.md` is the source of truth. In particular:
  - narrator never writes NPC speech;
  - NPC calls write only their own small actions;
  - free prose on creative calls, no JSON;
  - names never distorted;
  - epistemic isolation;
  - base mode: the world waits for the player.
- Cheap models only; typed decisions go to the first-line decider with the existing <0.8 escalation (`EscalatingJudge`).
- Keep the task 19 fast/slow lane (`defer_slow`, `settle()`) and a deterministic event log: every event write on the main thread, in a fixed order.
- No world-specific code: Witcher data lives in `worlds/witcher/`.
- Never commit `data/`, `campaigns/`, `.env`, or book text longer than one sentence. If `data`/`campaigns` are symlinked into the worktree, add files by explicit path.
- Live-check budget under 0.60 USD.
- Run `nix develop --command pytest -q` and check its real exit code before every commit.
- Old behaviour stays available behind `Engine(dialogue="classic")` until the A/B pairs are generated; `"living"` is the new default.

## Review Focus

1. **The player is addressed by an NPC who does not know the player's name.** The address is by label ("чужинцю") or by "you". The exchange must still stop and hand the floor to the player. Pinned in Task 4.
2. **The only NPC present answers a direct question with silence or a gesture.** The turn must deliver something readable (narration of the silence or the gesture line), and the app must not show an empty or broken turn. Pinned in Tasks 4 and 7.
3. **The player cuts in during the third line of an exchange.** Later lines must never be shown, their pending calls are cancelled, and extraction covers only what was delivered. Pinned in Task 4.
4. **NPCs keep arguing until the cap.** The exchange stops at `MAX_EXCHANGE_LINES`, the floor goes to the player, and there is no loop. Pinned in Task 4.
5. **A corpus written with «quotes» instead of dashes.** Building a profile must fail with a clear "no dialogue lines found in dash format" error, not write an empty profile. Pinned in Task 1.

---

### Task 1: World profile from a corpus

**Files:**
- Create: `harness/profile.py`, `worlds/witcher/profile.json` (generated, numbers only)
- Test: `tests/test_profile.py`

**Interfaces:**
- Produces:
  - `DialogueLine(speech: str, beats: list[str], words: int, is_question: bool, has_beat: bool, paragraph: int)`
  - `dialogue_lines(text: str) -> list[DialogueLine]`, which reuses `harness/style.split_npc_output` for speech/beat splitting.
  - `WorldProfile` (dataclass, JSON-serialisable):
    - `length_bins: dict[str, float]`, with bins `"1"`, `"2-3"`, `"4-7"`, `"8-15"`, `"16-30"`, `"31+"` as shares;
    - `median_words: float`;
    - `question_share: float`;
    - `no_beat_share: float`;
    - `narration_between_share: float`;
    - `narration_median_words: float`;
    - `speaker_run_mean: float`;
    - `n_lines: int`;
    - `source: str`.
  - `profile_from_text(text: str, source: str) -> WorldProfile`, which raises `ValueError("no dialogue lines found in dash format")` when fewer than 50 lines are found.
  - `profile_of_lines(lines: Sequence[str]) -> WorldProfile` (for engine output).
  - `distance(a: WorldProfile, b: WorldProfile) -> dict[str, float]`: per-metric absolute difference, plus `"length_bins_l1"`.
  - `load_profile(world: str) -> WorldProfile | None`.
  - CLI: `python -m harness.profile build <world> <corpus_path>` writes `worlds/<world>/profile.json`.
- Speaker runs: consecutive dash paragraphs with no narration paragraph between them count as alternating speakers. Document this approximation in the module docstring and in `docs/assumptions.md`.

- [ ] **Step 1: Write the failing tests.**
  - `test_dialogue_lines_split_speech_and_beats`: on a 3-paragraph synthetic text, «— Ні. — буркнув він.» gives `words == 1` and `has_beat`.
  - `test_profile_bins_and_median`: on 60 synthetic lines of known lengths, the bins match the expected shares and the median.
  - `test_profile_rejects_quote_format`: a «…»-quoted corpus raises `ValueError` with the message above.
  - `test_distance_zero_for_identical`.
- [ ] **Step 2: Run `nix develop --command pytest tests/test_profile.py -q`.** Expected: FAIL (module missing).
- [ ] **Step 3: Implement `harness/profile.py` as specified.**
- [ ] **Step 4: Run the tests.** Expected: PASS. Then run the CLI on `data/witcher_books.txt` and check `median_words` is about 10 and the `"2-3"` share about 0.14 (the lead's measurement on 2026-10-20).
- [ ] **Step 5: Commit** `harness/profile.py`, `tests/test_profile.py`, `worlds/witcher/profile.json`.

### Task 2: Decision counter

**Files:**
- Create: `harness/decisions.py`
- Modify: `harness/pipeline.py` (expose per-turn counts in `TurnResult`), `app/game.py` (`debug["decisions"]`), `app/static/app.js` (show it in the debug panel)
- Test: `tests/test_decisions.py`

**Interfaces:**
- Produces:
  - `DecisionCount(judgments: int, escalations: int, llm_calls_by_role: dict[str, int], code_choices: int)`, with `total` as a property.
  - `count_since(engine: Engine, first_event_id: int, judgment_mark: int, call_mark: int) -> DecisionCount`.
  - `TurnResult.decisions: DecisionCount | None`.
  - `aggregate(counts: Iterable[DecisionCount]) -> DecisionCount` for scene and session totals.
- `code_choices` counts the code-made choices the engine already logs as notes: name masking, seeded names, trimming (Task 3), shape enforcement, and cap stops (Task 4).

- [ ] **Step 1: Failing tests.**
  - `test_turn_reports_decision_counts`: a fake-provider turn with 2 NPC lines has `llm_calls_by_role["npc"] == 2` and `judgments >= 1`.
  - `test_aggregate_sums`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Count from the existing `JudgmentLog` entries and the provider call records the app's `Recorder` and the evalkit cassette already keep.
- [ ] **Step 4: Run the full suite.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 3: Response shape and fitting

**Files:**
- Create: `harness/shape.py`
- Modify: `harness/style.py` (`npc_instruction(prof, language, shape: Shape | None = None)`, shape sentence; stop requiring a beat in every line; add "answer the last thing said, not the whole situation"), `worlds/witcher/style.md` (remove wording that makes a beat mandatory)
- Test: `tests/test_shape.py`

**Interfaces:**
- Produces:
  - `class Shape(str, Enum)`: `SILENCE`, `GESTURE`, `WORD`, `SHORT`, `NORMAL`, `LONG`.
  - `word_bounds(shape: Shape, profile: WorldProfile | None) -> tuple[int, int]`. Defaults when there is no profile: WORD (1, 2), SHORT (3, 9), NORMAL (10, 25), LONG (26, 80), SILENCE and GESTURE (0, 0) spoken words.
  - `shape_instruction(shape: Shape, language: str | None) -> str`, an English instruction line.
  - `fit_to_shape(text: str, shape: Shape, bounds: tuple[int, int], *, allow_trim: bool = False) -> tuple[str, str]`, which returns `(text, how)` with `how` in `{"ok", "trimmed", "regenerate"}`:
    - speech beyond 1.5× the upper bound returns `"regenerate"` on the first call;
    - the caller regenerates once, then calls again with `allow_trim=True` to trim at a sentence boundary;
    - SILENCE returns `("", "ok")`;
    - GESTURE keeps beats only and drops speech.

- [ ] **Step 1: Failing tests.**
  - `test_word_shape_rejects_long_speech` returns `"regenerate"`.
  - `test_trim_at_sentence_boundary` (with `allow_trim`): result ≤ upper bound and ends with sentence punctuation.
  - `test_gesture_keeps_only_beats`.
  - `test_silence_is_empty`.
  - `test_npc_instruction_mentions_shape`.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Count words of the spoken part only, using `split_npc_output`.
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 4: Director exchange loop

**Files:**
- Modify: `harness/director.py`, `harness/pipeline.py` (`turn()`, `_launch()`, NPC loop), `harness/settings.py`
- Test: `tests/test_exchange.py`

**Interfaces:**
- Consumes: `Shape`, `word_bounds`, `fit_to_shape`, `shape_instruction` (Task 3); `load_profile` (Task 1).
- Produces:
  - `settings.MAX_EXCHANGE_LINES = 6`, the cap per turn. It replaces the use of `MAX_SPEAKERS` in living mode; `MAX_SPEAKERS` stays for classic.
  - `PLAYER_FLOOR = "player"` and `NOBODY` in `director.py`.
  - `next_floor_questions(npcs: Mapping[str, str]) -> dict[str, Question]`: one batch holding `"next"`, a choice over the NPCs plus `PLAYER_FLOOR` (with the meaning "someone just addressed the player, or the talk naturally turns to them") plus `NOBODY`, and `"shape"`, a choice over the `Shape` values.
  - `decide_next(judge: Judge, state: Sequence[str], npcs: Mapping[str, str]) -> tuple[str, Shape]`.
  - `Engine(dialogue: str = "living")`.
  - `TurnResult.stop_reason: str` in `{"player_addressed", "nobody", "cap", "interrupted"}`.
- Loop, in living mode, after narration (or after the player input when Task 5 skips narration):
  1. `decide_next` with the state including all lines so far in this turn.
  2. If the choice is an NPC, generate its line with the shape, `heard=` all earlier lines this turn, fit, deliver, write the events.
  3. Repeat until `PLAYER_FLOOR`, `NOBODY`, the cap, or an interrupt.
- Each step is sequential. The next decision and the next line can be prefetched only if the result stays deterministic; otherwise keep it sequential and report the latency.
- The NPC check (`_npc_line`) applies to every line as now.

- [ ] **Step 1: Failing tests,** with a scripted FakeJudge.
  - `test_exchange_stops_when_player_addressed`: an NPC line addressing the player by the label «чужинцю» with the player's name hidden, then `next == player` gives `stop_reason == "player_addressed"` and 1 utterance (Review Focus 1).
  - `test_exchange_runs_npc_to_npc`: horst, then elza, then horst, then nobody gives 3 utterances in order, and each later line's prompt contains the earlier lines.
  - `test_exchange_cap`: the judge always picks an NPC, so the turn stops after `MAX_EXCHANGE_LINES` with `stop_reason == "cap"` (Review Focus 4).
  - `test_interrupt_in_third_line_cancels_rest`: the handle fires during line 3, so there are 3 utterances (the last one cut), no 4th call is made, and extraction segments cover only the delivered text (Review Focus 3).
  - `test_silence_shape_writes_no_speech`: the only NPC is chosen with shape SILENCE, so no utterance is written and the turn's narration or a `silence` note makes the turn readable (Review Focus 2).
  - `test_classic_mode_unchanged`: `dialogue="classic"` passes the existing task 12/14 director tests.
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.** Make the next-floor decision depend only on main-thread state, so the log stays deterministic.
- [ ] **Step 4: Run the full suite.** Expected: PASS. Then run it 5 times and confirm there is no flakiness.
- [ ] **Step 5: Commit.**

### Task 5: Narration only when needed

**Files:**
- Modify: `harness/director.py`, `harness/pipeline.py`
- Test: `tests/test_exchange.py` (extend)

**Interfaces:**
- Produces:
  - `needs_narration_question() -> Question`, a yes/no: "Does this moment need a narrated passage (a change of scene, an action with a visible result, someone arriving, a pause worth describing, an outcome to tell), or is it just talk?"
  - It is asked in the same batch as the first `decide_next` when possible.
  - When the answer is no, the narrator call is skipped and `TurnResult.narration == ""`.
- Outcome mode (task 19): when an outcome was judged for a non-unbounded player, narration is always on.

- [ ] **Step 1: Failing tests.**
  - `test_quick_exchange_skips_narrator`: the player says one line and the judge says no narration, so 0 narrator calls are made and NPC lines are delivered.
  - `test_outcome_forces_narration`.
  - `test_app_turn_without_narration`: the app's SSE stream shows the speaker lines with no `narr_start` (Review Focus 2).
- [ ] **Step 2: Run them.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 6: Engine uses the profile

**Files:**
- Modify: `harness/pipeline.py`, `harness/style.py`, `harness/repetition.py` (optional), `app/game.py`
- Test: `tests/test_profile.py` (extend)

**Interfaces:**
- Consumes: `load_profile`, `profile_of_lines`, `distance`.
- Produces:
  - the engine loads `load_profile(world)` once and passes it to `word_bounds` and into the shape question as a prior line ("in this world about N% of replies are 1–3 words");
  - per turn, `debug["dialogue"]` holds the rolling `profile_of_lines` over the session's NPC lines and its `distance` to the world profile.

- [ ] **Step 1: Failing test.** `test_session_profile_in_debug`: after 3 fake turns, `debug["dialogue"]["median_words"]` exists.
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 7: App — cut in by typing, tap to skip pace

**Files:**
- Modify: `app/game.py`, `app/server.py`, `app/static/app.js`, `app/static/style.css`
- Test: `app/tests/test_app_dialogue.py`, `app/tests/ui_check.py` (extend)

**Interfaces:**
- Produces:
  - `Game.skip()` makes the current stream deliver all remaining words at once, with no interrupt semantics. It sets `pace` to 0 for the rest of the turn.
  - `POST /api/skip`.
  - `Game.start_turn(text)` while a turn runs: it fires the interrupt at the current point, waits for the turn to finish (`wait_idle`), then starts the new turn with `text`. It no longer returns 409.
  - The input box stays enabled during a turn.

- [ ] **Step 1: Failing tests.**
  - `test_send_during_exchange_interrupts_then_runs`: the first turn's last utterance is `interrupted`, and the second turn exists.
  - `test_skip_delivers_rest_without_interrupt`: no `interrupted` flag, and all words are delivered.
  - `test_empty_exchange_turn_renders` (Review Focus 2).
- [ ] **Step 2: Run.** Expected: FAIL.
- [ ] **Step 3: Implement.** The UI shows a hint under the stream ("торкніться, щоб показати одразу").
- [ ] **Step 4: Run the tests and the Playwright check** (`nix develop --command python app/tests/ui_check.py`). Expected: PASS. Update the screenshots.
- [ ] **Step 5: Commit.**

### Task 8: Measurement, reference scenes, A/B, reports

**Files:**
- Create:
  - `experiments/dialogue/find_scenes.py` (ranks book scenes by distinct speakers and dialogue density; prints line ranges only);
  - `worlds/witcher/scenes/*.json` (3 reference setups in our own words: who is there, what is going on, what each wants; Rinde from the story "Останнє бажання" is one);
  - `experiments/dialogue/live_check.py`;
  - `reports/dialogue/SUMMARY.md`;
  - `reports/decisions_count.md`.
- Modify: `app/static/ab_data.js` (new pairs), `README.md` (a "How many decisions per action" section).

**Interfaces:**
- Consumes: everything above.
- `live_check.py` runs:
  - the 3 reference scenes (the player is a silent onlooker; the protagonist's lines are left out of the book numbers when the protagonist is not an engine speaker);
  - 2 inn sessions of 20 turns, in `living` and `classic` modes.
- It writes the profile distance, the share of 1–3-word lines, the median, seconds to first word, the decision counts per action, scene and session, and cost.
- The cassette goes under `campaigns/` (not committed).

- [ ] **Step 1: Run `find_scenes.py`.** List the top 10 scenes in the report by line ranges and speaker counts; pick 3, Rinde included.
- [ ] **Step 2: Write the 3 scene setups.** No copied lines.
- [ ] **Step 3: Run `live_check.py`.** Acceptance from the spec:
  - in the long sessions the share of 1–3-word lines is > 0;
  - the median spoken length is ≤ 2× the profile's median.

  If either fails, report it and stop; do not tune silently.
- [ ] **Step 4: Generate 10 A/B pairs.** Each pair is a whole short exchange, classic vs living, on the same situations. No book text. The key goes to `reports/dialogue/ab_key.json`.
- [ ] **Step 5: Write `reports/dialogue/SUMMARY.md`** (verdict first, numbers vs profile, quoted short examples, latency, spend), **`reports/decisions_count.md`** (per action, scene, session, with the session's real numbers) and **the README section.**
- [ ] **Step 6: Commit.**
