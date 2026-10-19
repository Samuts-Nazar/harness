"""Playwright check at phone size (390x844) against the offline fake app: two turns, one
interrupt, the debug view. Screenshots go to app/screenshots/.

    nix develop --command python app/tests/ui_check.py
"""
from __future__ import annotations

import pathlib
import socket
import sys
import tempfile
import threading
import time

import uvicorn
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.server import create_app  # noqa: E402
from app.stacks import fake_stack  # noqa: E402

SHOTS = pathlib.Path(__file__).resolve().parents[1] / "screenshots"
SHOTS.mkdir(exist_ok=True)
errors: list[str] = []


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def shot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print("shot", name)


def no_hscroll(page, label):
    w = page.evaluate("[document.documentElement.scrollWidth, document.body.scrollWidth, "
                      "document.getElementById('feed').scrollWidth, "
                      "document.getElementById('feed').clientWidth]")
    assert w[0] <= 390 and w[1] <= 390 and w[2] <= w[3], f"horizontal scroll at {label}: {w}"


def main() -> None:
    stack = fake_stack()
    game = Game(lambda new: open_campaign(stack, root=tempfile.mkdtemp(), new=new), pace=0.08)
    port = free_port()
    server = uvicorn.Server(uvicorn.Config(create_app(game), host="127.0.0.1", port=port,
                                           log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    while not server.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/"

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="uk-UA")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.goto(url)
        page.wait_for_selector(".intro")
        shot(page, "01-start")

        # turn 1: type, send, watch narration then a labelled NPC line stream; let it finish
        page.fill("#input", "Я киваю Горсту й питаю, що сталося на млині.")
        page.click("#btnSend")
        page.wait_for_selector(".narr .w:nth-child(6)")
        shot(page, "02-narration-streaming")
        page.wait_for_selector(".npc[data-who=horst] .w:nth-child(6)")
        assert page.text_content(".npc[data-who=horst] .who") == "Горст"
        assert page.is_visible("#btnInterrupt")
        shot(page, "03-npc-speaking")
        page.wait_for_selector("#composer:not([hidden])", timeout=60000)
        no_hscroll(page, "after turn 1")
        shot(page, "04-turn1-done")

        # "how does he know that?": the offline judge finds a channel; the spoiler is a tap away
        page.click(".npc[data-who=horst] .ask")
        page.fill(".askbox textarea", "Звідки він знає про хлопців?")
        shot(page, "04b-ask")
        page.click(".askbox .btn.primary")
        page.wait_for_selector(".npc[data-who=horst] .askres")
        res = page.inner_text(".npc[data-who=horst] .askres")
        assert res.startswith("Може знати:"), res
        assert not page.is_visible(".npc[data-who=horst] .spoiler")
        page.click(".npc[data-who=horst] .linkbtn")
        assert page.is_visible(".npc[data-who=horst] .spoiler")
        no_hscroll(page, "after the answer")
        shot(page, "04c-channel-answer")

        # turn 2: interrupt the NPC mid-line
        page.fill("#input", "Мовчки дивлюсь на Ельзу.")
        page.click("#btnSend")
        page.wait_for_selector(".npc[data-who=elza] .w:nth-child(4)")
        before = page.locator(".npc[data-who=elza] .w").count()
        page.click("#btnInterrupt")
        page.wait_for_selector("#composer:not([hidden])", timeout=60000)
        after = page.locator(".npc[data-who=elza] .w").count()
        assert page.locator(".npc.cut").count() >= 1, "interrupted line must be marked"
        assert after < 30 and after >= before, (before, after)
        shot(page, "05-interrupted")

        # character panel
        page.click("#btnChar")
        page.wait_for_selector("#charPanel:not([hidden])")
        chips = page.locator(".chip").all_inner_texts()
        assert any("сталевий меч" in c for c in chips), chips
        shot(page, "06-character-panel")
        page.click("#charClose")

        # debug view
        page.click("#btnDebug")
        page.wait_for_selector("#debugPanel:not([hidden]) h4")
        text = page.inner_text("#debugBody")
        for needle in ("до першого слова", "Виклики моделей", "Судження", "Журнал подій", "narrator"):
            assert needle in text, needle
        page.wait_for_selector("#debugBody details")
        assert "Хто що знає" in page.inner_text("#debugBody")
        page.click("#debugBody summary:has-text(\"Горст\")")
        assert "acquainted" in page.inner_text("#debugBody")
        shot(page, "07-debug")
        page.click("#btnDebug")

        # reload keeps the story
        page.reload()
        page.wait_for_selector(".intro")
        assert page.locator(".me").count() == 2
        shot(page, "08-after-reload")
        browser.close()

    server.should_exit = True
    assert not errors, errors
    print("OK: 2 turns, 1 interrupt, character panel, debug view, reload; no console errors")


if __name__ == "__main__":
    main()
