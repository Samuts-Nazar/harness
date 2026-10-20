# Tools registry

Every tool the repo uses or has chosen, checked against live sources on **2026-10-19**. Entry format:
role, chosen tool and version (or "open"), alternatives checked, reason, sources, date checked. Re-check an
entry when it is older than a month or when work starts that depends on it.

Method notes:
- "In repo" versions were measured in the dev shell (`nix develop`), which is pinned by `flake.lock`
  (nixpkgs `26.11pre1093421.f20cd90e28fe`, lastModified 2026-10-16).
- "Upstream" versions come from PyPI / GitHub releases / official docs fetched today.
- The `nixos` MCP search index was stale today (its unstable index listed python3 3.13.12 and uv 0.11.4 while the
  locked nixpkgs ships python 3.14.7 and uv 0.13.0), so it was not used for version claims. Whether nixpkgs already
  packages Python 3.15 was not verified (the `nix search` check timed out).
- Page summaries were produced by a fetch tool; where it returned an inconsistent date the entry says so.
- Open roles: no choice is made here, only candidates. (Web framework, transport and frontend were decided in task 11.)

## Runtime and environment

### Python
- Role: language and interpreter. Chosen: **Python 3.14.7** (from the locked nixpkgs); `pyproject.toml` says `>=3.11`.
- Upstream: 3.15.0 released 2026-10-09 (bugfix phase), 3.14.8 (2026-09-30), 3.13.16, 3.12.15; 3.10 is end-of-life since 2026-10-01.
- Alternatives: stay on 3.14 (chosen); move to 3.15.0 (ten days old; `uv` 0.13 already defaults to it; pydantic 2.14 and Litestar claim support).
- Reason: 3.14.7 is a current stable line and nothing in the repo needs 3.15 features. Re-check 3.15 in about a month, after first bugfix releases and after nixpkgs packages it.
- Sources: https://www.python.org/downloads/ ; https://github.com/astral-sh/uv/releases
- Checked: 2026-10-19.

### nixpkgs channel / flake inputs
- Role: reproducible dev shell. Chosen: single input `nixpkgs = "nixpkgs"` (indirect registry id), locked at `26.11pre1093421.f20cd90e28fe` (2026-10-16). `prototype/ui/shell.nix` hard-codes the same tarball URL and hash.
- Alternatives: pin to a named channel (`nixos-unstable` or stable 25.11, which the nixos MCP lists as current stable).
- Reason: the rolling lock gives current Python and PyPI-matching packages (pytest and playwright equal PyPI latest). Risk: the indirect id resolves through the user's registry when the lock is regenerated, so a fresh `nix flake update` on another machine can pull a different tree; `flake.lock` fixes this. The two locks (`flake.lock`, `shell.nix`) must be bumped together.
- Sources: `flake.lock`; nixos MCP `channels` (search.nixos.org).
- Checked: 2026-10-19.

### uv
- Role: Python project/package manager (in the dev shell; not yet used to build anything). Chosen: **uv 0.13.0** (locked nixpkgs).
- Upstream: 0.13.1 (2026-10-14). 0.13.0 (2026-10-09) made Python 3.15 the default for automatic downloads and tightened tar validation.
- Alternatives: pip + venv, poetry, pdm, hatch.
- Reason: keep. One patch behind; no action. Note that uv-managed Python downloads would now pick 3.15 while the Nix shell uses 3.14; do not mix them.
- Sources: https://pypi.org/project/uv/ ; https://github.com/astral-sh/uv/releases
- Checked: 2026-10-19.

