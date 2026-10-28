"""Phone context row collapses to one summary line (JEG-1134).

Jeremy picked option C on 2026-10-27: measure the context row (#v2Context, JEG-1119) on a phone, then A (it is already
one line, about 48 px) or B (taller: rebuild the one-line summary on it). Below 1024 px the row wraps onto three lines
(league and freshness, the buttons, the "On the chart" line), so B. Below 768 px the row is now one line: a summary
("Full PPR · 12 teams · 4 sources") and the freshness chip. Tapping the summary opens the roster line, Edit league,
Customize, the ⋯ menu and the "On the chart" line under it. Jeremy's two decisions from option A (2026-10-26) carry
over: the "On the chart" line may hide while the row is closed, and the source count leaves out DDF Value.

Checks at 390x844 and 375x667: closed, the row is one line no taller than 48 px with the freshness chip on the summary's
line, Edit league, Customize, ⋯ and the "On the chart" line are not shown, and the summary's count equals the outside
sources in the legend; open, those controls show, Edit league opens its panel, and nothing scrolls sideways. At 1440x900
the summary is not rendered and Edit league and Customize show as before.
Discrimination: test_guard_fails_without_the_collapse serves v2.css without the JEG-1134 block (the wrapped row on main
before this change) and requires failures. Each run prints one JEG1134-MEASURE line per width with the row's height.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import re
import socketserver
import sys
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
CSS = ROOT / "app" / "v2" / "v2.css"
PHONES = ((390, 844), (375, 667))
ONE_LINE_MAX = 48
SUMMARY = re.compile(r"^(Standard|Half PPR|Full PPR) · \d+ teams · (\d+ sources?|DDF Value only)$")
# The JEG-1134 block in v2.css, from its opening comment to the end of its phone media query.
BLOCK = re.compile(r"/\* JEG-1134 \(Jeremy 2026-10-27.*?\n\}\n", re.S)


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
  const ctx = document.getElementById('v2Context');
  const r = ctx.getBoundingClientRect();
  const shown = id => { const e = document.getElementById(id); return Boolean(e && e.offsetParent && e.getBoundingClientRect().height > 0); };
  const mid = e => { const b = e.getBoundingClientRect(); return (b.top + b.bottom) / 2; };
  const summary = document.getElementById('v2ContextSummary');
  const fresh = document.getElementById('v2Freshness');
  const basis = document.querySelector('#v2Context .v2-ctx-basis');
  const outside = [...document.querySelectorAll('#v2ShowingLegend li')]
    .filter(li => !/[★✦]/.test((li.querySelector('.v2-sym') || {}).textContent || '')).length;
  return {height: Math.round(r.height * 10) / 10,
          summaryShown: shown('v2ContextSummary'), expanded: summary.getAttribute('aria-expanded'),
          summaryText: document.getElementById('v2ContextSummaryText').textContent.trim(), outside,
          sameLine: shown('v2ContextSummary') && shown('v2Freshness') ? Math.abs(mid(summary) - mid(fresh)) <= 2 : null,
          summaryHeight: summary.getBoundingClientRect().height,
          edit: shown('v2EditLeague'), customize: shown('v2EditSources'), more: shown('v2ContextMore'),
          basis: Boolean(basis && basis.offsetParent && basis.getBoundingClientRect().height > 0),
          freshness: shown('v2Freshness'), overflow: document.documentElement.scrollWidth - innerWidth};
}"""


def _playwright():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    return sync_playwright


def run_checks(css=None) -> list[str]:
    sync_playwright = _playwright()
    errors: list[str] = []
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=_render_env.chromium_executable(p), args=_render_env.HERMETIC_ARGS)
        try:
            for width, height in PHONES + ((1440, 900),):
                tag = f"[{width}x{height}]"
                page = browser.new_page(viewport={"width": width, "height": height}, device_scale_factor=1)
                page_errors: list[str] = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.add_init_script(_render_env.pin_data_week_script())
                if css is not None:
                    page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
                page.goto(base + "#player-values", wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr')", timeout=60000)
                page.wait_for_timeout(500)
                m = page.evaluate(MEASURE)
                print(f"JEG1134-MEASURE {tag} closed: {json.dumps(m)}", file=sys.stderr)
                if width >= 768:
                    if m["summaryShown"]:
                        errors.append(f"{tag} the phone summary shows on a wide screen: {m}")
                    if not (m["edit"] and m["customize"] and m["more"] and m["basis"]):
                        errors.append(f"{tag} the wide row lost a control: {m}")
                else:
                    if not m["summaryShown"] or m["summaryHeight"] < 44:
                        errors.append(f"{tag} no 44 px summary line: {m}")
                    if m["height"] > ONE_LINE_MAX:
                        errors.append(f"{tag} closed row is {m['height']} px, want one line of at most {ONE_LINE_MAX}")
                    if m["edit"] or m["customize"] or m["more"] or m["basis"]:
                        errors.append(f"{tag} closed row still shows controls: {m}")
                    if not m["freshness"] or not m["sameLine"]:
                        errors.append(f"{tag} freshness chip is not on the summary's line: {m}")
                    if not SUMMARY.match(m["summaryText"]):
                        errors.append(f"{tag} summary reads {m['summaryText']!r}")
                    count = re.search(r"(\d+) sources?$", m["summaryText"])
                    if (int(count.group(1)) if count else 0) != m["outside"]:
                        errors.append(f"{tag} summary {m['summaryText']!r} but {m['outside']} outside sources in the legend (DDF Value is not counted)")
                    if m["summaryShown"]:
                        page.click("#v2ContextSummary")
                        page.wait_for_timeout(200)
                        o = page.evaluate(MEASURE)
                        print(f"JEG1134-MEASURE {tag} open: {json.dumps(o)}", file=sys.stderr)
                        if o["expanded"] != "true" or not (o["edit"] and o["customize"] and o["more"] and o["basis"]):
                            errors.append(f"{tag} open row does not show its controls: {o}")
                        if o["overflow"] > 0:
                            errors.append(f"{tag} open row scrolls sideways by {o['overflow']} px")
                        if o["edit"]:
                            page.click("#v2EditLeague")
                            page.wait_for_timeout(300)
                            if page.evaluate("() => document.getElementById('v2Popover').hidden"):
                                errors.append(f"{tag} Edit league did not open its panel from the open row")
                            page.keyboard.press("Escape")
                            page.wait_for_timeout(200)
                        page.click("#v2ContextSummary")
                        page.wait_for_timeout(200)
                        c = page.evaluate(MEASURE)
                        if c["expanded"] != "false" or c["edit"] or c["height"] > ONE_LINE_MAX:
                            errors.append(f"{tag} second tap did not close the row: {c}")
                if m["overflow"] > 0:
                    errors.append(f"{tag} page scrolls sideways by {m['overflow']} px")
                if page_errors:
                    errors.append(f"{tag} page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class PhoneContextRowTest(unittest.TestCase):
    def test_phone_row_is_one_summary_line_that_opens(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_without_the_collapse(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertEqual(len(BLOCK.findall(css)), 1, "the JEG-1134 block in v2.css was not found")
        self.assertNotEqual(run_checks(css=BLOCK.sub("", css)), [], "the checks passed with the JEG-1134 CSS removed")


if __name__ == "__main__":
    unittest.main()
