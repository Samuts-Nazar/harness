#!/usr/bin/env bash
# Install Laya (CPU torch) into a venv on the 1TB disk, not on root.
set -e
D=/home/cock/1TB/AI/laya
mkdir -p "$D"
uv venv --python python3 "$D/venv"
UV_INDEX_STRATEGY=unsafe-best-match uv pip install --python "$D/venv/bin/python" \
  --extra-index-url https://download.pytorch.org/whl/cpu "laya[serve]"
"$D/venv/bin/laya-serve" --help 2>&1 | head -20 || true
