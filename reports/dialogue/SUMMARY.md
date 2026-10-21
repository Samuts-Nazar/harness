# Living dialogue: live check (task LD-8)

Run on 2026-10-21 with the default live models (`ModelConfig.live()`, first-line decider with the
0.8 escalation). Script: `experiments/dialogue/live_check.py`. Raw outputs and the cassette are in
`/home/cock/projects/harness/campaigns/ld/` (git-ignored, not committed). Spend: **0.217 USD** of 0.60.

## Verdict

Acceptance rules from the spec, on the two 20-turn inn sessions (living mode):

| rule | session A | session B | pooled |
|---|---|---|---|
| share of 1-3-word spoken lines > 0 | **6.8%** (3 of 44) | **9.4%** (3 of 32) | 7.9% (6 of 76) |
| median spoken length <= 2x the profile median (10 words, so <= 20) | 6.5 (0.65x) | 6.0 (0.60x) | 6.0 |

**Both rules pass on the final run.** Two honest caveats:

1. The first run of the same two sessions (before I added error capture; nothing else changed)
   gave session A **0% short lines** (19 lines, median 7) and session B 6.8% (44 lines). So the
   "> 0" rule failed in session A on that run and passed on the repeat. With 30-45 lines per
   session, whether a 1-3-word line appears at all is partly luck. Nothing was tuned between runs.
2. The result is far from the book's *shape*, only on the right side of the two thresholds. Book:
   22% of lines are 1-3 words, 18% are 31+ words, median 10. Living engine (pooled): 8% short,
   **0% over 15 words**, median 6. The engine is now too uniform and a little too short, where
   classic was too long (below).

## Numbers against the profile (speech only)

Profile = `worlds/witcher/profile.json` (18669 book lines). Bins are shares of spoken lines.

| | lines | 1-3 words | 4-7 | 8-15 | 16-30 | 31+ | median | question share |
|---|---|---|---|---|---|---|---|---|
| book profile | 18669 | 21.9% | 19.9% | 22.0% | 18.0% | 18.2% | 10 | 22% |
| living, session A | 44 | 6.8% | 55% | 39% | 0% | 0% | 6.5 | 23% |
| living, session B | 32 | 9.4% | 56% | 34% | 0% | 0% | 6.0 | 44% |
| classic, session A | 20 | 0% | 5% | 35% | 45% | 15% | 18 | 20% |
| classic, session B | 20 | 0% | 10% | 20% | 50% | 20% | 18 | 15% |

- Classic always replies with exactly one line of 16-45 words (median 18, 1.8x the profile): it
  passes the median rule only barely and has no short lines at all (0 of 40).
- Living has the shorter lines and several speakers, but nothing long. The distance to the profile
  (L1 over the length bins) is 0.98-1.03 for living, 0.68-0.80 for classic: **classic is closer to
  the book by this metric** because the book has a long tail that living does not produce, while
  living has the short end that classic lacks. The user's blind A/B decides.
- Every engine line carries a beat (`no_beat_share` 0 against the book's 0.54): the NPC always
  adds an action to the speech. A visible tell, not part of the acceptance rules.
- The narration metrics are not compared (the engine has no narration paragraphs between lines).

## Reference scenes (living, 5 silent-onlooker turns each)

The protagonist (Geralt) is an engine speaker in the Rinde and Cintra scenes, so the book numbers
include his lines and the comparison is like for like (the "leave out the protagonist" rule was
not needed). Kings' council has no protagonist.

| scene | book lines (range) | book median / 1-3 words | engine lines | engine median / 1-3 words | stops |
|---|---|---|---|---|---|
| Rinde council (`rinde_council`, book 5585-5700) | 47 | 19 / 8.5% | 23 | 7 / 8.7% | cap 4, nobody 1 |
| Cintra feast (`cintra_feast`, 2960-3140) | 65 | 16 / 15% | 16 | 5 / 25% | cap 3, nobody 2 |
| Kings' council (`vizima_kings`, 19921-20039) | 60 | 22.5 / 12% | 5 | 10 / 0% | addressed 1, cap 1, nobody 3 |

Top-10 book scenes from `find_scenes.py` (line ranges in the file, name stems in the script
output): 25801-25919, 19921-20039, 34161-34279, 33841-33959, 34001-34119, 29601-29719,
29761-29879, 33641-33759, 55880-55998, 54160-54278. All ten are in the later volumes (they have
more distinct names per window). Picked: the kings' council (rank 2; many speakers, no
protagonist), Rinde (forced by the brief; a book-1 story) and the Cintra feast (a book-1 scene
with five clear speakers, chosen instead of the busier but far more context-dependent late-volume
scenes, which I could not set up in a few sentences). Speaker counts are an upper bound (a name
mentioned twice counts). Setups: `worlds/witcher/scenes/*.json`, in our own words.

In 8 of the 15 scene turns the exchange hit the cap (6 lines); the Rinde scene mostly runs to
the cap, the kings' council is much quieter (1 line per turn, and one turn had no word at all).
A short line from the Rinde run: the burgomaster tapping the table and asking the priest
"Скільки?" at the end of a line.

## Speed (living vs classic)

Seconds from the start of the turn to the first word shown (turns with words only):

| | median | mean | p90 | max |
|---|---|---|---|---|
| living A | 7.6 | 7.9 | 10.3 | 21.4 |
| living B | 4.3 | 7.7 | 13.7 | 19.5 |
| classic A | 10.5 | 11.9 | 19.6 | 22.5 |
| classic B | 11.3 | 12.3 | 17.6 | 18.6 |
| scenes (living) | 10-12 | | | 14.7 |

Living reaches the first word 1.5-2.5x earlier in the inn (the narration is skipped on 25 of 40
turns, and a short line is quick). The whole turn (until the player has all
the text) is longer: median 12-14 s in the living sessions against 11 s in classic, and up to 59 s
(six-line exchanges: scenes 10-40 s median). With a six-line exchange the player reads while lines
keep arriving, but the last line comes late.

## Decisions

See `reports/decisions_count.md`. In short: about 16-20 decisions per turn in the inn sessions
for both modes (living 408 and 310 in the two sessions, classic 373 and 323), of which about
three quarters are typed judgments; living replaces most narrator calls (13 and 7 per 20 turns
against 26 and 23) with more NPC calls (58 and 47 against 38 and 37). A six-line exchange costs
about 44 decisions, a turn with no lines about 12.

## Problems found while measuring

1. **Slow-lane failures (a real bug, not fixed here).** In the repeat of session A the slow lane
   failed on 5 of 20 turns (session B: 2): `ExtractionRejected: new_facts[N]: unknown source
   'Горст~2'`. The extractor names the second line of the same NPC in a turn by the display name
   plus `~2`, while the segment key is `horst~2`. The turn's records are then rolled back (the
   text stays on screen). Probably `Engine._ids_for_names` (pipeline.py) maps names but not
   the `~N` form. The first run had 1 and 5 such failures. It does not change the dialogue
   numbers above, but it loses memory of the exchange in those turns.
2. The first-run A/B sides come from separate campaigns, so a pair has the same player line, not
   the same history.
3. `npc_line_rejected` fires in 7-18 notes per session in both modes (output check); not a new
   problem.

## A/B for the user

`/static/ab.html` (data `app/static/ab_data.js`): 10 pairs, the first 5 player turns of session A
and of session B, each side a whole exchange (narration if any, then the lines) from the classic
and the living engine, sides shuffled with a fixed seed (living on side A in 6 of 10). The key is
`reports/dialogue/ab_key.json`. No book text on the page. The old path stays behind
`--dialogue classic`.
