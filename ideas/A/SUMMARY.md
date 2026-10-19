# Session A summary: world and simulation

No code, no changes to `docs/decisions.md` or `harness/`. No paid API calls (web search only, 2026-10-19). Source marking in each file: **[V]** found via search; **[M]** from memory, link not opened. Treat [M] items as leads.

Limits to know: the task-2 experiment reports (E1–E3) are not in this worktree (it was cut from the initial commit), so I did not use their measurements. Several external pages were read only as search snippets; I did not verify their numbers. I could not retrieve the Talk of the Town paper.

## Topics and main options

| # | File | Options in one line each |
|---|---|---|
| A1 | `01_information_spread.md` | **A** eager background propagation (costly, always current). **B** fully lazy at meeting (cheap, needs memoized place decisions). **C** place reach by formula in code + person-level lazy Jev (candidate default). **D** carrier-based sources (adds a concrete "who told me"). Distortion: none / named operators with one call per version / per-hop chain. |
| A2 | `02_belief_and_trust.md` | **A** stored numeric trust per pair. **B** no stored trust, judged from retrieved records each time. **C** records plus a small track-record ledger (candidate default). **D** narrator decides (baseline). PC stance: derived from play / declared by player / hidden model for narrator colouring. |
| A3 | `03_background_world_decisions.md` | **A** retrieve canon at event time and judge analogues. **B** one-off preprocessed canon reaction index. **C** pivot-driven divergence tracking. **D** rules only. Needs: closed reaction vocabulary (Jev cannot write), a divergence ledger, and a choice of canon "pull" (strong / weak / none). |
| A4 | `04_offscreen_agents.md` | **A** goal clocks with Jev ticks. **B** lazy retrospective at meeting. **C** clocks for what, lazy prose for how it was told (candidate default). **D** regional batch ticks (for faceless world only). "Something to tell" = a record type shared with unsaid remainders. |
| A5 | `05_mechanics_without_numbers.md` | Separate competence (from records), situation (judged), and environment (the only random part). **A** hidden Jev probability + code draw. **B** deterministic competence, randomness only as environmental complications. **C** narrator adjudication (baseline). **D** position/effect classes. Combat surprise comes from world records made before the fight. |
| A6 | `06_time.md` | One world clock, two drivers, shared duration judgment. **A** turn-based with duration accounting (baseline). **B** flowing inside scenes with silence budget, hold, and prefetch. **C** continuous flowing everywhere. **D** beat-based ticks. Travel/sleep/waits as legs with a risk check; skips as batch catch-up. |

## The three most important open questions

1. **Does the engine need a hidden random draw at all, and is the PC Geralt or a normal person?** (A5 questions 1 and 3.) This decides whether any mechanics option is acceptable and how strong the PC's baseline is.
2. **How strongly should canon pull the campaign?** (A3 question 1.) Strong pull needs a one-off structured ingestion of the books; no pull makes the canon only a context source.
3. **How many agents should live off-screen, and may their off-screen lives change the world?** (A4 questions 1–2.) This sets whether the cheap goal-clock approach is enough or ripple effects are needed.

## Possible conflicts (evidence, `decisions.md` unchanged)

