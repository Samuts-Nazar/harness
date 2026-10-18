# Task 2: Experiments that answer open design questions

Work fully autonomously. Do not ask questions. When something is ambiguous, choose the most reasonable option, record the assumption in the report, and continue.

## Context

Read `docs/decisions.md` first. These experiments produce measurements for design decisions. They are throwaway scripts, not engine code.

## Inputs

- `data/witcher_books.txt`: one plain-text file (about 8 MB) with the seven Witcher saga books plus Season of Storms. Detect its language and encoding first and record them in the report. Locate book and chapter boundaries if possible.
- `data/Ragnar.md`: the chronicle of the player's current campaign (Act I). Treat it as canon for the player character.
- `data/` must be in `.gitignore`. Never commit these files or long excerpts from them.
- `OPENROUTER_API_KEY` from the environment.

## Budget

Total API spend for this task must stay under 3 USD. Track spend per experiment and stop an experiment early if it would exceed its share. Prefer cheaper models for bulk work and use strong models only where the comparison needs them.

## Experiments

### E1. Knowledge leakage: instructed versus filtered

Question: does a character leak facts it should not know when those facts are in its context with an instruction not to use them, compared with when the facts are simply absent?

- Build 30 or more test cases from the books: a character, a moment in the story, and a fact that character cannot know at that moment (another character's secret, an event elsewhere, a later event). Store cases in `experiments/e1/cases.jsonl`.
- Condition A: the fact is in the context with an explicit "this character does not know this" instruction. Condition B: the fact is absent. In both conditions the user turn probes for the fact.
- Measure leakage with an LLM judge, and spot-check at least 10 judgments manually by reading them; report agreement.
- Run at least three narrator models of different strength.

### E2. Jev versus LLM-with-JSON for narrow judgments

Question: is Jev better, cheaper, or faster than a standard LLM with structured output for the judgments the engine needs, on text in the dataset's language?

- Look up Jev's current API and access routes first (TypeSafe direct API, OpenRouter beta as `typesafe/jev-1.13`, AI/ML API). Its interface is a decision endpoint with typed questions, not a chat endpoint. If Jev is unreachable with the available keys, run the LLM side only and document exactly what blocked Jev.
- Judgment types:
  - contradiction: does this passage contradict this canon fact? (yes/no)
  - relationship change: how did character X's attitude toward the player change in this scene? (worse / unchanged / better, plus a magnitude score)
  - salience: would this NPC notice or care about this event? (yes/no)
  - uncertainty: is the outcome of this action genuinely uncertain? (yes/no)
- Build a labeled set of 40 or more items from the books and `Ragnar.md`. Write labels yourself, justify each in one line, and mark the ones you are unsure about.
- Report accuracy, calibration of returned probabilities where available, latency, and cost per 1000 judgments.

### E3. State extraction from a narrated turn

Question: which models extract state changes from a narrated turn accurately enough?

- Take 20 or more scene passages and write the expected JSON diff for each by hand: new facts with free-text content plus metadata (who witnessed, where, notability), inventory changes, injuries, relationship shifts.
- Compare at least four models, including at least one small one (around 4B to 8B parameters), on precision and recall of extracted facts, invented facts (hallucinations), witness-list accuracy, cost, and latency.

## Output

- Code under `experiments/` with a README on how to rerun each experiment.
- `reports/experiments/E1.md`, `E2.md`, `E3.md` with numbers, tables, examples of failures, and limitations of the test sets.
- `reports/experiments/SUMMARY.md`: what each result means for the design questions, stated as conditions ("if X matters, use Y"), not verdicts.
- Commit after each experiment.
