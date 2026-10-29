"""JEG-1232: the column order control and the reordered trade opportunities table, rendered (private preview).

Serves the repo and opens app/v2-concept/column-order.html (Fieldnotes tokens; illustrative rows; the column catalog, sort and saved-league
store are the site's own modules) headless at 1366x900 and 390x844, and checks:

  * an untouched league draws today's column order;
  * Move up / Move down work from the keyboard (Tab to reach them, Enter and Space to press), keep focus on the pressed
    button, announce the new position, and the end buttons stay focusable and announce "already first/last";
  * the order survives a reload (stored in the workspace's ui.columnOrder) and nothing else in ui changes;
  * header and body cells stay aligned in every order tried, the grouped Market perception header sits over Edge and
    Charts fair, and sorting from the header still sorts the rows;
  * a hidden optional column keeps its place and returns there when shown again; Reset restores the default;
  * on a phone the controls are 44px targets, the page does not scroll sideways and the card lines follow the order.

Set JEG1232_SCREENSHOTS=<dir> to save the desktop and phone screenshots used in the PR.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import os
import socketserver
import threading
import unittest
from pathlib import Path

from tests import _render_env

ROOT = Path(__file__).resolve().parents[1]
PAGE = "app/v2-concept/column-order.html"
BASE = ["opponent", "trade", "capture", "proj", "ours", "market", "theirs", "overall", "rank"]

HEAD_ORDER = """() => [...document.querySelectorAll('#v2LgOppsTable thead tr:first-child th')].map(th => th.dataset.col === 'marketGroup' ? 'market' : th.dataset.col)"""
# Every body cell sits under its own header cell: same left and right edge (1px), every row, the group over its two cells.
ALIGNED = """() => {
  const box = n => n.getBoundingClientRect();
  const near = (a, b) => Math.abs(a - b) <= 1;
  const head = id => document.querySelector(`#v2LgOppsTable thead th[data-col="${id}"]`);
  const errors = [];
  document.querySelectorAll('#v2LgOppsTable tbody tr').forEach(tr => {
    [...tr.children].forEach(cell => {
      const id = cell.dataset.cell; const th = head(id);
      if (!th) { errors.push(`no header for ${id}`); return; }
      const a = box(th), b = box(cell);
      if (!near(a.left, b.left) || !near(a.right, b.right)) errors.push(`${id}: header ${a.left}-${a.right}, cell ${b.left}-${b.right}`);
    });
    const g = head('marketGroup'), m = tr.querySelector('[data-cell="market"]'), f = tr.querySelector('[data-cell="fair"]');
    if (g && (!near(box(g).left, box(m).left) || !near(box(g).right, box(f).right))) errors.push('Market perception is not over Edge and Charts fair');
    if (tr.children.length !== document.querySelectorAll('#v2LgOppsTable thead tr:first-child th').length + 1) errors.push('cell count');
  });
  return errors;
}"""
BODY = """() => [...document.querySelectorAll('#v2LgOppsTable tbody tr')].map(tr => ({rank: tr.querySelector('[data-cell="rank"]').textContent,
  capture: Number(tr.querySelector('[data-cell="capture"]').textContent.replace(' pts', '')), first: tr.children[0].dataset.cell}))"""
FOCUS = """() => { const a = document.activeElement; return a ? {column: a.dataset.column || null, move: a.dataset.move || null, tag: a.tagName, sort: a.dataset.sort || null} : null; }"""
UI = """() => JSON.parse(JSON.stringify(window.TradeValueWorkspace.store.get().ui))"""


@contextlib.contextmanager
def _server():
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(ROOT))) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/{PAGE}"
        finally:
            server.shutdown()


class ColumnOrderRenderTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        cls._stack = contextlib.ExitStack()
        cls.url = cls._stack.enter_context(_server())
        cls.pw = cls._stack.enter_context(sync_playwright())
        try:
            cls.browser = cls.pw.chromium.launch(args=_render_env.HERMETIC_ARGS + ["--no-sandbox"], executable_path=_render_env.chromium_executable(cls.pw))
        except Exception as exc:
            cls._stack.close()
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        cls.shots = os.environ.get("JEG1232_SCREENSHOTS")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._stack.close()

    def open(self, width=1366, height=900):
        context = self.browser.new_context(viewport={"width": width, "height": height}, device_scale_factor=2 if width < 768 else 1)
        self.addCleanup(context.close)
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda e: errors.append(str(e)))
        self.addCleanup(lambda: self.assertEqual(errors, [], "no page errors"))
        page.goto(self.url)
        page.wait_for_selector("#v2LgOppsTable", state="attached")
        return page

    def press(self, page, column, move, key="Enter"):
        page.focus(f'button[data-column="{column}"][data-move="{move}"]')
        page.keyboard.press(key)
        page.wait_for_function("() => document.getElementById('previewAnnounce').textContent !== ''")
        return page.text_content("#previewAnnounce")

    def test_default_order_aligned(self):
        page = self.open()
        self.assertEqual(page.evaluate(HEAD_ORDER), BASE)
        self.assertEqual(page.evaluate(ALIGNED), [])
        self.assertFalse(page.is_visible("#v2LgColumnOrderReset"), "nothing to reset for an untouched league")
        self.assertNotIn("columnOrder", page.evaluate(UI), "an untouched league stores no order")

    def test_keyboard_move_focus_and_announce(self):
        page = self.open()
        # Tab reaches the move buttons from the control's summary.
        page.focus("#v2LgColumnOrder summary")
        page.keyboard.press("Tab")
        self.assertEqual(page.evaluate(FOCUS)["move"], "up")
        self.assertEqual(page.get_attribute('button[data-column="opponent"][data-move="up"]', "aria-disabled"), "true")
        self.assertEqual(self.press(page, "capture", "up"), "DDF Value capture moved to position 2 of 9.")
        self.assertEqual(page.evaluate(FOCUS), {"column": "capture", "move": "up", "tag": "BUTTON", "sort": None}, "focus stays on the pressed button")
        self.assertEqual(self.press(page, "capture", "up", "Space"), "DDF Value capture moved to position 1 of 9.")
        self.assertEqual(page.evaluate(HEAD_ORDER)[:3], ["capture", "opponent", "trade"])
        self.assertEqual(page.evaluate(FOCUS)["column"], "capture", "focus kept when the column reaches the end")
        self.assertEqual(page.get_attribute('button[data-column="capture"][data-move="up"]', "aria-disabled"), "true")
        self.assertEqual(self.press(page, "capture", "up"), "DDF Value capture is already first.")
        self.assertEqual(page.evaluate(HEAD_ORDER)[0], "capture", "an end press changes nothing")
        self.assertEqual(self.press(page, "market", "down"), "Market perception moved to position 7 of 9.")
        self.assertEqual(page.evaluate(ALIGNED), [])
        label = page.get_attribute('button[data-column="market"][data-move="down"]', "aria-label")
        self.assertEqual(label, "Move Market perception down")
        described = page.evaluate("""() => document.getElementById(document.querySelector('button[data-column="market"][data-move="down"]').getAttribute('aria-describedby')).textContent""")
        self.assertEqual(described, "7 of 9")

    def test_saved_across_reload_and_nothing_else_changes(self):
        page = self.open()
        before = page.evaluate(UI)
        self.press(page, "rank", "up")
        self.press(page, "rank", "up")
        after = page.evaluate(UI)
        order = after.pop("columnOrder")
        self.assertEqual(after, before, "sort, filters, summary columns and basis are unchanged")
        self.assertEqual(order["opps"][6:], ["rank", "theirs", "overall"])
        page.reload()
        page.wait_for_selector("#v2LgOppsTable")
        self.assertEqual(page.evaluate(HEAD_ORDER)[6:], ["rank", "theirs", "overall"])
        self.assertTrue(page.is_visible("#v2LgColumnOrderReset"))
        stored = page.evaluate("() => JSON.parse(localStorage.getItem(window.TradeValueWorkspace.STORAGE_KEY))")
        self.assertTrue(any((w.get("ui") or {}).get("columnOrder") for w in stored["workspaces"]))

    def test_sorting_and_alignment_in_every_order(self):
        page = self.open()
        default_ranks = [r["rank"] for r in page.evaluate(BODY)]
        orders = [("rank", "up"), ("trade", "down"), ("opponent", "down"), ("market", "up"), ("market", "up")]
        for column, move in orders:
            self.press(page, column, move)
            self.assertEqual(page.evaluate(ALIGNED), [], f"aligned after moving {column} {move}")
        page.click('button[data-sort="capture"]')
        page.wait_for_selector('th[data-col="capture"][aria-sort="descending"]')
        rows = page.evaluate(BODY)
        self.assertEqual([r["capture"] for r in rows], sorted((r["capture"] for r in rows), reverse=True), "sorted by capture, highest first")
        self.assertEqual(sorted(r["rank"] for r in rows), sorted(default_ranks), "rank text does not change with the order or the sort")
        self.assertEqual(page.evaluate(ALIGNED), [])
        self.assertEqual(page.evaluate("() => document.querySelectorAll('#v2LgOppsTable th[aria-sort]:not([aria-sort=\"none\"])').length"), 1)
        page.click('button[data-sort="fair"]')
        page.wait_for_selector('th[data-col="fair"][aria-sort="descending"]')
        self.assertEqual(page.evaluate(ALIGNED), [])

    def test_hidden_column_keeps_its_place_and_reset(self):
        page = self.open()
        page.check('input[data-summary-column="theirs:rosterF"]')
        page.wait_for_selector('th[data-col="summary:theirs:rosterF"]')
        self.assertEqual(page.evaluate(HEAD_ORDER)[-1], "summary:theirs:rosterF", "a newly shown column goes where it goes today, after the base columns")
        for _ in range(9):
            self.press(page, "summary:theirs:rosterF", "up")
        self.assertEqual(page.evaluate(HEAD_ORDER)[0], "summary:theirs:rosterF")
        self.assertEqual(page.evaluate(ALIGNED), [])
        page.uncheck('input[data-summary-column="theirs:rosterF"]')
        page.wait_for_function("() => !document.querySelector('th[data-col=\"summary:theirs:rosterF\"]')")
        self.assertEqual(page.evaluate(HEAD_ORDER), BASE)
        page.check('input[data-summary-column="theirs:rosterF"]')
        page.wait_for_selector('th[data-col="summary:theirs:rosterF"]')
        self.assertEqual(page.evaluate(HEAD_ORDER)[0], "summary:theirs:rosterF", "back in its saved place")
        summary_cols = page.evaluate(UI)["summaryColumns"]
        page.click("#v2LgColumnOrderReset")
        page.wait_for_function("() => document.querySelector('#v2LgOppsTable thead th').dataset.col === 'opponent'")
        self.assertEqual(page.evaluate(HEAD_ORDER), BASE + ["summary:theirs:rosterF"])
        ui = page.evaluate(UI)
        self.assertNotIn("opps", ui.get("columnOrder", {}), "Reset removes the saved order")
        self.assertEqual(ui["summaryColumns"], summary_cols, "Reset leaves the shown columns alone")
        self.assertEqual(page.evaluate(FOCUS)["tag"], "SUMMARY", "focus goes to the control after Reset")
        self.assertFalse(page.is_visible("#v2LgColumnOrderReset"))
        if self.shots:
            Path(self.shots).mkdir(parents=True, exist_ok=True)
            self.press(page, "capture", "up")
            self.press(page, "capture", "up")
            page.screenshot(path=str(Path(self.shots) / "column-order-1366-fieldnotes.png"), full_page=True)
            page.goto(self.url + "?theme=live")
            page.wait_for_selector("#v2LgOppsTable")
            page.screenshot(path=str(Path(self.shots) / "column-order-1366-live.png"), full_page=True)

    def test_phone(self):
        page = self.open(390, 844)
        self.assertTrue(page.is_visible("#v2LgOppsCards"))
        self.assertEqual(page.evaluate("() => document.documentElement.scrollWidth <= window.innerWidth"), True, "no sideways scroll")
        sizes = page.evaluate("() => [...document.querySelectorAll('.v2-colorder-move')].map(b => { const r = b.getBoundingClientRect(); return [r.width, r.height]; })")
        self.assertTrue(all(w >= 44 and h >= 44 for w, h in sizes), sizes)
        page.click('button[data-column="theirs"][data-move="up"]')
        page.wait_for_function("() => document.getElementById('previewAnnounce').textContent !== ''")
        lines = page.evaluate("() => [...document.querySelector('#v2LgOppsCards li').querySelectorAll('[data-line]')].map(p => p.dataset.line)")
        self.assertEqual(lines, ["trade", "capture", "proj", "ours", "theirs", "market"], "card lines follow the saved order")
        if self.shots:
            page.screenshot(path=str(Path(self.shots) / "column-order-390-fieldnotes.png"), full_page=True)


if __name__ == "__main__":
    unittest.main()
