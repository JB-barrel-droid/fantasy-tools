"""Player values chart on phones: Full screen pop-out and touch-to-inspect, rendered.

Loads the built Player values tab headless with touch emulation at 320, 360 and
390 px wide (portrait) and 844 x 390 (a phone turned sideways), plus 1440 px as
the desktop control. Every value reads the engine back (TradeValueV2.chart()), so
a card that looks right but names the wrong player fails:

  * the "Full screen" button in the chart head is at least 44 x 44 px on phones
    and not shown on a desktop screen;
  * it opens the chart in a full-viewport dialog (focus on Close, page scroll
    locked, no sideways overflow); Close and Escape shut it and focus returns
    to the Full screen button;
  * portrait: a "rotate to landscape" prompt shows, Dismiss hides it and it stays
    hidden on the next open; sideways: no prompt;
  * touch: a tap on a point shows that player's card (the engine's row at that
    x); a drag moves the card with the finger and opens nothing; a second tap
    on the player still shown opens the details; the full-screen chart takes
    touches itself (touch-action none) while the inline chart leaves vertical
    scroll to the page (pan-y);
  * arrow keys on the focused chart still announce the player (a11y kept);
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js / v2.css with one
fault each (touch handlers gone, a first tap opens the details, the prompt cannot
be dismissed, focus not returned, no scroll lock, the button missing on a sideways
phone, full-screen chart lets the page scroll, the prompt shows sideways) and requires each to fail.
"""
from __future__ import annotations

import functools
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests.test_v2_expand_render import _built_dist, _serve  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"

PHONES = ((320, 640), (360, 740), (390, 844), (844, 390))

STATE = """() => { const V2 = window.TradeValueV2, ch = V2.chart(), box = document.getElementById('v2Chart').getBoundingClientRect();
  const tip = document.getElementById('v2Tip'), btn = document.getElementById('v2FullScreen'), b = btn.getBoundingClientRect();
  const x = document.getElementById('v2Expand').querySelector('.v2-expand-box').getBoundingClientRect();
  return {n: ch.slice.length, names: ch.slice.map(r => r.name), px: ch.slice.map((r, i) => box.left + ch.x(i) * box.width / ch.width),
    py: box.top + box.height / 2, tipShown: !tip.hidden, tipName: tip.hidden ? null : (tip.querySelector('h3') || {}).textContent,
    tipHint: tip.hidden ? null : (tip.querySelector('.v2-meta:last-child') || {}).textContent,
    drawer: !document.getElementById('v2Drawer').hidden, expanded: V2.expanded(),
    btn: {display: getComputedStyle(btn).display, w: b.width, h: b.height},
    boxW: x.width, boxH: x.height, innerW: innerWidth, innerH: innerHeight, overflow: document.documentElement.scrollWidth - innerWidth,
    bodyOverflow: getComputedStyle(document.body).overflow, active: document.activeElement ? document.activeElement.id : '',
    hint: !document.getElementById('v2RotateHint').hidden, touchAction: getComputedStyle(document.getElementById('v2Chart')).touchAction,
    say: (document.getElementById('v2ChartSay') || {}).textContent || ''}; }"""


def _settle(page, ms=250):
    page.wait_for_timeout(ms)


def _cdp(page, client, kind, x=None, y=None):
    points = [] if x is None else [{"x": x, "y": y}]
    client.send("Input.dispatchTouchEvent", {"type": kind, "touchPoints": points})


def _close_all(page):
    page.keyboard.press("Escape")
    _settle(page)
    if page.evaluate("() => window.TradeValueV2.expanded()"):
        page.click("#v2ExpandClose")
        _settle(page)
    if page.evaluate("() => !document.getElementById('v2Drawer').hidden"):
        page.keyboard.press("Escape")
        _settle(page)


