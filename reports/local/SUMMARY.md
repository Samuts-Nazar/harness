# Local model in the harness: live check (2026-10-28)

Server: llama.cpp (Unsloth build), Gemma 4 26B-A4B QAT, alias gemma-local, --parallel 2, 16384 context, reasoning off (`docs/local-llm.md`). Stack: `local_stack` (every role on that model, `LLMJudge`, no network, cost 0). Script: `experiments/local_live_check.py`, 4 turns through `app.game.Game`. Raw outputs are outside the repo.

Numbers, in seconds: first word / until readable / slow lane after.
- Fixture, before the JSON fix: start 44; 58/119/46, 87/143/69, 53/125/33, 80/94/42
- Fixture, JSON fix: start 42; 61/110/60, 67/127/62, 94/143/29, 61/72/47
- Fixture, plus one-line JSON, parallel: start 33; 55/89/34, 93/171/96, 101/150/23, 84/136/38
- Fixture, same, serial: start 45; 54/114/26, 92/118/86, 92/192/59, 122/142/21
- A real player package, JSON fix: start 89; 163/231/58, 212/299/91, 118/192/53, 103/116/40

Each turn made 12–58 calls, mostly judgments (8–43 batches); the biggest prompt was 3.0–4.5k tokens (fits in 16384 with 2 slots). No timeout, fallback, HTTP error or exception. On the real package: the start built, 4 turns completed, the inline read worked, the Source stayed off the panel, Yennefer sensed it, backpack and laptop ended open. The hosted stack takes about 21 s to the first word.

Fixed: judgments keyed by the question's text (5 failures per turn, now 0); one-line JSON (about a third of the output tokens); local timeout 120 s; no hosted embedder in local mode. Serial was not faster (summed first words 359 s serial vs 333 s parallel), so parallel stays.

Not fixed: speed (about 10 sequential calls before the narration, rare cache hits, about 20 notice-check batches when a container opens); the narrator writes NPC speech (each rejection costs another narrator call; unquoted speech survives stripping); machine memory pressure (0.2 GB RAM free, 12 GB swap, 23% iowait; some calls fell to ~3 tok/s); prose repetition, similes, the narrator acting for the player, wrong gender agreement for Yennefer, the extractor losing or renaming items.
