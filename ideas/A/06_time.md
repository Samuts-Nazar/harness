# A6. Time (turn-based vs flowing; travel, sleep, long waits)

Source legend: **[V]** = found via search on 2026-10-19; **[M]** = from memory, link not opened.

## 1. Seed

> "Two modes to compare: turn-based, and flowing (silence counts as time passing; NPCs act without waiting). What happens during travel, sleep, long waits."

Closed in `decisions.md`: "two modes will be built and compared in play: turn-based (world waits for the player) and flowing (silence counts as time passing)". Also closed: narration streams at speaking pace; interruption is a button; each NPC line is a separate isolated call; **quality beats cost and latency**; played from phone and laptop; state is an append-only event log.

This topic therefore does not decide *whether* to build both, only what each means in the engine, what the shared parts are, and how big time jumps behave.

## 2. Completed idea

**2.1 One clock, two drivers.** Both modes share the same world clock (in-world time as engine state). They differ only in *what advances it*:
- *Turn-based:* time advances by the **declared duration** of what happened in the turn (a conversation exchange ~ 1–2 minutes; a search of a room ~ 20 minutes). Nothing happens between turns.
- *Flowing:* time additionally advances by **wall-clock silence** mapped to in-world time at a ratio, and NPCs can act in that interval.
Building the duration estimate (turn-based) is a prerequisite for flowing, because actions in flowing mode also take in-world time. So a single "duration judgment" is the shared core.

**2.2 Duration judgment.** For each action/event: Jev choice from duration buckets (seconds, a minute, minutes, hour, hours, half-day, day, days, weeks) with probabilities, from the action text and context; code resolves to a number inside the bucket and checks it against the physical record (distance, speed, load). The narrator may *propose* durations in its output, validated by this judgment. Without it, time drifts (an LLM narrator happily lets "an hour pass" while a conversation continues).

**2.3 What "silence" means in flowing mode.** Silence from the player is meaningful (hesitation, patience, distraction) but also may be mere real-world distraction (phone call, tea). So: silence advances time only within a **budget** per scene (soft cap), at a rate that depends on the scene's pacing (in a tense standoff seconds matter, in a camp scene they do not). When the cap is reached the world **holds** ("pause") rather than burning story time. A visible indicator of the mode and of a hold is a Session B concern.

