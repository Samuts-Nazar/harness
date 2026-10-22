# Interactive Book UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** The phone app reads like an interactive book. It has:
- a per-character ink that the player can change;
- a hideable legend;
- quick action suggestions next to the input;
- a long-press line menu;
- a drawer for everything else.

**Architecture:**
- The server gives each character an opaque per-campaign token and stores inks in the campaign. Events and the transcript carry tokens instead of ids.
- A minimal turn assistant (new `harness/assistant.py`) suggests 2–3 actions from the player character's view after each turn.
- The client (`app/static/`, plain JS, no build step) renders one continuous page. Each character's speech is coloured through one CSS variable per token, so a change recolours past and future lines at once.

**Tech Stack:** Python 3.14, Starlette + SSE, plain HTML/CSS/JS, Playwright check at 390×844, pytest with fake providers.

**Spec:** `docs/superpowers/specs/2026-10-22-interactive-book-ui-design.md` (read it; mockups in `docs/design/ui-mockups/`).

## Global Constraints

- Visual direction is fixed by the user:
  - Option B "ink" from `page-speakers.html`.
  - States from `ink-states.html`.
  - Option C (suggestions above the input, with small ✋/💡 icons) from `action-bar.html`.
  - Dark "paper" theme, a serif (Alegreya, with an offline serif fallback), dialogue written with dashes, no chat bubbles.
- The ink belongs to the character, not the line. A change recolours all past and future lines of that character immediately. Inks are stored server-side per campaign.
- Never send real ids or unlearned names to the client. Labels are masked by the engine, and keys are opaque tokens.
- No feature regressions:
  - cut-in by typing, ✋ interrupt, tap to skip, «Звідки він це знає?», «Помилка моделі», retroactive cut (last NPC line only);
  - panel, debug;
  - reload continuity, pause in background, turn ids, `npc_act` for gestures.
- Colour is never the only cue: the dash and speech tags carry the speaker, and the legend has names.
- Accessibility: readable at 390 px, body text ≥ 16 px, line length ≤ about 40 em, visible keyboard focus, reduced motion respected.
- Suggestions must not delay the first word of the next turn. Measure it.
- Cheap models only. A live check costs under 0.10 USD. Never commit `data/`, `campaigns/`, `.env`. Run `nix develop --command pytest -q` and check its real exit code before every commit.

## Review Focus

1. **A stranger whose name is learned mid-scene.** The token and ink stay the same. The legend label switches from appearance to name, and past lines keep their colour. Pinned in Task 1.
2. **More than 8 characters present.** Auto-assignment reuses the least recently active colour and never crashes. Pinned in Task 1.
3. **A reload in the middle of a scene.** Inks, the legend and the page layout (paragraphs per utterance/gesture/narration/player line) are identical to the live view. Pinned in Tasks 1 and 3.
4. **Typing a suggestion, then cutting in while an NPC speaks.** The suggestion text is inserted, not sent. Sending cuts in as today. ✋ shows only while text streams. Pinned in Task 3.
5. **A long press on an old line.** «Помилка моделі» and «Перебити тут» are hidden. «Звідки він це знає?» is shown only on NPC speech. Ink is available on gestures too. Pinned in Task 3.

---

### Task 1: Character tokens, inks and the cast endpoint (server)

**Files:**
- Modify: `app/game.py`, `app/campaigns.py`, `app/server.py`.
- Create: `app/inks.py` (palette and assignment).
- Tests: `app/tests/test_app_cast.py`.

**Interfaces:**
- Produces:
  - `token_for(campaign_seed: str, character_id: str) -> str`: a stable 8-character opaque token, for example a hash prefix.
  - `PALETTE: tuple[str, ...]`: 8 accessible inks on the dark page.
  - `assign_ink(present_tokens: Sequence[str], inks: Mapping[str, str], recency: Sequence[str]) -> str`: a free colour if there is one, otherwise the colour of the least recently active token.
  - `GET /api/cast -> [{"tok": str, "label": str, "ink": str, "present": bool}]`, where `label` is the masked label the player character perceives.
  - `POST /api/ink {"tok": str, "ink": str} -> {"ok": true}`, persisted in the campaign (settings or meta) and emitted as an SSE event `ink {tok, ink}`.
  - All events (`speaker`, `word`, `npc_act`, …) and the transcript entries carry `tok` and `label` instead of `who`/`name`.

