"""Local check: a game package's start and 4 turns through app.game.Game, every role on the local
llama.cpp server (docs/local-llm.md; no key, no network, no cost).

    nix develop --command python experiments/local_live_check.py [PACKAGE.yaml] [OUT_DIR]

PACKAGE defaults to app/tests/fixtures/outsider_ellander.yaml; OUT_DIR (raw JSON, it may hold
canon records and the sheet: keep it out of git) to /tmp/local_live. The canon store is
$LOCAL_BE or /home/cock/projects/harness/campaigns/canon/be.db. The server URL and model:
$LOCAL_URL, $LOCAL_MODEL. Prints per turn: first-word latency, total time, model calls,
timeouts/fallbacks, judge parse failures, the transcript; then the panel (the latent Source must
not be there), Yennefer's noticed facts and the backpack state.
"""
from __future__ import annotations

import json
import os
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
for k in ("HARNESS_CANON_DB", "HARNESS_CANON_DB_BE", "OPENROUTER_API_KEY"):
    os.environ.pop(k, None)  # proves no hosted call is possible

from app import newgame  # noqa: E402
from app.game import Game  # noqa: E402
from app.stacks import LOCAL_MODEL, local_stack  # noqa: E402
from harness.canon.play import what_knows  # noqa: E402
from harness.judge import JudgeError  # noqa: E402
from harness.models import PLAYER  # noqa: E402
from harness.providers import LOCAL_URL  # noqa: E402

PKG = Path(sys.argv[1] if len(sys.argv) > 1 else ROOT / "app/tests/fixtures/outsider_ellander.yaml")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/local_live")
OUT.mkdir(parents=True, exist_ok=True)
BE = os.environ.get("LOCAL_BE", "/home/cock/projects/harness/campaigns/canon/be.db")
TURN_WAIT = float(os.environ.get("LOCAL_TURN_WAIT", 900))

T1 = "Підводжуся з землі, обтрушую коліна й кажу жінці: «Вибачте... Де я? Здається, я заблукав»."
T2_READ = "Знімаю рюкзак, розстібаю його, дістаю ноутбук, відкриваю й читаю свої нотатки про духа лампи."
T2_OPEN = "Знімаю рюкзак, розстібаю його, дістаю ноутбук і відкриваю його."
T3 = "Питаю її: «Чому ви так на мене дивитеся? Щось зі мною не так?»"
T4 = "Іду далі поруч із нею."


class Meter:
    """Every HTTP call to the server: seconds, prompt/completion tokens, server timings; and the
    typed-judgment batches (LLM calls per batch, failures)."""

    def __init__(self, stack) -> None:
        self.calls: list[dict] = []
        self.judge_batches: list[dict] = []
        self.lock = threading.Lock()
        client = stack.provider._client
        post = client.post

        def timed_post(url, **kw):
            t0 = time.monotonic()
            r = post(url, **kw)
            try:
                j = r.json()
            except ValueError:
                j = {}
            msgs = (kw.get("json") or {}).get("messages") or [{}]
            with self.lock:
                self.calls.append({
                    "t0": round(t0, 2), "s": round(time.monotonic() - t0, 2),
                    "status": r.status_code, "sys": (msgs[0].get("content") or "")[:60],
                    "usage": j.get("usage"), "timings": j.get("timings")})
            return r

        client.post = timed_post
        judge = stack.judge
        ask, complete = judge.ask, judge._complete
        local = threading.local()

        def counted_complete(messages):
            local.n = getattr(local, "n", 0) + 1
            return complete(messages)

        def metered_ask(state, questions):
            local.n = 0
            t0 = time.monotonic()
            err = None
            try:
                return ask(state, questions)
            except JudgeError as e:
                err = str(e)[:300]
                raise
            finally:
                with self.lock:
                    self.judge_batches.append({
                        "tags": [q.tag for q in questions.values()], "llm_calls": local.n,
                        "s": round(time.monotonic() - t0, 2), "error": err})

        judge._complete, judge.ask = counted_complete, metered_ask

    def mark(self) -> tuple[int, int]:
        with self.lock:
            return len(self.calls), len(self.judge_batches)

    def since(self, m: tuple[int, int]) -> dict:
        with self.lock:
            calls, batches = self.calls[m[0]:], self.judge_batches[m[1]:]
        pt = [c["usage"]["prompt_tokens"] for c in calls if c.get("usage")]
        return {"http_calls": len(calls), "max_prompt_tokens": max(pt, default=0),
                "sum_prompt_tokens": sum(pt),
                "sum_completion_tokens": sum((c.get("usage") or {}).get("completion_tokens", 0)
                                             for c in calls),
                "cached_tokens": sum(((c.get("timings") or {}).get("cache_n") or 0) for c in calls),
                "http_errors": [c for c in calls if c["status"] != 200],
                "judge_batches": len(batches),
                "judge_retries": sum(1 for b in batches if b["llm_calls"] > 1),
                "judge_failures": [b for b in batches if b["error"]]}


def has_content(pkg) -> bool:
    return any(it.get("content") for it in pkg.data["player"].get("inventory") or [])


