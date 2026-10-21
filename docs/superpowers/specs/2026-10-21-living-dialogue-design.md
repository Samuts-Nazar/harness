# Living dialogue and the world profile — design

Date: 2026-10-21. Status: draft for the user's approval.
First of three projects against "averaging" (this one; then a decision layer; then prose tone).

## Intent and the why

The user's ideal: the player reads something very close to a page of the source author (Sapkowski for the Witcher) while taking part in it. The main fear is that the text will not feel like a book because of AI traits. The most visible one is averaging: every reply is a polished, mid-length, complete answer to everything at once, with a gesture, in the same voice. "Not like character.ai."

Measured on 2026-10-20: in the Ukrainian Witcher books the spoken part of a dialogue line has a median of 10 words, 21% of lines have 1–3 words and 17% have over 30. Our NPC lines from the task 15 style bake-off (378 lines) have a median of 32–38 words, 0% at 1–3 words, and 50–62% over 30. Every turn also has the same shape: narration, then NPC lines with gestures.

The engine is world-agnostic, so "the feel of the source" cannot be hard-coded for the Witcher. It comes from each world's reference texts.

## Goals

1. **World profile.** A per-world profile computed from that world's reference corpus (`data/witcher_books.txt` for the Witcher), stored under `worlds/<world>/profile.json` (numbers only, no text). It describes dialogue rhythm:
   - distribution of spoken-line length;
   - how often the speaker changes, and runs of one speaker;
   - share of lines that are questions, including questions answered with a question;
   - share of lines with no gesture or speech tag;
   - share of lines addressed to someone other than the last speaker, where the text allows it;
   - share of narration between lines, and its length;
   - in scenes with 3+ speakers, how talk is spread between them.

   The method must work on any text in the same format and be documented, so a new world gets its profile by running one command on its corpus.
2. **Response shape before text.** Before an NPC call, the scene director decides the shape of that NPC's response: silence, gesture only, one word, short, normal, long. The decision draws on the character (core voice and temperament), mood, what was just said, who was addressed and the tempo of the exchange. The world profile is the prior. Code enforces the shape:
   - the NPC call is told the shape;
   - an output far outside it is regenerated once, then trimmed at a sentence boundary;
   - silence and gesture-only are legitimate results.
3. **Narration only when needed.** In a quick exchange there is no narrator call at all; the turn is just the lines. The director decides per turn whether narration is needed (scene change, an action, a pause worth describing, arrival of someone). This also makes quick exchanges faster.
4. **Gestures are not mandatory.** The style sheet and NPC prompt stop pushing a beat into every line. The share of lines with beats follows the profile.
5. **NPCs talk to each other.** In base mode the director may let NPCs exchange several lines among themselves: argue, interrupt, tease, answer the wrong question. The floor returns to the player as soon as someone addresses the player, or the exchange naturally dies down. The player may cut in at any time (the existing interrupt). A hard cap on lines per world beat keeps a runaway exchange from running on (builder picks the number and records it).
6. **Each line reacts to the last thing said**, not to a summary of the whole situation. The NPC context makes the last line or lines prominent. Unfinished thoughts, evasions, jokes instead of answers and questions back are allowed. Each character keeps its own manner through the scene: the immutable core from task 19 plus manner notes from task 15.
7. **Measurement.**
   - **Automatic.** The same metrics as the profile, computed over a played session and over generated test scenes, with the distance to the profile reported. A test fails if, after this work, the share of 1–3-word lines in a long test scene is still 0 or the median length is still over twice the profile's.
   - **Reference scenes.** Find multi-speaker dialogue scenes in the books by speaker count and density. The user remembers one: Rinde near the end of the story "Останнє бажання" (Jaskier, Geralt, a priest and probably the mayor arguing while the djinn wrecks the town and Yennefer tries to bind it). Use a few of them as test situations: same setup, the engine generates, then compare against the profile and against the book scene's numbers. Never commit book text beyond a sentence.
   - **Blind A/B for the user.** On the phone, like `app/static/ab.html`: book-like or not, old engine vs new engine.
8. **Decision count.** The user wants to see how many decisions the engine makes per player action, per scene and per session, out of interest and for the repo. Count every typed judgment, every LLM call by role and every code-made choice that the debug log records. Show the counts in the debug view per turn. Write a short report with real numbers from a played session (`reports/decisions_count.md`) and add a section to `README.md`.