- [ ] **Step 1: Failing tests.**
  - `test_cast_hides_real_ids_and_unlearned_names`: the json has no `horst` id and no «Горст» before he is introduced.
  - `test_token_and_ink_stable_when_name_learned` (Review Focus 1).
  - `test_auto_ink_distinct_then_reuses_least_recent` with 10 characters (Review Focus 2).
  - `test_ink_change_persists_across_reopen`.
  - `test_events_and_transcript_carry_tokens_not_ids`.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 2: Minimal turn assistant

**Files:**
- Create: `harness/assistant.py`.
- Modify: `app/game.py`, `app/server.py`, `harness/decisions.py` (count its calls).
- Tests: `tests/test_assistant.py`, `app/tests/test_app_suggestions.py`.

**Interfaces:**
- Produces:
  - `suggest(engine: Engine, n: int = 3, avoid: Sequence[str] = ()) -> list[str]`. One cheap call (role `"assistant"`, model `DEFAULT_NPC`, or `DEFAULT_NARRATOR` if that tests better). The context is the player character's view only, the same filter the panel and the narrator use. It returns short Ukrainian action lines in the player's voice; `*…*` marks actions.
  - `Game` computes suggestions in its own thread after `turn_done`, never on the turn thread or before the next turn's first word, and emits `suggestions {turn, items}`.
  - `GET /api/suggestions?more=1` returns 3 more and avoids the shown ones.
  - Suggestions for a turn are dropped as soon as a new turn starts.

- [ ] **Step 1: Failing tests.**
  - `test_suggest_sees_only_player_view`: a fact the player character does not know is absent from the prompt.
  - `test_suggestions_emitted_after_turn_done_not_before`.
  - `test_more_avoids_shown`.
  - `test_new_turn_discards_pending_suggestions`.
- [ ] **Step 2: Run the tests.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the full suite.** Expected: PASS.
- [ ] **Step 5: Commit.**

### Task 3: The book page (client)

**Files:**
- Modify: `app/static/index.html`, `app/static/app.js`, `app/static/style.css` (a rewrite is allowed; keep the event contract).
- Tests: `app/tests/ui_check.py` (extend), the node client tests used in Task 12 of the dialogue plan (extend or add).

