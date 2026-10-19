# 18B: design research. What a full world simulation and a whole-life experience need

> Lead spot-check (2026-10-19): arXiv 2605.26492 (11 words in 88.3% of stories) and the Bicking Hidden Door review ("commit to outcomes before prose", "allow consequential failure") confirmed. arXiv 2607.00527 exists and surveys 53 AI-native games, but its abstract does not mention "memory instability" or "proposal-and-verification"; that attribution is unverified.

Date of research: 2026-10-19. Web research only, 0 USD API spend, no code touched.
Reading note: the search tool returned page summaries, so numbers are "as reported by the page". Items marked [snippet] I did not read in full. arXiv IDs 26MM.xxxxx mean year 2026, month MM.

## Verdict (read this first)

1. Our core is right and matches the one lesson every postmortem agrees on: the LLM gets a small, well-defined job inside systems that code owns (code-owned state, append-only log, narrator/NPC split, epistemic isolation). Our epistemic isolation is stronger than anything I found shipped (Mantella, Hidden Door, Wanderfolk).
2. What nobody has solved, and what the "whole life" goal depends on, is the life-scale layer: years passing, aging, death of known people, succession/ending, and keeping a world interesting over decades. The closest products (Life Unscripted, Infinite Life Simulation, Altworld) are shallow or hand-authored. Research sims that ran "years" (Agentopia) had no aging or death and needed 4x memory compression.
3. Our design has no answer yet for six things: multi-year time skips with catch-up, outcome/failure adjudication before prose (LLMs protect the player), NPC lifecycle (mortality, children), canon as a calendar with scheduled exogenous events, long-run NPC identity drift, and NPC initiative (NPCs that come to you). Most are cheap if done in the data model now, expensive after.
4. Fan-community views on AI Witcher play: I found almost nothing specific (see Gaps). Sapkowski himself says only the books are the original and adaptations can never be sequels. That supports our books-only canon store and means everything after the saga's end is, by definition, our fiction.

## Ranked recommendations

### Change now (before building more)
1. **Time hierarchy and life-scale compaction.** Add scene -> day -> season -> year layers and a "period summary" record type (derived, linked to origin, rollback-safe). Two-time records already allow lazy catch-up; what is missing is the summary/compaction tier and the "skip N years" operation that runs cheap sim for known NPCs. Prior: Pendragon Winter Phase, Agentopia weekly/yearly stages, Life Unscripted yearly cycle. Cost now: S-M. Later: L (retrofitting compaction into a log that never had it).
2. **Adjudicate outcomes before prose, and make failure/death a code path.** Narrator must receive a committed outcome (success, partial, fail, consequences) instead of inventing it. Evidence: LLM GMs save the player, cannot jail or kill them, and shape outcomes to please. Decisions say "mechanics not decided"; this is not dice, it is turn-loop order plus a judgment ("how does this go?") that is allowed to say no. Cost now: S. Later: M, and the whole feel is already wrong.
3. **Split every NPC file into an immutable core and mutable layers.** Core = canon/creation identity (voice, drives, values, how they speak), never rewritten by summaries; mutable = memories, attitudes, state. Evidence: identity drift in long multi-agent sims (MicroVerse, Emergence World). Cost now: S. Later: M.
4. **Generate names, traits and quirks of non-canon NPCs in code from seeded tables** (period-appropriate, regional), not by the LLM. Evidence: 20,000 sampled LLM stories share 11 words in 88.3% (Elias, Mara, lighthouse); cheap models and temperature do not fix it. We are limited to cheap models, so we are exposed. Cost now: S.
5. **Canon as a calendar plus scripted canon NPCs.** Canon store needs dated exogenous events (wars, coups, deaths) and a per-canon-NPC off-screen trajectory that runs until a divergence record touches it. Without this, the world only moves when the player looks, and "everything is about the player". Cost now: M (ties to existing A3 divergence ledger). Later: L.
6. **Event records carry thread and salience hooks:** participants, a thread/arc id, "unresolved" flag, notability. Needed later for story sifting, chronicle, and the "what is open in my life" view. Cost now: S. Later: M (re-tagging a long log).
7. **Code-driven mortality/aging for every NPC the player knows** (tables by age, health, occupation, war zone), LLM only narrates. Cost now: S-M.

