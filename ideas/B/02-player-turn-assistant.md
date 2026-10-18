# B2. Player turn assistant

Session B, task 5. No code, no paid calls. Web pages read on 2026-10-19. Labels: **[User]**, **[Added]**, **[Found]** (with link).

## 1. Seed

[User] "The user often does not want to write out actions or lines. Wanted: generate an action or line from scratch; correct a generated draft by feedback in words ('this part was great, this was extra, and here is a new idea'), which the user has not seen done anywhere; improve something the user already wrote. Whether the assistant learns the user's style from feedback over time is a setting. Constraint already known: the assistant may only use what the player character knows, otherwise it becomes a leak channel. The user worries it can slide into generic slop; the goal is less friction and more enjoyment."

## 2. Completed idea

### 2.1 Three jobs, one pipeline [Added]
1. **Generate** from nothing (or from a one-line nudge: "be rude", "ask about the ring").
2. **Revise by words**: the user's feedback is a mix of *keep*, *drop*, *add* and *tone*. This is the new part.
3. **Polish** the user's own text (fix, tighten, in-character voice) without changing what they meant.

All three produce a **draft**. A draft is not a world event. It lives in a side store (per turn, versioned) and becomes an event only on *send*, as the player's action/line. Discarded drafts leave no trace in the log, so they cannot leak into NPC memory and need no rollback.

### 2.2 The knowledge boundary is the whole safety design [Added]
The decisions already say the PC is a being like any other. So the assistant's context is built by the **same retrieval as the PC's own context**: PC-known facts (witnessed, heard, self-known by B1), the scene as the PC perceives it, the PC's known goals and relationships. Never the narrator's omniscient view. Three leak paths to close, in descending danger:

1. **Context leak**: the assistant is given facts the PC lacks. Closed by construction (filter, not instruction); `reports/experiments/E1.md` supports this: instructing "do not use X" is weaker than not providing X.
2. **Pretraining leak**: for the Witcher, the model knows the saga (E1: about 5% of canon-case replies in the filtered condition leaked through pretraining). The assistant may "helpfully" write a line that uses a book secret the PC does not know. Needs an **output-side check**: one typed judgment on each draft: "does this draft rely on a fact the PC has no channel to know?" (E1 and E2: Jev handles narrow yes/no checks at about 0.28 s and sub-cent per thousand).
3. **Player-knowledge leak**: the *user* knows things the PC does not (they read the debug view, or a previous scene was narrated omnisciently). If the user types it, it is their choice. If the assistant picks it up from the user's feedback ("make him mention the king's illness"), the check in (2) fires and the draft is flagged, not silently rewritten. A setting decides whether the user may knowingly override (B5).

Noted gap: the check needs the PC's channel graph. Scenes where the PC *could* know but has not been shown it (an unread letter) are the borderline cases for the salience/channel judgment.

### 2.3 Revise by words: what is actually being done [Added]
User feedback like "the first sentence is great, drop the threat, add that he laughs it off" is a small program over the draft. Doing it as a single "regenerate with feedback" call loses the part the user liked, because the model re-rolls everything. The missing piece is **units with identity**: split the draft into units (sentences or beats), number them, and parse the feedback into operations on those units.

### 2.4 Slop [Added]
The user's worry is valid and has a mechanical cause: the assistant's own previous output is the most available style example, so it drifts toward its own average. Mitigations that fit this engine:
- Style examples come from **what the user actually sent** (final text after the user's edits), never from drafts the assistant produced and the user did not touch.
- Offer **different intents, not different wordings**: three drafts that do three different things (press, deflect, buy time) beat three paraphrases.
- Keep a short, user-visible **ban/avoid list** learned from rejections ("dismissive 'I see'", "narrator-voiced introspection").
- Length control: default short. Most slop is length.

## 3. Options

### Option A. Whole-draft regeneration with feedback in the prompt
- **How:** one LLM call with: PC-known context, last draft, the user's feedback text. Output: new draft. A Jev call checks the knowledge boundary.
- **Strengths:** simplest; works with any model; zero UI.
- **Weaknesses:** "this part was great" is not guaranteed to survive; the user has to re-read everything each time; drift toward the model's average on every retry.
- **Cost:** 1 generation + 1 Jev check per iteration; about 2-4 s.

### Option B. Unit-level edit: feedback becomes keep/drop/add/tone operations, code applies them
- **How:** (1) the draft is stored as numbered units. (2) One small LLM call turns the user's words into a typed edit list `{keep:[ids], drop:[ids], add:"idea in the user's words", tone:"..."}`; ambiguity is allowed (`unclear: [ids]`). (3) Code applies keep/drop literally, so kept units are **byte-identical**. (4) A second generation only *writes the added idea and the seams* between kept units. (5) Jev boundary check on the whole result; if flagged, the unit that triggered it is marked and the user sees why in plain words.
- **Strengths:** preserves what the user liked by construction; the user reads only what changed; the edit list is auditable and can feed learning (2.5). This is the capability the user says they have not seen.
- **Weaknesses:** two calls; the parse step can misread "this" (which unit?). Mitigation: the UI shows the parse ("keeping 1, 3; dropping 2; adding: he laughs it off") before generating, one tap to confirm or correct.
- **Cost:** 2 LLM calls + 1 Jev check; 3-6 s. The parse call is small and could be a cheaper model.

### Option C. Direct manipulation: tap a unit for keep / drop / rewrite, plus an optional spoken or typed note
- **How:** the draft is shown as units; each can be marked by tap (and a note typed or dictated). Feedback in words remains possible as the note. Equivalent edit list as B, but the parse is trivial.
- **Strengths:** fastest on a phone, no ambiguity, no parse errors; good for "I just want to nudge this".
- **Weaknesses:** less "talk to it" feel, more UI. It does not need to replace B; B's parse can fill the same data structure from free text.
- **Cost:** only the add/seam generation + Jev check (1 + 1).

### Option D. Intent menu first, expand second
- **How:** before generating text, show 3-4 one-line **intents** in the PC's voice ("press him on the toll", "pretend not to hear", "ask about the missing cart"). The user taps one (or edits it); only then is the line or action written.
- **Strengths:** least reading; the choice is about what to do, which is the interesting part; avoids slop because the user picks the direction. Also a good wide-open mode for "I do not know what to do".
- **Weaknesses:** one more tap for people who already know; the menu itself can be generic if not conditioned on the PC's goals and the scene.
- **Cost:** 1 small generation for the menu, 1 for the expansion, 1 Jev check.

### Reading the options
- If **preserving the user's voice and the good parts** matters most: B (with C's tap UI as an input method).
- If **speed on a phone** matters most: C or D.
- If **you want the minimum to prove it works**: A first, but expect the user to feel the "re-rolled everything" problem, because it is exactly the thing the seed asks to avoid.
- Polish (job 3) is the same as B with an empty `add` and a `keep all, tone: fix` instruction; generate-from-scratch is D or a nudge into A.