def yen_id(eng):
    yen = [c for c, p in eng.profiles.items() if "Йеннефер" in (p.name or "")]
    return yen[0] if yen else None


def backpack(eng):
    return [{"item": el.item, "id": el.id, "loc": el.location, "open": el.open}
            for el in eng.live.snapshot().get(PLAYER, {}).values()
            if "рюкзак" in el.item or "backpack" in el.item.lower() or "ноутбук" in el.item
            or "laptop" in el.item.lower()]


def main() -> None:
    url, model = os.environ.get("LOCAL_URL", LOCAL_URL), os.environ.get("LOCAL_MODEL", LOCAL_MODEL)
    stack = local_stack(url, model)
    meter = Meter(stack)
    pkg = newgame.parse(PKG.read_text("utf-8"))
    turns = [T1, T2_READ if has_content(pkg) else T2_OPEN, T3, T4]
    print(f"package: {PKG.name}; inline content: {has_content(pkg)}; server {url} model {model}")
    t0, m = time.monotonic(), meter.mark()
    try:
        game = Game(lambda new: newgame.open_package(stack, pkg, root=OUT / "campaigns",
                                                     canon_db=BE), pace=0.0, suggestions=False)
    except Exception as e:  # report, never retry
        print("START FAILED:", type(e).__name__, str(e)[:500])
        print(json.dumps(meter.since(m), ensure_ascii=False))
        raise SystemExit(1)
    start = {"seconds": round(time.monotonic() - t0, 1), **meter.since(m),
             "notes": [n.get("kind") for n in game.eng.devlog]}
    print("START built in", start["seconds"], "s;", json.dumps({k: start[k] for k in (
        "http_calls", "max_prompt_tokens", "judge_batches", "judge_retries")}))
    results = {"package": PKG.name, "start": start, "turns": []}
    for i, text in enumerate(turns, 1):
        m, t0 = meter.mark(), time.monotonic()
        dev0, rec0 = len(game.eng.devlog), len(game.camp.recorder.calls)
        tr0 = len(game.state()["transcript"])
        exc = None
        try:
            game.start_turn(text)
            time.sleep(0.5)
            end = time.monotonic() + TURN_WAIT
            while game.phase != "idle" and time.monotonic() < end:
                time.sleep(0.2)
            game.wait_idle(TURN_WAIT)
        except Exception as e:  # noqa: BLE001
            exc = f"{type(e).__name__}: {str(e)[:300]}"
        dbg = getattr(game, "debug", {}) or {}
        notes = game.eng.devlog[dev0:]
        tim = dbg.get("timing", {})
        st = game.state()
        new = st["transcript"][tr0:]
        r = {"turn": i, "text": text, "first_word_s": tim.get("first_word_s"),
             "total_s": tim.get("total_s"), "slow_s": tim.get("slow_s"),
             "wall_s": round(time.monotonic() - t0, 1), "engine_calls": len(
                 game.camp.recorder.calls) - rec0, **meter.since(m), "exception": exc,
             "error": dbg.get("error"), "model_error": dbg.get("model_error"),
             "timeouts": [n for n in notes if n.get("kind") in (
                 "model_timeout", "model_fallback", "script_regenerated")],
             "note_kinds": sorted({str(n.get("kind")) for n in notes}),
             "transcript": [{"kind": e.get("kind"), "who": e.get("name") or e.get("who"),
                             "text": e.get("text")} for e in new]}
        results["turns"].append(r)
        print(f"\n== turn {i}: first word {r['first_word_s']} s, total {r['total_s']} s, "
              f"slow lane {r['slow_s']} s, wall {r['wall_s']} s; engine calls {r['engine_calls']}, "
              f"HTTP calls {r['http_calls']} (max prompt {r['max_prompt_tokens']} tok), judge "
              f"batches {r['judge_batches']} (retries {r['judge_retries']}, failures "
              f"{len(r['judge_failures'])}), timeouts/fallbacks {len(r['timeouts'])}, "
              f"exception {exc}, error {r['error']}")
        for e in r["transcript"]:
            print(f"  [{e['kind']}{' ' + str(e['who']) if e['who'] else ''}] {e['text']}")
        (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1,
                                                      default=str))
    eng = game.eng
    yen = yen_id(eng)
    panel = game.panel()
    chips = [c["text"] for c in panel.get("chips", [])]
    results["final"] = {
        "panel": panel, "source_on_panel": any("Джерел" in c or "Source" in c for c in chips),
        "yennefer": yen, "yen_knows": what_knows(eng, yen) if yen else [],
        "backpack": backpack(eng), "calls": meter.calls}
    (OUT / "results.json").write_text(json.dumps(results, ensure_ascii=False, indent=1, default=str))
    print("\npanel chips:", chips)
    print("Source shown on the panel:", results["final"]["source_on_panel"])
    print("Yennefer noticed:", [k["text"] for k in results["final"]["yen_knows"]
                                if k["how"] != "told"][:12])
    print("backpack/laptop:", results["final"]["backpack"])
    print("spend", stack.spend.total, "calls", stack.spend.calls)


if __name__ == "__main__":
    main()