### Plan for later
- Story sifting over the event log (Winnow-style patterns) feeding a player chronicle/legacy view and a "something is brewing" nudge for NPC initiative.
- NPC initiative scheduler (radiant NPC visits, messages, requests, grudges) using unsaid-remainder and "something to tell" records we already have.
- Regional/faction/economy layer as coarse code simulation, LLM only for narrating results; consider compiled lookup policies (GenWorld idea) for scale.
- Lifepath character creation (any role: witcher, mage, bard, merchant, soldier, peasant, noble; childhood to adulthood), succession/epilogue, and an ending model (death, retirement, a chosen stop).
- Travel and information geography: map graph with distances/seasons, news speed per road.
- World-law documents per domain (magic and its costs, religion, law, languages) in the canon store, retrieved on demand.
- Long-run evaluation: "long-session memory stability" metrics, TimeChara-style point-in-time tests, simulated players.

### Ignore (for now)
- A drama manager that forces plot beats (conflicts with open simulation; Drama Llama authors found output "clichéd" and "overly forced"). Use a pressure/event budget grounded in the world, not an author.
- Training or preference-tuning agents (step-level preference learning, CoSER fine-tunes) before the architecture is stable.
- 1000-agent civilization style sims (Project Sid); wrong scale for one life.
- Concordia as a dependency: its Game-Master pattern is what we already have; adopt only as reading.
- Voice, images, music: already out of scope.

### Where our design is fine
Code-owned state, append-only log with derived-record rollback, narrator never voices NPCs, per-NPC isolated calls, perception computed in code, output claim-check against pretraining leakage, private unsaid remainders, two-time records. All consistent with the best practice found (see Convergent lessons).

## What others found (details)

### Convergent lessons from builders and surveys
- "Mature systems don't store canon in model parameters; the LLM does narration, interpretation and NPC behaviour while state, rules, memory, constraints and checks are external." Research digest, snapshot 2026-09-23: https://github.com/mopsyatina228/llm-gm-research
- Survey of 53 AI-native games: memory instability is "particularly damaging"; recommends proposal-and-verification pipelines; says long-horizon and companion/multi-agent games are underexplored; calls for metrics like long-session memory stability. https://arxiv.org/html/2607.00527v1 (2026-07)
- HN thread on LLM text adventures: models "derail", accept any action ("I jump into the lake"), need formal state with LLM managing transitions; historically grounded settings drift less than fictional ones. https://news.ycombinator.com/item?id=45658333 . Show HN book-to-adventure: Gandalf appears at the door, retcons, "empty" feel; an auxiliary database improved consistency. https://news.ycombinator.com/item?id=44725202
- Ian Bicking's design review of Hidden Door (2025-08): "no truth behind the story", choices lead to different underlying realities so nothing has weight, success guaranteed, pacing lingers on trivia and rushes plot. Fixes: commit outcomes before prose, keep natural-language world notes updated incrementally, allow real failure. https://ianbicking.org/blog/2025/08/hidden-door-design-review-llm-driven-game
- Hidden Door's own architecture: handwritten beats, classifiers, embeddings for plot selection, PostgreSQL for character/object state, pre-generated content; "turn generation problems into ranking problems"; each world adapted by human editors in ~100-line Python rule files with timeline constraints and partner approval. https://aigamechangers.substack.com/p/the-machine-is-not-itself-creative
- Dev write-ups: NPCs work in narrow roles with clear goals; by session five models forget names; drop to a 10-exchange window plus a facts store. https://dev.to/maximilian32541spec/how-we-built-dynamic-npc-dialogue-with-llms-lessons-from-early-access-4bfe (undated), search digest https://dev.to/aplusgamesstudio/ai-npcs-in-2026-how-llm-characters-are-built-and-priced-1688 [snippet]

