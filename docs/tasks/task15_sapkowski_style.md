# Task 15: Living characters in Sapkowski's style

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `docs/tools.md`, `reports/bakeoff/SUMMARY.md`, `reports/language/SUMMARY.md`, assumptions 70–82, `harness/context.py`, `harness/director.py`.
Task 14 runs at the same time and changes what context data is shown (names as knowledge, own recent lines, actions vs speech). Put your work in a new `harness/style.py` (prompt wording, style guidance, exemplar selection) and change `harness/context.py` only to call it.

## User feedback from the first play
Горст's first line: "Є справа. П’яту ніч поспіль виє біля старого млина, а двох хлопців знайшли мертвими коло греблі. Ми хочемо, щоб ти з’ясував, що там водиться, і поклав тому край. За плату, звісно. Скільки коштує твоя робота, Рагнаре?"
The user: this is a neural-network style, not Sapkowski; "Є справа" sounds like AI; no life — the speaker does not look around to check nobody listens, does not hesitate, bargain, fear. "Такого не має бути."

## Goal
NPC lines and narration that read like Sapkowski in the Ukrainian translation: living people with their own manner, subtext, gestures, haggling, irony, fear, interruptions; no assistant-like tidy summaries.

## 1. NPCs act, not only speak
- An NPC's output may include its own small actions and manner woven into the line (looks around, lowers voice, fidgets, pauses), as the Ukrainian books write dialogue with a dash. These are the NPC's own behaviour, so the NPC call may write them; it must never write anyone else's actions or speech, nor the player's. Stored as the NPC's observable actions (perceived by those present) plus its speech.
- Update the narrator NPC-speech check and the dialogue-dash detector so NPC output with its own beats is accepted, and narration still may not contain NPC speech.

## 2. Style guidance from the books
- Write a short style sheet for this world from your reading of the Ukrainian translation (`data/witcher_books.txt`): dialogue rhythm, how people of each class speak, irony, what Sapkowski avoids. Keep it in `worlds/witcher/style.md` (no book quotes longer than a sentence in the repo).
- Exemplars at runtime: pick 1–3 short passages from the local book file that match the situation (e.g. a village elder hiring a witcher, haggling, a tavern) and include them as style examples in the prompt. Loaded from `data/` at runtime only, never committed. Measure the added tokens and cost.
- Character voice: each NPC profile gets a few manner notes (how this person talks), generated once per new NPC by a cheap model from the profile, stored with the profile.

## 3. Style bake-off
- Situations: the inn scene opening (Горст, Ельза, Рагнар) plus 8 more dialogue moments built from the task 7 NPC/narrator sets.
- Variants: current prompt vs new style prompt vs new style prompt + exemplars; models: `openai/gpt-6-luna` and 2–3 other models from the live catalog under the price ceiling that public signals suggest write better literary prose (state why, with links; record in `docs/tools.md`). 3 samples each.
- Grade blind yourself: "sounds like Sapkowski in Ukrainian" 1–5, liveliness 1–5, Ukrainian quality, in character, knowledge leaks, does it act for others. Also flag assistant-isms ("Є справа.", tidy summaries, "звісно" fillers).
- Also prepare a blind A/B set of 10 pairs (best old vs best new) as a simple page under `app/static/ab.html` (or a markdown file) so the user can judge on the phone; the key stays out of the page.

## Budget
Under 0.60 USD.

## Output
Full report in the final message: verdict, tables, quoted examples (old vs new for the Горст line), chosen model per role if it changes, cost and latency impact, open questions, branch and worktree as absolute paths.
