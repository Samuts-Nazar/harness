# Cost summary (task 6)

Live runs on OpenRouter + Jev, real `usage.cost` per call. Total API spend for this task: **$0.12** (the key's own daily counter; includes two aborted variant runs).

## Quick numbers

| What | Cost |
|---|---|
| **1 hour of play, 30 turns**, default stack (DeepSeek-v4-flash narrator+NPC, Haiku extractor) | **$0.04** |
| 1 hour, 60 turns, same | **$0.08** |
| 1 hour, 30 / 60 turns, all-Haiku-5.5 | $0.07 / $0.14 |
| 1 hour, 30 / 60 turns, all-Gemini-3.1-flash-lite | $0.10 / $0.20 |
| One turn (default stack) | $0.0013, ~14 calls, ~21 s of summed call time |

Off-screen agents, per **in-game day** (1 hour of play is about 0.1–0.2 in-game days at 5 min/turn):

| Option | 10 agents | 50 agents | 200 agents |
|---|---|---|---|
| (a) batched Jev tick | $0.0008 | $0.004 | $0.016 |
| (b) Jev tick + DeepSeek summary | $0.002 | $0.010 | $0.040 |
| (b) Jev tick + Haiku summary | $0.003 | $0.016 | $0.066 |
| (c) lazy, 3 meetings/day (Haiku catch-up) | $0.0015 | $0.0015 | $0.0015 |

Ingestion of all books (~5.0M characters, ~9 MB file), extrapolated from one chapter (70k chars):

| Model | Cost | Tokens in / out | Time (sequential / 8 parallel) |
|---|---|---|---|
| Haiku 5.5 | $0.84 | 2.5M / 1.2M | 1.6 h / 12 min |
| DeepSeek-v4-flash | $0.54 | 2.4M / 1.2M | 6.4 h / 48 min |
| Qwen3.5-9B (cheapest measured) | $0.32 | 2.1M / 0.8M | 2.9 h / 22 min |

**Reading it:** the turn loop dominates. Off-screen agents are cheap (cents per in-game day even at 200 agents). Ingestion is a one-off under a dollar. Turn cost is driven by judgments (about half) and regeneration, not by the big generation calls.

## Findings that change the picture

1. **Judgments are ~49% of default-stack cost.** Per turn: ~6 Jev calls ($0.000034 each) and ~4 Haiku escalation calls ($0.000114 each). 46 Haiku calls followed 71 Jev calls, so escalation is common (relationship magnitude goes to the LLM directly by design; unknown-claim and salience checks escalate often).
2. **Regeneration inflates generation cost.** 12 turns needed 19 narrator calls (9 narrator-speech rejections) and 25 NPC calls for 13 spoken lines (17 line rejections, 5 fallbacks to "I don't know what to tell you").
3. **The output check looks too strict as tuned, which is a quality problem, not only a cost one.** In the default run the two-NPC turn (5) and the second-hand turn (6) both ended in the fallback line. The all-Haiku run had 1 fallback but still 11 rejections. Cost numbers include all of this.
4. **A weaker extractor means failed turns.** With a Gemini-lite extractor one turn raised `ExtractionRejected` (turn rolled back, calls still paid). Two earlier variant runs crashed on it before I made the runner tolerant. The engine has no recovery beyond one retry.
5. **Context grows until the 10-event history cap (about turn 5), then plateaus** (narrator ~1.7k, NPC ~2.7k input tokens). Fact and memory lists grow with campaign length and nothing built so far caps them, so later turns will cost more than these 12-turn means.
6. **Language caveat.** The scene was played in English. Ukrainian measured about 2.4 characters per token on the book chapter; Ukrainian play will cost more per turn (my guess 1.3–1.6x for generation calls; not measured).
7. **Latency:** ~21 s of summed call time per turn, because calls run one after another (narrator 3.7 s, each NPC attempt 3.7 s, extractor 1.7 s, each Haiku judgment 1 s, each Jev call 0.27 s). Speed is a likelier problem than cost. Nothing is parallelised in the measured path, and time to first word was not measured.

## Scene

12 scripted player turns (`experiments/cost/run_scene.py`): arrival, questions to the innkeeper, a **two-NPC turn** (5), a **second-hand knowledge** case (6: the bard is asked what the innkeeper said; a seeded fact is also "told by innkeeper"), a claim the bard cannot know (9), a trust question (8). Setup cost $0.00005.

Calls per role are narrator/NPC/extractor/Jev/Haiku-judge:

| turn | calls | in tok | out tok | cost $ | call time s |
|--|--|--|--|--|--|
| 1 | 1/1/1/4/2 | 4053 | 1192 | 0.00068 | 16.2 |
| 2 | 3/2/1/9/5 | 12428 | 2135 | 0.00152 | 20.8 |
| 3 | 1/1/1/5/3 | 6724 | 968 | 0.00067 | 11.1 |
| 4 | 1/1/1/5/3 | 7117 | 1054 | 0.00079 | 17.6 |
| 5 (two NPCs) | 1/6/1/8/7 | 32378 | 2135 | 0.00257 | 42.8 |
| 6 (second-hand) | 1/3/1/5/4 | 16753 | 1387 | 0.00141 | 23.7 |
| 7 | 1/3/1/11/10 | 20120 | 2698 | 0.00188 | 34.0 |
| 8 | 1/1/1/4/2 | 8655 | 885 | 0.00081 | 7.2 |
| 9 (unknown to NPC) | 2/3/1/6/4 | 25242 | 1572 | 0.00211 | 20.4 |
| 10 | 3/1/1/6/2 | 12888 | 1661 | 0.00098 | 20.9 |
| 11 | 1/0/1/2/1 | 3673 | 731 | 0.00055 | 6.2 |
| 12 | 3/3/1/6/3 | 27320 | 1535 | 0.00215 | 28.6 |
| **mean** | 14.4 calls | 14779 | 1496 | **0.00134** | 20.8 |

Per role, default stack (all 12 turns):

| role | model | calls | $/call | in tok/call | out tok/call | s/call |
|--|--|--|--|--|--|--|
| narrator | deepseek-v4-flash | 19 | 0.000141 | 1367 | 236 | 3.73 |
| npc | deepseek-v4-flash | 25 | 0.000119 | 1710 | 186 | 3.69 |
| extractor | haiku-5.5 | 12 | 0.000233 | 792 | 307 | 1.72 |
| jev | jev-1.14 | 71 | 0.000034 | 813 | 41 | 0.27 |
| judge (escalation) | haiku-5.5 | 46 | 0.000114 | 901 | 48 | 1.01 |

Variants, same scene. Mean per turn: default $0.00134, all-Haiku $0.00233, all-Gemini-lite $0.00341. Per call: Haiku narrator $0.00045, Haiku NPC $0.00043; Gemini-lite narrator $0.00061, NPC $0.00076, extractor $0.00053 (Gemini-lite is the priciest per token here, $0.25/$1.50 per M). Full tables: `python -m experiments.cost.analyze`. Raw per-call logs: `calls.jsonl`, `variants/*/calls.jsonl` (sizes only, no prompt text).

## Off-screen agents: assumptions

Measured: Jev about $0.042 per million input tokens (output free), $0.000034 per in-scene call, 0.27 s; Haiku judgment $0.000114; DeepSeek call $0.000119 (1710 in / 186 out, below list price); Haiku list price $0.10 / $0.50 per M, which matched the measured extractor calls.

- (a) One tick per agent per day is one Jev call, ~1200 input tokens (state, day events, ~6 questions): $0.00005. Plus 25% of ticks escalate to one Haiku judgment ($0.000114). Total **$0.000079 per agent-day**.
- (b) = (a) + one summary call per agent-day: DeepSeek at the measured $0.000119, or Haiku with 1500 in / 200 out ($0.00025). **$0.000198 / $0.000329 per agent-day.**
- (c) Nothing until a meeting, then one catch-up call: 3000 in / 400 out on Haiku ($0.0005) or DeepSeek ($0.00035). Cost is meetings times catch-up and does not depend on agent count. 3 meetings/day gives $0.0015; 10/day gives $0.005 (Haiku). The world is frozen between meetings.
- Not included: persistence, the scene-level cost once the player does meet an agent, and the quality of the updates (not evaluated).
- The 25% escalation rate is a guess. In-scene escalation measured 65% (harder questions). If off-screen ticks escalate like that, (a) roughly doubles; still under $0.05 per day at 200 agents.

## Ingestion: details

`ingest_probe.py` on the first chapter of the corpus (lines 15521–16260, 69,763 characters, 13 chunks of ~6000 characters). The prompt asks for JSON events (what, who, where, witnesses, reactions, notability), in Ukrainian. All 13 chunks gave valid JSON on all three models. Scale factor to the whole corpus: 4,998,019 / 69,763 = **71.6** (characters, not the 9 MB file size, since Cyrillic is 2 bytes per character). Per chapter: Haiku $0.0117 (34.5k in / 16.5k out, 78 s, 76 events), DeepSeek $0.0076 (33.1k / 16.1k, 323 s, 99 events), Qwen-9B $0.0045 (28.8k / 10.6k, 145 s, 60 events).

- **Event counts are not a quality measure.** I did not grade the extractions; counts differ by 1.6x. Judge quality before choosing the cheapest.
- One chapter is a thin sample; a quiet dialogue chapter would give fewer events. Expect about ±30% on cost.
- Time assumes sequential calls; DeepSeek was 4x slower than Haiku per chunk. With 8 parallel requests (rate limits permitting) the whole corpus is under an hour for any of them.
- Model outputs were not saved (the books must not be committed).
