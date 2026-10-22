# Morning notes for the user (book-ui, night of 2026-10-22)
- Night started: Task 1 and Task 2 complete; Task 3 (book page) in progress; Tasks 4, 5 queued; final review and merge after.
## Problems found overnight
## Open questions for the user
- Bake-off above the price ceiling? (still open)
- 8 GB Gemma 4 E4B local download for a base-model tone test? (still open)
- Task 3: the agent added a small-caps speaker name before each NPC paragraph; I ruled to follow your mockup B instead (no name on gestures, a subtle name only when the speaker changes and the line has no "— сказав X" beat). Confirm, or say if you want names always / never.
- «Помилка моделі» and «Перебити тут» had no server endpoints in the real app; added to Task 4.
- Live check (Task 4): the first word of a turn now comes after 10–23 s, mostly the mimo-v2.6-pro narrator (it was ~6–9 s with luna). Decide: keep mimo-pro for quality, or narrator on mimo-flash for speed.
- Action suggestions arrive 3–13 s after a turn ends and cost ~$0.00015 each; once a suggestion was written in an NPC's voice (being fixed).
- «Помилка моделі» works only on the very last world output; if the last thing was a gesture, it is refused (no regeneration path for gestures yet).
