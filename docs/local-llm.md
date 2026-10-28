# Local model server (Gemma 4 26B-A4B, Unsloth build)

Measured 2026-10-28 on the RTX 3070 Laptop (8 GB): about 27 tokens/s generation on prose, 190–300 tokens/s prompt processing, VRAM about 6.6 GB.
Start (the Unsloth build of llama.cpp needs its own CUDA 13 libraries on `LD_LIBRARY_PATH`, otherwise it silently runs on the CPU at ~50 tokens/s prompt):

    CU=/home/cock/.unsloth/studio/unsloth_studio/lib/python3.13/site-packages/nvidia/cu13/lib
    G=$(ls /home/cock/1TB/AI/huggingface-cache/hub/models--SC117--gemma-4-26B-A4B-it-qat-heretic-GGUF/snapshots/*/gemma-4-26B-A4B-it-qat-heretic-UD-Q4_K_XL.gguf)
    LD_LIBRARY_PATH=$CU:/run/opengl-driver/lib /home/cock/.unsloth/llama.cpp/llama-server -m "$G" \
      --host 127.0.0.1 --port 8090 --parallel 2 --flash-attn on --no-context-shift -c 16384 \
      --ubatch-size 1120 --alias gemma-local --fit on --kv-unified --jinja \
      --spec-type ngram-mod --spec-ngram-mod-n-match 24 --spec-ngram-mod-n-min 48 --spec-ngram-mod-n-max 64 \
      --reasoning off --ctx-checkpoints 2

Parameters copied from the command Unsloth Studio itself used for this model (its log in `~/.unsloth/studio/logs/server/`). The nix `llama-server` also works but is slower here (about 18 tokens/s with `--n-cpu-moe 18`).
