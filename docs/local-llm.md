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

## Playing the game on it

With the server up (`curl -s http://127.0.0.1:8090/v1/models` lists `gemma-local`):

    nix develop --command python -m app --local [--local-url http://127.0.0.1:8090/v1/chat/completions] [--local-model gemma-local] [--local-timeout 120]

Every role (narrator, NPCs, extractor, typed judgments, assistant, reader) runs on that one model;
the role fallbacks are the same model. Typed judgments go to it as an `LLMJudge` (JSON answers), not to a
hosted decision model. No OpenRouter key is read and nothing goes over the network (the canon store
is searched by full text only, without the hosted embedder). The cost is 0, the price caps do not
apply to a local model (`policy.allow_local`). A narrator or NPC call may take `--local-timeout`
seconds (default 120, the hosted stack uses 20) before it is retried once.
`LocalProvider` keeps at most 2 requests in flight (the server's `--parallel 2`), from any thread.

A game package (the file-package step): open the page, «Нова гра з файлу», pick the `.yaml`. The
package and the campaign stay on this machine (`campaigns/`, git-ignored).

Measured check (4 turns through `app.game.Game`): `experiments/local_live_check.py [PACKAGE] [OUT]`,
summary in `reports/local/SUMMARY.md`.
