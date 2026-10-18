# A1. Information spread (rumours, distance, distortion)

Source legend: **[V]** = page found and read via search on 2026-10-19; **[M]** = from my memory, link not opened this session (treat as a lead, not a verified claim).

## 1. Seed

> "Quiet deeds stay with witnesses; loud deeds travel with time and distance and reach regions the player has never visited; people there hold different attitudes to them. Open: does the world propagate rumours continuously in the background, or lazily (decide what an NPC could have heard at the moment the player meets them, then record it permanently)? Do rumours distort as they travel?"

Closed in `decisions.md`: information spreads by notability; epistemic isolation is enforced at retrieval; an NPC must not comment on what it had no channel to learn nor on what it would not care about (salience is a separate judgment); records carry when/where/who-witnessed/how-loud.

## 2. Completed idea (what the seed needs but does not say)

**2.1 Two layers of "who knows".** The seed mixes two different questions:
- *Place level:* did news of event E reach place P by day d? (a property of geography, trade routes, time)
- *Person level:* given that news reached P, did this particular NPC hear it, in what version, from whom, and do they care? (a property of the person)
Keeping them apart is what makes laziness cheap: the place level can be nearly free (code only), the person level is where Jev/LLM calls go.

**2.2 Loudness is a number with a reason.** Today a record has "how loud/notable it is". Needs: a score 0..1 produced once by a Jev judgment at the moment the event is extracted ("would this be talked about beyond the witnesses?"), plus a *kind* (violence, magic, death of a notable, crime, miracle, scandal, politics) because different kinds travel through different channels (a massacre travels along roads; a court scandal travels through nobles and servants; a monster kill travels through guilds and inns).

**2.3 Channels, not just distance.** Speed and reach depend on carriers: merchants/caravans, soldiers, pilgrims, bards, couriers, servants of nobles, guild networks, letters, mages' sendings. In the Witcher world this matters (mages, Oxenfurt scholars, Dandelion-type bards). A channel is a record too (route A–B exists, travel time N days, who uses it).