**2.4 What NPCs do in silence.** Each NPC has intents (A4 unsaid remainders, goals). During silence, a lightweight **pending-action selector** for each present NPC: Jev "does NPC N act now?" (yes/no with probability) from its intents, patience, relationship to the PC, and the elapsed silence; if yes, its isolated call produces the action or line. NPCs therefore *speak into the silence* ("Well?"), leave, or act. This is the part of flowing mode that costs: N present NPCs × one cheap judgment per silence step. Steps are discrete (e.g. every few seconds of wall-clock, or event-driven timers set by the NPC's patience), so the cost is bounded.

**2.5 Quality vs. flowing — a real tension.** `decisions.md` makes quality beat latency, and each NPC line is its own isolated call. In flowing mode an NPC "waiting" is cheap; an NPC *speaking* costs a full call with latency of several seconds. Resolution: NPC reaction in silence may be **prefetched** (generated ahead while the player thinks, held in a buffer, discarded if the player acts first) — more calls, same quality, no extra latency. The cost of discarded prefetches is the price of flowing mode and should be measured in the comparison.

**2.6 Time-passing events: scales.** Treat time scales as three regimes handled differently:
1. *Scene scale* (seconds–minutes): exchange by exchange, both modes.
2. *Segment scale* (hours–a day): travel legs, sleeping, waiting; handled as "montage" with summary and risk checks (below).
3. *Skip scale* (days–months): handled as a batch: world catch-up (A1 reach is free, A4 goal clocks tick, A3 pivots due are processed in order, body state recovers/decays, the PC's capability summary may be updated by training, A5).

**2.7 Travel.** Divide a route into legs at natural boundaries (settlements, crossings, wilderness stretches) from the map records. For each leg: (a) duration from distance and travel mode (code); (b) one cheap Jev "does anything notable happen on this leg" (score) from route danger, season, the PC's visibility and reputation (A1), time of day; (c) if yes, a Jev choice of encounter type from the region's ecology (A5 hidden presence), which opens a scene; if no, a one-line summary only. Travel *prose* is optional: a "road narration" call can be on demand (player setting). Companions (horse, people) take part: their needs and moods are part of the montage (Session B state).

**2.8 Sleep.** Sleep is a bounded skip with: recovery of body state (rest, wound healing, hunger accumulates), a **watch check** (Jev: does anything disturb the sleeper given location, security, and who knows where the PC is — A1/A2), dreams or nightmares as optional flavour records from the PC's stress state (Session B), and a **wake-up interrupt rule** (a sleeper wakes if danger is proximate; sleep length can be shortened by events). Sleeping outdoors versus a guarded inn is the main branch.

**2.9 Long waits ("wait until the festival"; "wait for him to come out").** A wait is a skip with **interrupt conditions** that the player (or narrator) names, plus engine-owned ones (anything that touches the PC's known goals, danger to the PC, an NPC seeking the PC — A4 tellable with urgency). Process in short steps until the target time or an interrupt fires; this is what prevents silently skipping an ambush.

**2.10 Retroactive interruption and time.** Rolled-back state includes the clock: the clock must be derived from the log like everything else, so removed text restores the earlier time. The unsaid-remainder intent from a cut utterance is a cheap seed for "what the NPC does next in silence" in flowing mode.

**2.11 What the user can compare.** Concrete metrics for the planned comparison in play: perceived pace; cases where the PC "missed" something because of silence; frequency of wasted prefetches; cost per in-world hour; whether the world feels alive or intrusive; mobile vs laptop difference.

## 3. Options

### Option A — Pure turn-based with duration accounting
Time advances only by Jev-validated durations. No wall-clock coupling.
- *Records:* clock state and `time_cost` on each event; skips as batch events.
- *Calls:* +1 cheap Jev per turn (duration); skips cost per §2.6.
- *Strengths:* simplest; predictable; best for thought-through play and for phone use (nothing happens while you put the phone down); easiest rollback.
- *Weaknesses:* the world is passive in scenes; NPCs never fill silence, so scenes lack pressure; hesitation costs nothing; this is the "chat" feel the project wants to get beyond.

### Option B — Flowing in scene, with silence budget and hold  *(the version of "flowing" I would build first)*
Wall-clock silence maps to in-world time inside a scene up to the budget, NPC pending-action checks run at discrete steps, prefetch enabled; between scenes (travel, sleep, waits) use turn-style declared skips.
- *Strengths:* gives the live-conversation feel exactly where it matters; bounded cost; the phone case is safe because of the hold.
- *Weaknesses:* tuning of ratio and budget by scene type; extra calls for prefetch; some players will find it stressful without a setting to scale or disable it.
- *Calls:* per silence step N cheap Jev (parallel) + occasionally a full NPC call; with prefetch, 1 extra NPC call buffer per active NPC.

### Option C — Continuous flowing everywhere (clock always runs)
Wall-clock always advances in-world time, including during travel and waits; the player can pause. The world is a real-time simulation with the text interface.
- *Strengths:* strongest "living world" feel; consistent single regime.
- *Weaknesses:* highest cost; unsuitable for long text generation latency (a travel leg could outpace the narration); unfair when the player is reading (reading must count as paused); hard on phones. Needs the **real-time-with-pause** idea from RTS/CRPG design, i.e. pause automatically while the narration streams.

### Option D — Beat-based "ticks" (hybrid structure)
Time advances in beats of a fixed in-world length (e.g. 30 seconds in a scene). In every beat each NPC may act (Jev check), the player may act or pass; passing is allowed and advances the next beat. Silence in real time does not matter; "pass" is explicit (or a timeout counts as pass).
- *Strengths:* turn-based predictability with the world acting each beat; NPCs speak into silence in a controlled, reproducible way; no wall-clock coupling, so phone-safe; easy to test.
- *Weaknesses:* feels like a game-loop, not like conversation; the explicit "pass" action is friction; less novel.

### Conditions for choosing
- Start with **A** as the baseline for any comparison (it is also the shared core).
- If the main aim is feeling a live scene (pressure, impatience, interruption): **B**.
- If you want to test whether the world can run on its own: **C** only after B is stable.
- If you want predictable, testable "world acts each moment" without real-time coupling, or you will play mostly on a phone: **D**.
All of A–D share the duration judgment, montage regime (§2.6–2.9), and skip catch-up. The comparison in play is mostly A vs B; D is a cheap third arm because it reuses the NPC pending-action selector.

## 4. Prior art

- **Real-time with pause** **[M]** — the Infinity Engine games (Baldur's Gate), Pillars of Eternity and Dragon Age: Origins combine real-time action with a pause and automatic pause on events; no URL verified this session. Lesson: "pause when the player must read or decide" is the standard solution to the reading/attention problem (§2.3, Option C).
- **RimWorld speed controls and auto-pause on alerts** **[V, general]** — storyteller-driven events interrupt time (https://rimworldwiki.com/wiki/Storyteller). Lesson: events as pause triggers; interrupt conditions on waits (§2.9).
- **Dwarf Fortress adventure mode travel and the worldgen sim** **[V]** — the world runs in time; travel is fast-forward with encounters; knowledge arrives via caravans and taverns https://dwarffortresswiki.org/Knowledge . Lesson: travel as legs plus encounter checks is the proven structure.
- **Mount & Blade / Crusader Kings campaign maps** **[M]** — real-time with adjustable speed and pause; lessons only on pause-first UX; no source retrieved.
- **Blades in the Dark downtime** **[V]** — time between scores is a structured skip with defined activities and faction clocks advance https://gnomestew.com/background-events/ . Lesson: skips as formal phases, which matches the "skip scale" batch.
- **Generative Agents** **[V]** — the world clock advances in steps where agents re-plan; the simulation runs ahead of the observer https://arxiv.org/abs/2304.03442 . Lesson: agents in the paper plan with a time grid; our NPC pending-action selector is a much lighter version.
- **LLM-based game masters** **[V, thin]** https://www.envisioning.com/research/pixels/llm-game-masters.md . Streaming narration with low latency feels live; the system there is request/response, not flowing.
- **MUDs and live-service text games** **[M]** — real-time text worlds with NPCs acting regardless of the player; no source; relevant for the "NPCs act while you type" feel.
- **AI Town (a16z) and other LLM town sims** **[M]** — real-time town sims with continuous ticks; I did not retrieve a source; lesson: continuous ticks with many LLM agents is where cost explodes, which supports Option B's scoped flowing.

## 5. Interactions

- **A1:** place-level reach is a function of elapsed time, so skip scale is almost free; person-level judgments occur lazily when met.
- **A2:** patience and trust change with elapsed silence; time affects what is still believed (fading).
- **A3:** scheduled canon pivots must fire in order inside skips.
- **A4:** update periods and the tellable queue; the unsaid-remainder intent drives NPC action in silence.
- **A5:** duration of exchanges in combat; training/recovery per time; rest rules.
- **Session B interactions (brief not read):** the interruption button and retroactive window (decided), time mode as a setting, mobile vs laptop attention, text pacing "like speech", ambient events during silence.
- **Decisions:** consistent. Two flags: (1) quality-beats-latency vs flowing needs the prefetch device in §2.5, otherwise they pull in opposite directions; (2) the clock must be log-derived for rollback; time-dependent lazily created records (A1/A4) must carry `derived_from` so rollback removes them.

## 6. Questions for the user

1. Чи має час іти, поки ти думаєш над відповіддю, і наскільки довго можна мовчати, перш ніж гра сама призупиниться?
2. Чи прийнятно, що персонаж може сказати "Ну?" або піти, якщо ти довго мовчиш?
3. Чи хочеш ти, щоб подорожі й сон були короткими переказами, а детальні сцени вмикалися лише коли щось сталося?
4. Чи можна гравцеві сказати "чекаю до вечора" і гра сама зупиниться, якщо щось станеться?
5. Чи будеш ти грати переважно з телефона (тоді постійний хід часу може заважати), чи з ноутбука?
