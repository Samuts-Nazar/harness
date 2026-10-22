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
from app import newgame  # noqa: E402
from app.campaigns import open_campaign  # noqa: E402
from app.game import Game  # noqa: E402
from app.inks import PALETTE  # noqa: E402
from app.server import create_app  # noqa: E402
from app.stacks import fake_stack  # noqa: E402

SHOTS = pathlib.Path(__file__).resolve().parents[1] / "screenshots"
SHOTS.mkdir(exist_ok=True)
errors: list[str] = []

SAY = "p[data-line=say]"
EXAMPLE = (pathlib.Path(__file__).resolve().parents[2] / "docs" / "game_package_example.yaml"
           ).read_text(encoding="utf-8")
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


def sheet_items(page, sel, i, rates=False):
    """Open the line menu on the i-th paragraph matching `sel` with a right click (desktop) and
    return the actions it offers (the rating items only with `rates`); close it again."""
    page.locator(sel).nth(i).click(button="right")
    page.wait_for_selector("#sheet[open]")
    acts = page.eval_on_selector_all("#sheet [data-act]", "ns => ns.map(n => n.dataset.act)")
    page.keyboard.press("Escape")
    page.wait_for_selector("#sheet:not([open])", state="attached")
    return acts if rates else [a for a in acts if not a.startswith("rate")]


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
    root = tempfile.mkdtemp()
    game = Game(newgame.opener(stack, root=root,
                               fallback=lambda new: open_campaign(stack, root=root, new=new)),
                pace=0.08, open_package=lambda pkg: newgame.open_package(
                    stack, pkg, root=root, canon_db=False))
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
        assert page.locator(f"{hsel} .who").first.is_visible(), "speaker names are on by default"
        assert page.text_content(f"{hsel} .who").strip().rstrip(":"), "the label has a name"
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
        # speaker names (default on): a label on every NPC speech paragraph and every gesture
        for kind in (SAY, ACT):
            n = page.locator(kind).count()
            assert n and page.locator(f"{kind} .who:visible").count() == n, f"every {kind} line is named"
        assert page.locator(".me .who, .narr .who, .intro .who").count() == 0, "player and narration unnamed"
        no_hscroll(page, "after the exchange")
        shot(page, "05b-exchange-with-gesture")

        # line menu: the last NPC line versus an old line, versus a gesture (the server offers
        # model error and the retroactive cut: state.actions)
        assert page.evaluate("actions") == ["model_error", "cut"]
        last_e = page.locator(esel).count() - 1
        got = sheet_items(page, esel, last_e)
        assert got == ["challenge", "model_error", "cut", "ink"], got
        long_press(page, esel, last_e)
        page.wait_for_selector("#sheet[open]")
        page.wait_for_timeout(250)  # the sheet's rise
        shot(page, "05c-line-menu-last-line")
        page.keyboard.press("Escape")
        assert sheet_items(page, hsel, 0) == ["challenge", "ink"], "old line: no cut, no rewrite"
        assert sheet_items(page, f"{ACT}[data-tok='{horst}']", 0) == ["ink"]
        # the live gesture carries its event id (the last gesture of a story can be rewritten)
        assert page.locator(f"{ACT}[data-tok='{horst}']").first.get_attribute("data-event"), \
            "a gesture knows its event"

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

        # ratings: 👍/👎 on world lines only; 👎 asks for an optional note; one rating per line
        assert sheet_items(page, hsel, 0, True)[-2:] == ["rate_up", "rate_down"]
        assert sheet_items(page, ".narr", 0, True)[-2:] == ["rate_up", "rate_down"]
        assert sheet_items(page, ACT, 0, True)[-2:] == ["rate_up", "rate_down"]
        page.locator(".narr").first.click(button="right")
        page.click("#sheet [data-act=rate_up]")
        page.wait_for_selector(".narr[data-rating=up] .rmark")
        page.locator(hsel).first.click(button="right")
        page.wait_for_selector("#sheet[open]")
        assert "Добре написано" in page.inner_text("#sheet [data-act=rate_up]")
        shot(page, "05d2-rating-in-the-menu")
        page.click("#sheet [data-act=rate_down]")
        page.wait_for_selector(f"{hsel} .askbox textarea")
        assert page.get_attribute(f"{hsel} .askbox textarea", "placeholder") == \
            "Що не так? (можна пропустити)"
        assert page.inner_text(f"{hsel} .askbox .btn.ghost") == "Пропустити"
        no_hscroll(page, "rating note box")
        shot(page, "05d3-rating-note")
        page.fill(f"{hsel} .askbox textarea", "Надто гладко, як з газети.")
        page.click(f"{hsel} .askbox .btn.primary")
        page.wait_for_selector(f"{hsel}[data-rating=down] .rmark")
        assert page.locator(f"{hsel} .askbox").count() == 0
        assert page.inner_text(f"{hsel}[data-rating=down] .rmark").strip() == "👎"
        mark_h = page.evaluate("(s) => { const p = document.querySelector(s); "
                               "return p.getBoundingClientRect().height }", f"{hsel}[data-rating=down]")
        # rating again replaces: up, then down (skipping the note) on the narration
        page.locator(".narr").first.click(button="right")
        page.click("#sheet [data-act=rate_down]")
        page.click(".narr .askbox .btn.ghost")
        page.wait_for_selector(".narr[data-rating=down] .rmark")
        assert page.locator(".narr .rmark").count() == 1, "one mark per line"
        rated = page.evaluate("fetch('/api/ratings').then(r => r.json())")
        assert sorted(rated.values()) == ["down", "down"], rated
        no_hscroll(page, "rated lines")
        shot(page, "05d4-rated-lines")

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
        assert page.is_visible("#placesNone"), "no places on this map: the drawer says so"
        assert "немає позначених" in page.inner_text("#placesNone")
        no_hscroll(page, "drawer")
        page.wait_for_timeout(300)  # the drawer's slide-in
        shot(page, "06-drawer")

        # speaker names switch: off hides every label (past lines too), the choice survives a reload
        assert page.get_attribute("#btnNames", "aria-pressed") == "true"
        page.click("#btnNames")
        assert page.get_attribute("#btnNames", "aria-pressed") == "false"
        assert page.locator(".who").count() > 0 and page.locator(".who:visible").count() == 0, "all labels hidden"
        no_hscroll(page, "names off")
        page.click("#btnNames")
        assert page.locator(".who:visible").count() == page.locator(".who").count(), "back on: all shown"
        page.click("#btnNames")  # off again for the reload check below

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

        # reload: the same paragraphs, in the same inks, names still off
        before = page_signature(page)
        page.reload()
        page.wait_for_selector(".intro")
        wait_idle(page)
        page.wait_for_function("([t, c]) => getComputedStyle(document.documentElement)"
                               ".getPropertyValue('--ink-' + t).trim() === c", arg=[horst, ink_h])
        after = page_signature(page)
        assert page.locator(".me").count() == 5
        page.wait_for_function("document.querySelectorAll('.rmark').length === 2", timeout=10000)
        assert page.locator("[data-rating=down]").count() == 2, "the rating marks survive a reload"
        after = page_signature(page)
        assert before == after, json.dumps([b for b, a in zip(before, after) if b != a] or
                                           [len(before), len(after)], ensure_ascii=False)[:2000]
        assert page.locator(".who").count() > 0 and page.locator(".who:visible").count() == 0, "names stay off"
        page.click("#btnMenu")
        page.wait_for_selector("#drawer[open]")
        assert page.get_attribute("#btnNames", "aria-pressed") == "false"
        page.click("#btnNames")  # on again
        assert page.locator(".who:visible").count() == page.locator(".who").count()
        page.keyboard.press("Escape")
        no_hscroll(page, "after reload")
        shot(page, "08-after-reload")

        # keyboard: focus is visible on the controls
        page.focus("#btnMenu")
        page.keyboard.press("Tab")
        outline = page.evaluate("getComputedStyle(document.activeElement).outlineStyle")
        assert outline not in ("none", ""), outline

        # "Нова гра з файлу": a bad file gives field + fix; the example gives the summary card;
        # start; the first narration of the new game
        page.click("#btnMenu")
        page.click("#btnNewGame")
        page.wait_for_selector("#newGame:not([hidden])")
        assert not page.locator("#drawer").evaluate("d => d.open")
        page.fill("#pkgText", "version: 2\nworld: witcher\n")
        page.click("#pkgCheck")
        page.wait_for_selector(".ng-err")
        errs = page.inner_text("#pkgResult")
        assert "version" in errs and "Як виправити" in errs and "player" in errs, errs
        no_hscroll(page, "package errors")
        shot(page, "10-newgame-errors")
        page.fill("#pkgText", EXAMPLE)
        page.click("#pkgCheck")
        page.wait_for_selector(".ng-card h3")
        card = page.inner_text("#pkgResult")
        for needle in ("Задано у файлі", "Вереска", "Вирішить світ", "Межі", "ринок"):
            assert needle in card, needle
        no_hscroll(page, "package summary")
        shot(page, "11-newgame-summary")
        page.click("#pkgStart")
        page.wait_for_selector("#newGame", state="hidden")
        page.wait_for_function("() => { const i = document.querySelector('.intro'); "
                               "return i && i.textContent.startsWith('Ранок третього дня') }")
        wait_idle(page)
        assert page.locator(".me").count() == 0
        assert "ринок" in page.inner_text("#sceneTitle")
        npc_before = page.locator(SAY).count()
        page.fill("#input", "*показую торговці гребінець* Ви знаєте цього хлопця?")
        page.click("#btnSend")
        page.wait_for_function("() => document.querySelectorAll('.narr, p[data-line=say]')"
                               ".length > 0", timeout=30000)
        wait_idle(page)
        assert page.locator(".narr").count() + page.locator(SAY).count() > npc_before
        no_hscroll(page, "package game")
        shot(page, "12-newgame-first-turn")

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
          "suggestions, line menu rules, drawer, debug, reload signature, new game from a file "
          "(errors, summary, start, first turn); no console errors")


if __name__ == "__main__":
    main()
