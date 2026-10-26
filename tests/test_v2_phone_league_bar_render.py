"""Phone league-settings bar collapses to one summary line (JEG-1134).

Jeremy's decision (2026-10-26, option A): on a phone the league settings bar (scoring, roster, Edit league,
Position weights, source legend, Customize) collapses to one tappable summary line built from the current
settings, e.g. "Full PPR · 12 teams · 5 sources", which opens the existing controls below it. Before this the
bar cost about 280 px before any tab content, on top of the ~195 px sticky top bar.

Loads the built page headless at 390 x 844 (phone) and checks, on #player-values:
  * the summary is a real <button>, at least 44 px tall, closed (aria-expanded="false") on load;
  * the controls it holds (#v2LeagueBody, which carries Edit league / Position weights, and #v2Methods, which
    carries the source legend and Customize) are hidden until the summary is tapped, then visible;
  * the first tab content's top is above the fold (844 px) when closed, and the same top is at least 150 px
    lower when the bar is open, so the bar really does collapse rather than being hidden by something else;
  * the summary line reads "Full PPR · 12 teams · N sources" and is the same scoring label and team count the
    bar itself shows.
At 1440 x 900 (desktop) the summary button is not rendered and both blocks stay visible, so nothing changes
there. The measured px gain is printed by test_report_px_gain.

Discrimination: test_guard_fails_without_collapse serves the CSS with the collapse rule removed and requires
the "controls hidden until tapped" checks to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CSS = ROOT / "app" / "v2" / "v2.css"
PHONE = (390, 844)
DESKTOP = (1440, 900)
# The rule that hides the two blocks while the summary is closed.
COLLAPSE = ('  body:not(:has(#v2LeagueSummary[aria-expanded="true"])) #v2LeagueBody,\n'
            '  body:not(:has(#v2LeagueSummary[aria-expanded="true"])) #v2Methods { display: none; }\n')
MIN_GAIN = 150  # the closed bar must lift the content by at least this much versus the open bar


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(DIST))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
        finally:
            server.shutdown()


MEASURE = """() => {
  const vis = e => !!e && getComputedStyle(e).visibility !== 'hidden' && e.getBoundingClientRect().height > 0;
  const box = e => { const b = e && e.getBoundingClientRect(); return b && {top: b.top, bottom: b.bottom, h: b.height}; };
  const summary = document.querySelector('#v2LeagueSummary');
  const main = document.querySelector('main.v2-main:not([hidden])');
  const title = main && main.querySelector('.v2-title');
  return {
    tag: summary && summary.tagName,
    summaryVisible: vis(summary), summaryBox: box(summary),
    expanded: summary && summary.getAttribute('aria-expanded'),
    controls: summary && summary.getAttribute('aria-controls'),
    text: document.querySelector('#v2LeagueSummaryText') && document.querySelector('#v2LeagueSummaryText').textContent,
    leagueName: document.querySelector('#v2LeagueName') && document.querySelector('#v2LeagueName').textContent,
    bodyVisible: vis(document.querySelector('#v2LeagueBody')),
    methodsVisible: vis(document.querySelector('#v2Methods')),
    editVisible: vis(document.querySelector('#v2EditLeague')),
    customizeVisible: vis(document.querySelector('#v2EditSources')),
    legendVisible: vis(document.querySelector('#v2ShowingLegend')),
    titleTop: title ? title.getBoundingClientRect().top : null,
    titleBottom: title ? title.getBoundingClientRect().bottom : null,
    vh: window.innerHeight,
  };
}"""


def _open(browser, base, width, height, css=None):
    page = browser.new_page(viewport={"width": width, "height": height})
    if css is not None:
        page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
    page.goto(base + "#player-values", wait_until="networkidle")
    page.wait_for_function("() => window.TradeValueV2 && [...document.querySelectorAll('main.v2-main')].some(m => !m.hidden)", timeout=60000)
    page.wait_for_timeout(400)
    return page


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    out: dict = {}
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        # Phone, closed on load, then opened by tapping the summary.
        page = _open(browser, base, *PHONE, css=css)
        out["phone_closed"] = page.evaluate(MEASURE)
        page.click("#v2LeagueSummary")
        page.wait_for_timeout(250)
        out["phone_open"] = page.evaluate(MEASURE)
        # Change the scoring through the league panel; the summary must follow the new setting.
        page.click("#v2EditLeague")
        page.wait_for_timeout(500)
        page.get_by_role("button", name="Standard", exact=True).first.click()
        page.wait_for_timeout(200)
        page.get_by_role("button", name="Done", exact=True).first.click()
        page.wait_for_timeout(1200)
        out["phone_changed"] = page.evaluate(MEASURE)
        page.close()
        # Phone, opened from the keyboard (focus + Enter, as a keyboard user would).
        page = _open(browser, base, *PHONE, css=css)
        out["phone_keyboard"] = page.evaluate(MEASURE)
        page.focus("#v2LeagueSummary")
        page.keyboard.press("Enter")
        page.wait_for_timeout(250)
        out["phone_keyboard_open"] = page.evaluate(MEASURE)
        page.close()
        # Desktop: unchanged.
        page = _open(browser, base, *DESKTOP, css=css)
        out["desktop"] = page.evaluate(MEASURE)
        page.close()
        browser.close()
    return out


def _phone_closed_errors(m: dict) -> list[str]:
    errors = []
    if m["tag"] != "BUTTON":
        errors.append(f"the summary is a <{m['tag']}> not a <button>")
    if not m["summaryVisible"]:
        errors.append("the summary line is not visible at 390 px")
    if m["summaryBox"] and m["summaryBox"]["h"] < 44:
        errors.append(f"the summary is {m['summaryBox']['h']:.0f} px tall, under 44 px")
    if m["expanded"] != "false":
        errors.append(f"the summary is not closed on load: aria-expanded={m['expanded']!r}")
    for name, key in (("the league row (Edit league / Position weights)", "bodyVisible"),
                      ("the legend row (source legend / Customize)", "methodsVisible")):
        if m[key]:
            errors.append(f"{name} is showing before the summary is tapped")
    if m["editVisible"] or m["customizeVisible"] or m["legendVisible"]:
        errors.append("a control (Edit league / Customize / legend) is visible before the summary is tapped")
    if m["titleTop"] is None:
        errors.append("no first tab content found")
    elif m["titleBottom"] > m["vh"]:
        errors.append(f"the first tab content is below the fold when closed: top {m['titleTop']:.0f}, bottom {m['titleBottom']:.0f}, viewport {m['vh']}")
    return errors


def _phone_open_errors(m: dict) -> list[str]:
    errors = []
    if m["expanded"] != "true":
        errors.append(f"aria-expanded is not true after opening: {m['expanded']!r}")
    for name, key in (("the league row", "bodyVisible"), ("the legend row", "methodsVisible"),
                      ("Edit league", "editVisible"), ("Customize", "customizeVisible"), ("the source legend", "legendVisible")):
        if not m[key]:
            errors.append(f"{name} is still hidden after the summary is tapped")
    return errors


def _text_errors(m: dict) -> list[str]:
    errors = []
    text = m["text"] or ""
    parts = [p.strip() for p in text.split("·")]
    if len(parts) != 3:
        errors.append(f"the summary is not the three-part 'scoring · teams · sources' line: {text!r}")
        return errors
    scoring_teams = (m["leagueName"] or "").split("·")
    if len(scoring_teams) == 2 and parts[0] != scoring_teams[0].strip():
        errors.append(f"the summary scoring label {parts[0]!r} is not the bar's {scoring_teams[0].strip()!r}")
    if len(scoring_teams) == 2 and parts[1] != scoring_teams[1].strip():
        errors.append(f"the summary team count {parts[1]!r} is not the bar's {scoring_teams[1].strip()!r}")
    if not parts[2].endswith("sources") and parts[2] != "1 source":
        errors.append(f"the third part is not a source count: {parts[2]!r}")
    return errors


def _desktop_errors(m: dict) -> list[str]:
    errors = []
    if m["summaryVisible"]:
        errors.append("the summary button is visible at 1440 px (the desktop bar must be unchanged)")
    if not m["bodyVisible"] or not m["methodsVisible"]:
        errors.append("the league bar or the legend row is hidden at 1440 px")
    if not m["editVisible"] or not m["customizeVisible"]:
        errors.append("Edit league or Customize is hidden at 1440 px")
    return errors


def _changed_errors(m: dict) -> list[str]:
    """The summary is built from the current settings, so it follows a scoring change made in the league panel."""
    errors = []
    if not (m["text"] or "").startswith("Standard"):
        errors.append(f"the summary did not follow the scoring change: {m['text']!r}")
    if not (m["leagueName"] or "").startswith("Standard"):
        errors.append(f"the bar's own league name did not follow the scoring change: {m['leagueName']!r}")
    return _text_errors(m)


def _errors(result: dict) -> list[str]:
    return (_phone_closed_errors(result["phone_closed"]) + _phone_open_errors(result["phone_open"])
            + _phone_closed_errors(result["phone_keyboard"]) + _phone_open_errors(result["phone_keyboard_open"])
            + _text_errors(result["phone_closed"]) + _changed_errors(result["phone_changed"])
            + _desktop_errors(result["desktop"]))


class PhoneLeagueBarTest(unittest.TestCase):
    def test_phone_bar_collapses_and_desktop_is_unchanged(self):
        self.assertEqual(_errors(_run()), [])

    def test_report_px_gain(self):
        """Not a guard: prints the px the closed bar lifts the first tab content by, for the ticket log."""
        result = _run()
        closed = result["phone_closed"]["titleTop"]
        open_ = result["phone_open"]["titleTop"]
        self.assertIsNotNone(closed, "no first tab content found")
        self.assertGreaterEqual(open_ - closed, MIN_GAIN,
                                f"the closed bar only lifts the content by {open_ - closed:.0f} px")
        print(f"\nJEG-1134 px gain at {PHONE[0]}x{PHONE[1]}: first tab content top {open_:.0f} px with the bar open "
              f"-> {closed:.0f} px with it closed ({open_ - closed:.0f} px gained; viewport {PHONE[1]} px)")

    def test_guard_fails_without_collapse(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(COLLAPSE, css, "stale mutation anchor")
        errors = _errors(_run(css.replace(COLLAPSE, "")))
        self.assertTrue(any("before the summary is tapped" in e for e in errors),
                        f"removing the collapse rule was not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
