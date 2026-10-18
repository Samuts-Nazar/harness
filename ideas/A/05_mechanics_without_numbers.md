# A5. Mechanics without tabletop numbers

Source legend: **[V]** = found via search on 2026-10-19; **[M]** = from memory, link not opened.

## 1. Seed

> "The user wants a simulation, not a solo tabletop game. Ideas on the table, none decided: randomness models the environment, not the character's competence; probabilities could come from a judgment about the situation instead of stats; skills grow through training and practice; a long-built relationship must not collapse from one bad moment; combat must be unpredictable (enemies underestimated, extra monsters)."

Closed in `decisions.md`: **Mechanics: not decided. Do not implement dice, stats, or success rules.** Everything below is options only. Also closed: no fixed attribute sheet; records are open-ended; code owns state; Jev gives typed judgments with probabilities.

## 2. Completed idea

**2.1 Where competence lives.** If there is no stat sheet, competence must be *derived from records*: what the character has done, trained, suffered, carries, knows. So "how good is X at swordplay" is a question answered by retrieval over X's history, not by reading a field. Two things follow:
1. A periodic **capability summary** (a versioned record, like the relationship summary in A2) condenses a long history into a short statement of what X can do and how reliably. It is rewritten at intervals and after major events, never mutated in place.
2. Any resolution step must cite the summary plus the *current state* (wounded, tired, drunk, armed or not — exactly the live-state elements in Session B).