## Non-goals

- Changing what characters decide (project 2) or the prose voice of the model (project 3).
- The live real-time scene mode (later; the director work here should make it easier).
- Re-tuning the model choice per role, unless a role clearly cannot follow shape instructions. Then report it and propose a bake-off rather than switching silently.

## Anti-goals (a failure even if it technically works)

- Short lines that feel clipped or rude for no reason: shortness must come from the character and the moment.
- NPC-to-NPC chatter that takes the scene away from the player, or runs on while the player waits.
- Hitting the profile's numbers with text that still reads as AI. The numbers are a guide; the user's blind judgement decides.
- Anything Witcher-specific in code. World specifics live in `worlds/<world>/`.

## Constraints

- `docs/decisions.md` is the source of truth. Relevant: scene modes (director-based base mode), free prose with no JSON on creative calls, narrator never writes NPC speech, NPC calls may write only their own small actions, names never distorted, epistemic isolation.
- Cheap models only (price policy in `docs/decisions.md`); typed decisions go to the first-line decider with the existing escalation rule.
- The fast/slow turn loop from task 19 stays. New fast-lane calls must justify their latency; report seconds to first word before and after.
- Budget for live checks: under 0.60 USD.
- Never commit `data/`, `campaigns/`, `.env`, or book text beyond a sentence.

## Decided

- The order of the three projects: dialogue first (this), then decisions, then tone (user, 2026-10-21).
- Agreed by the user: NPCs may talk among themselves, and the floor returns to the player when addressed or when talk dies down. The yardstick is the source's feel and its numbers, with the user's blind judgement as the final say. Count decisions per action, scene and session. Sapkowski is an example, not a script; other worlds get their own profile.
- The lead's calls: the shape categories above, narration optional per turn, `worlds/<world>/profile.json` as the storage, the A/B page as the user-facing check.

## Settled after the builder check (the lead's calls unless marked)

- **A world beat = one player turn (base mode).** The whole NPC exchange runs inside one `turn()`: narration if needed, then up to the cap of NPC lines, chosen one after another by the director, each line hearing the previous ones. Extraction runs once in the slow lane over the whole exchange. This replaces the fixed `MAX_SPEAKERS = 2` with the director's choice plus a cap. The world waits for the player afterwards, as base mode requires. Live mode stays a non-goal.
- **Cutting in.** The input box stays open while NPCs talk. Sending a message mid-exchange acts as the existing interrupt at the current point (the unsaid remainder becomes the NPC's private intent), and then the player's text is the next turn. The interrupt button works as now. The retroactive window stays "the last NPC utterance" (`docs/decisions.md`).
- **Reference scenes.** The player character is a silent onlooker placed in the scene (an unnamed bystander), and only canon characters talk. Book-scene numbers are computed without the protagonist's lines when the protagonist is not among the engine's speakers, so the comparison is like for like. Scene setups are written as short summaries in our own words: who is there, what is going on, what each wants. They are never inputs copied from the book. Off-stage forces such as the djinn come in as narrated events.
- **Tests.**
  - `pytest` with fakes checks the mechanics only: shape passed to the call, the over-length fallback, optional narration, the cap, cutting in, decision counts.
  - Whether real models follow the shapes is a live check script. It runs 3 reference scenes and 2 long inn sessions (20 turns each), and its numbers go in the report.
  - A recorded cassette may be kept under `campaigns/` (not committed) for re-runs. Refreshing it is the builder's job whenever prompts change.
- **A/B for the user.**
  - Old engine vs new engine on the same situations. The unit is a whole short exchange (narration if any plus the lines), not one reply. The old path stays runnable behind a setting long enough to generate the pairs.
  - No book text on the page.
  - The project counts as built when the automatic numbers meet the goals. The user's blind verdict then decides whether the work is accepted or goes another round (the user's rule: their judgement is final).

## Left to the builder

- Exact metric definitions where the text is ambiguous (how to detect addressee, how to split speech from beats in the corpus). Document the choices.
- How the director asks for shape (one batched decision with the speaker choice, or separate). Latency decides.
- The cap on NPC-to-NPC lines per beat, and how "the exchange died down" is judged.
- How the trimming fallback works for over-long output.
- Which reference scenes besides Rinde; pick by measurable criteria and list them.
