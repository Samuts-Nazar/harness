# A4. Off-screen agents (characters who keep living)

Source legend: **[V]** = found via search on 2026-10-19; **[M]** = from memory, link not opened.

## 1. Seed

> "Characters the player has met keep living: they pursue their own goals, and when met again they have something to tell. The whole world cannot be thousands of full agents (cost, speed); world development should be cheaper, full agents only on direct interaction."

Closed in `decisions.md`: two-level simulation. World cheaply (records + Jev, no agents). A character becomes a persistent agent once the player has interacted with it; in a scene it is fully active (own memory, goals, character); **off-screen it receives cheap periodic updates rather than full simulation.** NPC lines come from separate isolated calls. NPC keeps unsaid remainders as private intents.

So the open question is only *what the cheap periodic update is*, and how "something to tell" is produced and kept honest.

## 2. Completed idea

**2.1 Three tiers, with explicit promotion/demotion.**
- *T0 background population:* unnamed or barely named; exist as records and aggregate statistics (a town has a smith). No updates.
- *T1 known:* the player has seen/heard of them; a short record exists (name, role, location, a line of character). Updated only by world events touching them (A3).
- *T2 persistent agent:* the player interacted. Has goals, memory (their own knowledge records), relationships, and receives off-screen updates.
Promotion is by "interaction" (decisions.md). Demotion is needed too: an agent not met for N in-world months and with no live goal can be *parked* (updates stop; a single "what became of them" record is generated lazily if ever asked). This bounds cost over a long campaign.

**2.2 What an off-screen update is.** The minimum that preserves "they live": per agent, a **state tuple of free text**: current location/activity, goal list with stage, mood/standing summary, "things I'd tell the player" list, and pending intents (including unsaid remainders from past conversations). An update changes these through code-validated diffs, like all state.

**2.3 Goals must be explicit and few.** An agent with two or three goals (stated as one sentence each, with a stage description and what would complete or block it) behaves coherently; an agent with none drifts into generic filler when asked what it did. Goals come from the first interaction's character sheet (free text) and from the agent's own events (a revenge goal appears after the PC wronged them). Goals are records, so they are rollbackable and auditable.

**2.4 "Something to tell" is a data type, not a surprise.** A *tellable* is a record: `agent, content, source (its own experience or what it heard), t, salience-for-player, secrecy`. It is produced by the update when something notable happens to the agent, and it is *consumed* at the meeting: the scene's NPC call receives the tellables that pass (a) epistemic rule: the agent knows it, and (b) a Jev "would the agent tell this to the PC now?" (trust and relationship, A2). Unmatched tellables remain as intents. This is the same mechanism as the "unsaid remainder" intent; one structure handles both.

**2.5 Consistency between off-screen lives.** Two met agents who cross paths should have compatible histories. Simple rule: off-screen interaction between two agents happens only when their locations and schedules put them together *and* a Jev says it plausibly produces an event; the event is written once and appears in both agents' records. Otherwise they simply do not meet. This avoids combinatorial pair simulation (n² pairs).

**2.6 Plausibility audit at the meeting.** Whatever happened off-screen must still be checkable against the world: the agent could not have been in two places, could not have used an item the world records show was lost, and could not have heard a rumour that had not reached its place (A1). A check list at meeting time: location continuity (code), time continuity (code), knowledge channels (code), canon (existing canon check).

**2.7 Death and failure are legal.** If agents only ever succeed or merely wait, off-screen life reads as stagnation. The update must allow setbacks, injuries, deaths, changes of allegiance. Deaths in particular create world records others may hear about (A1).

## 3. Options

### Option A — Goal clocks with tick-based Jev updates
Each T2 agent has 1–3 goals, each with a stage count (like a Blades-in-the-Dark clock). Every update period (e.g. in-world week, or on every time skip, by code) one Jev judgment per goal: *progress* (advance/hold/setback) with probabilities, conditioned on the retrieved current state (location, resources, local world events). Outcomes are written as structured diffs; a one-line summary is produced only when a clock fills, a setback occurs, or the outcome touches another record.
- *Calls:* 1 Jev per active goal per period, only for agents above an activity threshold; for 40 agents × 2 goals × weekly ≈ 80 cheap calls per in-world week (parallel, batchable). Note this is cost on time-skip bursts, not per turn.
- *Strengths:* cheap, deterministic structure, easy dev view ("agent X is on stage 3/6 of 'find his brother'").
- *Weaknesses:* the log has outcomes but no prose; meeting-time stories need a separate generation step (Option C). Stages can feel mechanical if the goal wording is poor.

### Option B — Lazy retrospective at meeting time
Nothing runs while apart. At the meeting a **retrospective call** gets: the agent's character, goals, state at the last contact, elapsed time, world events at its location (A3), and what it could have heard (A1); it proposes a plausible life-interval as a short list of events with dates; Jev checks each (plausible? contradicts records? contradicts canon?); accepted events are committed as back-dated records.
- *Calls:* 1 LLM + n Jev per meeting; zero between meetings, so the cost is exactly proportional to what the player sees.
- *Strengths:* cheapest; the story is written once with full context; zero upkeep.
- *Weaknesses:* **back-filled facts can conflict with anything created in the meantime** (another NPC reported him dead; a caravan route changed). The retrospective must be given everything recorded about the agent since last contact, and, symmetrically, anything that later needs the agent's whereabouts at an intermediate time must trigger the retrospective first ("materialise on demand"). Also, the agent cannot affect the world between meetings (no ripple effects), which breaks "characters pursue goals" if goals have side-effects on others.
- Rollback: back-dated records are created at meeting time; if the player interrupts and rolls back the scene, they must roll back with it, unless they were created *before* the scene by a pre-scene materialisation step (preferable, committed first).

