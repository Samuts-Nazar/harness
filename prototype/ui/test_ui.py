"""Playwright-перевірка прототипу у мобільному в'ювпорті 390x844.
Запуск: nix-shell prototype/ui/shell.nix --run "python prototype/ui/test_ui.py"
"""
import pathlib
import sys
from playwright.sync_api import sync_playwright

HERE = pathlib.Path(__file__).parent.resolve()
SHOTS = HERE / "screenshots"
SHOTS.mkdir(exist_ok=True)
URL = (HERE / "index.html").as_uri() + "?pace=0.2"
errors = []


def shot(page, name):
    page.screenshot(path=str(SHOTS / f"{name}.png"))
    print("shot", name)


def wait_idle(page, timeout=60000):
    page.wait_for_selector("#dockIdle:not([hidden])", timeout=timeout)


def words(page, who, n):
    page.wait_for_function(
        f"document.querySelectorAll('.npc[data-who={who}] .w').length>={n}", timeout=60000)


def new_page(browser):
    ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                              is_mobile=True, has_touch=True, locale="uk-UA")
    page = ctx.new_page()
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(URL)
    return page


def no_hscroll(page, label):
    w = page.evaluate("[document.documentElement.scrollWidth, document.body.scrollWidth, document.querySelector('#story').scrollWidth, document.querySelector('#story').clientWidth]")
    assert w[0] <= 390 and w[1] <= 390 and w[2] <= w[3], f"horizontal scroll at {label}: {w}"


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # --- 1/2/4/5: стрімінг, NPC говорить, реакції, перебивання кнопкою ---
        page = new_page(browser)
        page.wait_for_selector(".narr .w:nth-child(8)")
        shot(page, "01-narration-streaming")
        words(page, "horst", 16)
        page.wait_for_selector("#dockSpeak:not([hidden])")
        shot(page, "02-npc-speaking-reactions-interrupt")
        page.click("[data-react=nod]")
        page.click("[data-react=hand]")
        assert page.locator(".react").count() == 2
        shot(page, "03-quick-reactions")
        words(page, "horst", 24)
        page.click("#btnInterrupt")
        wait_idle(page)
        assert page.locator(".npc[data-who=elza]").count() == 0, "після переривання Ельза не мала говорити"
        assert page.locator(".cutmark").count() == 1
        shot(page, "04-interrupt-button")
        no_hscroll(page, "interrupt")

        # debug-журнал
        page.click("#btnDebug")
        page.wait_for_selector("#logList .le")
        shot(page, "05-debug-log")
        assert "Відкат" in page.inner_text("#logList")
        page.click("#btnDebug")
        browser_ctx_close(page)

        # --- 2b: ретроактивне переривання ---
        page = new_page(browser)
        wait_idle(page)
        shot(page, "06-idle-last-utterance-footer")
        page.click("#btnCut")
        page.wait_for_selector(".cuttable")
        shot(page, "07-retro-cut-mode")
        target = page.locator(".npc[data-who=elza] .w", has_text="знаю").first
        target.click()
        page.wait_for_selector("#cutOk")
        shot(page, "08-retro-cut-confirm")
        n_before = page.locator(".npc[data-who=elza] .w").count()
        page.click("#cutOk")
        page.wait_for_selector(".gone")
        page.wait_for_timeout(300)
        shot(page, "09-retro-cut-greying")
        page.wait_for_selector(".gone", state="detached", timeout=10000)
        n_after = page.locator(".npc[data-who=elza] .w").count()
        assert n_after < n_before, (n_before, n_after)
        wait_idle(page)
        assert page.locator("#btnCut").count() == 0
        shot(page, "10-retro-cut-done")

        # --- 3: панель персонажа: кнопка та свайп ---
        page.click("#btnChar")
        page.wait_for_timeout(400)
        shot(page, "11-character-panel")
        assert page.locator(".card").count() == 6
        page.click("#charClose")
        page.wait_for_timeout(400)
        page.mouse.move(330, 400)
        page.mouse.down()
        page.mouse.move(200, 405, steps=6)
        page.mouse.up()
        page.wait_for_timeout(400)
        assert "open" in page.get_attribute("#charPanel", "class"), "свайп не відкрив панель"
        shot(page, "12-character-panel-swipe")
        page.evaluate("document.querySelector('#charPanel').scrollTop=600")
        page.wait_for_timeout(200)
        shot(page, "13-character-panel-scrolled")
        page.click("#charClose")
        page.wait_for_timeout(400)

        # --- 5: натискні імена та предмети ---
        page.locator(".narr .ent", has_text="Горст").first.click()
        page.wait_for_selector("#menu:not([hidden])")
        shot(page, "14-entity-menu-person")
        page.click("#menu button:has-text('Придивитись')")
        assert "Горста" in page.input_value("#fAct")
        page.locator(".narr .ent", has_text="Меч").first.click()
        shot(page, "15-entity-menu-item")
        page.click("#menu button:has-text('Оглянути')")
        shot(page, "16-entity-action-in-input")

        # --- 6: помічник ходу ---
        page.click("#btnAssist")
        page.wait_for_selector(".skel")
        shot(page, "17-assistant-loading")
        page.wait_for_selector(".opt")
        shot(page, "18-assistant-options")
        page.locator(".opt").first.click()
        page.wait_for_selector("#draftTools:not([hidden])")
        assert "Горсту" in page.input_value("#fAct")
        shot(page, "19-draft-in-input")
        page.click("#lockAct")
        page.click("#btnDislike")
        page.fill("#fbText", "надто різко")
        shot(page, "20-dislike-feedback")
        page.click("#fbSend")
        assert "Відсуваю кухоль" in page.input_value("#fAct"), "зафіксована дія мала лишитись дослівно"
        page.click("#btnModify")
        page.fill("#fbText", "м’якше")
        page.click("#fbSend")
        shot(page, "21-draft-modified-locked-part-kept")
        page.click("#btnOwn")
        assert page.input_value("#fAct") == ""
        page.fill("#fAct", "Мовчки роблю ковток пива.")
        page.fill("#fSay", "Розкажіть про греблю.")
        shot(page, "22-own-option")
        page.click("#btnSend")
        page.wait_for_selector(".me")
        wait_idle(page)
        shot(page, "23-turn-sent-world-reply")
        no_hscroll(page, "reply")

        # --- 7: помилка моделі ---
        page.click("#btnModelErr")
        page.wait_for_timeout(400)
        assert page.is_disabled("#errSend")
        shot(page, "24-model-error-sheet-empty")
        page.fill("#errText", "Горст не міг знати про греблю.")
        page.wait_for_timeout(100)
        shot(page, "25-model-error-sheet-filled")
        page.click("#errSend")
        page.wait_for_selector(".badge")
        wait_idle(page)
        assert page.locator(".me").count() == 1, "хід гравця мав лишитись"
        shot(page, "26-regenerated")

        # --- 8: завіса, пропуск ---
        page.click("#btnVeil")
        shot(page, "27-veil-armed")
        page.fill("#fAct", "Іду до виходу.")
        page.click("#btnSend")
        page.wait_for_selector(".sysnote.veil")
        wait_idle(page)
        shot(page, "28-veil-result")
        page.fill("#fAct", "Чекаю.")
        page.click("#btnSend")
        words(page, "horst", 6) if False else page.wait_for_selector("#dockNarr:not([hidden]), #dockSpeak:not([hidden])")
        page.click("#btnSkip")
        page.wait_for_selector(".sysnote:not(.veil)")
        wait_idle(page)
        shot(page, "29-skip")
        page.click("#btnPause")
        page.wait_for_selector("#pauseOv:not([hidden])")
        shot(page, "30-pause")
        page.click("#btnResume")
        page.click("#btnDebug")
        shot(page, "31-debug-log-after-play")
        no_hscroll(page, "end")
        browser.close()

    real = [e for e in errors if "favicon" not in e]
    print("console/page errors:", real)
    if real:
        sys.exit(1)
    print("ALL OK")


def browser_ctx_close(page):
    page.context.close()


if __name__ == "__main__":
    main()
