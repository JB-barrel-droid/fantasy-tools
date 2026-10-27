"""Top-bar season-value notice guard (JEG-1023; Jeremy, 2026-10-24).

The header carries one notice on every route: built for season-long value, not weekly start/sit decisions or
playoff optimization. "More" opens the full list (also: defenses and kickers are not yet accounted for; the
"Optimize for playoffs" line went with the setting, hidden by JEG-1119). An X dismisses it for the browser session.

Checks:
  * shown by default on every route (all views, the three Writing sections, both Values auditing views) at 1366x768
    and 390x844, with the visible line, no live region, and the full list behind "More";
  * the header is the same height shown and dismissed (and equal to the pre-notice height) at 1440x900, 1366x768 and
    1024x768, so the Compare verdict fit is untouched; phones: no sideways scroll at 390, 360, 320 and 844x390, with
    44 px buttons;
  * the X hides it on every route, it stays hidden across route changes and a reload, it returns in a fresh browser
    context, and it still works with sessionStorage blocked.

Discrimination (test_guard_fails_on_broken_builds): each break below must fail the check.
"""
from __future__ import annotations

import unittest
from pathlib import Path

from tests import _render_env
from tests.test_v2_phone_weight_render import _served

ROOT = Path(__file__).resolve().parents[1]
CSS = ROOT / "app" / "v2" / "v2.css"
JS = ROOT / "app" / "v2" / "v2.js"

def setUpModule():
    _render_env.ensure_built()


ROUTES = ["#writing/manifesto", "#writing/how-values", "#writing/research", "#player-values", "#trade-targets",
          "#risers-fallers", "#compare-trade", "#find-trade", "#values-auditing/value-pie", "#values-auditing/single-source"]
LINE = "Built for season-long value, not weekly start/sit decisions or playoff optimization."
DETAIL = ["season-long value", "weekly start/sit decisions", "playoff optimization",
          "Defenses and kickers are not yet accounted for"]
# Header heights before the notice existed (origin/main, measured 2026-10-24); the notice must not move them.
BASE_HEADER = {(1440, 900): 64, (1366, 768): 64, (1024, 768): 64}
DESKTOP = list(BASE_HEADER)
PHONES = [(390, 844), (360, 740), (320, 568), (844, 390)]

STATE = """() => {
  const n = document.getElementById('v2SeasonNote');
  const box = e => e.getBoundingClientRect();
  const vis = e => { const b = box(e); return b.width > 0 && b.height > 0 && getComputedStyle(e).visibility !== 'hidden'; };
  const text = document.getElementById('v2SeasonNoteText'), more = document.getElementById('v2SeasonNoteMore'), close = document.getElementById('v2SeasonNoteClose');
  const detail = document.getElementById('v2SeasonNoteDetail');
  const live = n.closest('[aria-live],[role=status],[role=alert]') || n.querySelector('[aria-live],[role=status],[role=alert]');
  const vw = document.documentElement.clientWidth;
  return {shown: vis(n), line: text.textContent.trim(), textVisible: vis(text), textH: box(text).height,
    textInView: box(text).right <= vw + 0.5 && box(text).left >= -0.5,
    moreH: box(more).height, closeH: box(close).height, closeW: box(close).width, moreVis: vis(more), closeVis: vis(close),
    detailShown: vis(detail), detailText: detail.textContent, expanded: more.getAttribute('aria-expanded'),
    detailOver: box(detail).right - vw, detailInView: box(detail).left >= -0.5,
    live: !!live, closeName: close.getAttribute('aria-label'),
    header: Math.round(box(document.querySelector('.v2-nav')).height * 10) / 10,
    over: document.documentElement.scrollWidth - vw,
    focus: document.activeElement && (document.activeElement.tagName + '.' + document.activeElement.className),
    dismissed: (() => { try { return sessionStorage.getItem('v2.seasonNoticeDismissed'); } catch (e) { return 'blocked'; } })()};
}"""

BLOCK_STORAGE = """() => { const boom = () => { throw new DOMException('blocked', 'SecurityError'); };
  Object.defineProperty(window, 'sessionStorage', {get: boom, configurable: true}); }"""


