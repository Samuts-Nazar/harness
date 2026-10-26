# Canon extraction by a subagent: one window to JSON

You read one window of the book (a range of file lines A–B that the controller gives you) and write
JSON files. Code then validates and loads them:

    python -m harness.canon.ingest --source data/witcher_books.txt --lines <arc A-B> \
        --chapters "L:Title,L:Title" --from-json <DIR> --glossary --out <X.db>

No model is called by the loader. What you write is checked field by field against closed lists and
the source text. A field that fails is either dropped (and counted) or loaded with a flag. Work only
from the text in your window. Do not use anything you remember about the books. If the text does not
say it, do not write it.

## 1. Reading the window

- Read `data/witcher_books.txt` with the Read tool, `offset = A`, `limit = B - A + 1`. The numbers
  the tool prints are the file line numbers. These are the numbers the loader uses.
- Each non-empty line is one paragraph. Empty lines are not paragraphs, and a line number that
  points to one is discarded.
- Never copy book text anywhere except into the `quote` field. Never put it in commits, reports or
  chat.

## 2. Files and names

Write into the directory the controller names (for this book: `campaigns/canon/raw_be/`, which is
git-ignored). Each file holds one JSON object in UTF-8: no code fences, no comments, no trailing
commas.

| File | Content | Who writes it |
|---|---|---|
| `window_<A>-<B>.json` | the event pass for lines A..B: `{"new_entities": [...], "events": [...]}` | every window subagent |
| `entities_<A>-<B>.json` | `{"entities": [...]}` for this window (optional; `new_entities` in the window file is enough) | optional |
| `entities.json` | one cast list for the whole arc (optional, usually written by the controller) | controller |
| `timeline.json` | `{"scenes": [...]}`, read only when the loader runs with `--v2` | not used by default |

- `<A>` and `<B>` are plain integers with no zero padding, exactly the range you were given:
  `window_15505-15904.json`.
- Window files are loaded in order of A. Lines that no window file covers are reported as
  `uncovered_lines`.
- All `entities*.json` files are merged, and so are all `new_entities`. When the same id appears
  twice, the first one loaded wins, and only its `aliases` are merged.
- `entities`, `new_entities`, `events` and `scenes` must be JSON arrays. Any other type makes the
  whole file invalid.
- A missing file or a file that does not parse is listed in the report (`json_files.missing` /
  `json_files.invalid`). The loader does not crash, but everything in that file is lost.

## 3. Entity ids (the most important convention)

Parallel subagents must give the same character the same id. Otherwise the loader treats them as two
people.

- Format: `<prefix>:<slug>`. The prefix is one of `char` (person), `coll` (group), `place`, `item`,
  `creature`. Any other prefix, or an id without a colon, means the entity is dropped.
- The slug is lowercase ASCII with words joined by hyphens, transliterated from the canonical
  Ukrainian name: `char:yennefer`, `char:ciri`, `place:temple-of-melitele`,
  `coll:temple-priestesses`. Unnamed people get a role slug: `char:ferryman`, `char:old-priestess`.
- **Reuse the ids in the cast list the controller gives you. Never rename them.** Add an entity to
  `new_entities` only when it is missing from that list. Before adding one, check whether it is the
  same person under a title or nickname. If it is, use the existing id.
- Every id you use in `place`, `participants`, `knowers`, `reactions`, `source` or `member_of` must
  exist: in the cast list, in your `new_entities`, or in another loaded file. An unknown id is dropped.

### Entity object

```json
{"id": "char:ferryman", "type": "person", "name": "перевізник", "aliases": ["старий перевізник"],
 "unnamed": true, "who": "An old man who keeps the ferry", "role": "ferryman",
 "standing": "Travellers pay him without arguing", "knows": [{"fact": "Knows the river fords", "basis": "inferred"}],
 "member_of": [], "first_line": 102}
```

- `type`: `person | collective | place | item | creature`. Keep it consistent with the prefix
  (`char`→person, `coll`→collective, `place`→place, `item`→item, `creature`→creature) or omit it.
  The loader derives the type from the prefix, **but a valid declared `type` overrides it**: a
  `char:` id with `"type": "place"` is stored as a place. A mismatch is never what you want.
- `name`: nominative case. If the name is in `worlds/witcher/glossary.json`, use its `canonical`
  form (for example `Ґеральт` with Ґ, `Йеннефер`, `Цірі`). Otherwise use the spelling in the text.
  For an unnamed entity, give a short Ukrainian description (`перевізник`).
- `aliases`: every other form the text uses: titles, nicknames, the text's own spelling when it
  differs from the glossary. Places are matched by name and aliases, so list both the case form and
  the nominative.
- `who`, `role`, `standing`: English, taken only from the text. `standing` is empty for places and
  items.
