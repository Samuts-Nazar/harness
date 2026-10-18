# experiments/

Throwaway scripts for task 2 (not engine code). Run everything from the repo root inside the dev shell. `data/` is git-ignored and must exist locally. Raw model outputs go to `experiments/*/results/` (git-ignored); the spend ledger is `experiments/results/spend.jsonl`.

Shared: `common/llm.py` is a minimal OpenRouter chat client plus the Jev decisions client, with a per-experiment spend ledger and a hard cap (`BudgetExceeded`). Reasoning is disabled by default; models where it is mandatory (Sonnet 5.5) fall back to `effort: low`.

```
nix develop --command python <script>
```

## E1: leakage, instructed vs filtered
```
python experiments/e1/make_cases.py        # writes cases.jsonl (39 cases); drops probe_neutral
python experiments/e1/fix_neutral.py       # re-adds the hand-written neutral probes
python experiments/e1/run.py --samples 2 --out raw_leading.jsonl                          # leading probes (~$1.1)
python experiments/e1/run.py --samples 1 --probe probe_neutral --out raw_neutral.jsonl    # neutral probes (~$0.5)
python experiments/e1/adjudicate.py raw_neutral.jsonl                                     # strong second judge (~$0.3-0.8)
python experiments/e1/analyze.py raw_leading.jsonl ; python experiments/e1/analyze_adj.py
```
`make_neutral.py` is the LLM draft of neutral probes; `fix_neutral.py` holds the final hand-edited ones. Cap in `run.py` is `CAP`.

## E2: Jev vs LLM-with-JSON
```
python experiments/e2/make_items.py        # writes items.jsonl (48 labeled items)
python experiments/e2/run.py --reps 2      # all systems (~$0.10)
python experiments/e2/analyze.py           # writes results/summary.md
python experiments/e2/batch_probe.py       # Jev batching latency/cost probe
```
Jev needs only `OPENROUTER_API_KEY` (endpoint `https://openrouter.ai/api/alpha/decisions`).

## E3: state extraction
```
python experiments/e3/make_gold.py         # writes passages.jsonl (line ranges into data/ + hand gold)
python experiments/e3/run.py               # 7 models x 20 passages + matcher (~$0.35)
python experiments/e3/analyze.py
python experiments/e3/show.py 49 71        # print non-empty lines of data/witcher_books.txt
```

## Data facts (recorded per task brief)
- `data/witcher_books.txt`: Ukrainian (translation by Sergiy Legeza and others), UTF-8 without BOM, 60,875 lines, 9.06 MB (the brief says ~8 MB). Not one clean per-book header: the first book title is on line 3 ("Останнє бажання"); the rest are separated by "Кінець першого/другого/третього/четвертого тому", short story titles inside the short-story collections, and `Розділ N` lines inside the novels. Appended translator commentary/notes sit between books. Rough line ranges used here: Last Wish 1-6300, Sword of Destiny 6790-15290, Blood of Elves 15500-21885, Time of Contempt 22100-28795, Baptism of Fire 29160-35609, Tower of the Swallow 35970-44775, Lady of the Lake 45240-56874, Season of Storms 59550-end. Names follow this translation (Любисток for Dandelion, Нільфгард, Мільва, Регіс, Ґеральт...).
- `data/Ragnar.md`: Ukrainian, UTF-8, 644 lines, 103 KB, Markdown headings. Characters: Ragnar (the player), Vesemir, young Geralt, Eskel; some dates in 1192-1193.
