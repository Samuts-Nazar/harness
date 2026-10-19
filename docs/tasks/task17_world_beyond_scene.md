# Task 17: The world beyond the scene — places, time, news, consequences

Work fully autonomously. Do not ask questions. Record ambiguities in `docs/assumptions.md`.
Read first: `docs/decisions.md` (Knowledge and characters, two-level simulation, Interaction/Time), `docs/pilot_vizima_test_plan.md`, `ideas/A/SUMMARY.md` and `ideas/A/01*` (spread), `ideas/A/04*` (off-screen agents), `ideas/A/06*` (time), `reports/decision_gaps.md` items 7, 9, 12, `reports/cost/SUMMARY.md` (off-screen cost), `harness/director.py`.
Task 16 runs at the same time (canon in play, `harness/canon/`). It provides scheduled canon events and character background knowledge through `harness/canon/api.py`; code against that interface (if it is not there yet, against: `ScheduledEvent(id, t, place, participants, summary, knowers, notability)` and `background(character, topic) -> knowledge or None`) and keep the coupling in one adapter.

## User decisions this task implements (pending in decisions.md)
- Player character for the pilot: a demon without limits. What the player declares happens; the engine never judges success of the player's own acts. Only the world's reaction is simulated.
- Base mode: no queue; the scene director decides who acts; the world waits for the player. (Live real-time scene is a later task.)
- World behaviour follows reality per situation, judged by scale and circumstances; nothing is a special mechanic.

## Build
1. **Places and movement.** A world map of places (pilot: Визима — корчма «Під Лисом», ринок, брама, кордегардія біля палацу, старий палац, берег озера; more can be added lazily). The player can go somewhere; leaving and entering scenes uses the existing enter/leave; travel takes in-world time judged per situation.
2. **One world clock** across scenes; time passes with turns and travel; the player can wait or skip ("чекаю до ранку"). Turn duration judged per situation (ideas A6).
3. **Spread of news** (gap 7, ideas A1): when a noteworthy event happens, its reach is computed by notability, time and distance; people elsewhere learn a version of it lazily when it matters (when the player meets them, or an agent acts). Versions can distort (named distortion operators from ideas A1), several versions coexist, each knowledge record has a source. Collectives (the town, the guard, the court) hold their version and a mood/attitude.
4. **Off-screen world** (gap 9, ideas A4): agents the player interacted with get cheap updates when time passes (goal + what they would plausibly do, one judgment, a "tellable" record when something happens). Authorities react to events by scale (the guard is sent, Velerad is told, the king hears). Scheduled canon events from task 16 are executed when their time comes unless re-judged.
5. **Consequences visible**: in the debug view, a "світ" section: what happened off-screen since the last turn, which news reached whom, with versions.
6. **Player acts without limits**: player actions are recorded as having happened (no success judgment); the extractor must not soften them.

## Tests and live check
- Tests with fake providers for each item; deterministic.
- Live script (under 0.30 USD): a short Vizima session by a scripted player: a miracle in the tavern, leave, wait until morning, go to the market — report who knows what, which versions, what the authorities did, and the cost per in-world day.
- Measure cost and latency of the off-screen step per in-world hour and per day.

## Budget
Under 0.60 USD.

## Output
Full report in the final message: what was built, the live session (quotes, short), costs, open questions, branch and worktree as absolute paths.
