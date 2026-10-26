#!/usr/bin/env python3
"""Click through the design preview.

Not part of make test. Needs Chrome and the Playwright Python package, and a
local server at the repo root:

    python3 -m http.server 8765 --bind 127.0.0.1
    python3 app/v2-concept/check_preview.py
"""

from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8765/app/v2-concept/index.html"
ERRORS: list[str] = []


def check(cond: bool, msg: str) -> None:
    if cond:
        print("ok", msg)
    else:
        ERRORS.append(msg)
        print("FAIL", msg)


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(BASE + "?theme=light", wait_until="domcontentloaded")
        page.wait_for_function("() => document.documentElement.dataset.ready === '1'")
        dur = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        check(dur == "200ms", f"default duration {dur}")
        check("Find the trade" in page.locator("#homeTitle").inner_text(), "home headline")
        check("Puka Nacua" in page.locator("#peekName").inner_text(), "peek names Puka")
        box = page.locator("#homeTitle").bounding_box()
        check(box is not None and box["y"] < 180, f"home title y={None if not box else round(box['y'])}")

        page.locator(".tabbar [data-go='targets']").click()
        page.wait_for_function("() => location.hash === '#targets'")
        check("split on Puka" in page.locator("#targetsTitle").inner_text(), "targets headline")
        check(page.locator("#targetList .player").count() >= 5, "buy list has several players")
        page.locator("#sideSell").click()
        check("Chris Olave" in page.locator("#targetsTitle").inner_text(), "sell headline")
        first = page.locator("#targetList .player").first
        first.locator("button").click()
        check("is-open" in (first.get_attribute("class") or ""), "card opens")
        check("FantasyCalc" in first.inner_text(), "expanded charts")
        first.locator("button").click()
        check("is-open" not in (first.get_attribute("class") or ""), "card closes")

        page.locator(".tabbar [data-go='compare']").click()
        page.wait_for_function("() => location.hash === '#compare'")
        title = page.locator("#compareTitle").inner_text()
        check("Close for the charts" in title, f"compare title: {title}")
        check(page.locator("#whyBtn").is_visible(), "show charts control visible without scrolling the button off")
        page.locator("#whyBtn").click()
        check(page.locator("#whyBtn").get_attribute("aria-expanded") == "true", "why expanded")
        check("FantasyCalc" in page.locator("#whyInner").inner_text(), "why shows charts")

        page.locator("[data-pick='get']").click()
        page.locator("#pickerSearch").fill("Gibbs")
        page.locator(".pick", has_text="Jahmyr Gibbs").click()
        check("Gibbs" in page.locator("[data-pick='get']").inner_text(), "swapped in Gibbs")
        check(page.locator("#compareTitle").inner_text() == "You come out ahead.", "verdict updates")

        page.locator("#clearTrade").click()
        check("Add a player" in page.locator("#compareTitle").inner_text(), "cleared trade")
        page.locator("#themeBtn").click()
        check(page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "dark", "dark theme")
        page.locator(".tabbar [data-go='more']").click()
        check("The desk" in page.locator("#moreSheet").inner_text(), "desk group")
        page.keyboard.press("Escape")

        page.emulate_media(reduced_motion="reduce")
        reduced = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        check(reduced == "0ms", f"reduced motion dur={reduced}")

        desk = browser.new_page(viewport={"width": 1280, "height": 800})
        desk.goto(BASE + "?theme=light&view=home&shot=1", wait_until="domcontentloaded")
        desk.wait_for_function("() => document.documentElement.dataset.ready === '1'")
        check(desk.locator(".topnav").is_visible(), "desktop nav")
        check(not desk.locator(".tabbar").is_visible(), "tab bar hidden on desktop")
        y = desk.locator("#homeTitle").bounding_box()["y"]
        check(y < 400, f"desktop title y={round(y)}")
        browser.close()

    if ERRORS:
        print(f"{len(ERRORS)} failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
