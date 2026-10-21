# Decisions per action, scene and session

Measured live on 2026-10-21 (`experiments/dialogue/live_check.py decisions`), final runs.
A decision is a typed judgment, a model call (per role) or a code-made choice
(`harness/decisions.py`). "Action" = one player turn.

## Per scene and per session

| unit | turns | judgments | of them escalated | model calls (narrator/npc/extractor/other) | code choices | total | per turn: mean / min / max |
|---|---|---|---|---|---|---|---|
| scene:cintra_feast (living) | 5 | 183 | 149 | 4/18/14/0 | 7 | 226 | 45.2 / 9 / 69 |
| scene:rinde_council (living) | 5 | 95 | 67 | 4/28/17/0 | 7 | 151 | 30.2 / 10 / 38 |
| scene:vizima_kings (living) | 5 | 100 | 74 | 4/8/15/0 | 4 | 131 | 26.2 / 9 / 76 |
| session A, classic | 20 | 259 | 198 | 26/38/45/0 | 5 | 373 | 18.6 / 7 / 30 |
| session A, living | 20 | 281 | 214 | 13/58/38/0 | 18 | 408 | 20.4 / 9 / 37 |
| session B, classic | 20 | 211 | 148 | 23/37/42/0 | 10 | 323 | 16.1 / 9 / 28 |
| session B, living | 20 | 206 | 147 | 7/47/29/0 | 21 | 310 | 15.5 / 9 / 34 |

Escalated = went from the first-line decider to the LLM (about three quarters of judgments).
Judgments include the output check of every NPC line and the salience and attitude questions, so a
turn with more lines has more of them.

## Per action (by what the turn produced)

Mean decisions per player turn, all final runs:

| mode | NPC lines in the turn | turns | total | judgments | model calls | code choices |
|---|---|---|---|---|---|---|
| living | 0 | 11 | 11.6 | 7.9 | 3.5 | 0.2 |
| living | 1 | 23 | 14.0 | 9.7 | 3.4 | 0.9 |
| living | 2-3 | 6 | 18.8 | 13.2 | 4.7 | 1.0 |
| living | 4-6 | 15 | 44.1 | 31.7 | 10.5 | 1.9 |
| classic | 1 | 38 | 17.4 | 11.7 | 5.3 | 0.4 |

(Classic has 1 turn with no line and 1 with 2-3 lines.) By narration: living turns with narration
23.3 decisions on average (27 turns), without 21.4 (28 turns, the scenes' long exchanges included);
classic always narrates (17.4 over 40 turns).

## Reading

- A living turn costs about as much as a classic one when it ends after one line (14 against 17),
  because the narrator call is skipped in 25 of 40 inn turns; it costs 2-3x when the exchange
  runs long (44 for 4-6 lines: each line adds an NPC call, its check and a director step).
- Code-made choices grow in living mode (18-21 per 20 turns against 5-10): shape trimming and
  regeneration, silences, gestures, "same speaker stopped", the exchange cap.
- The spend for all 7 final runs (and two earlier runs of the living sessions): 0.217 USD.
