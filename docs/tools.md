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
- Open roles: no choice is made here, only candidates.

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
  - Usage and cost: returned automatically on every response, streaming or not. **`usage: {include: true}` and `stream_options: {include_usage: true}` are deprecated and have no effect.** The repo still sends `"usage": {"include": True}`; harmless but dead. Gap 19 in `reports/decision_gaps.md` ("streaming requests do not ask for usage") is moot: usage arrives anyway and only needs parsing.
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
- Reason: keep; versions match PyPI because both come from the lock. `PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS` is set to run on NixOS. The UI test is outside `tests/` and not part of `pytest`.
- Sources: https://pypi.org/project/playwright/
- Checked: 2026-10-19.

### Prototype frontend
- Role: static HTML/CSS/JS, no build step, no framework (`prototype/ui/`). Prototype only; the production frontend is **open**, see below.

## Open roles (not chosen)

### Web framework for the phone app / API server
- Status: **open**. The engine is synchronous Python; a server must serve the phone page, accept turns, push streamed text and support the interrupt button.
- Candidates (PyPI, today):
  - FastAPI 0.147.0 (2026-10-19; releases almost daily and minors carry breaking changes, e.g. 0.146 deprecates `root_path`): Starlette + Pydantic, most documentation.
  - Starlette 1.9.0 (Python >=3.11): the toolkit under FastAPI; fewer features, WebSockets built in.
  - Litestar 2.25.0 (2026-10-18; claims Python 3.8 to 3.15): opinionated, OpenAPI, dependency injection.
  - Quart 0.23.1 (2026-08-29; requires Python >=3.13): async Flask API.
  - aiohttp 3.14.5: server and client in one library, WebSockets built in.
- ASGI server for the first four: uvicorn 0.54.0 (also hypercorn, granian).
- Sources: https://pypi.org/project/fastapi/ ; https://pypi.org/project/starlette/ ; https://pypi.org/project/litestar/ ; https://pypi.org/project/quart/ ; https://pypi.org/project/aiohttp/ ; https://pypi.org/project/uvicorn/ ; https://github.com/fastapi/fastapi/releases
- Checked: 2026-10-19.

### Streaming transport to the phone
- Status: **open**. Needs: server-to-client word stream at speaking pace, client-to-server interrupt with a retroactive cut point, and surviving mobile background/foreground (the world stops in the background, per decisions.md).
- Candidates:
  - Server-Sent Events plus ordinary POSTs: simplest, auto-reconnect built into `EventSource`; helper `sse-starlette` 3.5.0 (2026-09-28). One-way, so the interrupt is a separate POST.
  - WebSocket: two-way in one channel, native in Starlette/FastAPI/aiohttp/Quart; reconnect and resume logic is ours.
  - HTMX 4.0.0 (stable 2026-08-28, GitHub) with standalone SSE and WebSocket extensions: server-rendered fragments, minimal JS. npm `latest` for `htmx.org` still showed 2.0.11, so v4 may sit under another dist-tag.
  - Long-polling or chunked fetch streaming: works everywhere, clumsiest.
- Sources: https://github.com/bigskysoftware/htmx/releases ; https://github.com/sysid/sse-starlette/releases
- Checked: 2026-10-19.

### Frontend for the phone app
- Status: **open**. Candidates: plain JS as in the prototype (no build); htmx 4.0.0; Svelte 5.57.2; Preact 11.0.1. Compared on versions only.
- Sources: https://registry.npmjs.org/svelte/latest ; https://registry.npmjs.org/preact/latest
- Checked: 2026-10-19.

### Validation of LLM JSON
- Status: **open**; today hand-written validators in `harness/extractor.py` and `narrator.py`. Candidate: Pydantic 2.14.1 (2026-10-11, Python 3.10 to 3.15). It is also a FastAPI dependency, so adopt together with a web framework or not at all.
- Source: https://pypi.org/project/pydantic/
- Checked: 2026-10-19.

## Models

filled from task 7

## Recommended changes (ordered by value)

1. **Remove `"usage": {"include": True}` from `harness/providers.py` and `experiments/common/llm.py`, close gap 19, and handle mid-stream `finish_reason: "error"` chunks in `stream()`.** The parameter is deprecated and a no-op; usage is always returned, including in the final stream chunk. Risk: none.
2. **Bake off Laya against Jev on the repo's own judgment cases (fold into task 7); add a `/v1/systemone` adapter only if it wins.** It is free, local and small (322 to 421M), but its wire format differs from the OpenRouter endpoint and its calibration is reported weaker; our 0.8 escalation rule depends on calibration.
3. **Try `json_schema` structured output and prompt caching on narrator/extractor calls, per model, measured.** Both are live on OpenRouter; support varies by provider. Could cut retries and input cost. Risk: strict mode differs across providers; gate by model.
4. **Bump the nixpkgs lock when a fresh rev is available, in `flake.lock` and `prototype/ui/shell.nix` together.** Upstream is one patch ahead on Python (3.14.8), uv (0.13.1), SQLite (3.54.1). Low urgency. Do not move to Python 3.15 yet; re-check in about a month.
5. **Decide web framework and transport before building the server** (open roles above) after a short spike. FastAPI/Starlette + SSE with a POST for interrupt is the least-code path, but it is a candidate, not a decision.
6. **Watch httpx** (last release 2024-12-06, no 1.0). No action now; if async serving is adopted, evaluate aiohttp or the official OpenRouter SDK instead of adding custom async code.
7. **Set WAL and foreign keys when the engine moves to a file database; consider ruff.** Minor.
