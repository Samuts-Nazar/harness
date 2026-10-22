"""Live check of the book UI on the Vizima campaign (costs a few cents, cap $0.10).

    nix develop --command python app/tests/live_ui.py

Six turns in a real browser at phone size against a real server with the live stack: suggestions
(latency, cost), whether the next turn's first word waited for them, a tap on a place in the
drawer. Writes reports/ui/live.json and screenshots reports/ui/*.png. The key is never printed.
"""
from __future__ import annotations

import json
import pathlib
import socket
import sys
import tempfile
import threading
import time

import uvicorn
from dotenv import load_dotenv
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
load_dotenv("/home/cock/projects/harness/.env")
from app.game import Game  # noqa: E402
from app.server import create_app  # noqa: E402
from app.stacks import live_stack  # noqa: E402
from app.vizima import open_vizima  # noqa: E402

OUT = ROOT / "reports" / "ui"
OUT.mkdir(parents=True, exist_ok=True)
BUDGET = 0.06


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main() -> None:
    stack = live_stack(BUDGET)
    root = tempfile.mkdtemp(prefix="live-ui-")
    game = Game(lambda new: open_vizima(stack, root=root, new=new, canon_db=False), pace=0.04)
    stamps: list[tuple[float, dict]] = []   # (monotonic, event) for every event the game emits
    stop = threading.Event()

    def watch() -> None:
        seen = 0
        while not stop.is_set():
            for e in game.events_after(seen):
                seen = e["seq"]
                stamps.append((time.monotonic(), {k: e[k] for k in ("seq", "type", "turn") if k in e}
                               | ({"items": e["items"]} if e["type"] == "suggestions" else {})))
            time.sleep(0.01)

    threading.Thread(target=watch, daemon=True).start()
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(game), host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)

    def spent() -> float:
        return stack.spend.total

    rows: list[dict] = []
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="uk-UA")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.goto(f"http://127.0.0.1:{port}/")
        page.wait_for_selector(".intro")

        def idle() -> None:
            page.wait_for_selector("body[data-phase=idle]", state="attached", timeout=120000)

        def send(text: str) -> float:
            page.fill("#input", text)
            t = time.monotonic()
            page.click("#btnSend")
            return t

        def settled(turn: int) -> None:
            end = time.monotonic() + 120
            while time.monotonic() < end:
                if any(e.get("type") == "settled" and e.get("turn") == turn for _, e in stamps):
                    return
                time.sleep(0.05)

        def wait_sugg(turn: int, timeout: float = 60) -> bool:
            end = time.monotonic() + timeout
            while time.monotonic() < end:
                if any(e["type"] == "suggestions" and e.get("turn") == turn for _, e in stamps):
                    return True
                time.sleep(0.05)
            return False

        idle()
        plan = [
            ("type", "Я струшую дощ із плаща, сідаю до столу й питаю корчмаря, що тут нового."),
            ("tap", "Дивлюсь на людей у залі й питаю, хто тут головний."),
            ("type", "Я питаю, чи не чули вони щось про чудовисько біля міста."),
            ("nowait", "Я кажу, що можу допомогти за плату, і питаю, скільки пропонують."),
            ("type", "Я питаю, хто платитиме, і коли саме треба вирушати."),   # sent at once
            ("place", None),
            ("type", "Я роздивляюсь навколо й питаю першого-ліпшого перехожого, що тут коїться."),
        ]
        for i, (mode, text) in enumerate(plan, 1):
            before = spent()
            prev_pending = i > 1 and not any(
                e["type"] == "suggestions" and e.get("turn") == i - 1 for _, e in stamps)
            if mode == "tap":
                page.wait_for_selector("#sugg .sg", timeout=60000)
                page.click("#sugg .sg >> nth=0")
                text = page.input_value("#input")
                t0 = time.monotonic()
                page.click("#btnSend")
            elif mode == "place":
                page.click("#btnMenu")
                page.wait_for_selector("#places button")
                page.screenshot(path=str(OUT / "drawer-places.png"))
                names = page.eval_on_selector_all("#places button", "ns => ns.map(n => n.textContent)")
                page.click("#places button >> nth=0")
                text = page.input_value("#input")
                t0 = time.monotonic()
                page.click("#btnSend")
            else:
                t0 = send(text)
            idle()
            settled(i)
            t_settled = next(t for t, e in stamps if e["type"] == "settled" and e.get("turn") == i)
            first = game.debug.get("timing", {}).get("first_word_s")
            fw = next((t for t, e in stamps if e["type"] in ("narr_word", "word")
                       and e.get("turn") == i), None)
            spent_turn = spent() - before
            row = {"turn": i, "mode": mode, "text": text, "first_word_s": first,
                   "first_word_wall_s": round(fw - t0, 2) if fw else None,
                   "prev_suggestions_in_flight_at_send": prev_pending,
                   "waited_s": game.debug.get("timing", {}).get("waited_s"),
                   "total_s": game.debug.get("timing", {}).get("total_s"),
                   "slow_s": game.debug.get("timing", {}).get("slow_s"),
                   "turn_cost": game.debug.get("cost"), "error": game.debug.get("error")}
            if mode == "nowait":   # the next turn goes at once, not waiting for these suggestions
                page.screenshot(path=str(OUT / f"turn-{i}-before-suggestions.png"))
            else:
                ok = wait_sugg(i)
                s_before = spent()
                if ok:
                    t_s = next(t for t, e in stamps if e["type"] == "suggestions" and e.get("turn") == i)
                    row["sugg_latency_s"] = round(t_s - t_settled, 2)
                    row["sugg_items"] = next(e["items"] for _, e in stamps
                                             if e["type"] == "suggestions" and e.get("turn") == i)
                row["sugg_cost"] = round(spent() - before - (row["turn_cost"] or 0), 5)
                page.wait_for_timeout(300)
                page.screenshot(path=str(OUT / f"turn-{i}.png"))
            rows.append(row)
            print(json.dumps({k: v for k, v in row.items() if k != "sugg_items"}, ensure_ascii=False))
            if spent() > BUDGET * 0.9:
                print("budget nearly used; stopping")
                break
        page.wait_for_selector("body[data-phase=idle]", state="attached")
        page.click("#btnMenu")
        page.wait_for_selector("#people .person", timeout=5000)
        page.screenshot(path=str(OUT / "drawer-people.png"))
        page.keyboard.press("Escape")
        browser.close()
    game.wait_idle(60)
    stop.set()
    for row in rows:    # suggestions that arrived while the next turn was already running
        got = [(t, e) for t, e in stamps if e["type"] == "suggestions" and e.get("turn") == row["turn"]]
        done = [t for t, e in stamps if e["type"] == "settled" and e.get("turn") == row["turn"]]
        row["sugg_arrived"] = bool(got)
        if got and "sugg_latency_s" not in row and done:
            row["sugg_latency_s"] = round(got[0][0] - done[0], 2)
            row["sugg_items"] = got[0][1]["items"]
    out = {"rows": rows, "total_cost": round(spent(), 5), "calls": stack.spend.calls,
           "assistant_calls": len(game.eng.assistant_calls), "errors": errors,
           "places": names if "names" in dir() else None}
    (OUT / "live.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
    print("total cost", out["total_cost"], "errors", errors)


if __name__ == "__main__":
    main()