**Interfaces:**
- Consumes: Task 1's `tok` and `label` on events and the transcript, `/api/cast`, `POST /api/ink`, the `ink` event; Task 2's `suggestions` event and `/api/suggestions?more=1`.
- Layout:
  - **Top:** the place and time line, plus a legend toggle. Collapsed, the legend shows coloured dots; open, it shows dots and labels.
  - **Page:** narration paragraphs in the base ink; an NPC utterance paragraph (speech in the character's ink, its own beats in the base italic); a gesture paragraph (base italic); a player paragraph (italic, the player's own accent).
  - **Colour:** each character's speech gets the colour `var(--ink-<tok>)`, set on `:root`, so one change recolours everything.
  - **Bottom:** a suggestions row (2–3 chips; a tap inserts into the input), an icon slot (💡 when idle, a small ✋ tinted with the speaker's ink while text streams), the input, and send.
  - **Tap on streaming text:** show the rest at once (`/api/skip`).
  - **Long press, or right-click on desktop, on a paragraph:** a bottom sheet whose items follow the spec's rules (Review Focus 5). Ink opens an 8-swatch picker. «Помилка моделі» and «Перебити тут» call the existing endpoints.
  - **☰ drawer:** the panel, people (from `/api/knowledge`, grouped per token and label), places (Task 4), skip, debug.
- Use the mockup files as the visual reference: colours, type, spacing.

- [ ] **Step 1: Extend the UI check first.** At 390×844:
  - legend hide/show;
  - the ink picker recolours a past line (check its computed colour);
  - a suggestion tap fills the input without sending;
  - ✋ visible only while streaming;
  - the long-press sheet items on the last NPC line versus an old line;
  - the drawer opens;
  - a reload gives the same paragraphs and colours (Review Focus 3);
  - no console errors and no horizontal scroll.
- [ ] **Step 2: Run it.** Expected: FAIL.
- [ ] **Step 3: Implement.**
- [ ] **Step 4: Run the UI check and the full suite.** Expected: PASS. Save screenshots under `app/screenshots/`.
- [ ] **Step 5: Commit.**

### Task 4: Places in the drawer, and a live check

**Files:**
- Modify: `app/server.py`, `app/game.py`.
- Create: `reports/ui/SUMMARY.md`.
- Tests: `app/tests/test_app_places.py`.

**Interfaces:**
- Produces: `GET /api/places -> [{"name": str, "minutes": int}]` from the campaign world map (`harness/world/`), or `[]` without a world. The drawer lists the places; a tap puts «Іду до <place>» into the input.

- [ ] **Step 1: Failing test.** `test_places_from_vizima_world_and_empty_without_world`.
- [ ] **Step 2: Implement it, then run the tests.** Expected: PASS.
- [ ] **Step 3: Live check on the Vizima campaign.** 6 turns, budget under 0.10 USD. Record:
  - the suggestions' latency and cost per turn;
  - that the next turn's first word did not wait on suggestions;
  - 3 example suggestion sets (quote them);
  - screenshots from a real session.

  Write `reports/ui/SUMMARY.md` (readable on a phone).
- [ ] **Step 4: Run the full suite five times in a row** (all exit 0), **then commit.**

---

## Amendment 2026-10-22: Task 5 — new game from a file, plus the instruction document for any AI

The user's request: a document they can give to any AI chat, together with their idea for a game. That AI interviews them briefly and outputs one file. The user loads the file into the app and starts a new game exactly as they wanted, with the best possible experience. What the user fixes and what they leave to the world differs per idea, so almost every field is optional. A missing field means "the world decides", and the engine fills it sensibly.

### Task 5: Game package format, importer, "Нова гра з файлу", and `docs/new_game_instruction.md`

**Files:**
- Create: `app/newgame.py` (parse, validate, build a campaign), `worlds/witcher/start_points.yaml` (named canon start moments), `docs/new_game_instruction.md` (in Ukrainian, written for an external AI), `docs/game_package_example.yaml`.
- Modify: `app/server.py`, `app/game.py`, `app/campaigns.py`, `app/vizima.py` (reuse the builders; no duplication), `app/static/*` (a "Нова гра" screen in the ☰ drawer: paste or upload, a summary, then start).
- Tests: `app/tests/test_newgame.py`, extend `app/tests/ui_check.py`.

**Package (YAML, UTF-8, Ukrainian values)**
- Required: `version: 1`, `world` (`witcher` for now), and `player.description` (free text).
- Everything else is optional. A missing field means the world decides.
  - `player`:
    - `name`; `appearance`; `traits`; `knows` (what the character knows at the start);
    - `unbounded: true|false` (the pilot demon);
    - `hidden` (traits nobody sees).
  - `start`: one of the following:
    - `canon: <id from start_points.yaml>` (for example `vidmak_A_tavern`);
    - free text `{place, day, time, situation}`.

    Plus `who_is_here` (optional people, each with an optional `role`, `attitude` and `knows_player: false`).
  - `canon`: `follow` (the books as gravity, the default) or `loose` (canon only as background).
  - `tone`: free text, default "як у Сапковського". `pace`: `slow|normal|fast` (narration density).
  - `limits`: `{avoid: [...], veil: [...]}`, the content limits (decisions.md session zero).
  - `outcomes`: `real` (the default) or `unbounded` (overrides `player.unbounded`).
  - `dialogue`: `living` (the default) or `classic`. `assistant`: `on` (the default) or `off`.
  - `inks: {<label or name>: "#rrggbb"}`, optional colour presets.
  - `notes`: free text for anything else. It is stored and shown to the narrator as campaign intent; it never overrides the rules in decisions.md.

**Importer**
- It validates with clear Ukrainian errors (field, problem, how to fix) and never crashes on unknown fields: they are kept in `notes`, with a warning.
- It shows a summary card before starting: what was set, and what the world will decide.
- It builds the campaign through the existing builders. A canon start uses the canon store when present; a free start uses `npcgen` and the world map. The player sheet is used like `data/Ragnar.md`, giving looks through `derive_traits`.
- Missing fields are filled at start: one cheap call at most, recorded.

**`docs/new_game_instruction.md`**, written for any AI, in Ukrainian, ready to paste:
- the AI's role (game-start assistant);
- the interview: a few short questions; ask only what changes the game; skip what the user leaves to the world; propose concrete options when the user is stuck;
- what makes the experience good: a strong start situation with a hook; a player character with a want and a limit; people present with their own goals; tone; and limits asked tactfully;
- the exact output: one YAML block in the package format above, with comments;
- rules: never write the player character's feelings or decisions beyond what the user said; no copyrighted book text; names in Ukrainian forms;
- a full example (`docs/game_package_example.yaml`): a Vizima start with a free-form player character.

**Tests**
- Valid minimal and full packages.
- An unknown field leads to a warning.
- Bad values lead to readable errors.
- A canon start and a free start each build a playable campaign with the fake provider.
- A UI check: paste the example, see the summary, start, see the first narration.

**Budget:** under 0.10 USD for one live start check.
