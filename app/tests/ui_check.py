"""Playwright check at phone size (390x844) against the offline fake app: the book page.

Five turns (a living exchange with a gesture, tap to skip, typing to cut in, the small ✋), the
legend shown and hidden, the ink picker recolouring past lines, suggestions tap-to-insert and 💡,
the long-press sheet (items on the last NPC line versus an old line), the ☰ drawer, the debug
view, and a reload that gives the same paragraphs and colours. Screenshots go to app/screenshots/.

    nix develop --command python app/tests/ui_check.py
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
from playwright.sync_api import sync_playwright

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.inks import PALETTE  # noqa: E402
from app.server import create_app  # noqa: E402
from app.stacks import fake_stack  # noqa: E402

SHOTS = pathlib.Path(__file__).resolve().parents[1] / "screenshots"
SHOTS.mkdir(exist_ok=True)
errors: list[str] = []

SAY = "p[data-line=say]"
ACT = "p[data-line=act]"


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
                      "document.getElementById('feed').clientWidth, window.innerWidth]")
    assert w[0] <= w[4] and w[1] <= w[4] and w[2] <= w[3], f"horizontal scroll at {label}: {w}"


def words(page, sel):
    """The number of words in the last paragraph matching `sel` (0 if none)."""
    return page.evaluate("(s) => { const n = [...document.querySelectorAll(s)].pop(); "
                         "return n ? n.textContent.trim().split(/\\s+/).length : 0 }", sel)


def wait_words(page, sel, n, timeout=30000):
    page.wait_for_function("([s, n]) => { const p = [...document.querySelectorAll(s)].pop(); "
                           "return p && p.textContent.trim().split(/\\s+/).length >= n }",
                           arg=[sel, n], timeout=timeout)


def wait_new(page, sel, before, n, timeout=30000):
    """Wait for a new paragraph matching `sel` (more than `before` of them) with >= n words."""
    page.wait_for_function("([s, b, n]) => { const ps = document.querySelectorAll(s); "
                           "return ps.length > b && ps[ps.length - 1].textContent.trim()"
                           ".split(/\\s+/).length >= n }", arg=[sel, before, n], timeout=timeout)


def wait_idle(page):
    page.wait_for_selector("body[data-phase=idle]", state="attached", timeout=60000)


def color(page, sel, i=0):
    return page.evaluate("([s, i]) => getComputedStyle(document.querySelectorAll(s)[i]).color",
                         [sel, i])


def rgb(hexc):
    h = hexc.lstrip("#")
    return "rgb(%d, %d, %d)" % (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))


def page_signature(page):
    """What a reader sees: every paragraph's kind, speaker token, text and speech colour."""
    return page.evaluate("""() => [...document.querySelectorAll('#feed [data-line]')].map(p => {
        const c = p.cloneNode(true);
        c.querySelectorAll('.askbox, .askres').forEach(x => x.remove());
        const q = p.querySelector('.q');
        return [p.dataset.line, p.dataset.tok || '', c.textContent.trim(),
                q ? getComputedStyle(q).color : ''];
    })""")


def sheet_items(page, sel, i):
    """Open the line menu on the i-th paragraph matching `sel` with a right click (desktop) and
    return the actions it offers; close it again."""
    page.locator(sel).nth(i).click(button="right")
    page.wait_for_selector("#sheet[open]")
    acts = page.eval_on_selector_all("#sheet [data-act]", "ns => ns.map(n => n.dataset.act)")
    page.keyboard.press("Escape")
    page.wait_for_selector("#sheet:not([open])", state="attached")
    return acts


