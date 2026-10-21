# Task 22: "writes like a person" bake-off (user-graded)

Page: `app/static/human_ab.html` (data `app/static/human_ab_data.js`), open `http://192.168.1.109:8765/static/human_ab.html` while the app runs. Rate each text 1 to 5 per scene, optional note, copy the result string at the end. Choices stay in the browser. Key (not served): `reports/human_ab/key.json` (scene -> letter -> model). Runner: `experiments/human_ab/run.py`; raw outputs `experiments/human_ab/raw/out.jsonl`.

Moments: Горст opens, Горст haggles, Роше (rumours), Марта (recognises a witcher), two Vizima narration moments (enter the tavern, beer turns to blood). Prompts as in the engine today (style sheet on, no exemplars; NPC manner notes from task 15 `manners.json`). One sample per model per moment, temperature 0.8.

Candidates, dates and prices: `docs/tools.md`. Glitch filter: empty, under 3 words, foreign scripts, Russian-only letters, Latin words of 4+ letters, think/markup tags, over 330 words, cut off mid-sentence. Filtered texts are not shown to the user.

| Model | texts shown of 6 | glitches | cost USD | mean latency s |
|---|---|---|---|---|
| openai/gpt-6-luna (baseline) | 5 | 1 (i3 English "fair measure") | 0.0014 | 3.5 |
| xiaomi/mimo-v2.6-pro | 6 | 0 | 0.0051 | 11.2 |
| xiaomi/mimo-v2.6-flash | 5 | 1 (v2 Latin) | 0.0016 | 6.9 |
| z-ai/glm-5.3 | 2 | 4 (Latin x2, Chinese x2) | 0.0079 | 4.4 |
| deepseek/deepseek-v4.1-flash-1017 | 6 | 0 | 0.0024 | 3.5 |
| qwen/qwen3.8-27b | 6 | 0 | 0.0053 | 5.7 |
| cohere/command-a-plus | 3 | 3 (Russian letters, too long, English reasoning leak) | 0.0078 | 6.4 |
| bytedance-seed/seed-2-1-turbo | 5 | 1 (Russian letters) | 0.0100 | 10.5 |

Total spend 0.0413 USD of 0.20. No ranking by the agent; the user's grades are the result.