### Option C — Goal clocks for *what*, lazy prose for *how it was told*  *(my default candidate)*
Run Option A for the structured state; at meeting run a smaller version of B whose input is the structured log (not the whole life), so the retrospective only has to *narrate* committed outcomes, not invent them. The LLM writes the tellables and the agent's mood from the outcomes; Jev validates consistency with the log.
- *Strengths:* A's consistency and B's cost for prose; ripple effects possible because outcomes are committed; "something to tell" is grounded in a log.
- *Weaknesses:* two mechanisms to build; still bursts of calls at time skips (mitigate: only agents with an active clock change near an observable thing are processed; others get a single "uneventful" fast-forward).

### Option D — Regional batch ticks
One call per *region* per period handles all T2 agents in it plus background events: an LLM-written "world turn" in a structured format, validated by Jev and code.
- *Strengths:* cost scales with regions, not agents; agents in the same place interact consistently inside one call.
- *Weaknesses:* a big call can blur individuals (all agents get similar goals' worth of attention), harder to isolate epistemic context (one call sees all agents' knowledge, which weakens the isolation rule — the call would be a narrator-type call, allowed to see everything, but its output must be filtered to per-agent records afterwards). Use for background population (T0/T1) rather than T2.

### Conditions for choosing
- If the player will frequently return to the same people after short gaps and expect small changes: **A (or C)**.
- If the cast is large but visits are rare and long-gapped: **B** (or C with sparse clocks).
- If ripple effects between agents are central (a quest-giver's rival acting): **C**.
- Use **D** only for the faceless world, never for agents the player cares about.

## 4. Prior art

- **Shadow of Mordor Nemesis** **[V]** — named enemies keep memory of interactions and continue their own tasks off-screen, changing behaviour and dialogue on re-encounter https://godisageek.com/2014/06/middle-earth-shadow-mordor-michael-de-plater ; commentary https://filmstories.co.uk/?p=83424 . Lesson: a small set of persistent state variables (rank, grudges, scars) and *event hooks on re-encounter* is already enough to feel alive; the mechanism is closer to Option A with authored consequences.
- **Generative Agents (Park et al.)** **[V]** — 25 full agents plan their days, share news, form relationships https://arxiv.org/abs/2304.03442 . They are *all* full agents, costing one reasoning loop per agent per step — the reason decisions.md chose two levels. Lesson on content: day plans decomposed from hour to minute level and reflections supply the "something to tell"; the engine can copy the structure of tellables and reflection but not the running of all agents.
- **Dwarf Fortress historical figures** **[V]** — figures have histories, rumours, relationships maintained by the world sim https://dwarffortresswiki.org/Knowledge . Lesson: events involving figures are records first; the story is read from them later.
- **Blades in the Dark downtime** **[V]** — faction projects as clocks advanced during downtime https://gnomestew.com/three-mechanics-from-blades-in-the-dark-i-want-in-all-my-games/ , https://gnomestew.com/background-events/ . Lesson: Option A's goal clocks, with a human-checked sanity layer; the actual play reports (e.g. episodes at https://explorers-of-elsewhere.castos.com/episodes/faction-actions-elysia-rising-ep6-blades-in-the-dark-actual-play) show GMs narrating the clock results at the table, i.e. Option C's split.
- **Versu** **[V]** — autonomous characters with utility-based action selection within social practices https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf . Lesson: if an agent in a scene is to *act* on its goals (not only speak), goals plus practices give the action menu; off-screen it is overkill.
- **Skyrim/Radiant-style NPC schedules, Kenshi** **[M]** — schedules and routines as cheap off-screen life; I could not retrieve a source. Lesson only: schedules (code) are a free baseline for "where is X at time t".
- **"Do LLMs solve the problems of agent-based modelling?" critical review** **[V, thin]** https://arxiv.org/pdf/2504.03274 . Lesson (from abstract-level reading only): LLM-agent social simulations have validation and reproducibility problems; supports keeping the structured clock log and code checks as ground truth.

## 5. Interactions

- **A1:** met agents are carriers/hearers; the update is where "heard about E" lands.
- **A2:** tellables require the "would they tell me" trust judgment; track record accrues from tellables later confirmed or refuted.
- **A3:** world events touching the agent's location are inputs; agent goals feed "who reacts".
- **A5:** off-screen conflicts (fights, journeys) need the same outcome mechanism as on-screen.
- **A6 time:** the update period equals time-skip granularity; the flowing mode creates many small gaps, so period choice must be elapsed-time driven (do not run an update every few seconds of silence, accumulate until a threshold).
- **Decisions:** consistent with two-level rule. It strengthens one requirement: back-dated records need `valid_time` vs `record_time` and `derived_from`. The "unsaid remainder" intent and "tellable" should be one record type.

## 6. Questions for the user

1. Скільки людей, на твою думку, мають "жити далі" одночасно — десятки чи сотні (від цього залежить вартість)?
2. Чи має вигаданий поза кадром життєвий шлях ставатися справді (змінювати світ, поки гравця нема), чи достатньо, щоб він лише здавався правдоподібним при зустрічі?
3. Чи можуть персонажі поза кадром помирати, зраджувати, змінювати табір без участі гравця?
4. Чи мають персонажі, яких давно не бачили, "завмирати" (щоб не витрачати гроші), якщо це не ламає історії?
5. Чи хочеш ти, щоб персонаж сам шукав героя, якщо має важливу новину, а не чекав зустрічі?