### SQLite (library inside Python's `sqlite3`)
- Role: event log, facts, canon store (`harness/db.py`, `design/schema.sql`, `design/canon.sql`). Chosen: **SQLite 3.53.3** as linked into the dev-shell Python (`sqlite3.sqlite_version`).
- Upstream: 3.54.1 (2026-10-16), 3.54.0 (2026-10-09), 3.53.0 (2026-04-09; fixed a WAL-reset corruption bug, added `json_array_insert`, ALTER TABLE NOT NULL/CHECK changes).
- Features the design relies on: triggers (append-only), views, FTS5 (`canon_passage_fts`, `content=''`, `unicode61`), recursive CTEs for rollback cascades.
- Alternatives: DuckDB (analytics, not a fit for an append-only transactional log), PostgreSQL (needs a server; hosting is undecided), libSQL/Turso (SQLite fork with vectors; no need today).
- Reason: keep. 3.53.3 is above the WAL-reset fix; 3.54 changes do not matter to us. Set `PRAGMA journal_mode=WAL` and `foreign_keys=ON` explicitly when moving from in-memory to a file (not verified in code today).
- Sources: https://www.sqlite.org/changes.html
- Checked: 2026-10-19.

### python-dotenv
- Role: load `OPENROUTER_API_KEY` from `.env`. Chosen: nixpkgs build in the dev shell (installed version not printed; PyPI latest is **1.2.4**, 2026-10-01).
- Alternatives: `os.environ` only, direnv, pydantic-settings.
- Reason: keep; trivial and current.
- Sources: https://pypi.org/project/python-dotenv/
- Checked: 2026-10-19.

### pytest
- Role: tests (`tests/`, fake provider/judge). Chosen: **pytest 9.1.1** (dev shell) = PyPI latest.
- Alternatives: unittest, nox/tox for matrices (not needed).
- Reason: keep. No async tests today; a web layer would need pytest-asyncio or the anyio plugin (open).
- Sources: https://pypi.org/project/pytest/
- Checked: 2026-10-19.

### Linter / formatter
- Role: none configured today. Status: **open**, low priority.
- Candidates: ruff 0.17.1 (PyPI latest; lint + format), a type checker (not checked), none.
- Sources: https://pypi.org/project/ruff/
- Checked: 2026-10-19.

## LLM access

### httpx (HTTP client)
- Role: all calls to OpenRouter and the Jev endpoint (`harness/providers.py`, `harness/judge.py`, `experiments/common/llm.py`). Chosen: **httpx 0.28.1** = PyPI latest.
- Surprise: 0.28.1 is dated **2024-12-06**. No release in about 22 months and still no 1.0; the project looks quiet. Not deprecated, but watch it.
- Alternatives: aiohttp 3.14.5 (client + server, active), the official `openrouter` Python SDK 1.3.66 (Apache-2.0, "stable as of v1.0", sync and async), requests/urllib3 (sync only), the `openai` SDK pointed at OpenRouter.
- Reason: keep for now. The engine uses few request shapes (one non-streaming, one SSE, one Jev) and a hand-written client keeps the cost and allowlist logic in one place. If async serving and streaming are added, aiohttp or the official SDK deserve a short bake-off. Not recommended to switch now.
- Sources: https://pypi.org/project/httpx/ ; https://github.com/encode/httpx/releases ; https://pypi.org/project/openrouter/ ; https://pypi.org/project/aiohttp/
- Checked: 2026-10-19.

### OpenRouter (provider)
- Role: paid-API gateway for cheap models. Chosen: **OpenRouter** `/api/v1/chat/completions` (OpenAI-compatible). Model choice per role is in the Models section.
- Features we rely on and their current status:
  - Structured output: `response_format` with `json_schema` (optional strict) works only on models/providers that advertise `structured_outputs`; strictness varies by provider; a Response Healing plugin exists for non-streaming. The repo asks for JSON in the prompt and validates in code (`experiments/common/llm.py` also has `json_object` mode). `json_schema` is available but untested here and must be gated per model.
  - Streaming: SSE; `: OPENROUTER PROCESSING` comment lines must be skipped; mid-stream errors arrive as a `finish_reason: "error"` chunk under HTTP 200; the final chunk before `[DONE]` carries usage. Cancellation stops billing only on providers that support it. `OpenRouterProvider.stream` skips non-`data:` lines but does not handle mid-stream error chunks.
  - Usage and cost: returned automatically on every response, streaming or not. **`usage: {include: true}` and `stream_options: {include_usage: true}` are deprecated and have no effect.** Task 9 removed the dead `usage` flag; usage is read from the response and from the final stream chunk, and gap 19 is closed. The client also retries 429/5xx with backoff and treats a mid-stream `finish_reason: "error"` as an error.
  - Parallel requests: no per-request cap documented. Limits are credit-based (an in-flight estimated-cost hold; one request over budget returns 402 `weight_exceeds_budget`) and per-key/workspace budgets (403). The 20 requests/minute cap is for free models only. Our spend cap is client-side only.
  - Prompt caching: automatic for DeepSeek, Groq, Moonshot, Grok, Z.AI and OpenAI (GPT-5.6+); explicit `cache_control` for Anthropic (reads 0.1x), Gemini, Qwen; sticky routing by `session_id`. Relevant: NPC and narrator prompts share long prefixes. The repo sets no cache controls.
  - Embeddings: `/api/v1/embeddings` exists (see Retrieval).
