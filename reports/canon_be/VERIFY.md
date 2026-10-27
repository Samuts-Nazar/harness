# Verification of the «Кров ельфів» canon store (task 8b)

Store: `/home/cock/projects/harness/campaigns/canon/be.db` (git-ignored). It holds 234 events, 156 entities
(153 from the cast list plus 3 from window `new_entities`), 667 knower rows and 179 reactions. The finish
script `experiments/canon_be_finish.py` has been run on it.

Method: I picked 12 stored events from 9 of the 10 windows. For each one I read the cited lines of
`data/witcher_books.txt` and the lines around them, then checked the stored `what`, participants and
knowers (channel and learned time), the time and the place. This report gives line numbers and verdicts
only and quotes nothing from the book.

| id | window | lines | verdict | note |
|---|---|---|---|---|
| 380 | 15505-15900 | 15621-15625 | ok | The bard ends the ballad and Radcliffe thanks him. The money bucket comes from line 15641, which is not in `lines` (minor). Knowers are the people present. |
| 428 | 15901-16261 | 15949-15955 | ok | Ambush in the barn: the knife goes through a smoke figure. The four knowers were all present. The time is `before` 0.9, the anchor's guess. |
| 474 | 19009-19408 | 19155, 19197, 19205 | ok | Barge attack two weeks earlier, a pregnant girl among the victims. Geralt is `heard` and Lin Pitt is `told` by Geralt on day 1 morning, both correct. |
| 530 | 19409-19808 | 19615-19623 | ok | Dijkstra's two spies meet Lyubystok at the rector's bust and he goes with them. Day 1 afternoon follows the anchor table. |
| 610 | 19809-20208 | 20151-20155 | ok | Nenneke scolds Yennefer in the next room. Ciri is `overheard` and stored as a bystander. Yennefer's quiet answer matches the text. Day 1 night is the cross-chapter guess. |
| 630 | 20209-20608 | 20295-20299 | problem (minor) | The report to Vilgefortz is correct. Tissaia's channel is `inferred` although she is present; it should be `witnessed`. `place:vilgefortz-residence` is an invented place, because the text does not name the setting. |
| 672 | 20609-21008 | 20617-20649 | problem | The adepts mock Ciri, which is correct. The place is wrong: `place:temple-park` is stored, but the scene is the poultry yard where they feed the hens, and the park is only mentioned. "Day 21 morning" is the anchor's guess. |
| 695 | 20609-21008 | 20941-20951 | ok | Nenneke introduces Ciri to Yennefer in the refectory, and Yennefer remarks on possible elf blood. All three knowers witnessed it. `before` 0.2 is a guess. |
| 699 | 20609-21008 | 20979-20995 | problem | The guardianship announcement and Ciri's private resolve to run are correct. Yennefer (present) is stored as `inferred` with learned time day 21 afternoon instead of the event's own (flashback) time, so before day 21 she cannot recall it. |
| 707 | 21009-21408 | 21043-21045 | problem | Yennefer saying Geralt asked her to test Ciri is correct. Ciri (listener) is stored as `told` with learned time day 21 afternoon instead of the flashback time. This is late, not a leak. |
| 763 | 21409-21808 | 21623-21625 | ok | The quarrel over the nosebleed and a week of silence are correct. Day 2 depends on the inference that the nosebleed is the day 1 night of chapter 5 (confidence 0.6). |
| 784 | 21809-22100 | 21871-21875 | ok | Nenneke says goodbye at the departure, which is correct. Day 22 morning has an explicit cue: they leave the next morning. |

The result is 8 ok and 4 problems: one wrong place, two late learned times and one minor channel/place issue.

## The learned-time fault (found by the sample, checked across the store)

A `told`, `heard`, `read` or `inferred` knower row without its own `when` gets its learned time from
the ingest's `time_at_line`. That function uses the last dated (`day`) event that comes before the line in
line order. Chapter 7 is a flashback that sits in the file after the day 21 present, so for a flashback
line it returns day 21 afternoon (29700). These rows are affected: 699 (Yennefer), 707 (Ciri), 729 (Ciri)
and 751 (Eist). The effect is always "learned later than true", never earlier, so it cannot leak a
secret. It does hide flashback facts from Ciri and Yennefer until day 21. Rows 645 and 646 also have late
learned times, but there it is correct: Tissaia and Lydia learn an old story on day 1 night. The finish
script does not change these rows.

## Known weak points

- **Guessed times.** Chapter 1 is `before` 0.9/1.0 years, a guess from "over a year". Chapter 7's
  present is day 21, a guess of about three weeks after the nosebleed. Days 2-20 come from the
  cross-chapter link "the nosebleed night is day 1 night" (confidence 0.6). The chapter 6 Hagge/Vilgefortz
  scenes are set on day 1 evening or night with confidence 0.4, because the text only shows rain. The
  flashback offsets `before` 0.1-0.2 are guesses. 103 events have no story day: they are `before` events,
  ordered only by line number.
- **Guessed places.** Subagents invented the place entities `place:yennefer-room` (15 events),
  `place:temple-park` (12), `place:temple-garden`, `place:vilgefortz-residence`, `place:myrman-alley` and
  `place:inn-near-brothel` from context. Event 672 shows that the park can be wrong. 22 events carry only
  the umbrella `place:temple-of-melitele`.
- **Bystanders.** 29 participant rows are `bystander`. 16 of them have no knower row (for example Geralt
  in 479, 602 and 608, Yennefer in 612, and the zhahnytsia in 510-522). The loader does not add knowers
  for bystanders, so these people do not know events they stood next to. That is correct only where they
  really did not notice.
- **Gist, no keywords.** Records are English with Ukrainian names. Since the follow-up below every event has a
  Ukrainian one-sentence `gist_uk`, hand-translated from the stored `what` (no `kw_uk`), so everyday
  Ukrainian wording now matches in FTS.
- **Uncovered range.** Lines 16263-19007 (chapters 2-4, Kaer Morhen) are not in the store, by design.

## Follow-up fixes (scripts `experiments/canon_be_gist.py` and `experiments/canon_be_fix.py`, both idempotent)

- **Gist.** `campaigns/canon/raw_be/gists.json` ({event_id: sentence}, git-ignored with the store) holds 234
  Ukrainian sentences with the glossary names; `canon_be_gist.py` writes them to `canon_event.gist_uk` and
  rebuilds the FTS. A test checks that the everyday query "Йеннефер приїхала до храму" returns events and that
  their search rows contain the gist.
- **Event 672.** There was no poultry-yard place in the cast, so `place:temple-poultry-yard` (name
  "птахівник храму") was added as a minimal entity row. The event was moved there and its record meta flagged
  `place_unverified`; "in the temple park" in its `what` became "in the temple poultry yard".
- **Learned time of flashback knowers.** Rows 699 (Yennefer), 707 and 729 (Ciri) and 751 (Eist) now learn at the
  event's own `before` time with delay 0. The rule is: told/heard/read/inferred rows with learned time 29700
  whose event has t_from < 0. It matches exactly those four; the other early-learned rows (468, 469, 474, 624,
  645, 646) are correct and untouched.
- **Bystanders without knower rows (16): left as they are, by design.** A bystander is someone who stood near
  but did not take part or notice, so the loader gives no knower row. Where a bystander really noticed the
  event, the source should say so and the event should list them as witness.
- **Not fixed:** event 630 (Tissaia channel `inferred` instead of `witnessed`; invented place
  `vilgefortz-residence`) and the other guessed times and places listed above.
