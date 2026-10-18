# Session B (player experience): summary

Date: 2026-10-19. No code, no paid calls. Files: `01-live-character-state.md`, `02-player-turn-assistant.md`, `03-breaking-the-chat-format.md`, `04-immersion-layers.md`, `05-settings.md`. Session A's files were not touched.

## Topics and main options

**B1. Live character state**
- A: tagged records (kind, perceptibility, self-awareness), panel derived on read, others' perception by a batched Jev call at salient moments.
- B: A plus hidden "condition" records that emit self-known symptoms over time (poison, curse).
- C: panel as short narrated prose plus a few chips (phone-friendly).
- Core idea: panel = projection of the log; self-awareness is the same epistemic filter applied to the PC's own body.

**B2. Player turn assistant**
- A: whole-draft regeneration with feedback in the prompt.
- B: unit-level edit: words become keep/drop/add/tone operations, code applies them (kept text stays identical).
- C: tap-to-mark units (keep/drop/rewrite) plus a note.
- D: intent menu first, expand second.
- Core idea: assistant context = PC-known view; drafts stay out of the log; output-side Jev check; learning as an editable text note (PRELUDE/CIPHER).

**B3. Breaking the chat format**
- A: speech-paced stream, interrupt button, reaction taps.
- B: A plus hotspots in text and quick actions from the panel.
- C: B plus ambient events with a director and budget.
- D: C plus Façade-style beats (later).
- Core idea: one playback clock defines "said" (displayed/heard) for interruption, voice and time.

**B4. Immersion layers**
- Music: M1 tagged library; M2 pre-generated mood loops (open model); M3 live streaming generation (experimental vendor API).
- Voice: V1 local Ukrainian TTS (3 voices); V2 multilingual open models (Ukrainian unverified); V3 hosted API.
- Images: I1 expression portraits; I2 key-beat illustrations; I3 clips (deferred).
- Core idea: media are derived views made by a worker from player-visible text; never block the story, never leak.

**B5. Settings**
- A: flat settings page.
- B: presets plus advanced, campaign changes applied at scene boundary and logged.
- C: conversational "session zero" for limits, plus in-story safety verbs (pause / veil / rewind).
- Core idea: separate invariants, presentation settings and campaign settings (the last are logged events).

## All questions for the user (Ukrainian)

**B1**
1. Якщо персонаж отруєний і сам цього не знає, чи хочеш ти бачити в панелі лише симптоми ("нудить"), а причину дізнаватись у історії?
2. Чи може персонаж помилятися щодо власного стану (думати, що здоровий, коли це не так), чи панель має показувати правду про тіло, а помилятись може лише про зовнішній світ?
3. Яка панель тобі потрібніша на телефоні: короткі позначки-чипси, чи кілька речень "як ти почуваєшся", чи обидва?
4. Чи хочеш ти, щоб напарники (кінь, люди) мали таку саму панель, і чи бачити її ти маєш лише в межах того, що бачить твій персонаж?
5. Які елементи зі списку для тебе обов'язкові з першого дня, а які можуть зачекати (наприклад, ґрунтовна вага речей і ланцюжок "хто чий предмет")?

**B2**
1. Коли ти кажеш "ця частина була чудова", чи має вона після правки лишитись слово в слово, чи можна її трохи переписати?
2. Чи хочеш ти спершу бачити короткі варіанти намірів ("натиснути", "ухилитись", "виграти час"), чи одразу готовий текст?
3. Чи має помічник сам показувати чернетку після кожного ходу, чи лише коли ти просиш?
4. Якщо ти сам напишеш у відгуку щось, чого твій персонаж не знає, помічник має це відхилити, чи лише попередити тебе?
5. Чи готовий ти дозволити помічнику вести коротку "нотатку про твій стиль", яку ти можеш читати й правити, щоб він з часом звучав більше як ти?

**B3**
1. Чи хочеш ти малий набір швидких реакцій (кивнути, нахмуритись, покласти руку на меч) поки NPC говорить, чи це має завжди бути текстом?
2. Чи має історія підсвічувати імена й предмети, щоб ти торкався їх замість писати, наприклад "оглянути"?
3. У "потоковому" часі що має бути в тиші: лише звуки навколо (дзвін, дощ), чи ще й NPC, які самі підходять і щось кажуть?
4. Коли ти ховаєш телефон або йдеш з вкладки, світ має зупинятися (так я б зробив за замовчуванням) чи йти далі?
5. Чи потрібні тобі "відмотати" і "а що, якби" як звичайні кнопки, чи це лише для налагодження?

**B4**
1. Що для тебе важливіше: щоб музика була унікальна під цей світ, чи щоб працювала стабільно й без інтернету?
2. Чи досить для початку озвучувати лише оповідача й головних персонажів, а решту лишати текстом?
3. Чи допускаєш ти, що текст історії іде на зовнішній сервіс озвучення, чи голос має бути лише на твоєму комп'ютері?
4. Що тобі краще для початку: портрети персонажів зі зміною виразу, чи картинки до ключових моментів?
5. Чи можеш ти послухати кілька зразків української озвучки й сказати, яка якість для тебе прийнятна (я цього зробити не можу)?

**B5**
1. Які налаштування тобі треба змінювати під час гри, а які достатньо вибрати один раз на початку кампанії?
2. Чи згоден ти, щоб налаштування змісту (наскільки жорстоко, що лишати за кадром) визначались розмовою на початку, а під час гри були кнопки "пауза / за кадр / перемотати"?
3. Чи хочеш ти готові набори ("Історія", "Симуляція", "Хардкор") з можливістю розгорнути деталі?
4. Чи мають налаштування змісту діяти й на картинки та озвучення, чи тільки на текст?
5. Чи треба, щоб після зміни настройки світу було видно запис про неї в журналі гри, чи це лишається службовим?

## Possible conflicts with `docs/decisions.md` (evidence; the document was not changed)

1. **"The player sees only the story" vs the panel, hotspots, reaction palette, journal.** These are interface beyond narration. They show derived state, not background processes, so they are probably compatible, but the document should say whether "story" includes a character panel and controls. Evidence: B1 and B3 designs depend on it.
2. **Interruption: what "said" means.** The cut point is defined only as a point "inside the NPC's utterance". In streaming (generated faster than shown) and in voice (audio position) the generated text and the delivered text differ. Without defining *said = delivered to the player* the rollback boundary is ambiguous. Evidence: B3 section 2.1.
3. **Flowing time vs "quality beats latency".** Flowing mode asks the world to act without waiting while each NPC line is a separate call of seconds. Compatible only as slow flow; the document should not promise real-time feel. Also phone backgrounding must pause time. Evidence: B3 section 2.4.
4. **"No fixed attribute sheet" vs a panel with categories.** Not a true conflict if categories are tags on open records (B1 2.1); noted so the panel is not implemented as a fixed schema by accident.
5. **Witness lists** (from `reports/experiments/E3.md`, already known): perception of the PC's observable state depends on who is present; the decisions say witness/hearer metadata is stored, but E3 shows extractors get it wrong, so it should be computed in code. Evidence: E3 exact agreement 0.23-0.55.

## Cross-session notes
- Session A (topics A2 belief, A5 mechanics, A6 time) decides parts B1 and B3 depend on: progression of wounds and poisons, how time passes during travel and sleep, how fast timed effects tick.
- What I could not verify: Ukrainian support in Fish Audio S2, any hosted Ukrainian TTS service (none named), ACE-Step on 8 GB VRAM, whether anyone ships keep/drop-by-words editing. Each is stated as unverified in the topic files.
