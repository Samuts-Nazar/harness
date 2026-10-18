# harness — core skeleton

World-agnostic engine for single-player AI role-playing games. See `docs/decisions.md` (design)
and `docs/assumptions.md` (choices made while building the skeleton). Python, SQLite, no UI.

## Run

    nix develop --command pytest              # tests
    nix develop --command python -m harness.demo   # scripted scene

The demo uses a scripted fake provider. If `OPENROUTER_API_KEY` is set (env or `.env`) it calls
OpenRouter instead (this costs money; the key is never printed).

## Architecture

- `db.py`, `eventlog.py` — append-only SQLite event log (type, in-game time, location,
  participants, witnesses, notability, payload, `cause_id`). Triggers forbid UPDATE/DELETE.
  Rollback adds a marker for an event and everything it caused; derived state ignores rolled-back
  events.
- `facts.py` — two stores in one table: immutable `canon` and mutable `campaign`. A fact is text
  + source event, time, location, notability, and knowers (`witnessed`/`heard`/`told`).
  `visible_to(character, time)` is the only path to a character's knowledge, filtered in SQL.
- `context.py` — builds isolated contexts. Character context = visible facts + own earlier lines
  + pending intents + witnessed dialogue. Unknown facts are absent, not annotated. Narrator
  context = full campaign state + retrieved canon + recent events.
- `pipeline.py` (`Engine.turn`) — narrator → one streamed call per speaking NPC → extractor
  (JSON diff) → `extractor.validate_diff` → commit. A failed extraction rolls back the turn.
- `providers.py` — `Provider` protocol, `OpenRouterProvider`, scripted `FakeProvider`.
- `judge.py` — typed-judgment interface (yes/no, choice, score) with `StubJudge`. Slot only.
- `streaming.py` — word-paced streaming with a cut position (`InterruptHandle`).
- Interruption: live (handle fired while streaming) and `Engine.interrupt_retroactive(n)`
  (last NPC utterance only, once). The tail is dropped from the record, derived state is rolled
  back, an interruption fact is recorded for everyone present, the tail becomes the NPC's
  private intent.
- `agents.py` — promotion after first interaction, intents, off-screen update hook (stub).

Not built (undecided): mechanics, dice/stats, spreading of loud events, flowing time, media.
