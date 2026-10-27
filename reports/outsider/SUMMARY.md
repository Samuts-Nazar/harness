# Outsider campaign, plan 1: live check (2026-10-27)

Script: `experiments/outsider_live_check.py` (raw JSON kept outside the repo; it holds canon records).
Package: `app/tests/fixtures/outsider_ellander.yaml` (start `ellander_road`, a `latent` Source, a closed backpack with 21 items) with one change the script makes in memory: the laptop gets an inline `content` (six lines of INVENTED notes for a board game about a lamp spirit called Ормаз, not the saga). Canon store: `campaigns/canon/be.db` in the main checkout (FTS only). Live stack defaults (`app.stacks.live_stack`), cap $0.10, suggestions off, 3 turns:

1. «Підводжуся з землі, обтрушую коліна й кажу жінці: «Вибачте... Де я? Здається, я заблукав».»
2. «Знімаю рюкзак, розстібаю його, дістаю ноутбук і відкриваю свої нотатки про духа лампи.»
3. «Питаю її: «Чому ви так на мене дивитеся? Щось зі мною не так?»»

## Suite

`nix develop --command pytest -m "eval or not eval"`: exit 0, 1007 passed, 1 skipped, 45 s (`HARNESS_CANON_DB` not set; the known flake did not fail this run).

## Results

| Check | Result | Evidence |
|---|---|---|
| a) Source not on the player's panel | **pass** | Engine: `internal` element, `aware: false`, `channel: magic`, at every snapshot. Panel: 30 chips, none mentions it; no prose mentions it. |
| b) Yennefer's magic sense on entry | **pass (noticed), no spoken reaction** | She got the magic-sense fact at entry (`witnessed`). Salience: `liquid/d1-ultra` said no to all ten entry observations; the Source one was escalated and the LLM said yes, so it alone is `noteworthy`. Shown to her in turn 2. Her reaction was a gesture (pulls the reins, walks up the road). She never spoke in the 3 turns. |
| c) Reading the laptop | **pass, with a text flaw** | The 'Прочитано · ноутбук' block appears; 4 records with knower source `read: item:ноутбук` (MAX_RECORDS = 4, two of the six invented details are shown but not stored); clock +5 min; Yennefer and the walk-in gained no read records. Flaw: the reader got the whole turn as the request, commented on the actions and used an English word. |
| d) Backpack | **fail** | Closed state works (she perceived no backpack contents). In turn 2 the extractor wrote `move рюкзак → on:ground` and `remove ноутбук`, no `open`: contents never observed, backpack stays closed, the laptop is gone from the state and cannot be read again. |
| e) Latency, cost, deferral | evidence | First word 24.4 / 26.7 / 17.5 s; cost $0.0068 in 101 calls. Her canon memory held only earlier Rience/Dandelion scenes, nothing from the temple. The story clock reached only 09:07 (temple events are stamped 11:00), so the deferral was not exercised live. |
| realize | **not produced** | Yennefer never told him; the Source stays unaware. |

## Problems found

1. A duplicate of Yennefer: the narrator's «жінка в чорно-білій сукні» was admitted as a passer-by («Ванда», `npc_walkin1`); the walk-in spoke both lines and answered turn 3.
2. Her label for the player is a misspelt alias from be.db («Йеннфер»), taken by `CanonPlay.profile_for` as her appearance: a name he never learned.
3. Extractor and containers: "takes out the laptop" became `remove` (item lost); "unzips" produced no `open`.
4. The reader request is the whole turn, and its commentary goes to the player verbatim.
5. Records say "the player" («Гравець знімає рюкзак…» on the panel).
6. The magic observation stores the package's authoring wording as what she perceives.
7. First word 17–27 s.
8. «окуляри» appears twice on the panel.
