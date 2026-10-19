# harness — core

World-agnostic engine for single-player AI role-playing games. See `docs/decisions.md` (design,
source of truth) and `docs/assumptions.md` (choices made where the design was silent).
Python, SQLite, no UI.

## Run

    nix develop --command pytest                           # tests (fake provider/judge, no network)
    nix develop --command python -m harness.demo           # scripted scene, offline
    nix develop --command python -m harness.demo --live    # real cheap models (a fraction of a cent)

The demo is offline by default. `--live` loads `.env` (`OPENROUTER_API_KEY`, never printed) and
uses only models on the cheap allowlist (`harness/policy.py`): extractor `claude-haiku-5.5`,
narrator and NPC `deepseek-v4-flash`, Jev `typesafe/jev-1.14` with escalation to
`claude-haiku-5.5`. Override with `--narrator-model --npc-model --extractor-model --judge-model
--jev-model`; `--budget` caps spend (default $0.25). Anything off the allowlist is refused in code.
The demo writes the characters' memory files to `campaigns/demo/memory/` (git-ignored).

## Turn

1. The player acts. The **narrator** returns structured JSON: `description`,
   `observable_actions`, `speakers`. NPC speech inside it is rejected and regenerated (2 retries,
   then stripped and logged).
2. Each speaking NPC gets its own call with **its own context only** (derived memory: what it
   knows with sources, own condition, things just noticed, attitudes, intents, what it witnessed).
   The line is **output-checked** before it is shown: does it assert something this NPC had no
   channel to learn? If so, regenerate (2 retries, then a minimal in-character non-answer).
3. The **extractor** proposes fact text, source segment and notability, plus live-state changes.
   It does not say who knew what: a diff with `knowers` is rejected.
4. **Code decides who perceived each fact** from scene state (`perception.py`): present = sees and
   hears; outside = hears loud things only; observable actions in narration reach everyone present;
   speech reaches listeners as "told by X". State changes are validated against current state.
5. Commit; rewrite the memory files.

## Modules

- `db.py`, `eventlog.py` — append-only event log; rollback is a marker that cascades via `cause_id`.
- `facts.py` — immutable canon + mutable campaign facts; `visible_to(character)` is the only path
  to knowledge. Each knowledge record stores `how`, `source` (None = perceived directly) and the
  event it came from.
- `perception.py` — who perceived an event. `Scene.present` / `Scene.outside`.
- `state.py` — live character state (injury, clothing, inventory, equipment, internal), each
  element observable or hidden, persistent until an event changes it, derived from the log.
- `extractor.py` — diff parsing/validation (`new_facts`, `state_changes`); `narrator.py` —
  structured narrator output, speech detection/stripping, NPC line cleanup.
- `judge.py` — typed judgments behind one interface (`Judge.ask(state, {name: question})`):
  `JevJudge` (`POST /api/alpha/decisions`, batched per state), `LLMJudge`, `EscalatingJudge`
  (Jev, then LLM below p = 0.8; relationship magnitude straight to the LLM), `LoggingJudge`,
  `FakeJudge`. Every judgment is logged for the debug view (`Engine.judgments`).
- `attitudes.py` — attitudes (point at facts) and salience notices. `belief.py` — the swappable
  "how much does C believe this" slot (neutral 0.5).
- `memory.py` — per-character derivation and the Markdown writer (wikilinks between characters,
  places, events), regenerated after every committed turn and every rollback.
- `context.py` — prompt assembly for narrator, NPC, extractor. `pipeline.py` — `Engine`: turn,
  interruption (live and retroactive), `enter_scene`, `apply_state_change`, `rollback`.
- `policy.py` — model allowlist and spend cap. `providers.py` — OpenRouter and scripted fake.
- `streaming.py` — word-paced delivery with a cut position. `agents.py` — promotion, intents,
  off-screen hook (stub).

## Memory files

`<campaign_dir>/memory/characters/<id>.md` has *Knows* (each item with who told it, the event, the
place, belief), *Attitudes* (linked to the facts they concern), *Live state*, *Pending intents*.
They are engine memory, derived from the log (the log stays the source of truth); NPC context is
built from the same derivation. Use `Engine.rollback(event_id)` (not `log.rollback`) so they are
regenerated.

Not built (undecided): mechanics, dice/stats, spreading of loud events beyond the scene, flowing
time, belief model, player-facing chronicle, media.