- `knows` (people only): at most 4 items. Each item is `basis: "text"` (the text supports it) or
  `basis: "inferred"` (their job or position clearly implies it). No invented backstory.
- `member_of`: ids of `coll:` entities, and only when the text shows the membership.
  `first_line`: an integer.

## 4. Event object (one per thing that happens)

```json
{"id": "e1",
 "what": "English, 1-2 concrete sentences: who did what to whom; proper names in canonical Ukrainian",
 "ekind": "travel",
 "loudness": 0.2,
 "place": "place:... or null",
 "time": {"kind": "day", "day": 3, "part": "evening", "years_before": null},
 "participants": [{"entity": "char:...", "role": "actor"}],
 "knowers": [{"entity": "char:...", "channel": "witnessed", "source": null, "line": 15620, "when": null}],
 "reactions": [{"party": "char:...", "reaction": "warn", "attitude": "negative", "text": "English"}],
 "lines": [15620, 15622],
 "quote": "verbatim Ukrainian fragment, at most 15 words",
 "confidence": 0.8}
```

Each field, and what the loader does with it:

- `id`: a local label (`e1`, `e2`, ...). It is not stored.
- `what` (required): a non-empty string. Without it the event is dropped. Write English. Give proper
  names in the glossary's canonical form. With `--glossary`, code also fixes variant spellings.
- `ekind`, one of: `violence magic death crime politics law bargain conversation travel arrival
  revelation scandal monster ritual rumour intimate recovery other`. Any other value is loaded as
  `other` and flagged `bad_ekind`.
- `loudness`, from 0.0 to 1.0, measures how far the news spreads: 0 means only those present ever
  know; 0.3 means a tavern talks about it; 0.6 the whole town; 1.0 the whole realm. Values outside
  the range are clamped.
- `confidence`, from 0.0 to 1.0, is how sure you are that the text says this. Put doubt here
  instead of hedging in `what`.
- `place`: the id of a `place` entity, or `null`. An unknown id becomes null and is flagged
  `unknown_place`.
- `time`, one of these objects:
  - `{"kind": "day", "day": N, "part": P}`: story day N (an integer, at least 1) and part
    P ∈ `dawn morning noon afternoon evening night` or `"unknown"`. **Count days from the anchor the
    controller gives you** (for example "line A is day 12, morning"). Advance the day only on an
    explicit cue in the text: "the next day", "three days later", a night passing. The same evening
    keeps the same day.
  - `{"kind": "before", "years_before": Y}`: a past event that a character tells about. Y is a number
    (0.5 means "recently"), or null if the text does not say.
  - `{"kind": "unknown"}`: the text gives no time. The loader carries the last known time forward.
- `participants`: `role` ∈ `actor target victim speaker listener witness bystander subject` (any
  other role is stored as `subject`). An unknown entity is dropped. Anyone present whose role is not
  `bystander` must also appear in `knowers`.
- `knowers` are the people or groups who, by the text, know that this happened. `channel` ∈
  - `witnessed`: took part or saw it.
  - `told`: was told on the page; `source` = the teller's id.
  - `heard`: second-hand, teller unclear.
  - `hearsay`: rumour.
  - `overheard`.
  - `read`: a letter or a book.
  - `inferred`: worked it out from signs.
  - `sensed`: magic or senses beyond sight.
  - `innate`: knows it by nature.

  A bad channel or an unknown entity means the row is dropped. `line` is the line where the text
  shows them learning it. `when` is a time object, used only when they learn it later than the
  event happened. Never add someone just because they could have known. A private thought has no
  knowers except the thinker.
- `reactions`: what *other* parties are shown doing in response, in the same scene. `reaction` ∈
  `ignore dismiss investigate avoid flee freeze appeal_to_authority seek_protection retaliate punish
  negotiate bribe_or_pay conceal exploit mobilise comply defend support mourn accept scheme hire_help
  warn gossip demand challenge admire`. `attitude` ∈ `positive negative neutral ambivalent`, or null.
  `text`: English, the reaction as the text shows it. A word outside the list, or an unknown party,
  means the reaction is dropped. If the text shows no reaction, leave the list empty. Never infer
  feelings.
- `lines`: integer line numbers of non-empty lines **inside your window** that support the event.
  Numbers outside the window, or numbers of empty lines, are removed. If none are left, the event is
  flagged `no_valid_lines` and has no link to the source passage.
- `quote`: one fragment of at most 15 words, copied **exactly** from those lines, in the text's own
  spelling. Never correct it to the glossary form. The check ignores case, extra spaces,
  «»/“”/" quotes, dash and apostrophe variants. Keep the fragment inside one paragraph. The loader
  flags `no_quote` when the quote is empty, `quote_not_in_text` when it is not in the text, and
  `dup_quote` when an earlier event already used the same fragment, so give every event its own
  fragment.

## 5. What to extract

