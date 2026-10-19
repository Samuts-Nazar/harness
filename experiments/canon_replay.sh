#!/usr/bin/env bash
# Rebuild a pilot store from the saved raw model replies (no API calls). Usage: canon_replay.sh <slug> <model>
set -e
OUT=/home/cock/projects/harness/campaigns/canon
cd "$(dirname "$0")/.."
HARNESS_ENV=/home/cock/projects/harness/.env nix develop --command python -m harness.canon.ingest --replay \
  --model "$2" --source /home/cock/projects/harness/data/witcher_books.txt \
  --out "$OUT/pilot_$1.db" --raw "$OUT/raw_$1" --cap 0.01
