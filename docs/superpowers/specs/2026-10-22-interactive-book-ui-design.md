# Interactive book UI — design

Date: 2026-10-22. Status: approved by the user on 2026-10-22.

## Intent and the why

The user has not yet had a good experience with the game. A chat with Gemini in AI Studio felt better, partly because our phone UI is minimal and unpleasant. The user wants the game to be comfortable and good-looking before active play tests. The target feeling is "reading a book you take part in": a Sapkowski-like page, not a messenger. Telegram-style chat was considered and rejected.

The game's own features must stay quick to reach. These are interrupting, action suggestions, "how does he know that?", model error, retroactive cut, the character panel, places, content limits, and debug.

Mockups the user chose from, viewed in a browser: `docs/design/ui-mockups/page-speakers.html` (option B "ink"), `ink-states.html` (four states), `action-bar.html` (option C, with A's small icons).

## Goals (decided by the user unless marked)

1. **Book page.** The scene is continuous prose on one page:
   - serif type (Alegreya in the mockup);
   - dialogue written with dashes;
   - narration, NPC speech and NPC gestures in one flow;
   - the player's own words woven in, in italic;
   - no chat bubbles.
2. **Each character has their own ink.**
   - The speech of each character is set in that character's colour. Gestures and narration stay in the base text colour.
   - The colour belongs to the character, not to a line. Changing it recolours all of that character's past and future lines at once.
   - The colour is changed by a long press on any of that character's lines, through the line menu.
   - New characters get a colour automatically, distinct from everyone else present (lead's call: from a fixed, accessible palette; no two present characters share one).
   - Colours are saved per campaign.
3. **Legend "who is who."**
   - At the top, under the place and time, sits a legend that the player can show or hide.
   - Collapsed, it leaves only coloured dots.
   - Strangers appear by appearance label until the player character learns their name (names are knowledge, `docs/decisions.md`).
4. **Quick actions next to the input.** This is option C plus A's icons.
   - When it is the player's turn, 2–3 short action suggestions appear above the input. A tap puts one into the input for editing; nothing is sent automatically.
   - A small 💡 icon gives more suggestions. The turn assistant from `docs/decisions.md` sees only what the character knows.
   - While someone is speaking, a small ✋ "interrupt" takes 💡's place, tinted with the speaker's ink. It is small, not a big floating button.
   - Typing and sending while someone speaks cuts in, as now. A tap on the text shows the rest at once, as now.
5. **Long press on a line** opens a bottom sheet:
   - «Звідки він це знає?»;
   - «Помилка моделі — переписати» (only for the last world output, per `docs/decisions.md`);
   - «Перебити тут» (retroactive cut, last NPC line only);
   - «Чорнило цього персонажа».
6. **Menu ☰** opens a drawer over the text with:
   - the player character's state as chips plus a few sentences, from what the character perceives;
   - who is here and what I know about them;
   - where I can go;
   - pause / skip / veil;
   - settings, including the debug view.
7. **One theme for now:** dark "paper" (warm dark page, light ink).
   - It must be readable at phone size: line length under about 40 em, body around 16 px with generous line height.
   - Respect reduced motion. Keyboard focus is visible on desktop.
8. **Phone first, laptop works.** The same page with a wider text column; no separate layout (lead's call).

## Non-goals

- Visual novel stage, character portraits or images (no images in the first version, per `docs/decisions.md`).
- The live real-time scene mode (later; this UI must not block it).
- A light theme (later).
- Changing engine behaviour. This is UI work. The only exceptions are small read endpoints the UI needs, such as the suggestions call if it is not exposed yet, ink storage and the list of present characters with labels.

## Anti-goals

- Anything that reads like a messenger or a generic AI chat app.
- Controls cluttering the page while reading: only the input row and its two small icons are always visible.
- Colour as the only cue. Speakers must stay readable without colour (the dash and speech tags already carry who speaks; the legend has names).
- Losing any feature the current UI has: interrupt, skip, challenge, model error, retroactive cut, panel, debug, reload continuity, pause in background.

## Constraints

- Existing app: Starlette + SSE + plain HTML/CSS/JS, no build step (`app/static/`). Keep that unless there is a strong reason (record any change in `docs/tools.md`).
- Event contract from the living-dialogue work stays: turn ids, `npc_act` for gestures, narration events, `turn_done`, `retract`, `error`.
- Masking: never show a name the player character has not learned (the engine already masks; the UI must not reveal ids or real names in legend or menus).
- Fonts: load from Google Fonts with Cyrillic support, with a serif fallback that also works offline.
- Tests: the existing app tests keep passing. Extend the Playwright phone check (390×844) for:
  - ink assignment and recolouring of past lines;
  - legend hide/show;
  - suggestions tap-to-insert;
  - ✋ appearing only while someone speaks;
  - the long-press menu;
  - the drawer.

## Settled after the builder check (lead's calls)

- **Turn assistant is new work, in scope.** There is no assistant code yet (only the decision in `docs/decisions.md`). Build a minimal one now:
  - one cheap call, made after `turn_done` when it is the player's turn;
  - it reads only the player character's view: the same filter as the narrator and the panel;
  - it returns 2–3 short action options in the player's language;
  - 💡 asks for 3 more;
  - it must never delay the next turn's first word; measure it.
  - The rest of the assistant (praise-kept parts, feedback loop, style note) is later.
- **Menu items: show only what works.**
  - Shown now: the panel (`/api/panel`), what I know about people (`/api/knowledge`, presented per person), skip (`/api/skip`), debug.
  - "Where can I go": add a small read endpoint over the world map in `harness/world/`, if the campaign has a world. Travel still happens by typing ("іду на ринок").
  - Pause, veil, skip-scene and content limits are not built yet. Leave them out of the drawer for now rather than showing dead buttons.
- **Character keys.**
  - The client keys ink and the legend on an opaque, stable per-campaign token that the server derives from the character id. Real ids and names never reach the client unless the player character knows the name.
  - The legend endpoint returns token, current masked label and ink. When a stranger's name is learned, the label changes and the token and ink stay.
  - Ink is stored server-side in the campaign (one small write endpoint), so it survives a reload and a change of device.
- **What a "line" is.**
  - One utterance event (the NPC's speech together with its own beats) or one gesture event. Narration paragraphs are their own blocks. The player's lines are their own blocks.
  - The same NPC speaking twice in a turn gives two paragraphs, as in a book.
  - `state.transcript` must reproduce exactly this layout after a reload.
- **The long-press sheet hides items that do not apply.**
  - "Звідки він це знає?" appears on NPC speech only.
  - "Помилка моделі" appears only on the last world output.
  - "Перебити тут" appears only on the last NPC line.
  - Ink appears on any line of a character, including gestures.
- **Ink palette: 8 accessible colours.**
  - When more than 8 characters are present, auto-assignment reuses the colour of the character who spoke least recently.
  - A manual choice may duplicate another character's colour (the player's choice wins).
- **✋ and 💡.**
  - ✋ is shown while anything streams: narration or speech.
  - 💡 is shown when idle (the slow lane running in the background counts as idle).
  - The input stays enabled in every phase, and sending cuts in as today.

## Left to the builder

- Exact palette values, spacing scale and type scale, within the chosen look.
- How long press is detected on touch and on desktop (a context menu or long click).
- How ink is stored (campaign settings or app-side store) and keyed (character id, never the display name).
