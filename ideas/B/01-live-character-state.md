# B1. Live character state (the per-character panel)

Session B, task 5. No code, no paid calls. Web pages read on 2026-10-19. Labels: **[User]** = the user's own words, **[Added]** = my addition, **[Found]** = from outside, with link.

## 1. Seed

[User] "A panel per character carried from scene to scene." Draft list to complete: body (wounds, scars, fatigue, hunger, thirst, illness, poisons and elixir toxicity, intoxication, pain); timed effects (elixirs, oils, curses, magic); appearance (clothing and its condition, dirt and blood, hair, visible marks); equipment (worn, in hand, sheathed, condition); inventory with location (on body, bag, horse) and money; companions (horse, people); standing (wanted, disguised, reputation by place); posture and action (sitting, hiding, weapon drawn); inner state (mood, stress, fears, worldview change). "Each element observable or hidden. Others in a scene perceive the observable elements and may react." Open: "the player sees a panel for their own character; should it show only what the character knows about itself (an unnoticed poison not shown), while the AI knows everything?"

## 2. Completed idea

### 2.1 The panel is a view, not a store [Added]
`docs/decisions.md` says state is an append-only event log, records are open-ended (free text plus metadata), and there is "no fixed attribute sheet". So the panel cannot be a table of fields. It is a **projection**: current state derived from the log, grouped by a `kind` tag on each record (body / effect / appearance / gear / possession / companion / standing / posture / inner). The user's list is then the *default tag vocabulary and display grouping*, not a schema. New kinds (a curse the world invents) appear as records with a free-text label and the tag `other`, and are never blocked by the list.

### 2.2 Three independent properties of every panel record [Added]
The user's "observable or hidden" is one axis. The idea needs three, because they answer different questions:

| Property | Question | Who uses it |
|---|---|---|
| **truth** | What is actually the case? (code-owned, in the log) | narrator, extractor, world judgments |
| **perceptibility** | Can another person in the scene notice it, through which channel (sight, smell, hearing, touch), and how easily? | other characters' observation (feeds their isolated context) |
| **self-awareness** | Does the owner know it, suspect it, or feel only a symptom? | the player's own panel, the PC's context, the assistant (B2) |

Examples: fresh blood on a sleeve: truth yes, perceptible by sight (high), self-aware yes. Slow poison: truth yes, perceptible only to a healer/witcher (low), self-aware *no* until a symptom record ("queasy") appears. A curse on the PC that a sorcerer sees on sight: perceptible to a few, self-aware no. A fear the character hides: perceptible low, self-aware yes.

Key move: the owner's self-awareness is **the same epistemic filter the decisions already apply to NPCs** ("a character's context contains only facts that character witnessed or plausibly heard"), applied to the character's own body. [User] said the PC is a being of the world like any other (A2 seed); so the PC's knowledge of own body is not a special UI rule, it is a fact-with-source: "I feel queasy" is a fact the PC has through the channel *interoception*; "the elixir in my stomach is poisoned" is a fact the PC lacks.

### 2.3 Elements the draft list lacks [Added]
- **Concealment layer**: what is worn over what (cloak hides sword; sleeve hides scar). Perceptibility depends on it.
- **Treatment status** of wounds and illness (bandaged, stitched, splinted, untreated) and time since.
- **Sleep debt** and time of last meal/drink (inputs for fatigue/hunger without a stat).
- **Temperature and wetness** (cold, soaked), **cleanliness and smell** (smell is a perception channel in the Witcher: witchers, animals, dogs).
- **Senses state**: darkness adaptation, deafness after a blast, blindness; these change what the PC perceives, so they feed retrieval for the PC.
- **Hands**: what is occupied (holding reins, torch). Cheap and it drives many plausible reactions.
- **Light and noise the character emits** (torch, armour clank). Perceptibility of the *whole person*, not an element.
- **Carried load** and **chain of custody** of items (stolen, gifted, sealed; who knows it is stolen).
- **Obligations**: promises, debts, oaths, orders. They are facts with two parties; they belong in the panel because they shape behaviour.
- **Magic state specific to the Witcher world**: Signs strain, medallion reaction, mutations. The word is "engine is world-agnostic": put these under `other` with world-pack-defined display labels.
- **Companions carry the same panel** (a horse's wound, a companion's fear). The panel structure is per character and recursive; the companion panel obeys the same self-awareness rule (the PC sees only what the PC can see of a companion).
- **Short change strip**: what changed since the last scene (new wound, effect ended). Matters more on a phone than the full panel.

