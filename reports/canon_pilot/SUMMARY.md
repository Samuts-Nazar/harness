# Task 13: Canon ingestion pilot — "Останнє бажання": "Голос розуму-1" + "Відьмак" (2026-10-19)

Written by the lead from the worker's final report (the worker's file tool refused report files). Code: `harness/canon/`. Gold calendar and error taxonomy: `reports/canon_pilot/gold_notes.md`. Stores and raw replies: `campaigns/canon/` (git-ignored). Spend: about 0.19 USD of 0.60.

## Verdict
- **Facts are good, time is not.** Best run: `deepseek/deepseek-v4.1-flash-1017` with the v2 pipeline (scene-timeline pass, window split on bad JSON, name glossary). All 80 events read against the text: 2 wrong facts, 0 invented, 0 distorted names after the glossary. But 24 of 80 (30%) carry the wrong story day, and no event has a place.
- **Isolation held in 10 of 10 retrieval questions** (nobody got a record they could not know); only 6 of 10 answers were useful.
- **Recommended ingestion model: `deepseek/deepseek-v4.1-flash-1017`**: all 17 must-have events, lowest error rate, about 0.013 USD for the arc (v2). `openai/gpt-6-luna` flattens backstory time and drops knowers; `qwen/qwen3.8-omni-flash` is unusable (27% wrong facts, 19 of 55 quotes not in the text).
- **Do not extend to more stories yet.** Fix the list at the end first.

## Per model (every record read; counts about ±3)
| run | events | USD | time | wrong fact | invented | wrong time | place | knower extra | knower missing | names | wrong reaction | missing event | bad quote |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| deepseek v1 | 124 | 0.063 | 142 s | 2 | 0 | 46 (+18 lost) | 25 wrong | 1 | 32 | 0 (18 in Ukrainian) | 2 | 0 | 0 |
| luna v1 | 88 | 0.035 | 348 s | 2 | 0 | 40 (+13 lost) | 8 | 3 | 34 | 5 + 2 dup. entities | 3 | 1 | 5 |
| qwen v1 | 55 | 0.023 | 359 s | 15 | 3 | 18 (+5 lost) | 12 | 4 | 35 | 22 | 4 | 4 | 19 |
| **deepseek v2 + glossary** | 80 | 0.013 | 390 s | 2 | 0 | 24 | all empty | 0 | 12 | 0 | 6 of 35 | 0 | 1 |
| luna on deepseek timeline | 71 | 0.019 | 200 s | 1 | 0 | 29 | all empty | 2 | 15 | 8 | — | 1 | 1 |

Examples: qwen invented "1500 orens upfront" (the witcher refuses advance pay); deepseek v1 set Velerad's office talk in the tavern; luna marked the miller and Velerad "witnessed" for an attack nobody present saw. Good: Ostrit's confession is known only to Geralt; Velerad's tellings give Geralt `told<Велерад` rows.

## Why v2 helped
All three models lost count of story days in the second half. A separate scene-timeline pass by deepseek got the fight night (day 7) and awakening (day 9) right, still one day late on the audience and the miller. Window splitting saved 29 events lost to cut-off replies.

## Glossary
`harness/canon/glossary_witcher_arc1.json` (34 entries: canonical form, variants, oblique cases, proper/common) + `harness/canon/glossary.py`. Removed every Latin spelling of Foltest, Geralt, Velerad, Segelen, Adda. Limit: a Latin possessive becomes a Ukrainian genitive inside English text ("Фольтеста sister").

## Starting situations for Ragnar (the user picks)
From the chronicle: Ragnar and Geralt born 1174, left Kaer Morhen with Eskel in March 1193 and parted at a crossroads; Ragnar has black hair, marble skin, golden eyes, black claws, Chaos and black blood; trained in signs and potions.

- **A. The empty tavern, day 3 evening.** Ragnar rides in and stops at «Під Лисом» two days after the killing. The town talks of a white-haired Rivian now lodged at the palace guardhouse. Ragnar knows the proclamation and strzyga lore, not that Geralt is here. Least canon pressure.
- **B. Eve of the fight, day 6, north shore of the lake.** Townsfolk bolting doors for the full moon; a villager says a witcher went into the old palace today. Ostrit's plot, the fight and the sarcophagus are still ahead. Highest stakes, strongest canon pull.
- **C. The morning after, day 8, Vizima.** Geralt asleep and bandaged above the guardhouse with the 3000 orens; the king shouting; the princess alive; townsfolk trading versions. No scheduled canon event pending, only reactions: the safest test of "does the world behave like a simulation".

Open point: the book's Geralt is experienced and known; the chronicle's Geralt is Ragnar's age. All three keep him as Geralt and leave his age open.

## Retrieval check (10 questions, deepseek v2 store)
Right or no leak: 2, 3, 4 (ranking weak), 5 (noise instead of nothing), 6, 8, 10. Misses: 1 (no knower row for Velerad on the tavern events), 7 (time shift), 9 (Velerad on day 8 should know the outcome). Weak spots: Ukrainian queries vs English event text, no relevance cutoff, incomplete knowers, time shift.

## Must improve before extending
1. Day tracking: code check (monotonic days, cue words), second-model vote on the timeline, day ranges for vague cues.
2. Place: link scene places to entity ids.
3. Knowers: auto-add present participants; an "informed by" rule for officials stating unwitnessed facts; tellers are not "witnessed".
4. Retrieval: Ukrainian gist or embeddings; relevance cutoff; resolve persons before collectives.
5. Reactions: 6 of 35 wrong; consider a separate reaction pass with a "none" option.
6. Review: keep an agent review of records; unreviewed canon is permanent (gap G-6).
7. Cost at scale: the whole file is about 93× this arc, roughly 1.2–5.9 USD with these prompts (each window repeats the entity list); shorten or cache before scaling.
8. Not tried: `nvidia/nemotron-3.5-super-vl`, `xiaomi/mimo-v2.6-flash`, `z-ai/glm-5.3-flash`.