- Alternatives: direct vendor APIs, LiteLLM proxy, a local llama.cpp server for the "own hardware" path in decisions.md (not designed yet).
- Reason: keep; decisions.md fixes OpenRouter as the paid path.
- Sources: https://openrouter.ai/docs/features/structured-outputs ; https://openrouter.ai/docs/api-reference/streaming ; https://openrouter.ai/docs/guides/guides/usage-accounting ; https://openrouter.ai/docs/api-reference/limits ; https://openrouter.ai/docs/guides/features/prompt-caching ; https://openrouter.ai/docs/api-reference/overview
- Checked: 2026-10-19.

### Jev (typed decisions, hosted)
- Role: narrow typed judgments (choice, yes/no probability "Noul", score). Chosen: **`typesafe/jev-1.14`** via OpenRouter `POST /api/alpha/decisions` (alias `~typesafe/jev-latest`; 1.13 also listed). Context 262,144 tokens; output tokens free, input tokens billed. A Box question type (image locating, 1.14+) exists; irrelevant to us.
- Caution: the path contains `alpha`; the API may change. `harness/judge.py` keeps it behind one `Judge` interface.
- Alternatives: Laya (below), other decision models named in `docs/HANDOFF.md` (elorian/glimpse, perplexity/pplx-decider, liquid/d1-ultra), an ordinary cheap LLM with a closed-list prompt. Comparison belongs to task 7.
- Sources: https://openrouter.ai/docs/guides/community/jev
- Checked: 2026-10-19.

### Laya (local decision model server)
- Role: local, free stand-in for Jev. Status: **candidate, not wired**. Nothing in the repo calls it yet.
- Facts: Apache-2.0, by Convai Innovations; repo `NandhaKishorM/laya`, releases v0.4.10 to v0.4.12 on 2026-10-17 to 2026-10-19 (0.x, very fast churn). Checkpoints: `laya` (421M, ModernBERT-large, 512-token context, English), `laya-multilingual` (322M, 1024 tokens), `laya-typed-decisions` (421M, 1024 tokens, created 2026-09-18). About 1.5 to 2.3 GB VRAM for all three; CPU works. Server: `pip install "laya[serve]"`, `laya-serve`, `POST /v1/systemone` and `/v1/systemone/batch` (max 64 states). Env: `LAYA_DEVICE`, `LAYA_PORT`, `LAYA_API_KEY`.
- Compatibility gap: Laya mimics the **TypeSafe `systemone` wire format** (`/v1/systemone`), not OpenRouter's `/api/alpha/decisions`. `JevJudge` posts to the latter, so it needs a URL/shape adapter. The exact request body was not compared against the Laya README.
- Quality: the project's own README says base checkpoints are near chance zero-shot without domain fine-tuning and that shipped checkpoints are over-confident (calibration recommended; multilingual has no fitted temperature). A third-party article reports 0.766 vs Jev 0.727 accuracy on a typed-decisions benchmark and worse calibration (ECE 0.213 vs 0.144); that benchmark is not ours. Our 0.8 escalation threshold depends on calibration. About 20 options with descriptions per question before truncation.
- VRAM note: the dev machine has 8 GB shared with the compositor and a local LLM; 2 GB fits only if the other model is not loaded, or run Laya on CPU.
- Alternatives: Jev hosted; LLM-only judging.
- Reason: worth a bake-off against Jev on the repo's own judgment cases (E1/E2 data), including calibration at 0.8. Do not adopt on published numbers.
- Sources: https://github.com/NandhaKishorM/laya ; https://huggingface.co/convaiinnovations/laya ; https://knolli.ai/post/jev-vs-laya
- Checked: 2026-10-19.

