# Task 22b: blind writing test, round 2 (user-graded)

Page: `app/static/human_ab2.html` (data `human_ab2_data.js`), open `http://192.168.1.109:8765/static/human_ab2.html` while the app runs. Key (not served): `reports/human_ab/key2.json`. Runner: `experiments/human_ab/run2.py`; raw `experiments/human_ab/raw/out2.jsonl`.

Why a round 2: the user found the round-1 moments weak. Seven new moments built with the engine's own context builder and style sheet (no book excerpts): w0 a first meeting with Єніфер in Рінде (not the canon scene; a full character sheet in our own words; 3 samples), then a night street in Визім, a forced-failure gate attempt, a cynical sergeant's interrogation, two locals arguing about the striga, a superstitious herbalist, a tavern fight aftermath (2 samples each). Temperature 0.8.

GLM finding: GLM-5.3 endpoints refuse `reasoning: {enabled: false}` ("Reasoning is mandatory"). With `reasoning: {effort: "low", exclude: true}` the probe gave 0 glitches of 8 on default routing (Wafer) and on Z.AI; Z.AI was 3-5x slower and ~7x pricier, so default routing is used. Round 1's 4/6 glitches most likely came from reasoning being forced off.

| model | shown | glitches | cost USD | mean total s | mean first token s |
|---|---|---|---|---|---|
| z-ai/glm-5.3 | 14/15 | 1 (too long) | 0.0162 | 5.9 | 0.8 |
| z-ai/glm-5.3-flash | 14/15 | 1 (Latin) | 0.0040 | 10.3 | 1.6 |
| mistralai/mistral-large-4-0 (above ceiling) | 14/15 | 1 (Latin) | 0.0594 | 14.6 | 1.0 |
| xiaomi/mimo-v2.6-flash | 15/15 | 0 | 0.0044 | 17.9 | 3.4 |
| xiaomi/mimo-v2.6-pro | 15/15 | 0 | 0.0132 | 17.8 | 3.0 |

Total 0.097 USD plus ~0.03 for the probe. Two-call moments sum their latencies. No ranking by the agent; the user's grades are the result.