### 2.5 Learning the user's style (setting) [Added]
Three levels, all stored as **readable text the user can edit**, not hidden weights:
- **Off:** no memory beyond the current scene.
- **Session:** a short style note for this campaign, written by the assistant from the edit lists and final sends (what was kept, what was dropped, recurring added phrases).
- **Persistent:** a profile across campaigns.

[Found] This is the PRELUDE/CIPHER setting studied in *Aligning LLM Agents by Learning Latent Preference from User Edits* (NeurIPS 2024): the model infers a **description of the user's preference** from their edits, retrieves the descriptions from the k nearest past contexts, and prompts with the aggregate, avoiding fine-tuning ([Microsoft Research page](https://www.microsoft.com/en-us/research/publication/aligning-llm-agents-by-learning-latent-preference-from-user-edits/), [NeurIPS poster](https://neurips.cc/virtual/2024/poster/96078)). In the paper, it lowered the edit distance on summarisation and email tasks with a small extra LLM cost. Caveat: evaluated with a simulated (GPT-4) user on those two tasks, not on role-play; whether it avoids slop here is untested.

## 4. Prior art
- [Found] **AI Dungeon**: *Do / Say / Story* input modes, *Retry* with a retry stack, in-place editing of AI text, an `/alter` command ([help: Do mode](https://help.aidungeon.io/faq/do-mode), [Say mode](https://help.aidungeon.io/faq/say-mode), [Story mode](https://help.aidungeon.io/faq/story-mode), [How to play](https://help.aidungeon.io/faq/how-to-play)). Feedback is by *retrying or hand-editing*, not by words about the draft.
- [Found] **SillyTavern Guided Generations extension**: first-, second- and third-person *Impersonate*, *Guided Response* (type an instruction, press the button, the instruction is injected temporarily), *Guided Continue*, *Guided Swipe* ([settings wiki](https://github.com/Samueras/GuidedGenerations-Extension/wiki/Settings), [action buttons](https://github.com/Samueras/GuidedGenerations-Extension/wiki/ActionButtons)). Closest to "generate from a nudge" and "one-shot guidance"; none of the pages I read describes unit-level keep/drop. The claim "nobody does keep/drop by words" is only that: I did not find it, which is not proof.
- [Found] **PRELUDE / CIPHER** (above) for learning from edits.
- [Found] Academic framing: LLM player assistants that choose actions and explain them, and "fluctuating agency" when the model proposes the options ([survey, arXiv 2402.18659](https://arxiv.org/pdf/2402.18659); the search summary I read is secondary, so treat the agency claim as a pointer, not a result).
- Own study: Multihog's DnD framework and Concordia have no player-side assistant (`reports/code_study/`).

## 5. Interactions
- **Decisions:** epistemic isolation (the boundary check is the same filter as NPC contexts, applied on the player's side); event log (drafts stay out of it; *send* is the event); model-agnostic (the parse call can use a cheap model).
- **B1:** the assistant reads the self-known projection, so it cannot reveal an unnoticed poison.
- **B3:** with interruption, a draft may be half-typed when the NPC speaks; the draft survives, and "the user began to answer" is only recorded if actually sent. Quick reactions are drafts-of-zero-length.
- **B5:** learning level, length default, whether the user may knowingly override the knowledge boundary, whether drafts are shown automatically or on request.
- **Session A:** A2 (what the PC believes, not just knows, shapes what the assistant offers).

## 6. Questions for the user
1. Коли ти кажеш "ця частина була чудова", чи має вона після правки лишитись слово в слово, чи можна її трохи переписати?
2. Чи хочеш ти спершу бачити короткі варіанти намірів ("натиснути", "ухилитись", "виграти час"), чи одразу готовий текст?
3. Чи має помічник сам показувати чернетку після кожного ходу, чи лише коли ти просиш?
4. Якщо ти сам напишеш у відгуку щось, чого твій персонаж не знає, помічник має це відхилити, чи лише попередити тебе?
5. Чи готовий ти дозволити помічнику вести коротку "нотатку про твій стиль", яку ти можеш читати й правити, щоб він з часом звучав більше як ти?