def long_press(page, sel, i=0):
    """A touch long press (pointer down, hold, up) on the i-th paragraph matching `sel`."""
    box = page.locator(sel).nth(i).bounding_box()
    x, y = box["x"] + 20, box["y"] + box["height"] / 2
    opts = {"pointerType": "touch", "isPrimary": True, "clientX": x, "clientY": y, "bubbles": True}
    page.locator(sel).nth(i).dispatch_event("pointerdown", opts)
    page.wait_for_timeout(750)
    page.locator(sel).nth(i).dispatch_event("pointerup", opts)


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

    def console(m):
        # the web font is optional (offline serif fallback); /api/places comes with Task 4 and
        # the drawer shows no places section while it answers 404 (the browser logs that 404)
        where = (m.location or {}).get("url", "")
        if m.type == "error" and "fonts.g" not in where and not where.endswith("/api/places"):
            errors.append(m.text)

    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True, has_touch=True, locale="uk-UA")
        page = ctx.new_page()
        page.on("pageerror", lambda e: errors.append(str(e)))
        page.on("console", console)
        page.goto(url)
        page.wait_for_selector(".intro")
        wait_idle(page)
        assert page.is_visible("#btnIdea") and not page.is_visible("#btnInterrupt")
        shot(page, "01-start")

        # turn 1: narration, then a stranger's line in their own ink; ✋ only while it streams
        page.fill("#input", "Я киваю чоловікові й питаю, що сталося на млині.")
        page.click("#btnSend")
        wait_words(page, ".narr", 6)
        assert page.is_visible("#btnInterrupt") and not page.is_visible("#btnIdea"), "✋ while told"
        assert page.is_visible("#btnSkip")
        shot(page, "02-narration-streaming")
        wait_words(page, SAY, 6)
        horst = page.get_attribute(SAY, "data-tok")
        assert horst and len(horst) >= 6, horst
        hsel = f"{SAY}[data-tok='{horst}']"
        assert page.is_visible("#btnInterrupt")
        ink_h = page.evaluate("(t) => getComputedStyle(document.documentElement)"
                              ".getPropertyValue('--ink-' + t).trim()", horst)
        assert ink_h.lower() in PALETTE, ink_h
        assert color(page, f"{hsel} .q") == rgb(ink_h), "speech is in the character's ink"
        assert color(page, "#btnInterrupt") == rgb(ink_h), "✋ is tinted with the speaker's ink"
        assert page.text_content(f"{hsel} .who").strip(), "the speaker is named, not only coloured"
        shot(page, "03-npc-speaking")
        wait_idle(page)
        assert not page.is_visible("#btnInterrupt") and page.is_visible("#btnIdea"), "💡 when idle"
        no_hscroll(page, "after turn 1")
        shot(page, "04-turn1-done")

        # suggestions above the input: a tap fills the input and sends nothing
        page.wait_for_selector("#sugg .sg", timeout=30000)
        assert 2 <= page.locator("#sugg .sg").count() <= 3
        me_before = page.locator(".me").count()
        chip = page.locator("#sugg .sg").first.inner_text()
        page.locator("#sugg .sg").first.click()
        assert page.input_value("#input") == chip, (page.input_value("#input"), chip)
        page.wait_for_timeout(400)
        assert page.locator(".me").count() == me_before, "a suggestion is never sent by itself"
        assert page.get_attribute("body", "data-phase") == "idle"
        shot(page, "04a-suggestion-inserted")
        page.fill("#input", "")
        n = page.locator("#sugg .sg").count()
        page.click("#btnIdea")
        page.wait_for_function(f"document.querySelectorAll('#sugg .sg').length > {n}")
        no_hscroll(page, "with more suggestions")
        shot(page, "04b-more-suggestions")

        # legend: open shows names, collapsed leaves the coloured dots only
        assert page.is_visible(f"#legend .lg[data-tok='{horst}'] .dot")
        if page.get_attribute("#btnLegend", "aria-expanded") != "true":
            page.click("#btnLegend")
        assert page.is_visible(f"#legend .lg[data-tok='{horst}'] .nm")
        assert color(page, f"#legend .lg[data-tok='{horst}'] .nm") == rgb(ink_h)
        shot(page, "04c-legend-open")
        page.click("#btnLegend")
        assert page.get_attribute("#btnLegend", "aria-expanded") == "false"
        assert not page.is_visible(f"#legend .lg[data-tok='{horst}'] .nm")
        assert page.is_visible(f"#legend .lg[data-tok='{horst}'] .dot")
        shot(page, "04d-legend-collapsed")
        page.click("#btnLegend")
        assert page.is_visible(f"#legend .lg[data-tok='{horst}'] .nm")

        # "how does he know that?" from the line menu (a touch long press opens it)
        long_press(page, hsel, 0)
        page.wait_for_selector("#sheet[open]")
        acts = page.eval_on_selector_all("#sheet [data-act]", "ns => ns.map(n => n.dataset.act)")
        assert acts[0] == "challenge" and "ink" in acts, acts
        shot(page, "04e-line-menu")
        page.click("#sheet [data-act=challenge]")
        page.wait_for_selector("#sheet:not([open])", state="attached")
        page.fill(f"{hsel} .askbox textarea", "Звідки він знає про хлопців?")
        page.click(f"{hsel} .askbox .btn.primary")
        page.wait_for_selector(f"{hsel} .askres")
        res = page.inner_text(f"{hsel} .askres")
        assert res.startswith("Може знати:"), res
        assert not page.is_visible(f"{hsel} .spoiler")
        page.click(f"{hsel} .linkbtn")
        assert page.is_visible(f"{hsel} .spoiler")
        no_hscroll(page, "after the answer")
        shot(page, "04f-channel-answer")

        # turn 2: a living exchange (Ельза, Горст's gesture, Ельза again). The skip hint is
        # there while it is told; a tap delivers the rest at once, nothing is cut.
        from harness.director import NEXT_TAG, SHAPE_TAG
        stack.judge.rules[NEXT_TAG] = ["elza", "horst", "elza", "player"]
        stack.judge.rules[SHAPE_TAG] = ["normal", "gesture", "normal"]
        page.fill("#input", "Що ви обоє скажете?")
        page.click("#btnSend")
        page.wait_for_function(f"[...document.querySelectorAll('{SAY}')]"
                               f".some(p => p.dataset.tok !== '{horst}')")
        elza = page.evaluate(f"[...document.querySelectorAll('{SAY}')]"
                             f".find(p => p.dataset.tok !== '{horst}').dataset.tok")
        esel = f"{SAY}[data-tok='{elza}']"
        wait_words(page, esel, 3)
        assert page.is_visible("#btnSkip") and "одразу" in page.inner_text("#btnSkip")
        assert page.is_visible("#composer") and page.is_enabled("#input"), "input stays open"
        ink_e = page.evaluate("(t) => getComputedStyle(document.documentElement)"
                              ".getPropertyValue('--ink-' + t).trim()", elza)
        assert ink_e and ink_e != ink_h, "present characters get distinct inks"
        assert color(page, "#btnInterrupt") == rgb(ink_e), "✋ follows the speaker"
        shot(page, "05-exchange-skip-hint")
        t0 = time.time()
        page.click("#feed")  # a tap on the text shows the rest at once
        page.wait_for_selector(f"{ACT}[data-tok='{horst}']", timeout=60000)
        wait_idle(page)
        assert time.time() - t0 < 6, "a tap must deliver the rest at once"
        assert page.locator(esel).count() >= 2, "the same speaker twice is two paragraphs"
        assert page.locator(".cut").count() == 0, "a skip is not an interrupt"
        assert color(page, f"{ACT} .act-text") != rgb(ink_h), "a gesture stays in the base ink"
        no_hscroll(page, "after the exchange")
        shot(page, "05b-exchange-with-gesture")

        # line menu: the last NPC line versus an old line, versus a gesture (the server does not
        # offer model error / retroactive cut yet; with them offered, they show on the right line)
        assert sheet_items(page, esel, page.locator(esel).count() - 1) == ["challenge", "ink"]
        assert sheet_items(page, hsel, 0) == ["challenge", "ink"]
        assert sheet_items(page, f"{ACT}[data-tok='{horst}']", 0) == ["ink"]

        def with_actions(route):
            r = route.fetch()
            body = r.json()
            body["actions"] = ["model_error", "cut"]
            route.fulfill(response=r, body=json.dumps(body))

        page.route("**/api/state", with_actions)
        page.reload()
        wait_idle(page)
        last_e = page.locator(esel).count() - 1
        got = sheet_items(page, esel, last_e)
        assert got == ["challenge", "model_error", "cut", "ink"], got
        long_press(page, esel, last_e)
        page.wait_for_selector("#sheet[open]")
        page.wait_for_timeout(250)  # the sheet's rise
        shot(page, "05c-line-menu-last-line")
        page.keyboard.press("Escape")
        assert sheet_items(page, hsel, 0) == ["challenge", "ink"], "old line: no cut, no rewrite"
        assert sheet_items(page, f"{ACT}[data-tok='{horst}']", 0) == ["model_error", "ink"]
        page.unroute("**/api/state")
        page.reload()
        wait_idle(page)

        # ink: picked from the line menu of an old line; every past line of him changes at once
        page.locator(hsel).first.click(button="right")
        page.click("#sheet [data-act=ink]")
        page.wait_for_selector("#sheet .sw button")
        assert page.locator("#sheet .sw button").count() == 8
        new_ink = next(c for c in PALETTE if c not in (ink_h, ink_e))
        page.click(f"#sheet .sw button[data-ink='{new_ink}']")
        page.wait_for_function("([t, c]) => getComputedStyle(document.documentElement)"
                               ".getPropertyValue('--ink-' + t).trim() === c", arg=[horst, new_ink])
        assert color(page, f"{hsel} .q", 0) == rgb(new_ink), "a past line takes the new ink"
        dot = page.evaluate(f"getComputedStyle(document.querySelector(\"#legend .lg[data-tok='{horst}'] "
                            f".dot\")).backgroundColor")
        assert dot == rgb(new_ink), "the legend follows the ink"
        shot(page, "05d-ink-picker")
        page.keyboard.press("Escape")
        ink_h = new_ink

        # turn 3: type while the NPCs talk: it cuts in, then runs the new text
        stack.judge.rules[NEXT_TAG] = ["horst", "elza", "horst", "player"]
        stack.judge.rules[SHAPE_TAG] = ["normal"]
        game.base_pace = 0.3  # slow enough to type over him while he speaks
        page.fill("#input", "Говори, чоловіче.")
        nh = page.locator(hsel).count()
        page.click("#btnSend")
        wait_new(page, hsel, nh, 4)
        assert color(page, f"{hsel} .q", page.locator(hsel).count() - 1) == rgb(new_ink), \
            "a future line takes the new ink"
        page.fill("#input", "Годі. А ти що скажеш?")
        shot(page, "05e-typing-during-a-turn")
        stack.judge.rules[NEXT_TAG] = ["elza", "player"]
        page.click("#btnSend")
        page.wait_for_function("document.querySelectorAll('.me').length >= 4", timeout=60000)
        assert page.locator(".cut").count() >= 1, "the typed text must cut the line in"
        wait_idle(page)
        assert page.locator(".me").last.inner_text().startswith("Годі")
        assert page.input_value("#input") == "", "the typed text was sent, not kept"
        game.base_pace = 0.08
        shot(page, "05f-cut-in-by-typing")

        # turn 4: the small ✋ still interrupts
        stack.judge.rules[NEXT_TAG] = ["horst", "elza", "player"]
        page.fill("#input", "Мовчки дивлюсь на нього.")
        nh = page.locator(hsel).count()
        page.click("#btnSend")
        wait_new(page, hsel, nh, 4)
        box = page.locator("#btnInterrupt").bounding_box()
        assert box["width"] <= 48 and box["height"] <= 48, f"✋ is small: {box}"
        page.click("#btnInterrupt")
        wait_idle(page)
        assert page.locator(".cut").count() >= 2, "interrupted line must be marked"
        shot(page, "05g-interrupted")

        # ☰ drawer: the character's state, people (masked), skip, debug
        page.click("#btnMenu")
        page.wait_for_selector("#drawer[open]")
        chips = page.locator("#chips .chip").all_inner_texts()
        assert any("сталевий меч" in c for c in chips), chips
        page.wait_for_selector(f"#people [data-tok='{horst}']")
        people = page.inner_text("#people")
        assert "Горст" not in people and "horst" not in people, "people are masked"
        assert page.is_hidden("#placesSec"), "no places endpoint yet: no section"
        no_hscroll(page, "drawer")
        page.wait_for_timeout(300)  # the drawer's slide-in
        shot(page, "06-drawer")

        # debug view (from the drawer)
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
        page.click("#debugClose")
        assert page.is_hidden("#debugPanel")

        # reload: the same paragraphs, in the same inks
        before = page_signature(page)
        page.reload()
        page.wait_for_selector(".intro")
        wait_idle(page)
        page.wait_for_function("([t, c]) => getComputedStyle(document.documentElement)"
                               ".getPropertyValue('--ink-' + t).trim() === c", arg=[horst, ink_h])
        after = page_signature(page)
        assert page.locator(".me").count() == 5
        assert before == after, json.dumps([b for b, a in zip(before, after) if b != a] or
                                           [len(before), len(after)], ensure_ascii=False)[:2000]
        no_hscroll(page, "after reload")
        shot(page, "08-after-reload")

        # keyboard: focus is visible on the controls
        page.focus("#btnMenu")
        page.keyboard.press("Tab")
        outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        assert outline not in ("none", ""), outline

        # laptop: the same page, a wider column
        desk = browser.new_page(viewport={"width": 1280, "height": 800})
        desk.on("pageerror", lambda e: errors.append(str(e)))
        desk.goto(url)
        desk.wait_for_selector(".intro")
        desk.wait_for_timeout(300)
        shot(desk, "09-laptop")
        browser.close()

    server.should_exit = True
    assert not errors, errors
    print("OK: 5 turns (exchange + gesture, skip, cut in by typing, ✋), legend, ink recolour, "
          "suggestions, line menu rules, drawer, debug, reload signature; no console errors")


if __name__ == "__main__":
    main()
