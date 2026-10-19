# Task 5: Idea development (no code)

Work fully autonomously. Do not ask questions during the task; collect them for the user in the output instead.

This brief covers two separate sessions. Run the one you are told to run: **Session A (world and simulation)** or **Session B (player experience)**. Each session writes its own output files and never edits the other's.

## Purpose

The user's ideas are as important as the implementation, and most of what the user says is a raw idea, not a finished instruction. Your job is to take each idea, think it through, make it complete, find what others have done, and turn it into well-structured options the user can decide on. You do not decide. You propose.

## Rules

- Read `docs/decisions.md` first. Closed decisions are fixed; build on them, do not reopen them. If you find a real problem with a closed decision, note it in a separate "Possible conflicts" section with the evidence; do not change the document.
- Do not edit `docs/decisions.md`, do not write engine code, do not change `harness/`.
- No paid API calls of any kind. Web search and reading pages are fine. Any judging or comparing is done by you.
- Separate clearly: what the user said (quote the seed), what you added, what you found elsewhere (with source links and dates).
- Be concrete. Each option must say how it would work in this engine (which records, which judgments, which calls), not only what it is.
- Frame recommendations as conditions ("if X matters most, choose A; if Y, choose B"), not verdicts.
- Where a topic is large, prefer depth on a few key questions over a shallow list of everything.

## Output format (per topic)

1. Seed: the user's idea as stated below.
2. Completed idea: the fuller version, with the parts the user did not mention but the idea needs.
3. Options: 2 to 4 ways to realise it, each with how it works in this engine, strengths, weaknesses, cost in calls and latency.
4. Prior art: games, tabletop systems, papers, projects that do something similar, with links.
5. Interactions: which other topics or decisions it touches.
6. Questions for the user: short, plain Ukrainian, one sentence each, no jargon (or with the term explained in the same sentence). At most 5 per topic, most important first.

Write one file per topic under `ideas/A/` or `ideas/B/`, plus `ideas/A/SUMMARY.md` or `ideas/B/SUMMARY.md` that lists every topic, the main options in one line each, and all questions for the user collected in one place (in Ukrainian). Commit after each topic.

## Session A: world and simulation

Seeds (the user's own ideas, paraphrased from conversation):

1. **Information spread.** Quiet deeds stay with witnesses; loud deeds travel with time and distance and reach regions the player has never visited; people there hold different attitudes to them. Open: does the world propagate rumours continuously in the background, or lazily (decide what an NPC could have heard at the moment the player meets them, then record it permanently)? Do rumours distort as they travel?
2. **Belief and trust.** Every piece of knowledge has a source. How much a character believes it depends on trust and relationship with the source. The player character is a being of the world like any other, not a special case.
3. **Background world decisions.** Use many cheap typed judgments (Jev) for how the world develops and reacts: how did the world react to similar events in the original books, how does this campaign differ from the books, will this difference matter. Canon passages reach these judgments through retrieval (the books are about 9 MB of text; Jev's context is about 32K tokens).
4. **Off-screen agents.** Characters the player has met keep living: they pursue their own goals, and when met again they have something to tell. The whole world cannot be thousands of full agents (cost, speed); world development should be cheaper, full agents only on direct interaction.
5. **Mechanics without tabletop numbers.** The user wants a simulation, not a solo tabletop game. Ideas on the table, none decided: randomness models the environment, not the character's competence; probabilities could come from a judgment about the situation instead of stats; skills grow through training and practice; a long-built relationship must not collapse from one bad moment; combat must be unpredictable (enemies underestimated, extra monsters).
6. **Time.** Two modes to compare: turn-based, and flowing (silence counts as time passing; NPCs act without waiting). What happens during travel, sleep, long waits.

## Session B: player experience

Seeds:

1. **Live character state.** A panel per character carried from scene to scene. Draft list the user asked to make complete: body (wounds, scars, fatigue, hunger, thirst, illness, poisons and elixir toxicity, intoxication, pain); timed effects (elixirs, oils, curses, magic); appearance (clothing and its condition, dirt and blood, hair, visible marks); equipment (worn, in hand, sheathed, condition); inventory with location (on body, bag, horse) and money; companions (horse, people); standing (wanted, disguised, reputation by place); posture and action (sitting, hiding, weapon drawn); inner state (mood, stress, fears, worldview change). Each element observable or hidden. Others in a scene perceive the observable elements and may react. Open: the player sees a panel for their own character; should it show only what the character knows about itself (an unnoticed poison not shown), while the AI knows everything?
2. **Player turn assistant.** The user often does not want to write out actions or lines. Wanted: generate an action or line from scratch; correct a generated draft by feedback in words ("this part was great, this was extra, and here is a new idea"), which the user has not seen done anywhere; improve something the user already wrote. Whether the assistant learns the user's style from feedback over time is a setting. Constraint already known: the assistant may only use what the player character knows, otherwise it becomes a leak channel. The user worries it can slide into generic slop; the goal is less friction and more enjoyment.
3. **Breaking the chat format.** Not "world's turn, player's turn". Interruption by button, live and retroactive (already decided); text paced like speech; NPCs keep unsaid remainders as intents. What other interactive possibilities exist beyond these: reacting mid-scene, gestures, quick actions, ambient events.
4. **Immersion layers.** Background music by mood, voiced dialogue (Ukrainian), images and possibly animated scenes, growing as technology allows. Played on phone and laptop.
5. **Settings.** Which behaviours should be player settings (assistant learning, time mode, how much the player sees, content intensity, etc.).

## Final report

At the end, print a short summary: topics covered, the three most important open questions, and anything in `docs/decisions.md` that looks problematic.
