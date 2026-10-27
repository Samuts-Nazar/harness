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

## Re-run after fixes (2026-10-27)

Fixes (task 11), each with a fake-provider test in `tests/test_outsider_live_fixes.py`:

1. **Duplicate of a present NPC.** `SceneCast.review` keeps a code rule (after review round 1: the mention is the label, or holds every distinctive word of it, at least two; generic words like «жриця», «жінка» do not count), and for a mention that would become a passer-by while others are present adds one typed choice (`cast_same_person`: someone else, or one of the present people) to the batch it already asks, so no extra call. Code alone misses a present person described in other words («чарівниця з фіалковими очима»), and a choice alone would cost a judgment the code can often skip. The narrator already gets the present people under their labels («Present: …» uses `ref(PLAYER, c)`). The actual cause was problem 2: with the label «Йеннфер» the code rule could not match.
2. **Name leak.** `CanonPlay.profile_for` takes the label from the portrait's new `look` field (after review round 1: Yennefer «жінка в чорно-білому, з чорними кучерями», Nenneke «огрядна літня жриця в білому», Ciri «худенька дівчинка з попелястим волоссям»; also used for the no-store stand-ins; the live runs below used the first looks, «жінка в чорно-білій сукні» and «огрядна жриця в білому»). Without a `look`, it takes the first alias that is not a name form (`name_form`: capitalised, or sharing four letters with the name). Vizima: the labels of every person in `pilot_v3.db` (and the other pilot stores except `pilot_luna2`'s «Дальку», itself a name form) are unchanged, and the Vizima canon tests pass with `HARNESS_CANON_DB=pilot_v3.db`. `experiments/canon_be_fix.py` step 4 removed «Йеннфер» from be.db and from `raw_be/entities.json` (idempotent: a second run removes 0).
3. **Containers.** The extractor prompt (item ids on) now lists `open` and says that taking an item out is a `move` to `in_hand` and never a `remove`. In code, one safety net: a `move` of an item out of a closed container that it is in opens that container first, so its contents are observed once. (A rewrite of `remove` into a move, keyed on take-out verbs, was removed in review round 1: it kept broken or thrown-away items.)
4. **Reader request.** `readable.lookup_topic` finds the topic in code, with no call: the clauses that read or look something up, from their «про»/about on. «…дістаю ноутбук і відкриваю свої нотатки про духа лампи» gives «про духа лампи». This topic goes to term expansion, the reader, the duration judgment and the read event. The reader is told to answer only that topic, ignore the physical actions and write only in the output language. An answer that cannot be parsed is asked for once more. MAX_RECORDS is now 6 (records ≤ 600 chars as before).
8. **Panel duplicate:** one chip per text.

Suite: `nix develop --command pytest -m "eval or not eval"`: 1023 passed, 1 skipped. Run 1 had the known flake `test_stream_and_state_answer_while_slow_translations_run`, which passed when rerun alone. Run 2: no failures.

Live re-run: same script, same 3 turns, cap $0.10. Two runs: $0.0067 each, $0.0134 in total.

| Check | Run 1 | Run 2 (after the reader re-ask) |
|---|---|---|
| a) no duplicate / Source hidden | pass: no walk-in in 3 turns; Yennefer speaks every line herself as «Жінка в чорно-білій сукні»; no canon name anywhere in the transcript; the Source stays `internal`, `aware: false`, not on the panel | pass, same |
| b) Yennefer's magic sense | the magic-sense fact at entry (`witnessed`); she speaks now | same; in turn 3 she asks who taught him and asks to see what is written |
| c) reading the laptop | **fail**: the reader's answer (5 026 chars) did not parse, so "nothing found". Five probes with the same prompt all parsed: a one-off. Fixed by asking once more. | **pass**: request «про духа лампи»; the 'Прочитано · ноутбук' text is the notes, close to the text, in Ukrainian, with no commentary on the actions; 6 records with `read: item:ноутбук`; clock +5 min; Yennefer gained no read records |
| d) backpack | **pass**: the extractor wrote `move рюкзак → on:ground`, `open рюкзак`, `move ноутбук → in_hand`; she perceived the contents once | **pass**: the same form; the laptop stays in hand |

Latency (first word): 17.2 / 30.1 / 9.8 s and 27.3 / 32.3 / 7.9 s. Still to do: problems 5–7 (records that say "the player", the authoring wording of the magic observation, latency). The observation text for the contents of an opened pack reads "has X in hand or at the belt" (the category wording, not the location).