def check_phone(page, client, tag, width, height) -> list[str]:
    errors = []
    page.select_option("#v2Show", "100")
    _settle(page)
    page.evaluate("() => document.getElementById('v2FullScreen').scrollIntoView({block: 'center'})")
    _settle(page, 100)
    inline = page.evaluate(STATE)
    if inline["btn"]["display"] == "none" or inline["btn"]["w"] < 44 or inline["btn"]["h"] < 44:
        return errors + [tag + f"Full screen button not a 44 px target on a phone: {inline['btn']}"]
    if inline["touchAction"] != "pan-y":
        errors.append(tag + f"inline chart touch-action is {inline['touchAction']!r}, want pan-y (page keeps vertical scroll)")
    page.click("#v2FullScreen")
    _settle(page, 400)
    s = page.evaluate(STATE)
    if s["expanded"] != "chart":
        return errors + [tag + f"Full screen did not open the chart ({s['expanded']})"]
    if s["active"] != "v2ExpandClose":
        errors.append(tag + f"focus on {s['active']!r}, want the Close button")
    if s["boxW"] < s["innerW"] - 1 or s["boxH"] < s["innerH"] - 1:
        errors.append(tag + f"not full viewport ({s['boxW']:.0f} x {s['boxH']:.0f} in {s['innerW']} x {s['innerH']})")
    if s["overflow"] > 0:
        errors.append(tag + f"sideways overflow {s['overflow']}px")
    if s["bodyOverflow"] != "hidden":
        errors.append(tag + f"page scroll not locked (body overflow {s['bodyOverflow']!r})")
    if s["touchAction"] != "none":
        errors.append(tag + f"full-screen chart touch-action is {s['touchAction']!r}, want none")
    portrait = height > width
    if s["hint"] != portrait:
        errors.append(tag + f"rotate prompt shown={s['hint']} but portrait={portrait}")
    if portrait:
        page.click("#v2RotateDismiss")
        _settle(page)
        if page.evaluate(STATE)["hint"]:
            errors.append(tag + "Dismiss did not hide the rotate prompt")
    # Touch-to-inspect against the engine's rows.
    s = page.evaluate(STATE)
    i, j = 15, min(40, s["n"] - 1)
    page.touchscreen.tap(s["px"][i], s["py"])
    _settle(page)
    t = page.evaluate(STATE)
    if not t["tipShown"] or t["tipName"] != s["names"][i]:
        errors.append(tag + f"tap at point {i}: card shows {t['tipName']!r}, engine row is {s['names'][i]!r}")
    if t["drawer"]:
        errors.append(tag + "the first tap opened the details instead of inspecting")
    if t["tipHint"] and "Tap again" not in t["tipHint"]:
        errors.append(tag + f"card hint {t['tipHint']!r} does not say how to open the details by touch")
    _cdp(page, client, "touchStart", s["px"][i], s["py"])
    for step in range(1, 6):
        _cdp(page, client, "touchMove", s["px"][i] + (s["px"][j] - s["px"][i]) * step / 5, s["py"])
    _cdp(page, client, "touchEnd")
    _settle(page)
    d = page.evaluate(STATE)
    if d["tipName"] != s["names"][j]:
        errors.append(tag + f"drag to point {j}: card shows {d['tipName']!r}, engine row is {s['names'][j]!r}")
    if d["drawer"]:
        errors.append(tag + "a drag opened the details")
    _settle(page, 700)   # a person's second tap; Chrome's touch emulation drops a tap that follows a drag within ~300 ms
    page.touchscreen.tap(s["px"][j], s["py"])
    _settle(page, 400)
    if not page.evaluate(STATE)["drawer"]:
        errors.append(tag + "a second tap on the player shown did not open the details")
    _close_all(page)
    if page.evaluate("() => window.TradeValueV2.expanded()"):
        errors.append(tag + "could not close the full-screen chart")
    # The finger lands exactly on the crosshair the first tap drew; the second tap must still open the details.
    page.click("#v2FullScreen")
    _settle(page, 400)
    s = page.evaluate(STATE)
    page.touchscreen.tap(s["px"][i], s["py"])
    _settle(page, 700)
    page.touchscreen.tap(s["px"][i], s["py"])
    _settle(page, 400)
    if not page.evaluate(STATE)["drawer"]:
        errors.append(tag + "tapping the same point twice did not open the details")
    _close_all(page)
    # Escape closes and returns focus to the button that opened it.
    page.click("#v2FullScreen")
    _settle(page, 300)
    if portrait and page.evaluate(STATE)["hint"]:
        errors.append(tag + "the rotate prompt came back after Dismiss")
    page.keyboard.press("Escape")
    _settle(page)
    e = page.evaluate(STATE)
    if e["expanded"] or e["active"] != "v2FullScreen":
        errors.append(tag + f"Escape: expanded={e['expanded']} focus on {e['active']!r}, want closed and focus on the Full screen button")
    if page.evaluate("() => getComputedStyle(document.body).overflow") == "hidden":
        errors.append(tag + "page scroll still locked after closing")
    # Keyboard a11y kept (arrow keys announce).
    page.focus("#v2Chart")
    page.keyboard.press("ArrowRight")
    _settle(page, 150)
    if "rank" not in page.evaluate(STATE)["say"]:
        errors.append(tag + "arrow keys no longer announce the player")
    return errors