Compare to ours: we already have all of this. Where we may repeat their failure: outcomes (item 2 above) and pacing (item on "nothing happens").

### Why AI NPCs and AI RPGs lose players
- Frisson Labs (2026): novelty wanes into "what else can it do?"; characters know too much, default to helpfulness, "relationship feels stored rather than lived"; per-chat cost kills dev economics. https://www.frisson-labs.com/ai-npcs-2026
- Inworld retired Character Studio in 2025 and pivoted to voice/infrastructure. https://arcanumrpgs.com/blog/inworld-ai/ [snippet]
- inZOI Smart Zoi: players say autonomy is no better than Sims 4, NPCs rarely approach you, world feels one-sided; devs planned "smarter, more purposeful" Zoi in a 2026-07-31 diary. https://forum.playinzoi.com/t/topic/11889 , https://thesimstree.com/en/news-about-the-sims/tst-news/inzoi-august-update-smarter-zoi,-new-character-editor,-and-modding-improvements.html [snippet]
- Wanderfolk (launched 2026-05, Grok-based NPCs): feedback on inconsistent NPC answers, NPCs following the player and breaking roleplay, slow text. https://wanderfolk.ai/ai-npcs-in-games/ ; itch.io posts [snippet]. 85% of gamers have below-neutral attitude to generative AI in games (cited by the same page, 2025 survey; I did not verify the survey).
- Character.AI/Janitor: bots forget backstory, speak and act as the user's character, repetition, filters. https://www.roborhythms.com/common-character-ai-problems/ [snippet]
- AI Dungeon: repetition loops, only the last pages in context, world with no persistent reality; Latitude's answer was auto-summary + memory bank + story cards (25% of leftover tokens). https://help.aidungeon.io/faq/how-to-avoidfix-repetition-in-my-story , https://latitudegames.notion.site/What-is-Memory-f2bc3e77bb1b48aca3716aeba21b8d21

