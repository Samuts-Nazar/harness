# B5. Settings

Session B, task 5. No code, no paid calls. Web pages read on 2026-10-19. Labels: **[User]**, **[Added]**, **[Found]** (with link).

## 1. Seed

[User] "Which behaviours should be player settings (assistant learning, time mode, how much the player sees, content intensity, etc.)."

## 2. Completed idea

### 2.1 Three kinds of "setting" [Added]
Not everything adjustable is the same kind of thing, and mixing them causes bugs:

1. **Invariants (not settings).** Epistemic isolation, code-owned state, append-only log, canon vs campaign store. Turning these off would break the engine's guarantees (E1: filtering is the guarantee). The only legitimate bypass is the dev/debug view, already decided.
2. **Presentation settings (device or player level).** Text pace, voice/music/image on-off and volume, panel layout. They change nothing in the world; no log entry needed; they can differ between phone and laptop.
3. **Campaign settings (world-affecting).** Time mode, content limits, how harsh consequences are, canon strictness, assistant's permissions. They change what happens or what is generated, so changes must be **logged as events** (for reproducibility and rollback: "at turn 212 the user changed content intensity to X"), and some should only change at defined moments (scene boundary).

### 2.2 Candidate list, sorted [Added]
**Presentation (player/device):** text pace and pause style; skip behaviour; voice, music, images on/off and volume; font size; panel detail level (chips / prose / both); hotspots on/off; reaction palette on/off; notifications for ambient events.

**Information (campaign):**
- *How much the player sees about their own character*: self-known projection (B1) vs more explicit numbers/labels. The truth-view is dev-only, not a setting.
- *Journal*: PC-knowledge log on/off.
- *Suggestions*: whether the assistant proposes drafts automatically (B2).

**Time (campaign):** turn-based vs flowing (decided as two modes to compare); silence timer length; auto-pause on background (should be a fixed rule, B3); how ambient events scale; speed of passage during travel/sleep/wait (Session A6).

**Assistant (player):** on/off; length default; learning level off/session/persistent, with the style note readable and editable; whether the user may knowingly override the knowledge boundary (warn vs reject). The boundary itself ("PC-known facts only") is an invariant.

**Content (campaign):** categories and intensity: violence and gore, sexual content, cruelty/abuse, slurs and discrimination, horror, despair/death of companions. The Witcher books contain heavy material, so defaults matter. Modes per category: allowed in full / allowed but off-screen ("veil") / not present ("line").

**Consequence harshness (campaign):** how forgiving the world is. Mechanics are undecided (no dice/stats), so this is a **placeholder** only: record the user's preference as a free-text/choice setting and pass it into the judgments that decide outcomes; no behaviour is built until A5.

**Canon strictness (campaign):** how much drift from the books is accepted when a campaign event justifies it vs always rejected. This tunes a decided check without changing it (see Possible conflicts: only if the user wants it).

**Technical (player/device):** which model for which subtask, API key, cost cap per session, debug view on/off, media providers.

### 2.3 Where and when a setting is chosen [Added]
- **At the start** ("session zero"): the few settings that shape the whole campaign (content limits, time mode, assistant level).
- **Anytime, small:** presentation settings and the assistant.
- **In-story safety verbs**, not a settings page: pause, fade to black, skip, rewind. In tabletop this is the X-card idea: stop without having to explain.
- Settings apply at the next scene boundary unless they are presentation-only, so no scene is half in one mode.
- Defaults come from **presets** ("Story", "Simulation", "Hardcore") and can be unfolded into the individual settings; most users will never open the list.

## 3. Options

### Option A. One settings page, flat list, immediate effect
- **How:** every setting in a list; changes apply immediately; world-affecting ones logged.
- **Strengths:** simplest to build and understand.
- **Weaknesses:** overwhelming; allows changing time mode or content mid-sentence; no guidance for new users.
- **Cost:** none in calls.