An event is a discrete thing that happens or is established in the story world: an action, a speech
act with consequences, an arrival or a departure, a decision, a death, a revelation, an offer, a
deal, a promise, a lie, a plan, a threat, a lesson learned. Past events that characters tell about
are events too, with time kind `before`. For each event, record:

- **who**: `participants` with their roles;
- **what**: `what`, `ekind`;
- **when**: `time`;
- **where**: `place`;
- **who knew and how**: `knowers`, with channel, source and line;
- **how others reacted**: `reactions`.

Granularity: merge the beats of one scene into one event. A negotiation is one event, and a fight is
one or two. Do not make events for pure description, small talk or every line of dialogue. Keep a
separate event for anything someone could later ask about: a killing, an offer, a threat, a bribe,
a promise, a lie, a secret revealed, a plan. A window of about 400 lines usually yields 10–30
events. If the window starts mid-scene, extract only what happens inside your lines.

## 6. Checklist before writing the file

1. The file parses as JSON. Every id has a valid prefix and appears in the cast list or in
   `new_entities`.
2. Every vocabulary value is spelled exactly as listed above, in lowercase.
3. Every `quote` is copied character for character from a line listed in that event's `lines`.
4. All descriptive text is in English, all names are in canonical Ukrainian, and the time follows
   the controller's day anchor.

## 7. Worked example (invented text, not from the book)

The window is `window_201-207.json`. The cast list contains `char:olesia` (Олеся) and
`place:mill` (млин). The anchor is "line 201 is day 4, evening". The text:

```
201  Олеся постукала у ворота млина, коли вже стемніло.
202
203  Мірошник Тарас відчинив і впустив її, хоч і бурчав.
204
205  — Минулої зими вовки забрали в мене трьох овець, — сказав він. — Не ходи лісом сама.
206
207  Олеся кивнула і пообіцяла йти зранку битим шляхом.
```

The file `window_201-207.json`:

```json
{"new_entities": [
  {"id": "char:taras", "type": "person", "name": "Тарас", "aliases": ["мірошник"], "unnamed": false,
   "who": "The miller", "role": "host at the mill", "standing": "", "knows": [], "member_of": [], "first_line": 203}],
 "events": [
  {"id": "e1", "what": "Олеся arrives at the mill after dark and Тарас lets her in, grumbling.",
   "ekind": "arrival", "loudness": 0.1, "place": "place:mill",
   "time": {"kind": "day", "day": 4, "part": "evening", "years_before": null},
   "participants": [{"entity": "char:olesia", "role": "actor"}, {"entity": "char:taras", "role": "actor"}],
   "knowers": [{"entity": "char:olesia", "channel": "witnessed", "source": null, "line": 201, "when": null},
               {"entity": "char:taras", "channel": "witnessed", "source": null, "line": 203, "when": null}],
   "reactions": [], "lines": [201, 203], "quote": "Мірошник Тарас відчинив і впустив її", "confidence": 0.9},
  {"id": "e2", "what": "Wolves took three of Тарас's sheep last winter.",
   "ekind": "monster", "loudness": 0.3, "place": "place:mill",
   "time": {"kind": "before", "years_before": 0.5},
   "participants": [{"entity": "char:taras", "role": "victim"}],
   "knowers": [{"entity": "char:taras", "channel": "witnessed", "source": null, "line": 205, "when": null},
               {"entity": "char:olesia", "channel": "told", "source": "char:taras", "line": 205,
                "when": {"kind": "day", "day": 4, "part": "evening"}}],
   "reactions": [], "lines": [205], "quote": "вовки забрали в мене трьох овець", "confidence": 0.8},
  {"id": "e3", "what": "Тарас warns Олеся not to walk through the forest alone; she promises to take the road in the morning.",
   "ekind": "conversation", "loudness": 0.0, "place": "place:mill",
   "time": {"kind": "day", "day": 4, "part": "evening", "years_before": null},
   "participants": [{"entity": "char:taras", "role": "speaker"}, {"entity": "char:olesia", "role": "listener"}],
   "knowers": [{"entity": "char:taras", "channel": "witnessed", "source": null, "line": 205, "when": null},
               {"entity": "char:olesia", "channel": "witnessed", "source": null, "line": 207, "when": null}],
   "reactions": [{"party": "char:olesia", "reaction": "comply", "attitude": "positive",
                  "text": "Nods and promises to take the beaten road in the morning"}],
   "lines": [205, 207], "quote": "Не ходи лісом сама", "confidence": 0.9}]}
```

Notes on the example:

- The wolves are not an entity, because they matter only as the cause of the loss. If they acted
  again later in the text, they would become `creature:wolves`.
- Line 202 is empty, so it never appears in `lines`.
- The sheep story is a told past event: Тарас witnessed it, while Олеся learns it on day 4 (`told`,
  with Тарас as `source`).