## Retrieval (canon store)

- Role: finding relevant canon passages. Today: token-overlap placeholder (`FactStore.search_canon`); `design/canon.sql` defines an FTS5 table. Status: **open** (decisions.md says canon is retrieved, not how).
- Candidates (no choice made):
  1. SQLite FTS5 with BM25: already in the schema, no new dependency.
  2. Embeddings through OpenRouter `/api/v1/embeddings` (OpenAI text-embedding-3 and NVIDIA nemotron-embed models listed), vectors in plain SQLite BLOBs with a brute-force scan; per-call cost to be measured.
  3. `sqlite-vec` 0.1.9 on PyPI (GitHub tags are `0.1.10-alpha.*`, latest 2026-05-18): pre-1.0, sparse activity; only if brute force proves too slow.
  4. A local embedding model (not researched).
- Sources: https://openrouter.ai/docs/api-reference/embeddings ; https://pypi.org/project/sqlite-vec/ ; https://github.com/asg017/sqlite-vec/releases
- Checked: 2026-10-19.

## Prototype UI and tests

### Playwright (UI test)
- Role: drive the static phone prototype at 390x844 and take screenshots (`prototype/ui/test_ui.py`). Chosen: **playwright 1.64.0** (Python package) with `playwright-driver.browsers` from the same nixpkgs lock, run via `nix-shell prototype/ui/shell.nix`. PyPI latest is 1.64.0 (bundles Chromium 156, WebKit 27.2, Firefox 157). Python in that shell: 3.14.7.
- Alternatives: Cypress, Selenium, Puppeteer (no WebKit). Playwright has WebKit, useful because the player's phone is likely WebKit or Chromium mobile.
- Reason: keep; versions match PyPI because both come from the lock. `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS` is set to run on NixOS. The UI test is outside `tests/` and not part of `pytest`. Since task 11 the flake dev shell also carries `playwright` and the browsers (`app/tests/ui_check.py`), so `nix develop` suffices for the app's UI check; the prototype keeps its own `shell.nix`.
- Sources: https://pypi.org/project/playwright/
- Checked: 2026-10-19.

### Prototype frontend
- Role: static HTML/CSS/JS, no build step, no framework (`prototype/ui/`). Prototype only; the production frontend is **open**, see below.

## Open roles (not chosen)

### Web framework for the phone app / API server
- Role: serve the phone page, accept turns, push streamed text, take the interrupt. Chosen: **Starlette 1.3.1** (locked nixpkgs; PyPI latest 1.9.0, 2026-10-18) served by **uvicorn 0.51.0** (locked; PyPI 0.54.0, 2026-09-25). Both come from the flake dev shell (`flake.nix`), no new package source.
- Alternatives: FastAPI 0.147.0 (Starlette + Pydantic; its value is request validation and OpenAPI, and we have five tiny JSON endpoints; releases almost daily with breaking minors), Litestar 2.25.0 (opinionated, more than needed), Quart 0.23.1 (needs Python >=3.13, async Flask), aiohttp 3.14.5 (server and client in one, but no ASGI test client).
- Reason: least code. The engine is synchronous, so a turn runs in a worker thread and the async layer only reads an in-memory event list; Starlette's `StreamingResponse` is enough for SSE (no extra package), `StaticFiles` serves the page, and `TestClient` tests it. No Pydantic needed.
- Note: the locked Starlette is eight minor versions behind PyPI; the lock should be bumped with the other pins (recommended change 4). `starlette.testclient` warns that `httpx` support is deprecated in favour of `httpx2` (not in nixpkgs today; the tests work, revisit when the lock moves).
- Sources: https://pypi.org/project/starlette/ ; https://pypi.org/project/uvicorn/ ; https://pypi.org/project/fastapi/ ; https://pypi.org/project/litestar/ ; https://pypi.org/project/quart/
- Checked: 2026-10-19 (candidates, task 8); 2026-10-19 (chosen and PyPI versions re-checked live, task 11).

