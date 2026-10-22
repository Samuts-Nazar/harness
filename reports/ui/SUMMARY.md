# Book UI: Task 4 and live check

Branch `book-ui`. Phone-sized notes.

## What was added
- `GET /api/places` gives `[{name, minutes}]`, nearest first, from the
  campaign world map (`[]` without a world). The drawer lists them; a tap
  writes «Іду до <місце>» into the input and closes the drawer.
- `/api/state` gains `actions: ["model_error","cut"]` (empty while a turn
  runs or after death) and `turn`.
- `POST /api/model_error {event, explanation}`: only the last world output is
  rewritten. The note is stored per campaign (a CORRECTION event) and fed to
  later generations: NPC notes to that NPC, narration notes to the narrator.
  `event: null` means the last narration. Explanation is required.
- `POST /api/cut {event, after_words}`: retroactive cut of the last NPC line
  (once). The rest is never said, its facts are rolled back, the NPC keeps the
  rest as a private intent.
- Transcript entries carry `turn` (and narration entries `event`); the
  client's reload replay matches by turn id now.
- Suggestions go through the engine's script check (a foreign-script run:
  ask once more, then cut it out).

## Live check
Vizima campaign (no canon file), live cheap models, a real browser at
390x844 against a real server. **7 turns** (one more than asked, the place
tap). Total spend of the final run: **$0.0150**. Two earlier runs of the
script died on a bug in the script itself, after 3 turns each, about
$0.029 together. All three runs: about **$0.044**, under the $0.10 cap.

| turn | first word | suggestions after turn | cost of the set |
|---|---|---|---|
| 1 | 15.0 s | 6.7 s | $0.00013 |
| 2 (tapped a suggestion) | 16.9 s | 3.2 s | $0.00014 |
| 3 | 20.7 s | 9.3 s | $0.00015 |
| 4 (next turn sent at once) | 18.0 s | dropped, stale | n/a |
| 5 (sent while 4's were in flight) | **10.6 s** | 7.1 s | $0.00031 |
| 6 (place tap «Іду до брама») | 22.7 s | 4.8 s | $0.00009 |
| 7 | 18.5 s | 13.4 s | $0.00010 |

- Suggestion latency is counted from the end of the turn's slow lane, when
  the assistant thread starts: 3.2 to 13.4 s, median about 6.9 s. A set costs
  about $0.00015 (0.01 to 0.03 cent). A turn costs $0.001 to $0.0035.
- **The next turn did not wait for suggestions.** Turn 5 was sent while
  turn 4's suggestions were still being written: `waited_s` 0.0 and its first
  word came at 10.6 s, the fastest of the run. Turn 4's own suggestions
  were dropped as stale, as designed. `waited_s` was 0.0 on all seven turns.
  One sample, but the mechanism is a separate thread that nothing joins.
- First word in 10 to 23 s is the narrator and NPC models, not the UI. In
  two aborted runs it was 7 to 71 s: the provider's speed varies a lot.

## Three suggestion sets (verbatim)
Turn 1, after the tavern opening:
1. `*закушую губу і чекаю, коли корчмар розкаже більше*`
2. `Питаю: чи не бачили тут останнім часом когось із клинком довшим за руку.`
3. `*киваю п'яному візнику в кутку* Ти, друже, бачив щось цікаве сьогодні?`

Turn 5, after the talk about pay:
1. `*киваю вартовому* Розкажіть більше про того коня, хто його знайшов.`
2. `А як винагороду ділитимуть — на всіх чи на того, хто вб'є чудовисько?`
3. `*повертаюся до візника* А ти бачив щось теї ночі, чи тільки ремінь крутиш?`

Turn 7, at the gate:
1. `*Підходжу до вартового зі списом* Я чув про коня на сході від Кречева. Хто його знайшов?`
2. `*дивлюся на діряву бочку* Чия бочка? Вона ж тече просто в землю.`
3. `*стаю ближче до другого вартового* Ви бачили сліди того, що роздерло коня?`

## Problems seen
- Turn 3's set speaks like the NPC, not like the player ("Стільки, скільки
  воно варте…"): the assistant mixed up who asks. Needs a prompt look.
- Small slips: "Мені потрібен коней", "теї ночі".
- (Fixed after review) The place tap wrote «Іду до брама». Places now carry
  a `to` phrase («до брами», «на ринок»); `/api/places` returns it as `go`
  («Іду до брами»), falling back to «Іду: <name>». Model error is allowed
  only on the very last world output (not a gesture), else 400.
- Model error and cut are tested offline (fake providers) and in the UI check
  with the real endpoints; they were not run on live models (budget).

## Screenshots (`reports/ui/`, real live session)
`turn-1.png`, `turn-2.png`, `turn-3.png`, `turn-4-before-suggestions.png`,
`turn-5.png` (the book page with suggestions above the input),
`turn-6.png`, `turn-7.png`, `drawer-people.png`, `drawer-places.png`.
Raw numbers: `live.json`. Script: `app/tests/live_ui.py`.