### Option B. Presets + advanced + scene-boundary application
- **How:** three presets set sensible values; an "advanced" fold exposes all; campaign-affecting changes queue to the next scene boundary and are written as events.
- **Strengths:** friendly default; keeps the log consistent; presets are a place to put opinionated defaults (e.g. Simulation = flowing time, self-known panel, strict canon).
- **Weaknesses:** presets hide detail; the three presets must be designed and maintained.
- **Cost:** none in calls.

### Option C. Conversational session zero + in-story safety verbs
- **How:** at campaign start an LLM interviews the user in plain language ("what do you not want to see? how rough should the world be?") and writes the typed settings, which the user confirms. During play only the safety verbs exist plus a small quick-settings drawer. [Found] This resembles tabletop *Lines and Veils* discussed at the table before play, and the *X-Card* / *Script Change* tools used during play ([guide](https://crowscorner.bearblog.dev/playing-with-care-a-guide-to-rpg-safety-tools/), [Roll20 guest blog on Lines and Veils](https://blog.roll20.net/posts/guest-blog-an-introduction-to-lines-and-veils/)).
- **Strengths:** natural for an AI game; people state preferences in words better than they pick checkboxes; content limits get context ("not torture, but war is fine").
- **Weaknesses:** one LLM conversation to build and verify; wording must map to a bounded typed schema; the user should be able to see and edit the result.
- **Cost:** about one short conversation once per campaign.

### Reading the options
- If **speed to a working prototype** matters most: A (then B).
- If **a new user (or later other users)** must get a good experience without reading: B.
- If **content comfort and tone** matter most (the Witcher is dark): C for limits, plus the safety verbs in play.
- A, B, C are layers, not rivals: C can fill B's settings, which A displays.

## 4. Prior art
- [Found] **Lines and Veils** (Ron Edwards, in a Sorcerer supplement): lines = topics not in the game; veils = topics that happen off-screen ([guide](https://crowscorner.bearblog.dev/playing-with-care-a-guide-to-rpg-safety-tools/)).
- [Found] **X-Card** (John Stavropoulos): tap to stop; the game resumes without the content. **Script Change** (Beau Jágr Sheldon): pause, fast-forward, rewind, frame-by-frame ([same guide](https://crowscorner.bearblog.dev/playing-with-care-a-guide-to-rpg-safety-tools/), [StartPlaying overview](https://intercom.help/startplaying/en/articles/8719199-safety-tools)).
- [Found] **AI Dungeon**: input modes, retry and editing as player controls ([help](https://help.aidungeon.io/faq/how-to-play)).
- [Found] **SillyTavern Guided Generations**: every action button is individually shown or hidden in settings ([wiki](https://github.com/Samueras/GuidedGenerations-Extension/wiki/Settings)). A typical example of a flat list of optional features.
- Difficulty and accessibility option menus in games (assist modes, sandbox options) are a known pattern; I did not read a specific source in this session, so no link.

## 5. Interactions
- **Decisions:** epistemic isolation and event log are invariants; "player sees only the story" (settings on how much of the panel shows must not expose truth); two time modes (a setting by design); canon drift check (strictness knob).
- **B1:** self-awareness strictness, panel form.
- **B2:** learning level, override policy.
- **B3:** pace, silence timer, ambient frequency, safety verbs.
- **B4:** layer toggles, volume, content limits for images.
- **Session A:** A5 consequence harshness; A6 time.

## 6. Questions for the user
1. Які налаштування тобі треба змінювати під час гри, а які достатньо вибрати один раз на початку кампанії?
2. Чи згоден ти, щоб налаштування змісту (наскільки жорстоко, що лишати за кадром) визначались розмовою на початку, а під час гри були кнопки "пауза / за кадр / перемотати"?
3. Чи хочеш ти готові набори ("Історія", "Симуляція", "Хардкор") з можливістю розгорнути деталі?
4. Чи мають налаштування змісту діяти й на картинки та озвучення, чи тільки на текст?
5. Чи треба, щоб після зміни настройки світу було видно запис про неї в журналі гри, чи це лишається службовим?