1. **Append-only log vs lazy back-filling.** The lazy approaches (A1 B/C, A4 B/C) write records about the past at the moment they are first asked ("NPC heard on day 12", written on day 40). `decisions.md` has one "when" per record. Evidence: both topics need two timestamps, in-world `valid_time` and log `record_time`. Not a contradiction yet, but the schema must allow it, or lazy simulation cannot be stored legally.
2. **Rollback of lazily derived records.** Retroactive interruption rolls back state extracted from removed text. A lazily created record that was computed because of that text (an NPC's reaction, a back-filled backstory) would survive the rollback unless it carries a `derived_from` link. Needs a rule in the rollback design.
3. **Quality beats latency vs flowing time.** Each NPC line is a separate isolated call (several seconds). In flowing mode an NPC acting in silence needs such a call. Without prefetching ahead of the player (A6 §2.5) the two decisions pull in opposite directions. The comparison in play will mix this up with the modes themselves unless prefetch is counted.
4. **Jev does not generate text, but several desired judgments sound open** ("how did the world react in the books?"). They must be re-expressed as choices from a closed list (A3 §2.2). Not a problem with the decision; a constraint that the schema needs reaction vocabularies per world, which slightly weakens "world-agnostic" for the first build.
5. **Collective-level epistemic isolation.** `decisions.md` states isolation per character. Factions and towns also "react" (A3), so the same rule must apply to collectives (they react to their version of an event, not the truth). Not stated explicitly; a note rather than a conflict.

## Schema needs that recur across topics (for a later design step, not a decision)

- Knowledge record: `holder, content, source, channel, stance, t_learned (valid), record_time, derived_from, asserted_false_by_speaker`.
- Event loudness: a score plus a kind.
- Tellable / unsaid remainder: one record type.
- Divergence ledger (campaign vs canon) and a per-pair relationship summary and per-person capability summary as versioned, append-only records.
- A duration judgment and a `resolve(action, context) -> tier + diff` interface, both swappable.

## All questions for the user (Ukrainian), by topic

**A1 Поширення інформації**
1. Чи має вигадка змінюватись по дорозі — тобто чутка про вашого героя може стати легендою, яка не зовсім правдива?
2. Чи хочеш ти, щоб світ міг "обганяти" гравця — вістка прийшла в місто раніше за героя, і гравець цього не знав?
3. Чи важливо тобі, щоб кожна чутка мала конкретне джерело ("розповів купець із Вергена"), чи достатньо "у місті чули"?
4. Чи може гравець сам запускати чутки навмисно (заплатити барду, підкинути плітку) і чи це має бути окремою дією в грі?
5. Чи має репутація зникати з часом (люди забули), чи залишатися назавжди, якщо подія була гучною?

**A2 Віра й довіра**
1. Чи має герой гравця вірити чомусь автоматично (наприклад, що чує від друга), чи віра завжди залишається за гравцем?
2. Чи можуть NPC брехати героєві навмисно, і чи має гравець колись дізнаватися, що це була брехня, якщо сам не перевірив?
3. Чи хочеш ти бачити в налагоджувальному вікні *причину* довіри ("вірить, бо ти врятував його сестру"), чи достатньо результату?
4. Чи може довіра зруйнуватися від однієї великої зради, якщо до того були роки добрих стосунків, і від чого це залежить?
5. Чи мають NPC вірити неправдивим чуткам про героя навіть тоді, коли знають його особисто?

**A3 Фонові рішення світу**
1. Якщо гравець повернув події не так, як у книгах, чи мають великі книжкові події (війна, зради) все одно наближатися, чи світ має йти зовсім новим шляхом?
2. Чи готовий ти один раз заплатити за "розбір" книг у структурований вигляд (хто, що, як відреагував), щоб потім гра була дешевшою й точнішою?
3. Які книжкові події ти вважаєш такими, що мають статися за будь-яких умов (якщо взагалі такі є)?
4. Якщо в книгах нема схожого випадку, чи краще світ нічого не робить, чи вигадує реакцію за загальними законами світу?
5. Якою мовою лежать твої тексти книг (від цього залежить якість пошуку по них)?

**A4 Агенти поза кадром**
1. Скільки людей, на твою думку, мають "жити далі" одночасно — десятки чи сотні (від цього залежить вартість)?
2. Чи має життя персонажа поза кадром справді змінювати світ, поки гравця нема, чи достатньо, щоб воно лише здавалося правдоподібним при зустрічі?
3. Чи можуть персонажі поза кадром помирати, зраджувати, змінювати табір без участі гравця?
4. Чи мають персонажі, яких давно не бачили, "завмирати" (щоб не витрачати гроші), якщо це не ламає історії?
5. Чи хочеш ти, щоб персонаж сам шукав героя, якщо має важливу новину, а не чекав зустрічі?

**A5 Механіки без цифр**
1. Чи нормально, що за лаштунками гра кидає "кубик" (випадкове число), якщо гравець його ніколи не бачить, чи ти хочеш взагалі без випадковості в діях героя?
2. Чи має досвідчений герой майже ніколи не промахуватися в простих речах, а несподіванки приходити лише від світу (ще один монстр, зламана річ)?
3. Герой гравця — саме Геральт зі всіма книжковими здібностями, чи звичайна людина, яка вчиться з нуля?
4. Чи хочеш ти, щоб гра попереджала гравця про небезпеку словами ("це погана ідея"), чи мовчала й давала самому здогадатися?
5. Чи може герой загинути від "дурної" випадковості в бою, чи смерть має бути лише наслідком рішень?

**A6 Час**
1. Чи має час іти, поки ти думаєш над відповіддю, і наскільки довго можна мовчати, перш ніж гра сама призупиниться?
2. Чи прийнятно, що персонаж може сказати "Ну?" або піти, якщо ти довго мовчиш?
3. Чи хочеш ти, щоб подорожі й сон були короткими переказами, а детальні сцени вмикалися лише коли щось сталося?
4. Чи можна гравцеві сказати "чекаю до вечора" і гра сама зупиниться, якщо щось станеться?
5. Чи будеш ти грати переважно з телефона (тоді постійний хід часу може заважати), чи з ноутбука?
