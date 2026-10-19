# Task 10: Should records be stored in English? (2026-10-19)

Written by the lead from the worker's final report (the worker's file tool refused report files). Data, code, blind packets, grades: `experiments/language/`. Spend: 0.042 USD.

## Verdict: mixed — English records, Ukrainian names
- **`openai/gpt-6-luna` (chosen narrator/NPC): yes.** English facts and profiles did not measurably hurt the Ukrainian: NPC 4.42 vs 4.33, narrator 4.19 vs 4.44, both inside the noise. Leaks and staying in character unchanged.
- **The real cost is names.** With Latin names in records the model transliterates badly or lets them through (*Хостомил, Яск'єр, Рангар*, once a bare "Hostomyl"): 15% of luna narrator outputs, 37% of deepseek. Writing names, places and titles in Ukrainian inside the English record brings this to 0% (luna) and 4% (deepseek). Remaining slip: place names left undeclined ("двір Каер Морхен").
- **`deepseek/deepseek-v4.1-flash-1017` (fallback): worse on English context.** Narrator 3.63 vs 4.52 (−0.89, CI −1.48..−0.33); NPC leaks 64% vs 39% (+25 pts). Ukrainian names recover leaks (38%) and part of the narrator score (4.00).
- **Extractor: English facts are fine.** Recall 98% vs 94% (noise), precision 99% both, valid JSON 30/30 both, language instruction followed 30/30. With English facts, state items come out mixed-script; say "state items in English" too or normalise in code.
- **Not affected:** NPC speech in narration (0 of 162), narrator deciding the player's acts (no trend), format failures.

## Setup
- Task 7 items: 9 narrator scenes, 12 NPC situations, 10 extraction passages. Task 7 engine prompts plus one line "answer in Ukrainian".
- Variants: **UK** (Ukrainian context), **EN** (hand-translated, Latin names; player lines stay Ukrainian), **EN+UKNAMES** (EN with Ukrainian names/places/titles; added after EN showed the name problem).
- luna and deepseek at temperature 0.7, 3 samples per item per variant (EN+UKNAMES NPC: 2). Extractor: deepseek, 3 samples.
- 456 text outputs + 60 extractions graded blind by the Claude Code agent. EN+UKNAMES was graded in a later batch: blind to model, not to variant, so its gain may partly be grader drift. Differences under ~0.3 are noise.
- Effect sizes: mean of per-item differences, 95% bootstrap CI. Leak marking stricter than task 7; compare across variants only.

## NPC lines
| Model | Variant | Ukrainian | In character | Leak | Name/foreign slip | n |
|---|---|---|---|---|---|---|
| luna | UK | 4.33 | 4.50 | 31% | 0% | 36 |
| luna | EN | 4.42 | 4.47 | 22% | 8% | 36 |
| luna | EN+UKNAMES | 4.71 | 4.67 | 29% | 8% | 24 |
| deepseek | UK | 4.36 | 4.36 | 39% | 0% | 36 |
| deepseek | EN | 4.06 | 4.19 | **64%** | 6% | 36 |
| deepseek | EN+UKNAMES | 4.58 | 4.29 | 38% | 0% | 24 |

## Narrator
| Model | Variant | Ukrainian | Name/English intrusion | Calque/wrong form | Decides player's act | n |
|---|---|---|---|---|---|---|
| luna | UK | 4.44 | 0% | 0% | 4% | 27 |
| luna | EN | 4.19 | 15% | 11% | 4% | 27 |
| luna | EN+UKNAMES | 4.56 | 0% | 15% | 0% | 27 |
| deepseek | UK | 4.52 | 0% | 0% | 11% | 27 |
| deepseek | EN | **3.63** | **37%** | 0% | 19% | 27 |
| deepseek | EN+UKNAMES | 4.00 | 4% | 19% | 22% | 27 |

## Differences vs UK (95% CI)
| Model | Set | Metric | EN − UK | EN+UKNAMES − UK |
|---|---|---|---|---|
| luna | NPC | Ukrainian | +0.08 (−0.28..+0.44) noise | +0.38 (+0.06..+0.72), grader-drift caveat |
| luna | NPC | leak | −8 pts (−22..0) noise | −1 pt noise |
| luna | narrator | Ukrainian | −0.26 (−0.74..+0.22) noise | +0.11 (−0.19..+0.41) noise |
| deepseek | NPC | Ukrainian | −0.31 (−0.72..+0.11) noise | +0.22 (−0.01..+0.47) noise |
| deepseek | NPC | leak | **+25 pts (+11..+39)** | −1 pt noise |
| deepseek | narrator | Ukrainian | **−0.89 (−1.48..−0.33)** | **−0.52 (−0.89..−0.15)** |

## Extractor (deepseek, 30 per variant)
| Facts language | Fact recall | State recall | Precision | Bad state ops | Valid JSON | Language followed |
|---|---|---|---|---|---|---|
| Ukrainian | 94% | 67% | 99% | 27% | 30/30 | 30/30 |
| English | 98% | 67% | 99% | 16% | 30/30 | 30/30 |

## What to do
1. Records in English; names, places, titles in canonical Ukrainian via a glossary applied at write time. The player's own words stay verbatim.
2. Keep "answer in Ukrainian" in every narrator and NPC prompt.
3. Extractor: "state items in English", or normalise in code.
4. The deepseek fallback loses quality on English context: pick a fallback that tolerates it, or render Ukrainian context when the fallback is active.
5. Not tested: name declension over long play, memory files with many links, other models, other temperatures.
