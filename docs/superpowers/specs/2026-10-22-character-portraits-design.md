# Character portraits — design

Date: 2026-10-22. Status: draft for the user's approval.

## Intent and the why

NPC profiles today are short: a description, an appearance line, a manner sentence (task 15) and an immutable `core` (task 19). The models fill everything else with generic behaviour. In the round-2 blind test, all 15 texts made Yennefer the same thing: a "cold clerk-shopkeeper". She doesn't look up from her papers, echoes the player's words, and turns to money. The user's point: a rich character is a contrast ("a hedgehog to strangers, but the same needles become play and warmth in some circumstances"), and six tags cannot carry that. Goal: **the model stops guessing who the character is in this moment**.

Research behind this design:
- `reports/research/characters_yennefer.md`: Yennefer from the books, with about 10 stances by relationship × situation, the triggers that switch them, hidden layers and how they leak, and checkable speech features.
- `reports/research/characters_methods.md`: current methods. Character-arc and stance profiles beat flat traits (ArcANE 2026). Models drift to a polite-assistant default ("trait inertia"). An inner thought only in hard scenes is cheap (PersonaForge).

## Goals

1. **A portrait per important character**, replacing the flat profile as the source of truth for how they behave. Parts:
   - **Core paradox:** 1–2 sentences on the tension that drives them.
   - **Stances:** 6–10 rows of *relationship × situation → stance*. Each row covers what the character does and how they sound, with an optional "tail" (the action that follows a jab, e.g. Yennefer's water or examination in play mode).
   - **Switches:** ≤10 triggers, each an *event kind → which way the relationship moves, how strongly, for how long* (warm-up, flare-up, leak).
   - **Hidden layer:** what they never name, with leak channels (a secret action, an address-form change, lines getting shorter, a gesture). At most one leak per scene.
   - **Voice:** checkable rules (typical line length, address forms as a "thermometer" per relationship, politeness as a weapon or not, signature phrases at most one per line) and bans (things this character never says or does).
   - **3–4 short example lines**, written by us in 2–3 different stances, never copied from a book.
2. **Relationship state per pair** (NPC → person, the player first) stored in the event log, like attitudes today. It is a small record: kind (stranger, client, ally, close, rival, enemy, subordinate…), warmth, trust, and a short reason. Typed judgments after a turn (the decision layer, existing judge/decider) apply the portrait's switches, and they never update it silently from model prose.
3. **Slice per call.** The NPC call never sees the whole portrait. It gets a slice of about 250 words: the core, the current stance row (chosen in code from relationship state + situation: who holds power, whether there is an audience, the stakes), that stance's voice rules and example lines, the bans, and the leak allowed this scene (if any).
4. **Where portraits come from:**
   - *Canon characters* (those in the ingested arc: Geralt, Velerad, Foltest, the innkeeper and others; plus Yennefer as the showcase, see below): built semi-automatically from the local book text in several passes:
     - gather the character's scenes;
     - classify relationship, situation and stance;
     - extract switches, address forms and speech statistics;
     - write the portrait in our own words.

     Then a review pass: the lead reads it, and the user can edit. Expected about 60–70% automatic. Portraits are stored in the world folder (`worlds/witcher/portraits/<id>.yaml`), committed, with no book excerpts beyond a few words.
   - *Invented NPCs:* a short portrait (core, 3–4 stances, 3 switches, voice, 2 examples) generated once when the NPC is created (npcgen), only for NPCs who matter (named, recurring, or set in a game package). Background extras keep the cheap profile.
   - *Game packages:* a package may give a person a free-text portrait. The importer turns it into the structured form once, at game start.
5. **Fix the canon name form:** the translation uses **Йеннефер**. Any of our test scenes and docs that say «Єніфер» are fixed, and the glossary check catches it.

## Non-goals

- Fine-tuning or training a model.
- Rewriting the narrator's style (separate work: prose tone, project 3).
- Portraits for every background extra.
- Long-term character growth across months of game time (the portrait is fixed; only relationships move). Later.

## Anti-goals

- A character who "performs" the portrait: every line a signature phrase, every reply a stance announcement, overacted traits.
- Example lines copied into play (n-gram copying is measured; examples are dropped if they leak).
- The character naming their hidden layer outright.
- Slower first words. The slice is assembled in code; no extra model call on the fast lane, except an optional inner thought (below) only in hard scenes, and only if it pays off.
- Big blind-grading pages (the user rejected them). Quality is judged by the user's 👍/👎 in play plus at most 3–4 finalist pairs.

## Constraints

- **Engine:** Python, SQLite event log, a single connection per engine, fast and slow lanes. Relationship updates go on the slow lane.
- **Cheap models only** (mimo-v2.6-flash for NPCs now). The slice must fit their context and attention: about 250 words.
- **Knowledge stays the knowledge layer's job:** a portrait never gives an NPC facts it has not learned, and names stay knowledge.
- **The player character is the player's:** portraits apply to NPCs only. The player's own character sheet is unchanged.
- **Content:** never commit `data/`, nor book excerpts beyond a few words. Portraits are our own paraphrase.
- **Budget:** each experiment brief states one; canon extraction for the arc's ~10 characters should stay under $1 total (needs the user's OK if more).