**2.4 Fading.** Without refreshment, a rumour drops in "heat" over time. DF models knowledge fading over weeks and years while keeping longer-term reputation effects **[V]** (https://dwarffortresswiki.org/Knowledge). The engine needs the same distinction: *the story is forgotten, the reputation stays* (a derived record "region R thinks of X as a butcher" that outlives the individual event).

**2.5 Version vs. truth.** Each NPC's knowledge of E is its own record (`holder`, `event_id`, `version_text`, `source`, `t_learned`, `confidence`), never a pointer to the true event record. The true record is only visible to narrator/code. This is what makes epistemic isolation and distortion compatible: the NPC context receives `version_text`, which is already the distorted one.

**2.6 Distortion needs a spec, otherwise it is hallucination by another name.** The rule that protects the campaign: a distorted version must be *derivable* from the true event by a named operator, and the operator is recorded. Candidate operator list: exaggerate magnitude; merge with another event; swap or lose the actor; lose a mitigating detail (self-defence disappears); add a moral/supernatural gloss; shift place or time; attribute to a better-known figure. Without named operators the "distortion" cannot be audited against the canon check in `decisions.md` ("justified drift vs hallucination").

**2.7 Attitudes differ.** The seed's "people there hold different attitudes" is a *third* judgment, separate from reach and distortion: given NPC's records (faction, interests, past), version V, and the PC's reputation there, what stance does the NPC take (fear, admire, contempt, opportunism, indifference)? Output type: choice from a closed list + score for intensity.

**2.8 Player's own deeds are the main use case.** The player will most often meet this as "people know about me". Two design needs follow: (a) the player should *feel* the delay (arriving at a far town before the news does is valid and memorable); (b) the player's own reputation becomes a derived, per-region, per-faction summary, not a global number.

## 3. Options

### Option A — Eager background propagation
Every game-day (or per time-skip) code walks all "live" rumours and for each (rumour, neighbouring place) asks a Jev "does it spread here today?" Writes a `reached(place)` record each time; NPC knowledge is derived from place records when needed.
- *Records:* event, rumour-state per place, per-NPC knowledge on demand.
- *Calls:* O(live rumours × frontier places × days). Grows quickly with a long campaign; most calls are wasted on places the player never visits.
- *Strengths:* world state is always up to date; easy to debug; a "world map of what is known where" is always available (nice dev view).
- *Weaknesses:* expensive for exactly the thing the user wants to avoid; spends the budget on unobserved regions.
- *Latency:* hidden if run between turns, but long time-skips (weeks) cause a burst.

### Option B — Fully lazy at meeting time
Nothing happens until the player meets an NPC (or enters a place). Then: (1) code computes the event-to-here distance and elapsed time; (2) Jev: "could news of E (loudness l, kind k) have reached here by now?" with the factors as retrieved records; (3) if yes, Jev/LLM decides the version and the attitude; (4) result is written to the log as a permanent knowledge record dated *in the past* (`t_learned` earlier than "now").
- *Records:* event; knowledge records created on demand with `valid_time` (when NPC learned it) ≠ `record_time` (when written).
- *Calls:* ~3–5 per (NPC, relevant event) at first encounter, zero afterwards. Only events above a loudness threshold and inside a time/distance window are even considered; a pre-filter in code cuts candidates to a handful.
- *Strengths:* cost proportional to what the player observes; consistent with "world simulated cheaply".
- *Weaknesses:* **consistency**. Two NPCs in the same town asked at different times must not contradict each other about whether the town heard. Fix: the place-level decision is memoized the first time it is asked (a `place_knows(P,E,day)` record) so the second NPC inherits it. Second weakness: back-dated records interact with rollback (see §5).
- *Latency:* adds a short pre-scene step on first contact (can be batched into the scene-setup the narrator already needs).

### Option C — Hybrid: coarse reach by formula (code), person-level lazy (Jev)  *(my default candidate)*
- Place level, deterministic and free: reach radius `R(t) = f(loudness, kind, channel network) × t`. Computed on demand from the event record and the map graph, no LLM. Same inputs → same answer (no consistency problem, no memoization needed). Add a small seeded random jitter per (event, place) so the edge of the wave is not a perfect circle.
- Person level, lazy: when the player meets NPC N in place P and `P ∈ reach(E, now)`, three Jev judgments: *did N hear it* (depends on N's role: innkeeper yes, hermit no), *which version* (number of hops from distance and channel; distortion operators applied), *what stance* (see 2.7). Cache as knowledge record.
- Strengths: cheapest option that still gives geography, delay, and per-person difference; deterministic part is unit-testable.
- Weaknesses: the formula `f` is a hand-tuned thing; first version will be crude. Exceptional channels (a mage's sending) need explicit "teleport" records.
- *Calls:* 0 for places, ~3 per first-meeting-per-event.

### Option D — Carrier-based (news physically travels with agents)
News is a payload carried by named or class-level carriers along routes (the caravan leaves A on day 3 carrying E, arrives B on day 9). Lazy variant: routes are a table; "which carriers passed between A and B in the window and who could have told whom" is evaluated at meeting.
- *Strengths:* strongest causality (every hearing has a concrete source: "a merchant from Vizima told me"), which feeds belief/trust directly (A2). Most atmospheric.
- *Weaknesses:* needs a route/carrier model (more data and more world content) and makes the "source" field a required invention; heavier than C.
- Combine with C: C decides *whether* and *when*, D (cheap variant) only *labels the source*.

### How distortion fits (orthogonal to A–D)
- *D0 no distortion* (as in current Dwarf Fortress: no false rumours spread except about secret identities **[V]** https://www.dwarffortresswiki.org/index.php/Rumor). Zero cost, zero risk, but loses the legend-making the user seems to want.
- *D1 operator-based, one call per version:* given true event and hop count n, an LLM writes the version applying up to k named operators, a Jev judges "is the version derivable from E by these operators and consistent with canon world rules" (yes/no); on no, regenerate. ~2 calls per first hearing; the version is cached **per place** (towns share the town's version, individuals add their own spin only if the stance judgment says so). This keeps cost bounded.
- *D2 per-hop telephone chain:* each hop is a generation. Highest fidelity to real rumour dynamics, cost grows with hops, and later hops cannot be verified individually. Not recommended unless the player will actually watch the chain.
- Recommendation as a condition: if audit-ability and budget matter most, D1 with a named operator list; if the feeling of living legend matters more than control, D2 on a few chosen "legend-class" events only.

## 4. Prior art

- **Dwarf Fortress rumours/knowledge** **[V]** — rumours are knowledge about a historical event, originate from witnesses, spread via other figures, books, apprenticeship; caravans and taverns update fortress dwarves; no false rumours except identity. https://www.dwarffortresswiki.org/index.php/Rumor , https://dwarffortresswiki.org/Knowledge . Lesson: the lazy/"world history as records" shape is proven; the *distortion* part is something DF deliberately does not have.
- **Generative Agents (Park et al., 2023)** **[V]** — information diffusion was measured: from one seed idea (a party) 12 of 25 agents heard of it within two days; note the diffusion happens by conversation among *full agents* (expensive) https://arxiv.org/abs/2304.03442 . Lesson: shows emergent spread is possible, and that it is cost-bound by agent count — the thing decisions.md avoids.
- **Rumour-spread simulations with LLM agents** **[V]** — RumorSphere (million-scale agent-based rumour simulation) https://arxiv.org/html/2509.02172v2 ; "Simulating Rumor Spreading in Social Networks using LLM Agents" https://arxiv.org/html/2502.01450v1 ; "Simulating Misinformation Propagation in Social Networks using LLMs" https://arxiv.org/html/2511.10384v1 ; "AI Gossip" https://arxiv.org/pdf/2508.08143 . Lesson: these are network-science style (spread over graphs) and are useful for the *shape* of curves (S-curve, decay), not for narrative detail. I read only abstracts/snippets; I did not verify their numerical claims.
- **Talk of the Town (James Ryan et al.)** **[M]** — a simulated town where characters observe, tell, misremember and lie, with explicit mutation of mental models ("Toward Characters Who Observe, Tell, Misremember, and Lie", AIIDE workshop 2015; Ryan's later thesis). My search did not retrieve it; check before citing in any design doc. Lesson if it holds: distortion implemented as a small set of explicit mutation operators is exactly Option D1.
- **Shadow of Mordor Nemesis system** **[V]** — enemies keep names, ranks and memory of interactions and act off-screen https://godisageek.com/2014/06/middle-earth-shadow-mordor-michael-de-plater . Lesson: the player-facing payoff of "they heard of you" is recognition and changed behaviour, and it works with small data.
- **Books themselves** **[M]** — the Witcher saga is full of reputation outrunning the person (the Blaviken affair, "the Butcher" label, Geralt's reputation differing between Temeria, Redania and elsewhere). This is the canon-side test case for every option here; the canon store can supply the distortion operators actually used by the author.

## 5. Interactions

- **A2 Belief and trust:** the `source` field of a knowledge record is created here and consumed there. D (carriers) and "source" are the same idea.
- **A3 Background decisions:** loudness/kind, stance and "does this matter" are Jev judgments of the type described in A3; canon retrieval supplies how the books' world reacted to a similar event.
- **A4 Off-screen agents:** met agents are also carriers and also hearers; their off-screen update is a natural place to deposit "heard about E".
- **A6 Time:** a long time-skip is when lazy logic matters most; reach is a pure function of elapsed time so skip length is free for place-level.
- **Decisions:** the "when" in records must be two timestamps (in-world time and record time) so lazily back-filled records are legal in an append-only log. **Rollback caveat:** if the player interrupts and a state extraction is rolled back, any lazily created knowledge record that was derived from the removed part (for example an NPC reacting to a deed that is now "never said") must be rolled back too, so lazy records need a `derived_from` link. See Possible conflicts in SUMMARY.
- **Session B (not read):** the player's reputation display (B1 "standing: reputation by place") would consume the derived per-region reputation records defined here.

## 6. Questions for the user

1. Чи має вигадка змінюватись по дорозі — тобто чутка про вашого героя може стати легендою, яка не зовсім правдива?
2. Чи хочеш ти, щоб світ міг "обганяти" гравця — вістка прийшла в місто раніше за героя, і гравець цього не знав?
3. Чи важливо тобі, щоб кожна чутка мала конкретне джерело ("розповів купець із Вергена"), чи достатньо "у місті чули"?
4. Чи може гравець сам запускати чутки навмисно (заплатити барду, підкинути плітку) і чи це має бути окремою дією в грі?
5. Чи має репутація зникати з часом (люди забули), чи залишатися назавжди, якщо подія була гучною?
