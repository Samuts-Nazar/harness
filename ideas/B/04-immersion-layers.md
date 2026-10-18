# B4. Immersion layers (music, voice, images, animation)

Session B, task 5. No code, no paid calls (nothing here was tried; all quality and speed claims are from the cited pages). Web pages read on 2026-10-19. Labels: **[User]**, **[Added]**, **[Found]** (with link). Tool and model facts in this area age in months; re-check before building.

## 1. Seed

[User] "Background music by mood, voiced dialogue (Ukrainian), images and possibly animated scenes, growing as technology allows. Played on phone and laptop."

## 2. Completed idea

### 2.1 Architecture rule: media are derived views [Added]
Every layer is produced by a **media worker** that reads the event log (what the player was shown) and writes only media files, never state. Consequences:
- A failed or slow media call never blocks the story ("growing as technology allows" = layers can be added or absent).
- Media can be regenerated later with a better model from the same log.
- **No leak through media.** Image and voice prompts are built from the *player-visible* text and the PC-perceivable scene, never from the narrator's omniscient view. An image generated from an omniscient description could show the hidden assassin. Same filter as B2.
- Each layer is a **setting** (B5) and is independent: music without voice, voice without images.

### 2.2 Music [Added]
Needed: (1) a **mood signal**; (2) a way to turn it into sound; (3) rules so it does not flap.
- **Mood signal:** one typed judgment per scene beat (not per sentence): choice over a small world-pack-defined set (calm, tense, sorrowful, eerie, combat, tavern, travel...) plus an intensity score; inputs are the narration and B1's stress/fear and B3's ambient state. Jev fits (typed choice and score, 0.28 s p50 in E2).
- **Stability rules:** minimum hold time, change only when the mood differs by a margin (hysteresis), crossfade, duck under voice.
- Fits the single decision "player sees only the story": the music is part of the story's presentation.