## Decided (lead's calls, the user agreed to the outline on 2026-10-22)

- The structure above (core, stances, switches, hidden + leaks, voice, examples) and the per-call slice of about 250 words.
- Stance selection in code from relationship state and situation, not by the model guessing.
- Relationship state in the event log, updated by typed judgments.
- Canon portraits semi-automatic from the book, with review. Invented NPCs get short portraits only if they matter.
- Evaluation: the user's in-play 👍/👎 (ratings report per model and role), plus a few finalist pairs for Yennefer specifically.

## Settled after the builder check (lead's calls)

- **One phase per portrait.** A canon portrait describes the character in one phase of their story (`phase` field: book/story and a time span). Blending phases gives an anachronistic composite. Yennefer's first portrait is the **Rinde phase** («Останнє бажання»: first meeting with Geralt), which matches the test scene. More phases later, picked by the game date.
- **A playable Yennefer scene is in scope.** It is a game package with a free start in Rinde (a room she rents in a merchant's house, the player a stranger asking for help), committed under `worlds/witcher/packages/`. The «Останнє бажання» story is *not* ingested into the canon store in this project; that is later work.
- **Relationship pairs:** dynamic state for NPC→player. It starts from stranger, or from a package's `attitude`/`knows_player`. NPC→NPC relations are static in this version: a portrait may list relations (for example Yennefer→Geralt in a later phase), seeded once at start and used for stance selection in NPC exchanges, but not updated by judgments yet.
- **Canon extraction is agent work, not a pipeline.** Claude Code agents read the local book (free, as the project rules say) with throwaway helper scripts in `experiments/portraits/`, and write the YAML portraits once. There are no paid API calls, so no extraction budget. "60–70% automatic" is an estimate, not an acceptance bar. The bar is the lead's review plus the user's play.
- **Judges see the relationship too.** The outcome judge (agree, refuse, help) and the scene director get the NPC's current relationship to the player and its stance as one line, so a warm stance cannot get a cold outcome. Trust feeding belief (what an NPC believes from whom) is noted for later, not built now.
- **Name form:** «Єніфер» joins the glossary's wrong forms of Йеннефер. Our round-2 test files are corrected.

## Left to the builder

- Exact YAML schema and field sizes, within the parts above.
- The situation features (power, audience, stakes): where they come from (scene, outcome, director) and how they are computed.
- How the switches map to typed judgment questions, and decay over time.
- Whether an inner thought before speaking is added for hard scenes. A/B it on cost and effect; keep it out unless it clearly helps.
- Migration: existing `manner` and `core` fields become the fallback for characters without a portrait.
- Which canon characters to do first. Yennefer is the showcase, then those who actually appear in the Vizima starts.