### Streaming transport to the phone
- Role: server-to-client word stream at speaking pace, client-to-server interrupt, survive the app going to the background. Chosen: **Server-Sent Events (hand-written, about 25 lines) plus ordinary POSTs**. No `sse-starlette` (3.5.0, 2026-09-28): the format is `id:`, `event:`, `data:` lines, not worth a dependency.
- How it fits the decisions: every event has a global `seq`; the browser's `EventSource` reconnects by itself and sends `Last-Event-ID`, so a phone returning from the background gets exactly the events it missed. The client also tells the server when the page is hidden (`POST /api/presence`) and the server stops delivering words until it is visible again ("the world stops in the background"). Interrupt is `POST /api/interrupt`; the engine polls its `InterruptHandle` between words.
- Alternatives: WebSocket (two-way, but reconnect and resume are ours to write and the stream is one-way anyway), HTMX 4.0.0 with SSE/WebSocket extensions (server-rendered fragments; no build step either, but the stream here is data events, not HTML), long polling or chunked fetch (clumsier).
- Sources: https://developer.mozilla.org/docs/Web/API/Server-sent_events ; https://github.com/sysid/sse-starlette/releases
- Checked: 2026-10-19.

### Frontend for the phone app
- Role: the player's screen. Chosen: **plain HTML, CSS and JavaScript, no build step, no framework** (`app/static/`), reusing the palette of `prototype/ui/style.css`.
- Alternatives: htmx 4.0.0, Svelte 5.57.2, Preact 11.0.1 (all need a CDN or a build step; npm is not in the dev shell, so a build would be a new toolchain).
- Reason: the screen is a feed, one input and two sheets (about 200 lines of JS). A framework earns its weight when many components share state, which the later features (turn assistant, retroactive cut, tappable names) may bring; revisit then.
- Sources: https://registry.npmjs.org/svelte/latest ; https://registry.npmjs.org/preact/latest
- Checked: 2026-10-19.

### Validation of LLM JSON
- Status: **open**; today hand-written validators in `harness/extractor.py` and `narrator.py`. Candidate: Pydantic 2.14.1 (2026-10-11, Python 3.10 to 3.15). It is also a FastAPI dependency, so adopt together with a web framework or not at all.
- Source: https://pypi.org/project/pydantic/
- Checked: 2026-10-19.

## Models

Chosen by the task 7 bake-off on our own Ukrainian test set (`reports/bakeoff/SUMMARY.md`, catalog snapshot `experiments/bakeoff/catalog_2026-10-19.json`). Prices are USD per million tokens, input/output. Checked: 2026-10-19. Re-run the bake-off when notable new models appear.

| Role | Chosen | Fallback (other vendor) | Alternatives checked | Reason |
|---|---|---|---|---|
| Narrator | `openai/gpt-6-luna` ($0.10/$0.50) | `deepseek/deepseek-v4.1-flash-1017` ($0.15/$0.60) | glm-5.3-flash, qwen3.8-omni-flash, gemini-3.5-flash-lite, command-a-plus | Ukrainian 4.4/5, no flags in 9 scenes |
| NPC line | `openai/gpt-6-luna` | `deepseek/deepseek-v4.1-flash-1017` | same | Ukrainian 4.8/5, leaks 1 of 12 (others 4–7 of 12) |
| Extractor | `deepseek/deepseek-v4.1-flash-1017` | `qwen/qwen3.8-omni-flash` | same | recall 95%, precision 100%, fewest invalid state ops |
| Judge, first | `liquid/d1-ultra` (decision endpoint, ~$0.004 per 1000) | `perplexity/pplx-decider-v1.2` | jev-1.14, pplx-decider-flash-v1.2, Laya (local), elorian/glimpse (chat model, over the price ceiling) | 93.8%, best-calibrated decider, 10% escalate vs Jev's 41% |
| Judge, escalation (p < 0.8) | `openai/gpt-6-luna` as LLM judge | `deepseek/deepseek-v4.1-flash-1017` | — | 95.8%, $0.02 per 1000 |