### 2.3 Voice (Ukrainian) [Added]
- **Voice identity is a field on the character record** (voice id, pace, register); emotion tag per line from the line-generation call (the decisions already give each NPC line its own call, so the emotion cue is free).
- **Lexical stress and Ukrainian prosody are the quality problem**, not raw model quality. [Found] A Ukrainian voice-cloning TTS study reports a sentence-level stress-prediction preprocessing gave +0.87 MOS ([UCU repository entry](https://er.ucu.edu.ua/items/041afe17-faa2-4eb6-864f-33bf781fd249); the number is the thesis's own, I did not verify the method).
- **Alignment for interruption:** the cut point must map to a word index (B3). Models that return word timings, or per-sentence synthesis, make this possible; whole-file output without timings needs forced alignment (a speech-recognition pass), which adds latency.
- **Narrator vs NPCs:** voicing only the narrator and the main NPCs, text for extras, is a natural first scope.

### 2.4 Images and animation [Added]
- **Inputs:** B1's appearance records (clothing, blood, scars, hair, weapons drawn) are exactly what an image prompt needs; they make a bloody sleeve appear in the picture and keep characters consistent across scenes.
- **Granularity:** (a) character portraits with a few expression variants, selected by mood; (b) scene illustrations on key beats only; (c) short animated clips. Cost and latency grow steeply from (a) to (c).
- **Consistency** (same face across scenes) is the hard problem; a per-character reference image kept as a record is the standard approach.
- **Rating and content:** image models have their own content limits; B5 content intensity interacts.

### 2.5 Phone and laptop [Added]
- Browsers generally require a user gesture before audio starts and restrict background audio; a PWA or a "tap to begin" gate is needed. (General web platform behaviour, not verified in this session for the current OS versions.)
- Mobile data and battery: streaming audio is fine; images should be cached; video clips need a size budget.
- Hosting is undecided, and it decides *where media models run* (user's own GPU vs API). Offer layers as pluggable providers.

## 3. Options (per layer)

### Music

**M1. Tagged library, picked by the mood signal.**
- **How:** a folder of tracks/loops tagged by mood and intensity; mood judgment selects, code crossfades.
- **Strengths:** zero generation latency, predictable quality, works offline, trivial on a phone.
- **Weaknesses:** finite variety; **rights**: using commercial game soundtracks for something that is distributed to others is a legal problem, personal use is a grey zone; royalty-free or self-made libraries are safe.
- **Cost:** 1 Jev call per beat, no audio generation.

**M2. Pre-generated mood sets with an open model.**
- **How:** generate a library of loops per mood offline, once per world pack, with a local model. [Found] ACE-Step 1.5 (released 2026-01-28, MIT licence) is reported to generate a full song in under 10 s on an RTX 3090 with under 4 GB VRAM, and to support LoRA personalisation ([AMD blog](https://www.amd.com/en/blogs/2026/commercial-grade-ai-music-generation-on-amd-ryzen-ai-and-radeon-ace-step-1-5.html), [overview](https://rits.shanghai.nyu.edu/ai/ace-step-1-5-open-source-music-generation-that-rivals-commercial-ai/)). A community post titled "extremely slow on 8GB VRAM" exists ([Patreon](https://www.patreon.com/posts/157516177)); I could not read it, so treat 8 GB behaviour as untested.
- **Strengths:** a world-specific sound (Witcher-flavoured, no copyrighted score), generated once, played anywhere; safe licence.
- **Weaknesses:** quality varies; a human ear has to curate; loops need to loop cleanly.
- **Cost:** one-time generation; runtime same as M1.

**M3. Live streaming generation steered by the mood signal.**
- **How:** a streaming music model receives weighted text prompts that change with the mood. [Found] Google's Lyria RealTime: persistent WebSocket, send `WeightedPrompt` messages at any time, smooth transitions, 48 kHz stereo PCM; it is **experimental, instrumental only, output watermarked**, safety filters may block prompts ([docs](https://ai.google.dev/gemini-api/docs/realtime-music-generation)). The "weights" map directly to a mood vector.
- **Strengths:** continuous, adaptive, never repeats.
- **Weaknesses:** a paid API call stream for the whole session, an experimental model, a connection that must stay up on mobile; vendor-specific; not model-agnostic.
- **Cost:** continuous for the duration of play; not measured here.

Reading: **if reliability and offline play matter most, M1 (own or royalty-free library); if a unique world-fitting score matters most and you can curate, M2; if "music that follows the scene second by second" matters most and you accept a vendor service, M3.** M1 and M2 can share the same player code (M2 is M1 with a generated library).

### Voice

**V1. Local open Ukrainian TTS.**
- **How:** [Found] `tts_uk` (MIT licence): three voices (Tetiana, Lada: female; Mykyta: male), RAD-TTS++ acoustic model with Vocos vocoder at 44.1 kHz, controls for duration, pitch and energy; the page mentions no streaming ([PyPI](https://pypi.org/project/tts-uk/), [repo](https://github.com/egorsmkv/tts_uk)).
- **Strengths:** free, private, Ukrainian-native, fast vocoding.
- **Weaknesses:** only three voices; no cloning; emotion control is by prosody parameters, not by tag; alignment for interruption must be added.
- **Cost:** local compute only.

**V2. Multilingual open models with voice cloning.**
- **How:** [Found] Fish Audio S2 (March 2026) claims "80+ languages", inline emotion cues, multi-speaker dialogue, fully open-source ([changelog](https://docs.fish.audio/changelog)); the pages I read do not list Ukrainian, so **Ukrainian support is unverified**. Qwen3-TTS lists 10 languages (Chinese, English, Japanese, Korean, German, French, Russian, Portuguese, Spanish, Italian): **Ukrainian is not listed** ([summary](https://www.letsdatascience.com/news/qwen3-tts-delivers-high-fidelity-multilingual-speech-for-rea-2b40c647)).
- **Strengths if Ukrainian works:** per-character voices by cloning, emotion tags, streaming.
- **Weaknesses:** Ukrainian quality must be tested by ear; stress errors likely without preprocessing; GPU needs.
- **Cost:** local compute or hosted per-character price (not looked up).

**V3. Hosted API TTS with Ukrainian voices.**
- **How:** a commercial service. I did not verify specific services in this session, so no names or prices are claimed. They exist; check quality, voice count, streaming and price.
- **Strengths:** best quality likely, many voices, streaming, word timings sometimes provided.
- **Weaknesses:** per-character cost scales with play time; privacy: the story text leaves the machine; conflicts with "own hardware or own key" only if the key is not the user's.
- **Cost:** per character of text; a long campaign is a lot of characters.

Reading: **if privacy and zero running cost matter most, V1 now and revisit; if distinct NPC voices and emotion matter most, test V2 for Ukrainian first, else V3; if Ukrainian quality matters most, listen to V1 and V3 side by side before anything else.** Narrator-only voice is a sensible first step for all three.

### Images and animation

**I1. Expression portraits.** Per-character reference image plus a small set of pre-generated expressions; the mood/emotion tag selects. Cheapest, VN-style, great on a phone. Generated when the character becomes a persistent agent (decided trigger), so the cost is proportional to characters the player actually meets.

**I2. Key-beat scene illustrations.** A beat flagged as notable gets an image generated from the player-visible scene text plus appearance records, asynchronously; it appears when ready. Latency tens of seconds is acceptable because it does not block. Consistency via reference images.

**I3. Short animated clips.** Video models; minutes per clip on consumer hardware (not measured here); use only for very rare beats until the technology is cheaper. Design hook only: a media job type "clip" with a reference to the beat.

Reading: **if cost and phone-friendliness matter most, I1; if "the story shown as pictures" matters most, I1 + I2; I3 is deferred.** Local generation depends on the user's GPU, which is also what runs local LLMs; the hosting decision is open.

## 4. Prior art
- [Found] Adaptive/generative game music overview and examples: PAMG progressive adaptive generator ([FARM 2024](https://icfp24.sigplan.org/details/farm-2024/7/A-Progressive-Adaptive-Music-Generator-PAMG-An-Approach-to-Interactive-Procedural-)), condition-driven adaptive music ([arXiv 1306.1746](https://arxiv.org/pdf/1306.1746)). Search summaries on 2026 AI-music tooling are marketing-grade ([Soundverse](https://www.soundverse.ai/blog/article/ai-music-in-gaming)); treat as pointers only.
- [Found] Lyria RealTime, ACE-Step 1.5 (above).
- [Found] `tts_uk` and the UCU voice-cloning thesis (above), plus a curated hub of Ukrainian speech tools ([search result: egorsmkv speech-recognition-uk](https://www.sourcepulse.org/projects/2336415)).
- [Found] Left 4 Dead director: music and visual cues from the director's emotional state ([Wikipedia](https://en.wikipedia.org/wiki/Left_4_Dead)).
- [Found] Visual-novel and AI-roleplay frontends already use expression portraits; I did not find a specific cited source in this session, so no link.

## 5. Interactions
- **Decisions:** "player sees only the story"; model-agnostic and "other users later: own hardware or own key" (media providers must be pluggable); hosting undecided.
- **B1:** appearance records feed images; stress and fear records feed the mood signal.
- **B3:** the playback clock is shared with voice; ambient events and music must agree.
- **B5:** every layer is a toggle; volume and voice choice; content intensity affects images most.
- **Session A:** A1/A3 mood of regions; A6 time passing (travel music).

## 6. Questions for the user
1. Що для тебе важливіше: щоб музика була унікальна під цей світ, чи щоб працювала стабільно й без інтернету?
2. Чи досить для початку озвучувати лише оповідача й головних персонажів, а решту лишати текстом?
3. Чи допускаєш ти, що текст історії іде на зовнішній сервіс озвучення, чи голос має бути лише на твоєму комп'ютері?
4. Що тобі краще для початку: портрети персонажів зі зміною виразу, чи картинки до ключових моментів?
5. Чи можеш ти послухати кілька зразків української озвучки й сказати, яка якість для тебе прийнятна (я цього зробити не можу)?