def _new(browser, base, size, css, js, blocked=False, context=None, hash_="#trade-targets"):
    ctx = context or browser.new_context(viewport={"width": size[0], "height": size[1]})
    page = ctx.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    if blocked:
        page.add_init_script("(" + BLOCK_STORAGE + ")()")
    if css is not None:
        page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
    if js is not None:
        page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=js))
    page.goto(base + hash_, wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2", timeout=40000)
    page.wait_for_timeout(250)
    return ctx, page, errors


def _click(page, selector, tag, errors):
    """Click, or record that the button could not be clicked (a broken build must fail the guard, not hang it)."""
    try:
        page.click(selector, timeout=4000)
        return True
    except Exception:
        errors.append(f"{tag}: {selector} not clickable (hidden or off screen)")
        return False


def _go(page, route):
    page.evaluate("(r) => { location.hash = r; }", route)
    page.wait_for_timeout(150)


def run_checks(css=None, js=None) -> list[str]:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    errors: list[str] = []
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        try:
            # Desktop and phone: shown on every route, with the full list behind More.
            for size in ((1366, 768), (390, 844)):
                tag = f"{size[0]}x{size[1]}"
                ctx, page, page_errors = _new(browser, base, size, css, js)
                for route in ROUTES:
                    _go(page, route)
                    s = page.evaluate(STATE)
                    if not s["shown"] or not s["textVisible"]:
                        errors.append(f"{tag} {route}: notice not visible")
                    elif s["line"] != LINE:
                        errors.append(f"{tag} {route}: notice text {s['line']!r}")
                    if s["live"]:
                        errors.append(f"{tag} {route}: notice sits in a live region")
                    if s["over"] > 0:
                        errors.append(f"{tag} {route}: page scrolls sideways by {s['over']}")
                _go(page, "#trade-targets")
                _click(page, "#v2SeasonNoteMore", tag, errors)
                s = page.evaluate(STATE)
                missing = [d for d in DETAIL if d not in s["detailText"]]
                if not s["detailShown"] or s["expanded"] != "true" or missing:
                    errors.append(f"{tag}: full list not shown on More (shown {s['detailShown']}, expanded {s['expanded']}, missing {missing})")
                if s["detailOver"] > 0.5 or not s["detailInView"]:
                    errors.append(f"{tag}: full list runs outside the screen")
                page.keyboard.press("Escape")
                s = page.evaluate(STATE)
                if s["detailShown"] or s["expanded"] != "false":
                    errors.append(f"{tag}: Escape did not close the full list")
                if size[0] < 768:
                    if s["textH"] > 24:
                        errors.append(f"{tag}: phone notice wraps ({s['textH']} px tall); want one truncated line")
                    if s["moreH"] < 43.5 or s["closeH"] < 43.5 or s["closeW"] < 43.5:
                        errors.append(f"{tag}: phone buttons under 44 px (More {s['moreH']}, X {s['closeW']}x{s['closeH']})")
                if s["closeName"] != "Dismiss notice":
                    errors.append(f"{tag}: close button name {s['closeName']!r}")
                if page_errors:
                    errors.append(f"{tag}: page errors {page_errors[:2]}")
                ctx.close()
            # Header height: unchanged by the notice, shown or dismissed.
            for size in DESKTOP:
                tag = f"{size[0]}x{size[1]}"
                ctx, page, _ = _new(browser, base, size, css, js)
                shown = page.evaluate(STATE)["header"]
                _click(page, "#v2SeasonNoteClose", tag, errors)
                gone = page.evaluate(STATE)["header"]
                if abs(shown - BASE_HEADER[size]) > 1:
                    errors.append(f"{tag}: header {shown} px with the notice; was {BASE_HEADER[size]} px")
                if abs(gone - BASE_HEADER[size]) > 1:
                    errors.append(f"{tag}: header {gone} px dismissed; was {BASE_HEADER[size]} px")
                ctx.close()
            # Tablet widths: the tab row wraps there, so the notice may add its one 18 px row but no more.
            for size in ((768, 1024), (820, 1180)):
                tag = f"{size[0]}x{size[1]}"
                ctx, page, _ = _new(browser, base, size, css, js)
                shown = page.evaluate(STATE)
                _click(page, "#v2SeasonNoteClose", tag, errors)
                gone = page.evaluate(STATE)
                if shown["header"] - gone["header"] > 18.5:
                    errors.append(f"{tag}: header grows {shown['header'] - gone['header']} px with the notice; want at most 18")
                if shown["over"] > 0:
                    errors.append(f"{tag}: page scrolls sideways by {shown['over']}")
                ctx.close()
            # Phones: no sideways scroll, shown or dismissed.
            for size in PHONES:
                tag = f"{size[0]}x{size[1]}"
                ctx, page, _ = _new(browser, base, size, css, js)
                for state_name in ("shown", "dismissed"):
                    for route in ("#trade-targets", "#compare-trade", "#writing/research"):
                        _go(page, route)
                        s = page.evaluate(STATE)
                        if s["over"] > 0:
                            errors.append(f"{tag} {state_name} {route}: page scrolls sideways by {s['over']}")
                    if state_name == "shown":
                        grown = s["header"]
                        if not s["textInView"] or not s["closeVis"] or not s["moreVis"]:
                            errors.append(f"{tag}: notice text or buttons are off screen")
                        _click(page, "#v2SeasonNoteMore", tag, errors)
                        s = page.evaluate(STATE)
                        if s["over"] > 0 or s["detailOver"] > 0.5:
                            errors.append(f"{tag}: open full list overflows ({s['over']}, {s['detailOver']})")
                        _click(page, "#v2SeasonNoteMore", tag, errors)
                        _click(page, "#v2SeasonNoteClose", tag, errors)
                        if size[0] < 768 and grown - page.evaluate(STATE)["header"] > 45:
                            errors.append(f"{tag}: header grows {grown - page.evaluate(STATE)['header']} px with the notice; want at most 45")
                ctx.close()
            # Dismiss: every route, across navigation, reload, a fresh context, and blocked storage.
            for blocked in (False, True):
                tag = "blocked storage" if blocked else "dismiss"
                ctx, page, page_errors = _new(browser, base, (1366, 768), css, js, blocked=blocked)
                if not page.evaluate(STATE)["shown"]:
                    errors.append(f"{tag}: not shown at the start of a session")
                _go(page, "#compare-trade")
                _click(page, "#v2SeasonNoteMore", tag, errors)
                _click(page, "#v2SeasonNoteClose", tag, errors)
                s = page.evaluate(STATE)
                if s["shown"] or s["detailShown"]:
                    errors.append(f"{tag}: still showing after the X (notice {s['shown']}, list {s['detailShown']})")
                if "MAIN" not in (s["focus"] or ""):
                    errors.append(f"{tag}: focus after the X is on {s['focus']!r}, want the page content")
                for route in ROUTES:
                    _go(page, route)
                    if page.evaluate(STATE)["shown"]:
                        errors.append(f"{tag} {route}: notice came back after the X")
                if not blocked:
                    page.reload(wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                    page.wait_for_timeout(250)
                    if page.evaluate(STATE)["shown"]:
                        errors.append(f"{tag}: notice back after a reload in the same session")
                    fresh_ctx, fresh, _ = _new(browser, base, (1366, 768), css, js)
                    if not fresh.evaluate(STATE)["shown"]:
                        errors.append(f"{tag}: notice did not return in a new session")
                    fresh_ctx.close()
                if page_errors:
                    errors.append(f"{tag}: page errors {page_errors[:2]}")
                ctx.close()
        finally:
            browser.close()
    return errors


class TopbarNoticeRenderTest(unittest.TestCase):
    def test_notice_on_every_route_dismissible_no_height_change(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = CSS.read_text(encoding="utf-8")
        js = JS.read_text(encoding="utf-8")
        hide_on_compare = js + '\nwindow.addEventListener("hashchange", () => { if (location.hash === "#compare-trade") document.getElementById("v2SeasonNote").hidden = true; });\n'
        cases = {
            "notice missing on one route": (None, hide_on_compare, "#compare-trade: notice not visible"),
            "header grows": (css.replace(".v2-nav.has-notice > .v2-nav-inner { min-height: 46px; }", ""), None, "header"),
            "text overflows at 320": (css.replace(".v2-topnote-text { flex: 1 1 0; }", ".v2-topnote-text { flex: 0 0 auto; }"), None, "sideways"),
            "X does not hide": (None, js.replace("notice.hidden = !shown;", ""), "still showing after the X"),
            "dismissal not remembered": (None, js.replace('sessionStorage.setItem(KEY, "1");', ""), "came back after the X"),
            "blocked storage breaks the X": (None, js.replace('try { sessionStorage.setItem(KEY, "1"); } catch (error) { /* in-memory flag above */ }', 'sessionStorage.setItem(KEY, "1");'), "blocked storage"),
            "no full list": (None, js.replace("detail.hidden = !open;", ""), "full list not shown"),
        }
        for name, (c, j, want) in cases.items():
            if c is not None:
                self.assertNotEqual(c, css, f"{name}: mutation did not apply")
            if j is not None:
                self.assertNotEqual(j, js, f"{name}: mutation did not apply")
            with self.subTest(name):
                errors = run_checks(css=c, js=j)
                self.assertTrue(any(want in e for e in errors), f"{name} not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