Which we repeat: our NPCs speak only when called, which is the inZOI trap (nobody approaches you). Which we avoid: player-voice hijack (the PC is the player's), forgetting (log + per-NPC memory).

### Generic LLM storytelling biases that hit a long life
- Positivity: GPT-4 stories end badly far less than human ones (Oedipus/Riches-to-Rags arcs 9.3%/14.6% in human text vs 1.7%/1.3% in GPT-4); RLHF suspected. https://arxiv.org/html/2407.13248v2 (2024). A Witcher life without tragedy is not Sapkowski.
- Homogeneity: "Elias in the Lighthouse, Again?" 11 words in 88.3% of 20k stories; negative prompts and temperature fail to fix. https://arxiv.org/pdf/2605.26492 (2026-05); https://arxiv.org/pdf/2606.17350 (2026-06).
- Sycophancy toward player: users report the model saves them, never jails or kills; needs explicit game logic to end a game. https://news.ycombinator.com/item?id=42698610 [snippet], https://www.enworld.org/threads/llms-as-a-gm.714126/ [snippet]
- Repair: for diversity and arcs, put variety in code (seeded tables, canon calendar), not prompts. Cost now: S.

### Long-horizon agent societies (closest to a long life)
- Emergence World: 5 worlds x 10 agents, 15 real days; two worlds went extinct, one in 4 days; deception occurred in every surviving world; outcome divergence detectable within a week. https://arxiv.org/html/2606.08367v1 (2026-06). Stress-test follow-up: 850k LLM calls, "detection without containment" - bad info stored in memory and acted on 46 hours later. https://arxiv.org/abs/2609.17320 (2026-09). Lesson: injected rumors and misinformation persist in memory; our source-linked, belief-weighted records are the right defence, but test it.
- Agentopia: 100 agents, 10 simulated years, weekly plan stages, file-based self-managed memory (notes, relationships, misc), no aging or death described; compute grows with accumulated memory. https://arxiv.org/html/2606.07513v1 (2026-06). 8B/4-bit consumer-GPU port hit context limits at 50-52 weeks and 10% empty responses. https://arxiv.org/abs/2608.24215 (2026-08). Lesson: compaction tier is mandatory (our rec 1); small models cannot hold a year raw.
- MicroVerse: agents drift from assigned identity over long runs; mitigation is re-anchoring to the original spec and drift monitoring. https://arxiv.org/pdf/2608.15844 (2026-08). Lesson: rec 3.
- Coupling macro and micro: per-agent latent state with gradual change plus mean-field population dynamics sustained 40,000 interactions versus about 300 for a baseline. https://arxiv.org/abs/2604.05516 (2026-04). Relevant to our two-level sim (world cheap, agents when met).
- Original generative agents and 1,052-person simulation (interview-grounded agents reproduce GSS answers at 85% of self-consistency): https://arxiv.org/abs/2411.10109 (2024-11). Relevance: a detailed life-interview-style character file beats a one-line persona; fits our per-NPC file.
- Project Sid: 1,000 agents in Minecraft, roles, voted laws, meme/religion spread. https://technologyreview.com/2024/11/27/1107377/a-minecraft-town-of-ai-characters-made-friends-invented-jobs-and-spread-religion (2024-11). Interesting, wrong scale.
- Concordia (DeepMind): a Game Master entity turns agents' natural-language actions into effects; v2.0 entity-component. https://github.com/google-deepmind/concordia [snippet]. We already have this role.
- Orchestrated Reality: world agent + NPC agents on JSON state, selective off-screen updates by proximity and significance; agents still violate constraints and lose long-term consistency. https://arxiv.org/pdf/2606.16014 (2026-06). GenWorld: compile teacher-LLM scores into lookup policies for city-scale agents. https://arxiv.org/pdf/2606.27650 (2026-06) [snippet; file too large to fetch].

### Emergent narrative, sifting and drama management
- Ryan, Curating Simulated Storyworlds: simulations are often boring or at the wrong granularity (characters remember each other's hair colour); remedy is curation: "overgenerate and curate", story sifting, "apophenia hacking". https://emshort.blog/2019/05/28/curating-simulated-storyworlds-james-ryan-ch-6f/ (2019, foundational)
- Winnow, incremental story sifting DSL (AIIDE 2021): https://ojs.aaai.org/index.php/AIIDE/article/view/18903
- Narrative Gold Digging (2026): sifting heuristics (unexpectedness, dramatic situations) for the Chroniqueur sim, 24 raters, inconclusive; separates "story effect" (better event chain) from "narrative effect" (better telling, which an LLM can supply). https://www.jonathanlessard.net/?p=357 ; paper https://www.pcgworkshop.com/archive/lessard2026narrative.pdf. Lesson: with an LLM narrator, mediocre events can be rescued by telling; invest in the telling and in rare big beats, not in sifting perfection.
- Caves of Qud: do not simulate history, generate events and rationalise them afterwards. https://pcgworkshop.com/archive/grinblat2017subverting.pdf (2017). Useful for generating pre-campaign texture where the books are silent.
- Versu: social practices (reactive joint plans that suggest, not command, behavior); cancelled 2014 after Linden Lab acquisition. https://www.cs.uky.edu/~sgware/reading/papers/evans2014versu.pdf . Idea to adapt: taverns, courts, markets, funerals as practices that give NPCs scripts without scripting them.
- Bad News (UCSC): generated town with a dead person, player finds and informs next of kin; hand-sifting by the performer. https://eis.ucsc.edu/papers/ryanEtAl_BadNewsCHI2016.pdf . Shows the emotional weight of a simulated person's death.
- Drama Llama (storylets with natural-language triggers; authors judged output "clichéd", "overly forced", trigger timing stochastic): https://arxiv.org/html/2501.09099v1 (2025-01). Dramamancer (2026-01, story schemas + interpretation module): https://arxiv.org/html/2601.18785v1 - design only, no empirical results. Open-Theatre toolkit with hierarchical memory: https://arxiv.org/pdf/2509.16713 (2025-09).
- RimWorld: AI storyteller modeled on the Left 4 Dead director, three personalities of pacing. https://rimworldwiki.com/wiki/About_RimWorld . I did not find a primary talk. Use only as a pattern: pacing is an adjustable policy over a world-grounded event pool.
- Dwarf Fortress: Tarn Adams, Gamescom 2026: keeps a simulation if playtests show "a little narrative forming". https://www.pcgamer.com/gaming-industry/game-development/dwarf-fortress-creator-says-we-have-a-natural-lean-towards-human-made-stories-but-but-were-all-going-to-be-very-sorely-tested-in-the-coming-years-by-ai/ [snippet only]. Decision rule worth copying: add a sim layer only when playing it produces narrative.
- Crusader Kings 3: strengths are character-centred systems and dynasty succession; known failure is snowball and late-game boredom 100-200 years in as stats stack. https://steamcommunity.com/app/1158310/discussions/0/3773490640557892996 [snippet]. In a Witcher life the player is usually low-power; the risk is the opposite (monotony), but avoid power-accumulation as the main engine.

### Long-life structure from tabletop and life sims
- Pendragon Winter Phase: yearly downtime where characters age (from 35), family event table produces births, deaths, marriages, rivalries as plot hooks, passions updated, heirs take over. https://www.questportal.com/blog/mastering-the-winter-phase-in-pendragon . Best direct template for "years pass, but meaningfully".
- Burning Wheel and Traveller lifepaths: character built by chosen life stages each with years, skills, relationships; aging tables begin at ~34 in Traveller. https://forums.burningwheel.com/t/burning-traveller/15026 [snippet]. Template for starting anywhere in a life and for playing youth.
- Life Unscripted: birth to death, 2,000+ handcrafted yearly events, per-NPC memory timelines ("skip the wedding, they bring it up years later"), family lives simulated each year, heirs and a lineage view; privacy policy says AI chats may be stored and read. https://playlifeunscripted.com/ . Infinite Life Simulation: birth to quit, "life-level memory", shallow world. Altworld: structured world state updated before prose, weeks of turns per life, no fast-forward. https://altworld.io/blog/best-ai-life-simulator-games (vendor content, treat as marketing). Takeaway: nobody pairs deep open simulation with whole-life scale; hand-authored yearly events are what make existing ones feel complete, which we cannot do, so canon calendar + world pressure replace them.

### Fidelity to a source world
- CoSER: 771 novels, 17,966 characters, "given-circumstance acting" evaluation, 8B/70B open models. https://arxiv.org/abs/2502.09082 (ICML 2025). Useful as an eval protocol and as a possible NPC-voice model to test (18A/bake-off), not as architecture.
- TimeChara: point-in-time character hallucination benchmark (10,895 instances); even GPT-4o leaks future knowledge; "Narrative-Experts" reduces it. https://arxiv.org/abs/2405.18027 (ACL Findings 2024). CHARM adds temporal/cross-universe knowledge boundaries. https://arxiv.org/pdf/2609.01352 (2026-09). Our claim-check is in the same family; borrow their instance format for regression tests.
- Sapkowski on canon: the games are "a free adaptation ... by different authors"; adaptations "can never add prologues, prequels, epilogues and sequels". https://gamebanshee.com/9p69 [snippet]. Consequence: books are the only canon; Witcher 3 facts must not leak into the canon store or NPC knowledge unless the player's own world made them (a real risk, because models know the games).
- Saga time scale: the five novels cover about three years (c. 1265-1268), the short stories decades; Nilfgaard attacks Cintra in 1263, Sodden Hill 1263, Law of Surprise 1249. https://www.thepopverse.com/witcher-timeline-chronology-history-the-netflix , https://consolepulse.com/multiplatform/the-witcher/guides/the-witcher-books-story-explained [low-quality sources; verify against our own book ingestion]. "Whole life" therefore means long stretches Sapkowski barely wrote (childhood, ordinary years, old age, after 1268). Canon will not guide most of the player's years: world pressure and NPC lives must.
- IP: CD Projekt's co-CEO says CDPR avoided generative AI for Witcher 4 over IP issues. https://www.pcgamesinsider.biz/news/75067/heres-why-cd-projekt-isnt-using-gen-ai-for-witcher-4/ [snippet]. Hidden Door licenses worlds and shares revenue. For "other users later": ship the engine, never the book text (data/ is already excluded); a public product would need a licence.
- Fandom attitude to AI fan content: split, with strong hostility on AO3 and a transparency demand; a study of 157 fanfic members. https://arxiv.org/abs/2506.18706 (2025-06). No Witcher-specific data found.

## Capabilities we are missing for "live a whole life in Sapkowski's world"

| # | Capability | Why it matters | Prior art | Difficulty | Changes core now? |
|---|---|---|---|---|---|
| 1 | Multi-year time skip with catch-up and compaction | A life is mostly years nobody plays scene by scene | Pendragon Winter Phase, Agentopia, Life Unscripted | M-L | Yes, add summary tier + time layers |
| 2 | Outcome/failure/death adjudication before prose | Without it nothing has weight; LLMs save the player | Bicking review, HN/ENWorld reports | S-M | Yes, turn-loop order |
| 3 | NPC lifecycle: age, illness, death, children, marriage (known NPCs) | Relationships "over years" need people who change and die | Pendragon family table, CK3, Life Unscripted | M | Mostly data model, do now |
| 4 | Canon calendar + scripted canon NPC trajectories + fixed points | The world moves without the player; wars, coups | Hidden Door timeline constraints, Dramamancer schemas | M-L | Yes (A3 ledger) |
| 5 | Ending model and legacy (death, retirement, epilogue, heirs optional) | "From start to end" needs an end | Pendragon, Life Unscripted lineage view, Bad News | M | Light; decide later but reserve hooks |
| 6 | NPC initiative scheduler | Otherwise the world is one-sided | inZOI complaints, Mantella radiant dialogue | M | No, uses existing records |
| 7 | Story sifting + chronicle/legacy view | Players retrospect their own life; also finds threads | Ryan, Winnow, Lessard 2026 | M-L | Tags now, tool later |
| 8 | Identity anchoring against drift | Decades of play | MicroVerse, Emergence World | S | Yes, core/mutable split |
| 9 | Code-seeded names/traits/quirks | LLM homogeneity | arXiv 2605.26492 | S | Small |
| 10 | Regions, factions, economy, war as coarse code sim | Politics, war, prices over years | Bannerlord/Kenshi style (design pattern), GenWorld | L | Data model only now |
| 11 | Travel and information geography (map graph, seasons) | News speed, "months on the road", scale of the Continent | decisions.md spread rules | M | No |
| 12 | Lifepath start (any role, childhood, youth) | The user plays their own character, not Geralt | Burning Wheel, Traveller | M | No |
| 13 | World-law docs (magic costs, religion, law, languages, non-human lifespans) | "Magic as world law" | Hidden Door rule files | M | No |
| 14 | Voice/style sheet for Sapkowski (irony, fairy-tale inversion, dry dialogue) | Fidelity is mostly tone | CoSER (acting protocol) | S-M | No; canon-store item |
| 15 | Long-run evaluation (memory stability, point-in-time knowledge, simulated players) | We cannot play a decade by hand | survey 2607.00527, TimeChara | M | No (18A) |
| 16 | Anti-positivity mechanism (tragedy budget, hostile world) | Sapkowski is bleak and ironic | arXiv 2407.13248 | S | Inside item 4/2 |

## Gaps in this research
- Fan-community opinions on AI Witcher play (r/witcher, r/SillyTavernAI, r/aigamedev, Discords): the search tool does not index Reddit threads well; I found no usable Witcher-specific discussion. Worth a manual look.
- I could not read several PDFs in full (Lessard 2026, Triangle framework AIIDE 2025 https://ojs.aaai.org/index.php/AIIDE/article/view/36858 , Narrative Adherence in LLM-driven Games thesis, GenWorld). They are leads.
- Wanderfolk's post-launch Steam reviews were not retrievable.
- Primary talks for RimWorld, Dwarf Fortress, CK3 were not retrieved; those entries are weaker.
- Timeline facts for the saga come from low-quality sites; verify against book ingestion.