- Decision endpoint: `POST https://openrouter.ai/api/v1/systemone` (old `/api/alpha/decisions` also answers); the same client serves Jev, pplx-decider and d1-ultra. Needs retry with backoff on HTTP 429.
- Laya: zero-shot at chance (49–52%); not adopted. Fine-tune only if the game must run fully offline.
- `:free` models not tested yet; never the only option for a role.

## Recommended changes (ordered by value)

1. **Remove `"usage": {"include": True}` from `harness/providers.py` and `experiments/common/llm.py`, close gap 19, and handle mid-stream `finish_reason: "error"` chunks in `stream()`.** The parameter is deprecated and a no-op; usage is always returned, including in the final stream chunk. Risk: none.
2. ~~Bake off Laya against Jev.~~ Done in task 7: Laya zero-shot is at chance; not adopted.
3. **Try `json_schema` structured output and prompt caching on narrator/extractor calls, per model, measured.** Both are live on OpenRouter; support varies by provider. Could cut retries and input cost. Risk: strict mode differs across providers; gate by model.
4. **Bump the nixpkgs lock when a fresh rev is available, in `flake.lock` and `prototype/ui/shell.nix` together.** Upstream is one patch ahead on Python (3.14.8), uv (0.13.1), SQLite (3.54.1). Low urgency. Do not move to Python 3.15 yet; re-check in about a month.
5. ~~Decide web framework and transport.~~ Done in task 11: Starlette + uvicorn, SSE plus POST, plain JS (see the roles above).
6. **Watch httpx** (last release 2024-12-06, no 1.0). No action now; if async serving is adopted, evaluate aiohttp or the official OpenRouter SDK instead of adding custom async code.
7. **Set WAL and foreign keys when the engine moves to a file database; consider ruff.** Minor.

## Canon ingestion (task 13 pilot)

### Ingestion models
- Role: one-off structured ingestion of book text (entities, events, knowers, reactions). Candidates run on 2026-10-19 on the pilot arc (97k characters), live catalog checked the same day (469 models; cheap-policy set: input <= 0.60, output <= 2.50 USD per M):
  - `deepseek/deepseek-v4.1-flash-1017` ($0.15/$0.60): 124 events, $0.063, 142 s.
  - `openai/gpt-6-luna` ($0.10/$0.50): 88 events, $0.035, 348 s.
  - `qwen/qwen3.8-omni-flash` ($0.15/$0.47): 55 events, $0.023, 359 s.
  - Seen in the catalog but not run: `nvidia/nemotron-3.5-super-vl` ($0.10/$0.40, 1M context, newest cheap long-context model), `xiaomi/mimo-v2.6-flash` ($0.14/$0.28), `z-ai/glm-5.3-flash` ($0.048/$0.16), `inclusionai/ling-3.1-flash`, `deepseek/deepseek-v4.1-flash` ($0.038/$0.08, the non-1017 build). Candidates for the next bake-off; the cheapest ones may suit the second (mapping) pass.
- Recommendation and error counts: `reports/canon_pilot/SUMMARY.md`.
- Checked: 2026-10-19.

### Retrieval over canon passages
- Role: find canon passages and events for a question. Pilot choice: **SQLite FTS5** (`unicode61`) with a crude Ukrainian prefix stemmer (long words cut by two letters), plus typed lookup through `canon_knower`; no embeddings. Alternative: OpenRouter embeddings (not run). Result of the 10-question check is in the pilot report.
- Checked: 2026-10-19.

### Scene director and glossary (task 12, 2026-10-19)
- Role: first-line speaker decider for the scene director. Chosen: `liquid/d1-ultra` (the existing first judge, one batched `/systemone` call, mean 0.22 s over 27 calls); fallback `perplexity/pplx-decider-v1.2` via the judge fallback. Alternatives not re-run (no new bake-off). Observable-action lister: the extractor model `deepseek/deepseek-v4.1-flash-1017` (mean 1.1 s, plain lines). No new library or tool.

