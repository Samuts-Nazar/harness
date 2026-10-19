# harness — core

World-agnostic engine for single-player AI role-playing games. See `docs/decisions.md` (design,
source of truth) and `docs/assumptions.md` (choices made where the design was silent).
Python, SQLite, no UI.

## Run

    nix develop --command pytest                           # tests (fake provider/judge, no network)
    nix develop --command python -m harness.demo           # scripted scene, offline
    nix develop --command python -m harness.demo --live    # real cheap models (a fraction of a cent)

The demo is offline by default. `--live` loads `.env` (`OPENROUTER_API_KEY`, never printed) and
uses the models chosen by the task 7 bake-off (`harness/policy.py`, `docs/tools.md`): narrator and
NPC `openai/gpt-6-luna`, extractor `deepseek/deepseek-v4.1-flash-1017`, judgments first to
`liquid/d1-ultra` (decision endpoint) and, below p = 0.8, to `gpt-6-luna` as an LLM judge. Every
role has a fallback model from another vendor, used when a call fails after retries. Narration and
NPC speech are Ukrainian (`--language`). Override with `--narrator-model --npc-model
--extractor-model --judge-model --decision-model`; `--turns N` limits the turns, `--sequential`
switches the parallel turn off, `--budget` caps spend (default $0.25).
The demo writes the characters' memory files to `campaigns/demo/memory/` (git-ignored).

## Model policy

A model may be called over the API only if its live OpenRouter price is at most 0.60 USD input and
2.50 USD output per million tokens, it is not Anthropic, and it is not on the small deny list
(routers such as `openrouter/auto`). Decision models (not in the chat catalog) are allowed by an
explicit list: `liquid/d1-ultra`, `perplexity/pplx-decider-v1.2`, `perplexity/pplx-decider-flash-v1.2`,
`typesafe/jev-1.13`, `typesafe/jev-1.14`. Prices come from the OpenRouter catalog, cached on disk in
`.cache/openrouter_models.json` with a date and refreshed when older than a day; if a price cannot
be verified the model is refused. Both HTTP clients retry HTTP 429 and 5xx with exponential backoff.

## Saved campaigns

    eng = Engine.create_campaign("my-game", provider, profiles, scene)   # campaigns/my-game/
    eng = Engine.open_campaign("my-game", provider)                      # continue from the log

A campaign is a file-backed SQLite database (`campaign.db`, WAL, foreign keys on) plus `memory/`
and `judgments.jsonl`, under `campaigns/<name>/` (git-ignored). The scene, characters and language
settings are stored with it. In-memory (`Engine(...)` with no `conn`) stays the default for tests.
The connection allows use from several threads; the caller must run one turn at a time.

## Turn

0. Parallel turn (when the provider is thread-safe, as the OpenRouter one is): after the narrator,
   its speech check, each speaking NPC's chain (line, then the line's check) and later the
   salience and attitude judgments run concurrently. Lines are still delivered in narrator order
   and all event-log writes happen on one thread in a fixed order. In this mode an NPC does not
   see what another NPC said earlier in the same turn.
1. The player acts. The **narrator** returns structured JSON: `description`,
   `observable_actions`, `speakers`. NPC speech inside it is rejected and regenerated (2 retries,
   then stripped and logged).
2. Each speaking NPC gets its own call with **its own context only** (derived memory: what it
   knows with sources, own condition, things just noticed, attitudes, intents, what it witnessed).
   The line is **output-checked** before it is shown: does it assert something this NPC had no
   channel to learn? It is rejected only at suspicion p >= 0.7 and regenerated (2 retries); if every
   try is rejected, the least suspicious candidate is shown and logged.
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
  `DecisionJudge` (alias `JevJudge`; Jev, pplx-decider, d1-ultra via `POST /api/v1/systemone`,
  batched per state, retry with backoff), `LLMJudge`, `EscalatingJudge`
  (decider, then LLM below p = 0.8; relationship magnitude straight to the LLM), `FallbackJudge`,
  `LoggingJudge`,
  `FakeJudge`. Every judgment is logged for the debug view (`Engine.judgments`).
- `attitudes.py` — attitudes (point at facts) and salience notices. `belief.py` — the swappable
  "how much does C believe this" slot (neutral 0.5).
- `memory.py` — per-character derivation and the Markdown writer (wikilinks between characters,
  places, events), regenerated after every committed turn and every rollback.
- `context.py` — prompt assembly for narrator, NPC, extractor. `pipeline.py` — `Engine`: turn,
  interruption (live and retroactive), `enter_scene`, `apply_state_change`, `rollback`.
- `policy.py` — price-based model policy, defaults, fallbacks and spend cap. `retry.py` — backoff.
  `settings.py` — output/record language, NPC rejection threshold. `providers.py` — OpenRouter and scripted fake.
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
