# Task 14: Names are knowledge; "how does he know that?"; fixes from the first play test

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md`, `docs/tools.md`, `app/README.md`, assumptions 70–82.
Task 15 (style) runs at the same time and changes narrator/NPC prompt wording in a new style module; keep your prompt changes to the context data (who/what is shown), not wording/style, and keep them in `harness/context.py` functions it can call.

## Bug found by the user in play
In the inn scene Горст addressed the player as "Рагнаре" with no channel for the name (campaign `campaigns/inn-20261019-191047`; the seed "You, Рагнар, came to Брідки…" is known only to the player). Cause: `harness/context.py` renders every present character by real display name (`self.name(c)`) in NPC and narrator contexts, regardless of whether the viewer knows that name.

## 1. Names are knowledge
- A character knows another's name only through a channel (introduced, overheard, told, own life / prior acquaintance, canon). Until then the context renders that person by what the viewer can observe (e.g. "незнайомець із мечем за спиною, золоті очі"), stable within a scene so the model can tell people apart.
- Learning a name is a fact with a source like any other (introducing oneself, someone else saying it). Detection: the extractor and/or a decider on utterances that contain a name.
- Same for the narrator: it speaks from the player character's perception, so a stranger stays unnamed until the player character learns the name.
- The NPC output check also checks names: addressing someone by a name the speaker does not know is a leak.
- Tests with fake providers: the original bug (stranger addressed by name) is caught; after an introduction it is allowed.

## 2. "How does he know that?" (user decision)
- Model-error flow for knowledge leaks: the player marks an NPC line and says "he could not know this". The engine checks the speaker's channels for the claim (facts with knowers/sources, life background when it exists, names).
  - No channel: regenerate that line with the player's explanation; store the explanation per campaign (decisions: model-error button).
  - Channel exists: tell the player how the character knows it. In play show only the channel type and rough time ("чув від когось у селі два дні тому"); the full event goes behind a "показати (спойлер)" tap and in the debug view.
- In the debug view: per character, what they know and from where (fact, how, source, when), so the user can check knowledge directly.

## 3. Player actions vs speech
- The user writes actions in asterisks (`*не піднімаючи очей…*`) and speech as plain text. Today all player input is treated as speech (assumption 11). Split them: actions become observable actions (perceived by those present per normal rules); only speech is "said". Keep the player's text verbatim.

## 4. Smaller fixes from task 12
- An invalid extractor state change (e.g. revealing an item that is not in that category) drops that one change and logs it; it no longer rejects the whole turn.
- An NPC gets "what I already said in this scene" (its own recent lines, short) in context, so it does not repeat the same advice in new words. Measure on a 10-turn live session.
- Scene director: the innkeeper/addressed NPC is often missed when narration ends before he replies; fix the question or inputs, re-measure on the task 12 set (23/27 now).
- One glossary: merge `harness/canon/glossary.py` + `harness/canon/glossary_witcher_arc1.json` into `harness/glossary.py` + `worlds/witcher/glossary.json` (one format, one loader; keep `cases` and the proper/common flag). Check every form against the Ukrainian book text by counting.

## Tests and budget
All tests pass (report the count); new tests per item; Playwright phone check passes. Live checks under 0.30 USD.

## Output
Full report in the final message (what changed, tests, live numbers, spend, open questions, branch and worktree as absolute paths).