### 2.4 What shows on the player's panel [Added]
Two answers to the open question, and they are not exclusive:
- Show the **self-known projection** only (truth filtered by self-awareness). Hidden causes never appear; their *symptoms* do. This is the consistent reading of "player sees only the story".
- Offer the full truth only in the dev/debug view (already decided as visible only there).

The design question the user must decide is how strict the projection is (see questions): the PC is not only a body but a mind that can be wrong about itself (it may *believe* it is fine while a wound festers, or believe a wrong cause for a symptom). The panel then shows beliefs, and the truth can differ. [Found] Disco Elysium makes self-knowledge unreliable on purpose: skills speak, some mislead ([Slant Magazine review](https://www.slantmagazine.com/games/disco-elysium/), [Vector review](https://vector-bsfa.com/2025/01/17/review-disco-elysium-2019-za-um/)).

### 2.5 How others perceive it [Added]
Perception of the PC's observable elements by NPC *N* in the scene is an **observation event** written into N's memory (the same record type as "N heard X"), after a salience judgment: "would N notice this, and would N care?" That reuses the decided rule "an NPC must not comment on what it had no channel to learn, and should not comment on what it would not care about". Practical consequences: an NPC cannot react to a hidden scar; a scene entry produces a small set of "N sees: ..." facts, not a free-for-all.

[Found, own experiment] E3 (`reports/experiments/E3.md`) shows witness lists from an extractor are weak (exact agreement 0.23-0.55). So *who perceives* must be computed in code from the scene's cast, location, light and distance; the extractor only proposes the *element* (the new stain, the new wound), and injury extraction was good (F1 0.78-0.95 for all models tested).

## 3. Options

### Option A. Tagged records, panel derived on read, perception only at salient moments
- **How:** every panel item is a normal fact record with metadata `kind`, `perceptibility` {channel, ease}, `self_awareness` {known | suspected | unaware}, optional `expires_at` / `ticks`. The extractor proposes diffs (new wound, torn cloak); code validates (typed transaction pattern from the code study, pattern 2) and stores. Panel = query of live records with `self_awareness != unaware`, grouped by `kind`. Others' perception: when a character enters a scene or an element changes, one batched Jev call per observer: "would N notice [list of observable elements] given [light, distance, concealment]?" with a score; above threshold, write an observation fact.
- **Strengths:** minimal machinery, fits decisions exactly, no new schema.
- **Weaknesses:** `self_awareness` and `perceptibility` must be set at creation time by a judgment, so an extractor error propagates; symptoms of hidden conditions must be authored (see Option B).
- **Cost:** per turn: extraction already exists (0 extra). Perception: 1 batched Jev call per observer per scene entry or change (E2: Jev p50 0.28 s, batching four questions in one call cut latency about 4x). Expiry of timed effects is code, 0 LLM calls.

### Option B. Option A plus explicit "condition" records with a hidden cause and generated symptoms
- **How:** a hidden condition (poison, curse, infection) is stored as one record with `self_awareness: unaware`, plus a **symptom schedule**: when time advances, a typed judgment ("after 6 hours with this poison, what would the PC notice now? choice: nothing / mild nausea / sharp pain / collapse") may emit a new, self-known symptom record that links back to the cause by id. The narrator receives symptoms, not the cause; the cause is revealed when someone with a channel (healer, witcher senses, test) records a diagnosis event.
- **Strengths:** hidden-state drama (poisoned wine) works properly; the player cannot read the cause from the UI; consistent with E1 (filter at retrieval, not by instruction).
- **Weaknesses:** needs a progression judgment, which touches the undecided mechanics topic (how fast does a poison act, does a wound heal). Placeholder until Session A (A5) says more: ask Jev/LLM at each long time skip, canon retrieval for the Witcher-specific cases.
- **Cost:** 1 extra Jev call per active hidden condition per time advance (not per turn); canon retrieval only for named canon items (elixirs, monster poisons).

### Option C. Panel as short narrated prose ("how you feel") plus a few chips
- **How:** instead of a table, a small LLM call after each scene writes 2-3 sentences from the PC's point of view, built only from self-known records; chips only for the few items that need exact tracking (money, weapon in hand).
- **Strengths:** best for immersion and phone screen size; hides numbers naturally; no field-by-field display design.
- **Weaknesses:** one more generation per scene; prose can invent ("a dull ache in the knee") facts that are not in the records, so the output must pass the same extractor/validation or be marked as presentation-only and never re-extracted.
- **Cost:** 1 small generation per scene (not per turn); latency off the critical path, can be produced while the player reads.

### Reading the options
- If **clean hidden-information play** (poison, disguise, curse) matters most, A + B.
- If **screen economy and mood** matter most (phone play), C on top of A.
- If **simplicity first** and hidden effects are rare, A alone, and add B when the first hidden-poison story is wanted.
- They compose: A is the base in all cases.

## 4. Prior art
- [Found] **Project Zomboid** moodles: infection has "no moodle that displays directly"; the player sees symptoms (queasy, stress) while an invisible timer runs ([community thread](https://steamcommunity.com/app/108600/discussions/0/3397427506578090155)). The nearest shipped example of symptom-not-cause display.
- [Found] **Dwarf Fortress**: per-body-part wounds (open/bruise/scar/missing), pain driving unconsciousness, thoughts and preferences per dwarf ([wiki: Wound](https://dwarffortresswiki.org/index.php/Wound), [Thoughts and preferences](https://dwarffortresswiki.org/index.php/DF2014:Thoughts_and_preferences)). Shows how far a body-detail model can go; the cost is a fixed anatomy, which this engine does not want.
- [Found] **Kenshi**: limb-level damage, severing, hidden damage under a replaced limb ([health guide](https://kenshi.fandom.com/wiki/Guide_to_Health), [thread](https://steamcommunity.com/app/233860/discussions/0/1741104717704212092)). Example of consequence persistence tied to a body part.
- [Found] **Disco Elysium**: the character's own mind as an unreliable narrator ([Slant](https://www.slantmagazine.com/games/disco-elysium/)). Prior art for the "belief differs from truth" layer.
- [Found] **SillyTavern** tracker-style extensions (state blocks inside chat) are the usual shape of "panel" in LLM roleplay; the code study found their weakness: text memo merged by regex, no per-character view (`reports/code_study/SUMMARY.md`, Multihog).
- [Found, own study] ReverieMem's visibility sets and Concordia's per-entity memory (`reports/code_study/`) are the right base for perceptibility and self-awareness.

## 5. Interactions
- **Decisions:** epistemic isolation (self-awareness is the same rule); event log (panel derived; rollback restores it for free); two-level simulation (companion panels for off-screen agents update cheaply); canon check (Witcher poisons and Signs).
- **Session A:** A2 belief and trust (the PC's beliefs about itself are beliefs with a source); A5 mechanics (progression of wounds, toxicity thresholds); A6 time (timed effects need a clock; in flowing mode effects tick while the player is silent).
- **B2:** the assistant reads the self-known projection only.
- **B3:** posture/action and hands feed quick actions; unsaid intents are the NPC analogue of "inner state".
- **B4:** appearance records are the input for portraits and scene images, so a bloody sleeve shows in the picture.
- **B5:** how strict the self-awareness filter is, and how much numeric detail to show, are player settings.

## 6. Questions for the user
1. Якщо персонаж отруєний і сам цього не знає, чи хочеш ти бачити в панелі лише симптоми ("нудить"), а причину дізнаватись у історії?
2. Чи може персонаж помилятися щодо власного стану (думати, що здоровий, коли це не так), чи панель має показувати правду про тіло, а помилятись може лише про зовнішній світ?
3. Яка панель тобі потрібніша на телефоні: короткі позначки-чипси, чи кілька речень "як ти почуваєшся", чи обидва?
4. Чи хочеш ти, щоб напарники (кінь, люди) мали таку саму панель, і чи бачити її ти маєш лише в межах того, що бачить твій персонаж?
5. Які елементи зі списку для тебе обов'язкові з першого дня, а які можуть зачекати (наприклад, ґрунтовна вага речей і ланцюжок "хто чий предмет")?
