# Task 4: Revise the core to the updated decisions

Work fully autonomously. Do not ask questions. When something is ambiguous, choose the most reasonable option, record it in `docs/assumptions.md`, and continue.

## Context

- Replace `docs/decisions.md` with the new version provided with this task, then read it in full. It supersedes the previous version.
- Read `docs/assumptions.md`, `reports/code_study/SUMMARY.md`, `reports/experiments/SUMMARY.md`, `reports/experiments/E2.md` and `reports/experiments/E3.md` before changing code.
- The existing core in `harness/` (task 3) is the starting point. Change it; do not rewrite from scratch unless a part cannot be adapted.

## Spending

- Follow the model and spending policy in `docs/decisions.md` strictly. No Sonnet, Opus or comparable model over the API, for any purpose.
- Total API spend for this task: under 1 USD. Tests use the fake provider. Live calls only for a final smoke run of the demo and for checking the Jev request format.
- Any quality evaluation of outputs is done by you reading them, not by an API judge.

## Changes

1. Demo and network
   - The demo uses the fake provider by default. `.env` is loaded and the network is used only with `--live`.
   - Default live models come from the allowed list: extractor `anthropic/claude-haiku-5.5`; narrator and NPC lines a cheap allowed model of your choice (configurable per role); judge Jev with LLM escalation.

2. Perception computed in code
   - Scene state holds who is present and their positions or zones as far as needed for visibility and hearing. Choose the simplest model that supports "present in the same room sees and hears; outside hears loud things only" and record it as an assumption.
   - Who perceived an event is computed from scene state. The extractor no longer assigns knowers; it proposes fact text, the segment it came from, and notability only. Remove extractor-assigned knower lists from the diff schema.
   - Characters present perceive observable actions in narration, not only spoken lines. The narrator output marks observable actions so code can attribute them.

3. Narrator never speaks for NPCs
   - Narrator output is structured: description, observable actions, and the list of characters who speak next.
   - If the narrator output contains NPC speech, reject and regenerate (at most 2 retries, then strip the speech and log it). Detection may use the judge.

4. Source of knowledge
   - Every knowledge record stores its source (perceived directly, or told by character X) with the event it came from.
   - NPC context shows second-hand knowledge with its source ("heard from X"). The player character is treated like any other character; no special case.
   - No belief model yet: keep a swappable function slot for "how much does C believe this", returning a neutral default.

5. Live character state
   - Per character: injuries, clothing and condition, inventory, equipment, internal changes. Each element is observable or hidden. Elements persist until an event changes them.
   - The extractor may propose state changes; code validates them against existing state (cannot remove what is not there, etc.).
   - On scene entry and when an observable element changes, every present character perceives it. For each observer, a salience judgment decides whether the observation is surfaced in that NPC's next context as noteworthy.

6. Output check for NPC lines
   - Before an NPC line is accepted: judge whether it contains a claim the NPC had no channel to learn, given that NPC's visible knowledge. If yes, regenerate (at most 2 retries; then fall back to a minimal in-character non-answer and log it).

7. Judge implementation
   - Implement the Jev client behind the existing judge interface: `POST https://openrouter.ai/api/alpha/decisions`, question types `noul`, `choice`, `score`; `choice.criteria` is an object `{option: description}` (see `reports/experiments/E2.md` and `experiments/e2/`).
   - Batch questions about the same state into one call.
   - Escalation: if the probability of Jev's answer is below 0.8, ask the same question to a cheap allowed LLM and use its answer. Relationship magnitude goes to the LLM directly.
   - Log every judgment (question, answer, probability, escalated or not) for the debug view.

8. Per-character memory files (AI memory)
   - Derive one Markdown file per character from the event log: what the character knows (with sources), its attitudes (linked to the facts they concern), its live state, its pending intents. Use wikilinks between characters, places and events.
   - These files are engine memory. NPC context assembly reads from them or from the same derivation. They are regenerated after every committed turn and after any rollback.
   - Write them under a campaign directory that is git-ignored.

## Quality bar

- Tests for: perception computed from scene state (present vs absent vs outside), observable narration actions reaching present characters, extractor diff rejecting knower lists, narrator-speech rejection, source recorded on second-hand knowledge, live state persistence and perception on scene entry, output check regeneration and fallback, judge escalation threshold, memory file regeneration after rollback.
- Keep the existing tests passing or update them with a reason in the commit message.
- Update the README and `docs/assumptions.md`.
- Commit in small, working steps.
- Final report: what changed, live smoke-run results, total API spend.