## Style bake-off models (task 15, 2026-10-19)

- Role: candidates for NPC lines and narration that read as literary Ukrainian prose. Price ceiling: 0.60 / 2.50 USD per million tokens; catalog fetched live 2026-10-19 (`https://openrouter.ai/api/v1/models`).
- Public signals found (weak; no usable EQ-Bench page via the fetch tool, aggregator pages only): Z.ai GLM models rank high for creative writing on llmgateway.io ([creative writing ranking](https://llmgateway.io/models/creative-writing): GLM-5.2 is the only listed model within the ceiling); benchlm.ai lists GLM-5.1, MiMo-V2.5-Pro, Qwen3.8 Max near the top for fiction instruction following ([benchlm fiction](https://benchlm.ai/best/for/fiction); it says itself that this does not measure taste); a search summary credits DeepSeek V4 with the best open-weights creative quality ([bestllmfor.com](https://bestllmfor.com/guides/best-llm-for-writing/)), which is already the fallback. Nothing public measures Ukrainian literary prose. So the picks are by family, newest in the catalog under the ceiling: `z-ai/glm-5.3` (0.079/1.40), `xiaomi/mimo-v2.6-pro` (0.435/0.87), `qwen/qwen3.8-27b` (0.24/2.20), plus the current `openai/gpt-6-luna` (0.10/0.50).
- Result on our task (blind, 360 NPC outputs, details in the task 15 report): luna and mimo-v2.6-pro tie on style (3.7 / 3.8 of 5) and Ukrainian (4.4 / 4.6); mimo costs 3.7x and takes 3x the time; glm-5.3 writes the liveliest lines but breaks Ukrainian (Chinese or Latin fragments in 27-30% of outputs, leaks 55%; luna showed 20% Latin fragments too, but those were English catchphrases copied from the manner notes, since fixed); qwen3.8-27b is worst (reasoning text leaking into replies). **Decision: no change; luna stays NPC and narrator.** mimo-v2.6-pro is a candidate only if latency stops mattering.
- Alternatives not run: DeepSeek V4.1 flash (already the fallback), Gemini flash-lite (3.5), longcat 2.0, Cohere command-a-plus (0.30/1.50, Ukrainian quality unknown).
- Checked: 2026-10-19. Re-check when a new model appears under the ceiling.

### Character looks from the local file (task 14, 2026-10-19)
- Role: derive the player character's observable and hidden traits from `data/Ragnar.md` (about 100 KB) once per file. Chosen: the existing extractor model `deepseek/deepseek-v4.1-flash-1017` (live catalog: context 1,048,576 tokens, $0.15/$0.60, weekday surcharge tier $0.30/$1.20, inside the price rule). One real call cost $0.0022. Alternatives not run: `openai/gpt-6-luna`, `qwen/qwen3.8-omni-flash` (same band; no need to compare for a one-off). No new library.
- Checked: 2026-10-19.

## Canon in play (task 16, 2026-10-19/20)

- Role: embeddings for canon retrieval. Chosen `qwen/qwen3-embedding-8b` (live `GET /api/v1/embeddings/models`: 33 models; this one 0.01 USD per M input, 40960 context, multilingual). Compared on the pilot questions: `baai/bge-m3` (same price) ranked names over meaning (the plot question missed its events); qwen3-embedding-8b found them. Not run: `openai/text-embedding-3-large` (0.13), `voyageai/voyage-4`, `perplexity/pplx-embed-v1-4b`. Cost of embedding the 80 events: about 0.0001 USD. Query embedding is one call per question; failure falls back to full text.
- Role: timeline arbiter and knower/place/gist/reaction passes: `deepseek/deepseek-v4.1-flash-1017` (as ingestion), second timeline reader `openai/gpt-6-luna` (it wrote day 1 for every scene: a weak vote, useful only to flag disagreement), `xiaomi/mimo-v2.6-pro` tried as arbiter and was worse than deepseek with the code hints. Relevance verifier: the existing judge stack.
- No new library. Checked: 2026-10-20.
