#!/usr/bin/env bash
# Run laya-serve on CPU (config is env-only). Venv lives on the 1TB disk.
# libstdc++ comes from a nix gcc-lib path (the venv python is a nix python; nix-ld does not apply).
GCC=$(ls -d /nix/store/*-gcc-16.2.0-lib | head -1)
export LD_LIBRARY_PATH="$GCC/lib:/run/current-system/sw/share/nix-ld/lib:$LD_LIBRARY_PATH"
export LAYA_DEVICE=cpu LAYA_HOST=127.0.0.1 LAYA_PORT="${LAYA_PORT:-8765}" LAYA_PRELOAD=1
export LAYA_MODELS="${LAYA_MODELS:-english,multilingual}" LAYA_THREADS=6
export HF_HOME=/home/cock/1TB/AI/laya/hf
exec /home/cock/1TB/AI/laya/venv/bin/laya-serve
