# LoreVault (HelpfulToolsCompany/lorevault-extension)

- Repo: https://github.com/HelpfulToolsCompany/lorevault-extension (cloned, HEAD `c3d0529`, 2026-07-08, extension v1.1.0 per `manifest.json`)
- Contents: `index.js` (1426 lines), `settings.html`, `style.css`, `docs/privacy.html`, `docs/terms.html`, `README.md`, `manifest.json`. **Only the SillyTavern client is open. The server is closed.**
- **License:** `README.md:63-64` says "MIT", but the repo has **no `LICENSE` file** and `manifest.json` has no license field. An unattached MIT claim in a README is weak evidence. Treat as "MIT intended, not verifiable". Irrelevant in practice because there is nothing here to reuse as code.
- Paths below are relative to the repo root.

## What it is

A hosted memory-as-a-service for SillyTavern. The client sends every chat message to a remote API, and before each generation asks the API for a "story memory" block, which it injects into the prompt. Everything interesting (extraction, storage, retrieval, POV filtering) happens on the server.

## 1. What the client sends (from the code)

Backend base URL: a Supabase Edge Functions endpoint, `index.js:19` (`apiBase: 'https://<project>.supabase.co/functions/v1'`). Each request carries two headers: `Authorization: Bearer <Supabase anon key>` (hard-coded at `:22`, public by design) and `x-api-key: <per-user key>` (`apiCall`, `:313-341`). I do not reproduce the key here.

Endpoints used by the client:

| Endpoint | Method | Where | Payload / purpose |
|---|---|---|---|
| `register` | POST | `index.js:417-455` | `{email}` -> `{api_key, existing_user}` |
| `usage` | GET | `:347` | tier and daily usage (`currentTier` free/pro) |
| `ingest` | POST | `:529-580`, `:808` | `{chat_id, messages:[{message_id, role, content, speaker}]}`; returns `{events_created, messages_stored}` |
| `retrieve` | POST | `:582-633` | see below; returns `{context}` |
| `memories` | GET / DELETE | `:926-1060` | browse by `chat_id`, `event_type`, paging; delete one |
| `chats` | GET | `:862`, `:1088` | list stored chats |
| `delete` | POST | `:732`, `:1116`, `:1180` | delete a chat or all data |
| `checkout`, `billing-portal` | POST | `:687`, `:702` | Stripe |

**Ingest payload** (`:1217-1264`): hooks `MESSAGE_SENT` and `MESSAGE_RECEIVED`; each message is `{message_id: chat.length, role: 'user'|'assistant', content: <full text>, speaker: <display name>}`. `speaker` comes from `getSpeakerName` (`:472-479`): the user's name for user messages, `msg.name` in group chats, else the card's character name. Full message text leaves the machine. A chat import sends the whole history in batches of 20 (`:800-815`). Duplicate re-fires from swipes/regens are skipped client-side by comparing the last `message_id:role:content` key (`:1205-1213`), so a swipe does **not** delete the earlier ingested text. Whether the server dedupes or supersedes is unknown.

**Retrieve payload** (`:590-608`): `chat_id`, `current_context` (the last 5 messages concatenated, truncated to 4500 chars, `:483-489`), `current_characters` (names of speakers in recent messages, or card and group members, `:498-526`), `current_message_id` (= chat length), `token_budget` (default 1000), and, **only when POV is enabled and the tier is not free**, `pov_character: getCurrentCharacterName()` (`:603-607`), which is the card's `name2`.

**Injection** (`:1267-1290`): on `GENERATION_STARTED` the returned `context` string is injected with `setExtensionPrompt('lorevault', context, IN_PROMPT, 0)`. The code comment calls it a `[STORY MEMORY]` block (`:1277`). The client never sees structure: it receives opaque text.

Client-side data the server therefore holds: email, API key, full chat text, display names of speakers, chat ids of the form `<groupId|characterId>_<chatId>` (`:457-463`), timestamps, usage logs (`docs/privacy.html`, "User Content").

## 2. What can be inferred about the server

Inference sources: client code, memory-browser UI (`:960-1036`), `docs/privacy.html` and `docs/terms.html`, `README.md`. Everything in this section is **inference, not observation**.

