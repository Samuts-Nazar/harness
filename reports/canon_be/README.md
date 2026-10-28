# Canon scope: «Кров ельфів» for the Ellander start (plan 1, task 8)

Source: `data/witcher_books.txt` (not committed). The book starts at line 15505 and the next book at 22101.

Chosen by the controller on 2026-10-26 from the density of Yennefer, Nenneke, Ciri, Melitele and Ellander mentions per chapter:

| Chapter | Lines | Why |
|---|---|---|
| 1 | 15521–16261 | background: Yennefer and Ciri before the temple |
| 2–4 | 16261–19008 | not taken (Kaer Morhen, Ciri's training; not needed for this start) |
| 5 | 19009–19859 | Nenneke and the temple appear, Yennefer and Ciri |
| 6 | 19859–20603 | Yennefer prominent |
| 7 | 20603–22100 | the temple of Melitele, Nenneke, Yennefer and Ciri together |

Windows (about 400 lines each): 15505–15900, 15901–16261, 19009–19408, 19409–19808, 19809–20208, 20209–20608, 20609–21008, 21009–21408, 21409–21808, 21809–22100.

Extraction is done by Claude Code subagents following `reports/canon_be/EXTRACTION.md`, into `/home/cock/projects/harness/campaigns/canon/raw_be/` (git-ignored). No API spend.

## Load counts (ingest run, task 8)

| What | Count |
|---|---|
| entities | 156 (153 from the cast list + 3 added by windows) |
| canon_event | 234 |
| canon_participant | 633 |
| canon_knower | 662 from the ingest, + 5 `witnessed` rows added by the finish pass (667) |
| canon_reaction | 179 |
| dropped records | 0 |
| flagged | none |
| format failures / window failures | 0 / 0 |
| JSON files read | 11 |
| uncovered lines | 16263–19007 (chapters 2–4), by design |

**Inconsistent times.** Geralt's letter asking Yennefer for help (`before` 0.08 years, −42048) and her
reply (−15768) are stamped *after* her arrival at the temple (`before` 0.2 years, −105120), though in the
story the letter sends her there. Both stamps are anchor guesses. **Fixed 2026-10-28** by
`experiments/canon_be_fix.py` step 5: letter `before` 0.25 (−131400, read by Yennefer at 0.24), reply 0.23
(−120888); at the `ellander_road` start Yennefer now knows the letter and her reply.
