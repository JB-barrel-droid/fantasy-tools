"""Every module card expands and collapses, and the collapse is remembered (JEG-500, GL-17 and GL-18), rendered.

Builds dist/v2 into a temp copy of the built dist/ and loads each tab headless at 1440 x 900
and 390 x 844. For every card that is on screen:

  * the chevron is a 44 px button with aria-expanded; collapsing hides the card's body, keeps
    its title, and shows a one-line summary that is not empty;
  * the collapsed state survives a reload (and only that card is collapsed);
  * Expand: Player values' chart and table reuse the JEG-483 dialog; every other card spans its
    row at full width and returns on a second press (aria-pressed);
  * no page errors and no sideways scroll at 390.

The league editor is a native <details> card (JEG-1213): its module controls are found from its
nearest .v2-card ancestor like every other card's, and its summary must close it on Enter and open
it on a click with the title kept in view (JEG-1234).

Discrimination: test_guard_fails_on_broken_builds serves modules.js / v2.css with one fault each
(state not saved, collapsed card hides nothing, empty summary, chevron that does not announce
its state, expand that does nothing, small chevron) and requires each to fail.
test_guard_fails_on_broken_league_disclosure does the same on Find in league (collapse hides
nothing, expand does nothing, summary turned into a div, summary toggle cancelled).
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import shutil
import socketserver
import sys
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "pipelines"))
import build_v2_page  # noqa: E402

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    _render_env.ensure_built()


MODULES_JS = ROOT / "app" / "v2" / "modules.js"
V2_CSS = ROOT / "app" / "v2" / "v2.css"
LEAGUE_JS = ROOT / "app" / "v2" / "league.js"

# tab hash -> heading ids of the cards that must be on screen there
TABS = {
    "#player-values": ["v2ChartTitle", "v2TableTitle"],
    "#trade-targets": ["v2TSellTitle", "v2TBuyTitle"],
    "#risers-fallers": ["v2RRiseTitle", "v2RFallTitle"],
    "#compare-trade": ["v2GiveTitle", "v2GetTitle", "v2CVerdictTitle", "v2CResultTitle"],
    "#find-trade": ["v2FindTitle"],
    "#find-league": ["v2LgTitle"],
}
REUSED_EXPAND = {"v2ChartTitle", "v2TableTitle"}
# JEG-1213 made the league editor a native disclosure (<details class="v2-card"> whose <summary> holds the title). Its
# module controls are still checked like every card's, and its own summary must open and close it too (JEG-1234).
DISCLOSURE = {"v2LgTitle"}

DISCLOSURE_STATE = """(id) => { const card = document.getElementById(id).closest('.v2-card');
  const summary = card.tagName === 'DETAILS' ? card.querySelector(':scope > summary') : null;
  // A closed <details> hides its content with content-visibility (offsetParent stays set), so ask checkVisibility().
  const vis = el => Boolean(el && el.checkVisibility() && el.getBoundingClientRect().height > 0);
  const body = [...card.children].filter(c => c !== summary && !c.classList.contains('v2-mod-ctl')
    && !c.classList.contains('v2-mod-sum') && !c.hidden);
  return {details: card.tagName === 'DETAILS', summary: Boolean(summary), titleInSummary: Boolean(summary && summary.contains(document.getElementById(id))),
    open: card.open === true, titleShown: vis(document.getElementById(id)), bodyShown: body.some(vis),
    focused: Boolean(summary && document.activeElement === summary)}; }"""

CARD = """(id) => { const h = document.getElementById(id); const card = h && h.closest('.v2-card');
  if (!card) return null;
  const chev = card.querySelector(':scope > .v2-mod-ctl .v2-mod-chevron');
  const exp = card.querySelector(':scope > .v2-mod-ctl .v2-mod-expand');
  const sum = card.querySelector(':scope > .v2-mod-sum');
  const vis = el => Boolean(el && el.offsetParent !== null && el.getBoundingClientRect().height > 0);
  const body = [...card.children].filter(c => !c.classList.contains('v2-mod-ctl') && !c.classList.contains('v2-mod-head')
    && !c.classList.contains('v2-mod-sum') && !c.hidden);
  const r = card.getBoundingClientRect(), p = card.parentElement.getBoundingClientRect();
  return {shown: vis(card), module: Boolean(chev), expanded: chev && chev.getAttribute('aria-expanded'),
    chevH: chev ? chev.getBoundingClientRect().height : 0, chevW: chev ? chev.getBoundingClientRect().width : 0,
    expH: exp ? exp.getBoundingClientRect().height : 0, expShown: vis(exp), expPressed: exp && exp.getAttribute('aria-pressed'),
    title: vis(card.querySelector(':scope > .v2-mod-head')), summary: sum ? sum.textContent.trim() : '', summaryShown: vis(sum),
    bodyShown: body.some(vis), width: r.width, parentWidth: p.width, xl: card.dataset.xl || ''}; }"""


def _settle(page, ms=250):
    page.wait_for_timeout(ms)


def _serve(body, ctype, route, *_):
    route.fulfill(status=200, content_type=ctype, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def _ready(page, hash_):
    page.evaluate("h => { location.hash = h; }", hash_)
    page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.view()", timeout=60000)
    _settle(page, 500)


def _control(id_, cls):
    # The card is the heading's nearest .v2-card ancestor, a <section> or (the league editor) a <details>; the class is
    # matched as a whole token, the same element modules.js finds with closest('.v2-card').
    return (f"#{id_} >> xpath=ancestor::*[contains(concat(' ', normalize-space(@class), ' '), ' v2-card ')][1]"
            f" >> :scope > .v2-mod-ctl .{cls}")


def check_disclosure(page, t, id_) -> list[str]:
    """A native disclosure card: its summary is a keyboard and pointer control that hides and shows the body while the
    title stays in view. Leaves the card open."""
    errors = []
    s = page.evaluate(DISCLOSURE_STATE, id_)
    if not (s["details"] and s["summary"] and s["titleInSummary"]):
        return [t + f"not a disclosure with its title in the summary ({s})"]
    if not s["open"] or not s["bodyShown"]:
        return [t + f"disclosure starts closed (open {s['open']}, body {s['bodyShown']})"]
    card = f"#{id_} >> xpath=ancestor::details[1] >> :scope > summary"
    page.focus(card)
    page.keyboard.press("Enter")
    _settle(page, 150)
    closed = page.evaluate(DISCLOSURE_STATE, id_)
    if not closed["focused"] or closed["open"] or closed["bodyShown"] or not closed["titleShown"]:
        errors.append(t + f"Enter on the summary did not close it with the title kept ({closed})")
    page.click(card)
    _settle(page, 150)
    opened = page.evaluate(DISCLOSURE_STATE, id_)
    if not opened["open"] or not opened["bodyShown"] or not opened["titleShown"]:
        errors.append(t + f"a click on the summary did not open it again ({opened})")
    return errors


def check_tab(page, tag, hash_, ids, width) -> list[str]:
    errors = []
    _ready(page, hash_)
    for id_ in ids:
        t = f"{tag}{id_}: "
        s = page.evaluate(CARD, id_)
        if not s or not s["shown"]:
            errors.append(t + "card is not on screen")
            continue
        if not s["module"]:
            errors.append(t + "no chevron")
            continue
        if s["chevH"] < 44 or s["chevW"] < 44:
            errors.append(t + f"chevron is {s['chevW']:.0f} x {s['chevH']:.0f}, want 44 px")
        if s["expanded"] != "true" or not s["bodyShown"]:
            errors.append(t + f"starts collapsed ({s['expanded']}, body {s['bodyShown']})")
        if s["expH"] < 44:
            errors.append(t + f"expand control is {s['expH']:.0f} px tall")
        if id_ in DISCLOSURE:
            errors += check_disclosure(page, t, id_)
        # Expand
        if id_ not in REUSED_EXPAND:
            before = s["width"]
            page.click(_control(id_, "v2-mod-expand"))
            _settle(page, 150)
            on = page.evaluate(CARD, id_)
            if on["xl"] != "true" or on["expPressed"] != "true" or (before < 0.9 * on["parentWidth"] and on["width"] < on["parentWidth"] - 2):
                errors.append(t + f"expand: xl {on['xl']!r}, pressed {on['expPressed']!r}, width {on['width']:.0f} of {on['parentWidth']:.0f}")
            page.click(_control(id_, "v2-mod-expand"))
            _settle(page, 150)
            back = page.evaluate(CARD, id_)
            if back["xl"] == "true" or back["expPressed"] != "false" or abs(back["width"] - before) > 2:
                errors.append(t + f"second press did not restore ({back['xl']!r}, {back['width']:.0f} vs {before:.0f})")
        else:
            page.click(_control(id_, "v2-mod-expand"))
            _settle(page, 300)
            if not page.evaluate("() => Boolean(window.TradeValueV2.expanded())"):
                errors.append(t + "expand did not open the full-screen view")
            page.keyboard.press("Escape")
            _settle(page, 250)
        # Collapse
        page.click(_control(id_, "v2-mod-chevron"))
        _settle(page, 200)
        if id_ == "v2ChartTitle":   # the table beside a collapsed chart keeps its rows in view
            h = page.evaluate("() => document.getElementById('v2TableWrap').getBoundingClientRect().height")
            if h < 200:
                errors.append(t + f"the table is squashed to {h:.0f} px beside the collapsed chart")
        c = page.evaluate(CARD, id_)
        if c["expanded"] != "false":
            errors.append(t + f"aria-expanded is {c['expanded']!r} after collapsing")
        if c["bodyShown"]:
            errors.append(t + "collapsed but the body is still shown")
        if not c["title"]:
            errors.append(t + "collapsed card lost its title")
        if not c["summary"] or not c["summaryShown"]:
            errors.append(t + f"collapsed card has no one-line summary ({c['summary']!r})")
        elif len(c["summary"]) > 140:
            errors.append(t + f"summary is not one line: {c['summary']!r}")
    # The collapsed cards are remembered across a reload.
    page.reload(wait_until="networkidle")
    _ready(page, hash_)
    for id_ in ids:
        r = page.evaluate(CARD, id_)
        if r["expanded"] != "false" or r["bodyShown"] or not r["summary"]:
            errors.append(f"{tag}{id_}: not remembered after reload ({r['expanded']!r}, body {r['bodyShown']}, summary {r['summary']!r})")
    # Open them again and leave the device clean for the next tab.
    for id_ in ids:
        page.click(_control(id_, "v2-mod-chevron"))
        _settle(page, 150)
        r = page.evaluate(CARD, id_)
        if r["expanded"] != "true" or not r["bodyShown"]:
            errors.append(f"{tag}{id_}: did not open again")
    page.reload(wait_until="networkidle")
    _ready(page, hash_)
    for id_ in ids:
        if page.evaluate(CARD, id_)["expanded"] != "true":
            errors.append(f"{tag}{id_}: opening it again was not remembered")
    if width <= 390:
        overflow = page.evaluate("() => document.documentElement.scrollWidth - innerWidth")
        if overflow > 0:
            errors.append(f"{tag}{hash_}: horizontal overflow {overflow}px")
    return errors


def run_checks(overrides=None, viewports=((1440, 900), (390, 844)), tabs=tuple(TABS)) -> list[str]:
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
            for width, height in viewports:
                context = browser.new_context(viewport={"width": width, "height": height})
                page = context.new_page()
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                for name, (body, ctype) in (overrides or {}).items():
                    page.route(f"**/v2/{name}*", functools.partial(_serve, body, ctype))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                for hash_ in tabs:
                    errors += check_tab(page, f"[{width}px] ", hash_, TABS[hash_], width)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                context.close()
        finally:
            browser.close()
    return errors


class ModulesRenderTest(unittest.TestCase):
    def test_every_card_expands_collapses_and_is_remembered(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = MODULES_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        mj, cs = "text/javascript", "text/css"
        broken = {
            "state not saved": {"modules.js": (js.replace("    try { localStorage.setItem(", "    try { void (", 1), mj)},
            "collapsed card hides nothing": {"v2.css": (css.replace(
                '.v2-mod[data-collapsed="true"] > :not(.v2-mod-ctl):not(.v2-mod-head):not(.v2-mod-sum) { display: none !important; }',
                "", 1), cs)},
            "empty summary": {"modules.js": (js.replace('spec.summary() || "No data yet"', '""', 1), mj)},
            "chevron does not announce its state": {"modules.js": (js.replace(
                'chevron.setAttribute("aria-expanded", String(!closed));', "", 1), mj)},
            "expand does nothing": {"modules.js": (js.replace('card.dataset.xl = String(on);', "", 1), mj)},
            "small chevron": {"v2.css": (css.replace(
                ".v2-mod-btn { min-width: 44px; min-height: 44px;", ".v2-mod-btn { min-width: 20px; min-height: 20px; width: 20px; height: 20px;", 1), cs)},
        }
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    source = {"modules.js": js, "v2.css": css}[file]
                    self.assertNotEqual(body, source, f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, viewports=((1440, 900),), tabs=("#trade-targets",)), [],
                                    f"render checks did not catch: {name}")

    def test_guard_fails_on_broken_league_disclosure(self):
        # JEG-1234: the league editor (a <details> card since JEG-1213) is held to the same module checks, and its own
        # summary must stay a working disclosure. One fault each, on Find in league, must fail.
        js = MODULES_JS.read_text(encoding="utf-8")
        css = V2_CSS.read_text(encoding="utf-8")
        league = LEAGUE_JS.read_text(encoding="utf-8")
        mj, cs = "text/javascript", "text/css"
        broken = {
            "collapsed card hides nothing": {"v2.css": (css.replace(
                '.v2-mod[data-collapsed="true"] > :not(.v2-mod-ctl):not(.v2-mod-head):not(.v2-mod-sum) { display: none !important; }',
                "", 1), cs)},
            "expand does nothing": {"modules.js": (js.replace('card.dataset.xl = String(on);', "", 1), mj)},
            "summary is not a disclosure": {"league.js": (league.replace(
                'el("summary", {class: "v2-card-head v2-lg-card-summary"}', 'el("div", {class: "v2-card-head v2-lg-card-summary"}', 1), mj)},
            "summary toggle cancelled": {"league.js": (league.replace(
                'const league = el("details", {class: "v2-card v2-lg-editor", id: "v2LgCard", "aria-labelledby": "v2LgTitle", open: true},',
                'const league = el("details", {class: "v2-card v2-lg-editor", id: "v2LgCard", "aria-labelledby": "v2LgTitle", open: true,'
                ' onclick: "if (event.target.closest(\'summary\') && event.target.closest(\'summary\').parentElement === this) event.preventDefault()"},',
                1), mj)},
        }
        sources = {"modules.js": js, "v2.css": css, "league.js": league}
        for name, overrides in broken.items():
            with self.subTest(mutation=name):
                for file, (body, _) in overrides.items():
                    self.assertNotEqual(body, sources[file], f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(overrides, viewports=((1440, 900),), tabs=("#find-league",)), [],
                                    f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