- **Stack:** Supabase (Postgres plus Edge Functions) in the US (`docs/privacy.html`, "Data Storage and Security"), Jina AI for embeddings ("Your text is sent to Jina AI's API", `docs/privacy.html:78-79`; `docs/terms.html:131`), Stripe for billing. The extraction LLM is **not named** anywhere ("processed by AI to extract story events", `docs/privacy.html:78`).
- **Stored objects (privacy policy, 2.2):** chat messages, "AI-generated event summaries", "character names and relationship data", vector embeddings.
- **Event record shape** (from the memory browser, `index.js:960-1036`): `id`, `chat_id`, `created_at`, `event_type`, `summary`, `location` (optional), `characters_involved: string[]`. Event types are server-defined and used as a filter (`lorevault-memory-type-filter`, `settings.html:175`). So the unit of memory is an **LLM-written event summary** with a type, a location and a list of participants. Embeddings are over the summary.
- **Ingest pipeline** (README "How It Works"): messages are batched, an LLM extracts "characters, relationships, locations, and events", and the result is stored with embeddings. The free tier is limited by "Daily Extractions" (`settings.html:80`), so extraction is a metered LLM call per ingest.
- **Retrieval:** query is the last 5 messages (embedding search), restricted to `chat_id`, packed into a token budget, formatted as text. "Character Tracking - tracks character states, emotions, and relationships" (README) implies a second table of character state, also summarized into the injected block.
- **POV filter:** the client only passes one string, `pov_character`. For the server to implement "characters only recall events they witnessed" (`:644`), it needs at least a per-event witness list. The only visible field that can serve is `characters_involved`. Most likely the filter is `pov_character in characters_involved` on event rows at query time, i.e. **filtering at retrieval, on the server, on an LLM-extracted participant list**. Not verifiable. Observations about the weaknesses are in section 5.
- **Not inferable:** extraction prompt, schema of event types, how "witnessed" is decided (present in the scene vs. told about), what happens to events when a message is swiped or deleted, how character state is represented, whether secrets or hearsay are modelled.

## 3. Per-character knowledge separation

Only as a Pro feature flag: `povEnabled` (`:17`) -> `pov_character` in the request (`:603-607`), UI label "Characters only recall events they witnessed. Secrets stay secret." (`:644`). Granularity is one POV character per request, taken from the *card name* (`name2`). In group chats the card name is the group's current speaker only if SillyTavern sets `name2` to it. The client passes no witness information of its own.

## 4. History compression / retrieval

Server-side: ingest turns messages into event summaries (compression), retrieval is semantic search plus a token budget. Client side only sets `token_budget` (default 1000) and sends 5 recent messages as the query.

## 5. Canon / rule consistency

None visible. No canon store; "story memory" only.

## 6. Fit with `docs/decisions.md`

| Our decision | LoreVault |
|---|---|
| Epistemic isolation at retrieval, in code | Same idea, filter at retrieval, but behind a closed server and keyed on one name string. |
| Facts = free text + metadata (when, where, who witnessed/heard, loudness) | Event rows with `summary`, `location`, `characters_involved`, `event_type`, `created_at`. Closest to our record shape of the five projects, but no "heard vs witnessed", no loudness. |
| Code owns state, append-only event log | Events are append-style, but created by an LLM on a closed server. |
| Model-agnostic, own hardware or own key | No. Hosted service, fixed backend, cloud storage of full chat. |
| Privacy of player text | Conflicts: all text leaves the machine. |

## 7. What is reusable

- **Code:** nothing. It is a thin HTTP client for a proprietary service. Licensing unclear (see top).
- **Ideas:**
  - The event record shape `{event_type, summary, location, characters_involved, time}` as a minimal LLM-extracted unit, which our design extends with `heard_by`, loudness and provenance.
  - Retrieval query = recent messages plus a list of current characters, and a token budget as an explicit parameter.
  - POV as a *retrieval-time parameter* (`pov_character`) rather than a prompt instruction. Same principle as our decision.
  - Client-side dedupe of re-fired messages on swipes (`:1205-1213`), a reminder that regeneration must not double-write memory. Our event log with rollback solves this properly.
- **Warning from the design:** matching `characters_involved` extracted by an LLM is a weak witness model. A character mentioned in a message ("they spoke of Geralt") is not a witness, and an unnamed witness (a crowd) is missed. Our witness lists must come from code-side scene state, not from an extractor reading names off the text.

## 8. License

README says MIT. No LICENSE file is present, so the claim cannot be verified. The server is proprietary and governed by `docs/terms.html`. There is no right to the server software. The client is not useful to copy anyway.

## Assumptions / limits

- The server is not open. I did not call it or register an account (that would send data to a third party and the task is code study). All server statements in section 2 are inferences from client code and legal pages.
- I did not read `style.css` or the full `settings.html`.
