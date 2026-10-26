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
BANNED = (
    "FantasyCalc",
    "FantasyPros",
    "USA Today",
    "fixture_reindexed",
    "full_12",
    "we support",
    "Connect your",
    "sync with",
    "7 bench",
    "2 RB",
)


def check(cond: bool, msg: str) -> None:
    if cond:
        print("ok", msg)
    else:
        ERRORS.append(msg)
        print("FAIL", msg)


def words(text: str) -> int:
    return len(text.replace(".", "").split())


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        page = browser.new_page(viewport={"width": 390, "height": 844})
        page.goto(BASE + "?theme=light", wait_until="domcontentloaded")
        page.wait_for_function("() => document.documentElement.dataset.ready === '1'")

        dur = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        check(dur == "200ms", f"default duration {dur}")
        check(
            page.locator("#heroMicro").inner_text() == "Free · No sign-up · Nothing to connect · Saved on this device",
            "hero micro-line",
        )
        check(
            page.locator("#homeTitle").inner_text() == "Know who to trade for, before your league does.",
            "positioning line",
        )
        check(page.locator(".btn", has_text="Paste my league").is_visible(), "paste CTA")
        box = page.locator("#homeTitle").bounding_box()
        check(box is not None and box["y"] < 220, f"home title y={None if not box else round(box['y'])}")
        check("Buy Puka Nacua" in page.locator("#peekName").inner_text(), "peek is a buy")
        check("DDF Projected Value is ahead of the Market." in page.locator("#peekBlurb").inner_text(), "peek why")

        page.evaluate("() => document.fonts.ready")
        page.locator(".btn", has_text="Paste my league").click()
        page.wait_for_function("() => location.hash === '#paste'")
        check(page.locator("#pasteTip").inner_text().startswith("Pick where you copy"), "tip waits for a source")
        page.locator("[data-from='sleeper']").click()
        check("One team per page" in page.locator("#pasteTip").inner_text(), "sleeper tip")
        page.locator("[data-from='espn']").click()
        check("League, then Rosters" in page.locator("#pasteTip").inner_text(), "espn tip")
        page.locator("[data-from='yahoo']").click()
        check("rosters page" in page.locator("#pasteTip").inner_text(), "yahoo tip")
        page.locator("[data-from='other']").click()
        check("any player list" in page.locator("#pasteTip").inner_text(), "other tip")
        page.locator("[data-from='sleeper']").click()
        page.locator("#pasteBox").fill("Puka Nacua\nJaxon Smith-Njigba")
        page.locator("#addTeam").click()
        check(page.locator("#pasteCount").inner_text() == "1 team pasted", "running count")
        page.locator("#thatsAll").click()
        check(
            page.locator("#matchTitle").inner_text() == "Got it: 12 teams, 186 players",
            "match line",
        )
        page.locator("[data-team='The Sharp Friends']").click()
        check(page.locator("#toast").is_visible(), "toast shows")
        check(
            "Saved on this device. Bookmark this page or tap Export" in page.locator("#toastText").inner_text(),
            "toast copy",
        )
        check(page.locator("#toastExport").is_visible() and page.locator("#toastCopy").is_visible(), "toast actions")
        check(page.locator("#leagueBtn").inner_text() == "The Sharp Friends", "team remembered in the header")
        check(
            page.evaluate("() => localStorage.getItem('ddf-concept-team')") == "The Sharp Friends",
            "team stored on this device",
        )

        page.locator(".tabbar [data-go='settings']").click()
        page.wait_for_function("() => location.hash === '#settings'")
        check(page.locator("#dataLine").inner_text() == "Your data: saved on this device.", "settings data line")
        for label in ("Export", "Import", "Copy link"):
            check(page.locator("#dataActions").get_by_role("button", name=label).is_visible(), f"settings {label}")
        check("DDF Charted Value" in page.locator("#settings").inner_text(), "settings explains charted value")
        check("DDF Projected Value" in page.locator("#settings").inner_text(), "settings explains projected value")
        check("the Market" in page.locator("#settings").inner_text() or "The Market" in page.locator("#settings").inner_text(), "settings explains the Market")

        page.locator(".tabbar [data-go='targets']").click()
        page.wait_for_function("() => location.hash === '#targets'")
        title = page.locator("#targetsTitle").inner_text()
        check(title == "Buy Puka Nacua", f"buy headline: {title}")
        check(words(title) <= 6, f"buy headline length {words(title)}")
        check(page.locator("#targetsSub").inner_text() == "DDF Projected Value is ahead of the Market.", "buy why")
        check(page.locator("#targetList .player").count() >= 5, "buy list has several players")
        first = page.locator("#targetList .player").first
        first.locator(".player-sum").click()
        check("is-open" in (first.get_attribute("class") or ""), "card opens")
        opened = first.inner_text()
        check("DDF Projected Value" in opened and "The Market" in opened, "open card shows the two terms")
        check("FantasyCalc" not in opened, "open card does not name a chart")
        first.locator(".player-sum").click()
        page.locator("#sideSell").click()
        sell = page.locator("#targetsTitle").inner_text()
        check(sell == "Sell Chris Olave", f"sell headline: {sell}")
        check(page.locator("#targetsSub").inner_text() == "The Market is ahead of DDF Projected Value.", "sell why")

        page.locator(".tabbar [data-go='compare']").click()
        page.wait_for_function("() => location.hash === '#compare'")
        verdict = page.locator("#compareTitle").inner_text()
        check(verdict == "Don't do it", f"verdict: {verdict}")
        check(words(verdict) <= 6, "verdict is at most six words")
        why = page.locator("#compareSub").inner_text()
        check(
            why == "You give up 6.1 DDF Charted Value. Their lineup improves on the Market, so they'll likely accept.",
            f"viability line: {why}",
        )
        check(page.locator("#compareStamp").is_visible(), "stamp visible")
        page.wait_for_function("() => (document.querySelector('#readings').innerText || '').includes('10.7')")
        readings = page.locator("#readings").inner_text()
        check("The DDF read" in readings and "Same method, two inputs" in readings, "DDF group")
        check("DDF Charted Value" in readings and "6.1" in readings and "What you give up" in readings, "chart side")
        check("DDF Projected Value" in readings and "10.7" in readings, "projection side")
        check("3.9" in readings and "42.7" in readings, "point sizes")
        check("same thing as DDF Charted Value" in readings, "points agree with charted value")
        check("The Market" in readings and "6.1" in readings and "Whether they'll accept" in readings, "Market reading")
        check("The other team's read." in readings, "Market is the other read")
        chart_tip = page.locator("#readings .read-ddf .tip-btn").first
        chart_tip.click()
        check("starting from the trade charts" in page.locator(".tip-pop:visible").inner_text(), "charted tip")
        page.keyboard.press("Escape")
        check(page.locator(".tip-pop:visible").count() == 0, "escape closes the tip")
        proj_tip = page.locator("#readings .read-ddf .tip-btn").nth(1)
        proj_tip.focus()
        page.keyboard.press("Enter")
        check("rest-of-season projections" in page.locator(".tip-pop:visible").inner_text(), "projected tip from keyboard")
        page.keyboard.press("Escape")
        page.locator("#readings .read-market .tip-btn").click()
        check("before our adjustments" in page.locator(".tip-pop:visible").inner_text(), "market tip")
        page.keyboard.press("Escape")
        check(page.locator("#whyBtn").is_visible(), "show the math is on the first screen")
        check(page.locator("#whyBtn").inner_text() == "Show the math", "math control label")
        page.locator("#whyBtn").click()
        check(page.locator("#whyBtn").get_attribute("aria-expanded") == "true", "math expanded")
        math = page.locator("#whyInner").inner_text()
        check("DDF Charted Value" in math and "DDF Projected Value" in math and "The Market" in math, "math uses the value terms")
        check("ESPN" in math and "CBS, rest of season" in math and "Razzball" in math, "projection breakdown names the reads")
        check("21.7" in math and "17.8" in math, "projection breakdown has the weekly rates")
        check("one-for-one" in math, "lineup stand-in is named")
        check("one projection source" in math and "their side" in math, "stand-ins are named")
        page.locator("#shareBtn").click()
        check(page.locator("#shareCard").is_visible(), "share card")
        check("Don't do it" in page.locator(".share-title").inner_text(), "share card headline")

        page.locator("[data-pick='get']").click()
        page.locator("#pickerSearch").fill("Gibbs")
        page.locator(".pick", has_text="Jahmyr Gibbs").click()
        passed = page.locator("#compareTitle").inner_text()
        check(passed == "They'll pass", f"other side judges on the Market: {passed}")
        check("does not improve on the Market" in page.locator("#compareSub").inner_text(), "pass why")
        check("same thing as DDF Charted Value" in page.locator("#readings").inner_text(), "both inputs can agree")

        page.locator("#clearTrade").click()
        check(page.locator("#compareTitle").inner_text() == "Add a player to each side.", "cleared trade")
        check(words(page.locator("#compareTitle").inner_text()) <= 6, "empty headline length")

        whole = page.evaluate("() => document.body.textContent")
        for banned in BANNED:
            check(banned not in whole, f"no {banned}")

        page.locator("#themeBtn").click()
        check(page.evaluate("() => document.documentElement.getAttribute('data-theme')") == "dark", "dark theme")

        page.emulate_media(reduced_motion="reduce")
        reduced = page.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        check(reduced == "0ms", f"reduced motion dur={reduced}")
        confetti_display = page.evaluate(
            "() => { const el = document.querySelector('.confetti'); el.hidden = false; return getComputedStyle(el).display; }"
        )
        check(confetti_display == "none", f"confetti hidden when reduced ({confetti_display})")

        desk = browser.new_page(viewport={"width": 1280, "height": 900})
        desk.goto(BASE + "?theme=light", wait_until="domcontentloaded")
        desk.wait_for_function("() => document.documentElement.dataset.ready === '1'")
        check(desk.locator(".topnav").is_visible(), "desktop nav")
        check(not desk.locator(".tabbar").is_visible(), "phone tab bar hidden on desktop")
        check(desk.locator(".topnav").inner_text().find("Buy & sell") >= 0, "desktop buy and sell")
        check("Check a trade" in desk.locator(".topnav").inner_text(), "desktop check a trade")
        dbox = desk.locator("#homeTitle").bounding_box()
        check(dbox is not None and dbox["y"] < 420, f"desktop title y={None if not dbox else round(dbox['y'])}")

        shot = browser.new_page(viewport={"width": 390, "height": 844})
        shot.goto(BASE + "?theme=light&shot=1&view=compare", wait_until="domcontentloaded")
        shot.wait_for_function("() => document.documentElement.dataset.ready === '1'")
        check(shot.locator("#compareTitle").inner_text() == "Don't do it", "shot verdict settled")
        check(shot.locator("#compareStamp").is_visible(), "shot stamp settled")
        hidden = shot.evaluate(
            "() => { const el = document.querySelector('.confetti'); el.hidden = false; return getComputedStyle(el).display === 'none'; }"
        )
        check(hidden, "shot suppresses confetti")
        shot_dur = shot.evaluate("() => getComputedStyle(document.documentElement).getPropertyValue('--dur').trim()")
        check(shot_dur == "0ms", f"shot duration {shot_dur}")

        browser.close()

    if ERRORS:
        print(f"{len(ERRORS)} failed")
        return 1
    print("all checks passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
