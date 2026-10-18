# Assumptions (task 3)

Choices made where `decisions.md` or the task brief was silent. All are easy to swap.

1. **No prior reports.** `reports/*/SUMMARY.md` did not exist; nothing from them was used.
2. **Time** is integer in-game minutes since a campaign epoch. Turn-based mode only (fixed
   `minutes_per_turn`); flowing time is undecided and not built.
3. **Rollback is a marker, not a delete.** The log stays append-only (SQL triggers block
   UPDATE/DELETE). A `rollbacks` table marks events; every derived-state query filters on
   active events. Rollback cascades through `cause_id`. Facts are tied to their source event,
   so they vanish with it. No snapshots: derivation is cheap at this scale.
4. **Canon visibility.** Canon facts have knowers like campaign facts; a character sees a canon
   fact only if listed. The narrator retrieves canon via a token-overlap placeholder
   (`FactStore.search_canon`), swappable for embeddings.
5. **Who speaks** in a turn is passed in by the caller (`speakers=`). Choosing speakers
   automatically is not decided.
6. **One extractor call per turn.** Each diff fact names its `source` segment (player,
   narration, or an NPC id) so facts attach to the utterance they came from; this is what
   makes per-utterance rollback possible. Extraction retries once on an invalid diff; if still
   invalid the whole turn is rolled back and `ExtractionRejected` is raised.
7. **Diff authorization.** Only `new_facts` is allowed; unknown keys are rejected; every knower
   must be present in the scene; each fact needs at least one knower. A fact nobody knows is
   not representable (assumed to be a hallucination or a mistake).
8. **Information spreading by notability** (loud events travelling over distance/time) is
   decided in principle but has no specified algorithm and is not in the task scope. Notability
   is stored on events and facts; nothing propagates yet. Knowledge modes `heard`/`told` can
   only be assigned by the extractor to characters present.
9. **NPC context** includes: facts they know, their own earlier lines, pending intents, and
   utterances they witnessed. It does **not** include narration events, because narration may
   describe things a character cannot perceive. The narrator sees all campaign facts, relevant
   canon, and recent dialogue + narration.
10. **Interruption.** Live: words are delivered one by one; when the handle fires the current
    word is the last one delivered, the rest of the stream is drained (not shown) and kept as
    the NPC's private intent. Retroactive: allowed only for the last NPC utterance overall, once,
    with a cut point strictly inside it. Because the extractor cannot attribute facts to word
    ranges, all facts derived from that utterance are rolled back and re-extracted from the kept
    prefix only. If re-extraction fails, the cut stands with no facts from the kept part.
    The interruption fact ("X interrupted Y after N words: ...") is visible to everyone present.
    Words are whitespace-separated; the cut text is re-joined with single spaces.
11. **Intents** stay pending until explicitly resolved (`Intents.resolve`); nothing resolves
    them automatically, since when an NPC "returns to" an unsaid thought is undecided.
12. **Agent promotion** happens when an NPC speaks in a turn with the player (after the turn
    commits). The off-screen update hook is called for promoted agents not in the scene; the
    stub only records the call.
13. **Judge slot** (`harness.judge`) defines the typed interface and a stub; the skeleton
    pipeline holds it but does not call it, because which judgments are made where is undecided.
14. **Demo/OpenRouter.** The demo loads `.env` and uses OpenRouter when `OPENROUTER_API_KEY` is
    set (model from `HARNESS_MODEL`, default `anthropic/claude-sonnet-4.5`; one model for all
    roles). Real models may ignore the narrator instruction not to write NPC dialogue; no
    enforcement is built yet.