def check_desktop(page, tag) -> list[str]:
    s = page.evaluate(STATE)
    errors = []
    if s["btn"]["display"] != "none":
        errors.append(tag + "the Full screen button shows on a desktop screen")
    return errors


def run_checks(overrides=None, sizes=PHONES + ((1440, 900),)) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in sizes:
                tag = f"[{width}x{height}] "
                phone = width < 1000
                context = browser.new_context(viewport={"width": width, "height": height}, has_touch=phone, is_mobile=phone)
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda r: r.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                _settle(page, 400)
                if phone:
                    errors += check_phone(page, context.new_cdp_session(page), tag, width, height)
                else:
                    errors += check_desktop(page, tag)
                if page_errors:
                    errors.append(tag + f"page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class ChartFullScreenRenderTest(unittest.TestCase):
    def test_full_screen_and_touch_inspect(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        js, cs = "text/javascript", "text/css"
        phone = ((390, 844), (844, 390))
        broken = {
            "touch handlers gone": ({"v2.js": (v2.replace("    bindChartTouch(container, getChart);\n", "", 1), js)}, phone[:1]),
            "a first tap opens the details": ({"v2.js": (v2.replace(
                "if (g.drag || !g.wasShown) event.stopImmediatePropagation();", "if (g.drag) event.stopImmediatePropagation();", 1), js)}, phone[:1]),
            "the rotate prompt cannot be dismissed": ({"v2.js": (v2.replace(
                '      rotateDismissed = true;\n', "", 1).replace(
                'try { sessionStorage.setItem("v2RotateHint", "1"); } catch (error) { /* held in memory above */ }\n', "", 1), js)}, phone[:1]),
            "focus not returned to Full screen": ({"v2.js": (v2.replace(
                "expandOpener = opener || (kind", "expandOpener = (kind", 1), js)}, phone[:1]),
            "no page scroll lock": ({"v2.css": (css.replace("body.v2-expand-open { overflow: hidden; }", "", 1), cs)}, phone[:1]),
            "no Full screen button on a sideways phone": ({"v2.css": (css.replace(
                "@media (max-width: 767px), (max-height: 500px) and (pointer: coarse) {\n  .v2-app .v2-fullscreen",
                "@media (max-width: 767px) {\n  .v2-app .v2-fullscreen", 1), cs)}, phone[1:]),
            "the full-screen chart lets the page scroll": ({"v2.css": (css.replace(
                ".v2-expand .v2-chart { touch-action: none; }", "", 1), cs)}, phone[:1]),
            "the rotate prompt shows sideways too": ({"v2.js": (v2.replace(
                '"(max-width: 767px) and (orientation: portrait)"', '"(max-width: 1000px)"', 1), js)}, phone[1:]),
        }
        for name, (overrides, sizes) in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    source = {"v2.js": v2, "v2.css": css}[file]
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, sizes=sizes), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