**2.2 Separate three sources of uncertainty** (this is the content of the seed's first idea and the part most worth getting right):
- **Competence** (how skilled is the actor): comes from records, deterministic given the records, *not* rolled. Skill does not fluctuate by die; it fluctuates by condition (tired, hurt).
- **Situation** (how hard/dangerous is this): a judgment from the scene: terrain, weather, opponents' states, tools, preparation, information. Also not rolled.
- **Environment/luck** (what the world does independently of both): the only thing that is random, and it should be expressed as *world events* ("a second creature was nearby", "the rope was rotten", "the guard changed shift early"), not as a modifier on competence.
This gives the user's requirement a clean form: *randomness models the environment, not the character's competence*. The attempt's probability of success is then a conditional judgment (competence × situation); the environmental draw decides which unforeseen thing intrudes.

**2.3 Probability from judgment needs three guard-rails**:
- *Calibration:* a Jev score's probability is not a frequency until measured. A cheap internal test: run the same judgment on a library of canned situations with known intuitive outcomes (a trained soldier vs a drunk peasant; a novice vs a drake) and verify ordering and rough spread. I did not run such a test (no API calls permitted in this task).
- *Stability:* identical situation must yield nearly identical probability across repeated calls, or players learn to reroll by rephrasing. Cache judgments by hash of (retrieved records, action text) within a turn, and take the median of a few cheap calls for high-stakes ones.
- *Hero bias:* models tend to favour the protagonist. Judge from a symmetric framing (actor A vs actor B named neutrally, or the same prompt for PC and NPC), and use the "PC is a being like any other" principle (A2) as a test: swap PC and NPC and the probability should mirror.

**2.4 Outcome granularity.** One success/failure bit is poor. Use outcome *tiers* (e.g. clean success, success with cost, partial, failure, failure with escalation) as the Jev choice, with probabilities. Tiers are what the narrator writes from; the engine records consequences as state diffs (new wound, item lost, noise made, alarm raised).

**2.5 Skill growth.** Training and practice create **practice records** (what was done, how hard, under what instruction, what happened). Capability summary rewrites incorporate them. Growth should follow what real learning has: it is faster at the beginning, needs challenge (neither trivial nor hopeless), needs rest, needs instruction or feedback, and it also decays without use. The engine does not need a number for this: a Jev judgment "given this practice history, has the actor's capability in X changed since the last summary?" (choice: no / slightly / noticeably, with a short rationale written by the writer-LLM) is sufficient, run at rest, travel, and time-skip points.

**2.6 Relationships that do not collapse.** This is the same machinery as A2: the relationship is a body of records plus a summary; a single event changes the summary only if a judgment says it is *characteristic* (consistent with how the person has acted) or *shocking-but-decisive* (a betrayal of a kind that outweighs history because of what it is). The character can still react strongly in the moment (anger, withdrawal) without the long-term relationship being overwritten: separate **momentary reaction** from **standing assessment**. After the event, the standing assessment drifts in a direction depending on subsequent behaviour (repair, repetition).

**2.7 Combat unpredictability, made non-arbitrary.** The user wants "enemies underestimated, extra monsters". Make it something the world contained *before* the fight, not something invented when the player is winning:
- *Hidden strength:* the opponent's true capability is in the world records but the PC only perceives observable signals (build, gear, manner). The PC's estimate is an inference from those signals, with error; the narrator describes what is perceived. The gap between perception and truth is the surprise.
- *Hidden presence:* when an area/encounter is created or first entered, an environment-generator judgment (choice from the canon's ecology: nests, packs, patrols) decides what else is in the vicinity and records it as world facts at that time. "Extra monsters" then arrive from records already in the log (rollbackable, auditable, and honest in the canon check).
- *Escalation by consequence:* noise, blood, smell, duration of the fight make later arrivals plausible; each exchange of the fight is a short resolution step that may add a world event.
- *Fight structure:* resolve in short *exchanges* (a few seconds of story each), each updating live state (wounds, fatigue, positioning, items). This exposes the fight to interruption (decided) and prevents a single roll deciding a battle.

**2.8 What the player should see.** Per `decisions.md` the player sees only story. Probabilities are never shown (a dev view only). Risk cues are narrative ("this is a bad idea"), not meters. How much the narration warns is a setting (Session B).

## 3. Options (for the central question: how is an outcome produced?)

### Option A — Hidden probability from Jev; code samples
Jev judges P(tier) for the action given actor summary + live state + situation; code draws a random number; the narrator is told only the tier.
- *Records:* the action, the evidence set (ids of records used), the probabilities, the draw, the tier — all logged for the dev view.
- *Calls:* 1 retrieval + 1 Jev (+ optional 2 more for median); latency ~ one cheap round trip.
- *Strengths:* clear separation: judgment is reasoned, randomness is code; fully auditable; deterministic replay by logging the draw.
- *Weaknesses:* depends on Jev calibration/stability (2.3); the draw is still "dice" (hidden), which the user may or may not consider acceptable under "no tabletop numbers" — the numbers are not stats, they are probabilities of a situation, but the question is open (see questions).

### Option B — Environmental-event dice only (competence deterministic)
Competence × situation decide the *default* tier deterministically (a Jev choice at high confidence, no draw). Randomness is applied to the *environment*: an independent "complication check" per significant action: P(complication) is a Jev score of how unstable/exposed the scene is; if it fires, a Jev choice from a scene-specific complication list (from 2.7 hidden presence, weather, third parties) picks what happens.
- *Strengths:* implements the seed literally (randomness belongs to the environment); a skilled actor is reliably good; surprise comes from the world, which the user wants in combat.
- *Weaknesses:* weak on ordinary uncertainty (a skilled actor never fumbles, an unskilled one never gets lucky); some cases (a long shot, a duel between equals) need real variance in the attempt → cover with Option A for "contested between near-equals" cases. Without that the game can feel deterministic.

### Option C — Narrator adjudication without engine randomness
Narrator decides outcomes from context; LLM sampling temperature is the only randomness.
- *Strengths:* no machinery.
- *Weaknesses:* known failure mode for LLM game masters is smoothing toward the protagonist's success and toward narrative convenience (my hypothesis and a widely reported community observation **[M]**; I did not find a source I could verify); outcomes are not reproducible or auditable; violates "code owns state" in spirit.
- Baseline only.

### Option D — Position/effect framing (Blades-style) with Jev-set stakes
Jev classifies the *position* (controlled / risky / desperate) and *effect* (limited / standard / great) from the situation; a fixed small table (in code) maps position to tier probabilities; the player may change position by preparation (information, allies, gear), which changes the Jev's classification.
- *Strengths:* players understand it ("I need to prepare to make this less risky"), and it rewards cleverness; it needs fewer calibrated probabilities (five or so discrete classes).
- *Weaknesses:* it reintroduces a fixed table and tabletop vocabulary; if hidden from the player it is acceptable, if exposed it feels tabletop.

### Conditions for choosing
- If auditability and replay matter most: **A** (log the draw).
- If the world must be the source of surprise and a competent PC should reliably be competent: **B**, plus A for contested near-equal cases.
- If cheap and simple is the priority for a first prototype: **D** (few classes) feeding A.
- **C** only as a baseline to measure how much better A/B/D are.

Skill growth, relationships and combat structure (2.5–2.7) are compatible with any of A–D.

## 4. Prior art

- **Fate Core** **[V]** — ladder of adjectives, aspects as free-text facts that change outcomes, no learn-by-doing advancement; milestones change what is on the sheet https://evilhat.com/the-core-of-fate-core/ . Lesson: free-text facts mattering to resolution is close to this engine's records (but Fate still adds a number).
- **Powered by the Apocalypse (PbtA)** **[V]** — fiction-first, "moves" resolve by tiered outcomes (miss / mixed / hit) https://en.wikipedia.org/wiki/Powered_by_the_Apocalypse . Lesson: tiered outcomes with consequences, directly usable as the tier set in 2.4.
- **Ironsworn** **[V]** — progress tracks and vows as advancement (experience from fulfilling vows rather than from kills) https://gnomestew.com/ironsworn-review/ . Lesson: advancement tied to *story commitments*; could inspire growth from goals completed (A4).
- **BRP/RuneQuest improve-by-use; Burning Wheel advancement by successes and failures** **[V]** — mark a skill when used, test improvement afterwards, with higher ratings improving less; Burning Wheel needs a number of successes *and* failures at varying difficulty https://www.enworld.org/threads/rules-for-improve-by-doing-skills.334960/ . Lesson: "challenge and variety, not repetition" is a known rule for sensible practice-based growth; also the check happens after rest, not during the action.
- **Blades in the Dark** **[V]** — position/effect, clocks, "fortune" rolls https://gnomestew.com/three-mechanics-from-blades-in-the-dark-i-want-in-all-my-games/ . Lesson: Option D.
- **Dwarf Fortress** **[M]** — skills improve by use with detailed injury and fatigue models; combat is body-part level and emergent. Lesson: a simulation where the story comes from state, not rolls; the source I found did not cover mechanics, so unverified.
- **LLM game masters** **[V, thin]** — the architecture "deterministic server code decides mechanics; the model narrates" https://www.envisioning.com/research/pixels/llm-game-masters.md . Consistent with Option A and with decisions.md; does not answer how probabilities are produced.
- **Generative Agents reflection** **[V]** https://arxiv.org/abs/2304.03442 — periodic higher-level summaries of memory; template for capability summaries (2.1) and relationship summaries.
- **Witcher canon** **[M]** — Geralt's mutations, training and Witcher signs make him beyond ordinary human competence; the capability summary for the PC needs a canon-anchored baseline for witcher abilities, or the "being like any other" principle produces a weak Geralt. Whether the PC is Geralt or an original character is a prior question for the user.

## 5. Interactions

- **A2:** relationship-collapse resistance is the same summary/standing machinery; hero bias test uses PC/NPC symmetry.
- **A3:** the environment-generator judgment (hidden presence) draws on canon ecology via retrieval; "will this difference matter" is a probability judgment.
- **A4:** off-screen agents also need resolved outcomes (fights, journeys); a goal clock tick is a mini-resolution.
- **A6 time:** training and recovery depend on elapsed time; flowing mode makes durations of actions matter (a fight in real-time pacing vs exchanges).
- **Session B interactions (brief not read):** live state elements (wounds, fatigue, poison, gear) are the "current state" inputs here; observable vs hidden attributes (B1) map exactly onto perceived vs true strength (2.7).
- **Decisions:** all of this is *options*; implementing any of it requires the user to close "Mechanics". Keep a swap point: one interface `resolve(action, context) -> tier + diff` so Options A–D are interchangeable.

## 6. Questions for the user

1. Чи нормально, що за лаштунками гра кидає "кубик" (випадкове число), якщо гравець його ніколи не бачить, чи ти хочеш взагалі без випадковості в діях героя?
2. Чи має досвідчений герой майже ніколи не промахуватися в простих речах, а несподіванки приходити лише від світу (ще один монстр, зламана річ)?
3. Герой гравця — саме Геральт зі всіма книжковими здібностями, чи звичайна людина, яка вчиться з нуля?
4. Чи хочеш ти, щоб гра попереджала гравця про небезпеку словами ("це погана ідея"), чи мовчала й давала самому здогадатися?
5. Чи може герой загинути від "дурної" випадковості в бою, чи смерть має бути лише наслідком рішень?
