#!/usr/bin/env bash
# Run the canon pilot ingestion for one model. Usage: experiments/canon_run.sh <slug> <model>
# Output (git-ignored): /home/cock/projects/harness/campaigns/canon/pilot_<slug>.db, raw_<slug>/, run_<slug>.log
set -e
OUT=/home/cock/projects/harness/campaigns/canon
mkdir -p "$OUT"
cd "$(dirname "$0")/.."
HARNESS_ENV=/home/cock/projects/harness/.env nix develop --command python -m harness.canon.ingest \
  --model "$2" --source /home/cock/projects/harness/data/witcher_books.txt \
  --out "$OUT/pilot_$1.db" --raw "$OUT/raw_$1" --cap 0.15 ${3:-} >"$OUT/run_$1.log" 2>&1
