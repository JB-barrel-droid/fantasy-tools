"""Phones get one column, and an empty search says so (JEG-955, JEG-827).

JEG-955: every content grid in the app stacks below 768 px. The last one that
was still side by side on a phone was the two-up number row in the "Value range"
and "Exact ranks" popovers: each field got half a phone width. They stack now.

JEG-827 (folded in): a search that matches no player must say so. The Values
tab shows "No players match." with a "Clear search" button, and the values table
card (a header-only table) is hidden.

Discrimination: test_guard_fails_on_old_css serves the CSS with the fix removed
and requires the check to fail.
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
WIDTH = 375

NEW = ".v2-popover .row2 { flex-direction: column; gap: 12px; }"
OLD = ".v2-popover .row2 { flex-direction: row; gap: 12px; }"


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


ROW2 = """() => {
  const row = document.querySelector('.v2-popover .row2');
  if (!row) return null;
  const kids = [...row.children].map(k => { const b = k.getBoundingClientRect();
    return {left: Math.round(b.left), top: Math.round(b.top), width: Math.round(b.width), height: Math.round(b.height)}; });
  return {dir: getComputedStyle(row).flexDirection, kids};
}"""

EMPTY = """() => {
  const empty = document.getElementById('v2Empty');
  const card = document.getElementById('v2TableCard');
  const visible = el => { const r = el.getBoundingClientRect(); return r.width > 0 && r.height > 0; };
  return {
    emptyVisible: visible(empty),
    emptyText: (empty.innerText || '').replace(/\\s+/g, ' '),
    clearButtons: [...empty.querySelectorAll('button')].filter(b => !b.hidden).map(b => b.textContent.trim()),
    tableCardVisible: visible(card),
    rows: document.querySelectorAll('#v2Table tbody tr').length,
  };
}"""


def _run(css=None) -> dict:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise _render_env.unavailable("playwright is not installed")
    exe = _render_env.chromium_executable()
    if exe is None and _render_env.required() is False:
        raise _render_env.unavailable("no browser")
    with _served() as base, sync_playwright() as p:
        browser = p.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        page = browser.new_page(viewport={"width": WIDTH, "height": 812}, is_mobile=True, has_touch=True)
        if css is not None:
            page.route("**/v2/v2.css*", lambda route: route.fulfill(status=200, content_type="text/css", body=css))
        page.goto(base + "#player-values", wait_until="networkidle")
        page.wait_for_timeout(1500)
        # "Set exact values..." opens the Value range popover with its two number fields.
        page.select_option("#v2Show", "exact")
        page.wait_for_timeout(800)
        row2 = page.evaluate(ROW2)
        page.keyboard.press("Escape")
        page.wait_for_timeout(300)
        # A search that matches nothing.
        page.fill("#v2Search", "zzzznotaplayer")
        page.wait_for_timeout(1000)
        empty = page.evaluate(EMPTY)
        page.close()
        browser.close()
    return {"row2": row2, "empty": empty}


def _errors(result) -> list[str]:
    errors = []
    row2 = result["row2"]
    if not row2:
        errors.append("the value range popover did not open")
    else:
        if row2["dir"] != "column":
            errors.append(f"the two number fields sit side by side ({row2['dir']}), not in one column")
        lefts = {kid["left"] for kid in row2["kids"]}
        if len(lefts) > 1:
            errors.append(f"the number fields are not in one column: lefts {sorted(lefts)}")
    empty = result["empty"]
    if not empty["emptyVisible"]:
        errors.append("no empty state shown for a search that matches nothing")
    if "No players match" not in empty["emptyText"]:
        errors.append(f"the empty state does not say \"No players match\": {empty['emptyText'][:80]!r}")
    if "Clear search" not in empty["clearButtons"]:
        errors.append(f"the empty state offers no Clear search button: {empty['clearButtons']}")
    if empty["tableCardVisible"]:
        errors.append("the values table card is still shown with no rows in it")
    if empty["rows"]:
        errors.append(f"{empty['rows']} table rows rendered for a search that matches nothing")
    return errors


class PhoneLayoutCollapseTest(unittest.TestCase):
    def test_one_column_and_an_empty_state(self):
        self.assertEqual(_errors(_run()), [])

    def test_guard_fails_on_old_css(self):
        css = CSS.read_text(encoding="utf-8")
        self.assertIn(NEW, css, "stale mutation anchor")
        self.assertTrue(_errors(_run(css.replace(NEW, OLD))), "old CSS was not caught")


if __name__ == "__main__":
    unittest.main()
