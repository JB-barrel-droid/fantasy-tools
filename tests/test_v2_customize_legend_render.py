"""JEG-907: the chart legend and Customize are one state.

  L1  A line hidden with the chart legend opens Customize unticked, with the "Hidden with the chart legend" note;
      "Select all" on its group ticks it and Done brings the column back and clears the strip's "hidden" count.
  L2  Reset to default + Done brings a legend-hidden default line back.
  L3  Ticking the unticked row alone + Done brings it back.
  L4  A legend hide is this visit's state only: a reload shows the column again (nothing in localStorage keeps it).

Discrimination: L1 against a build whose draft starts from every shown series (the legend-hidden one ticked, so
"Select all" reads "Select none"); L2/L3 against a build whose Done keeps the legend hide.
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
from tests import _render_env  # noqa: E402
from tests._holds import pin_holds_in_dist  # noqa: E402

V2_JS = ROOT / "app" / "v2" / "v2.js"
SERIES = "usatoday"
HAS_COL = "() => [...document.querySelectorAll('#v2Table thead th')].some(t => /USA Today/.test(t.textContent))"


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass

        class Server(socketserver.ThreadingTCPServer):
            request_queue_size = 128

        with Server(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def _open(browser, base, js=None):
    page = browser.new_page(viewport={"width": 1440, "height": 900})
    page.errors = []
    page.on("pageerror", lambda error: page.errors.append(str(error)))
    if js is not None:
        page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=js))
    page.goto(base, wait_until="networkidle")
    page.wait_for_selector("#v2Table tbody tr")
    page.wait_for_timeout(600)
    return page


def _hide_with_legend(page):
    page.click(f"#v2Legend .v2-legend-item[data-series='{SERIES}']")
    page.wait_for_timeout(300)
    if page.evaluate(HAS_COL):
        return ["premise: the legend hide did not remove the USA Today column"]
    return []


def _customize(page):
    page.click("#v2EditSources")
    page.wait_for_selector("#v2Popover .v2-panel-body")


def _done(page):
    page.click("#v2Popover [data-apply='sources']")
    page.wait_for_timeout(400)


def _strip(page):
    return page.text_content("#v2ShowingText") or ""


def _back(page, label):
    errors = []
    if not page.evaluate(HAS_COL):
        errors.append(f"{label}: the USA Today column is still gone")
    if "hidden" in _strip(page):
        errors.append(f"{label}: the strip still counts a legend hide: {_strip(page)!r}")
    if page.evaluate("() => !document.getElementById('v2Popover').hidden"):
        errors.append(f"{label}: the dialog stayed open (Done was blocked)")
    return errors


def check_l1_select_all(page):
    errors = _hide_with_legend(page)
    if errors:
        return errors
    _customize(page)
    row = page.text_content(f"#v2Popover [data-series='{SERIES}'] >> xpath=ancestor::label") or ""
    checked = page.evaluate(f"() => document.querySelector(\"#v2Popover [data-series='{SERIES}']\").checked")
    if checked:
        errors.append("L1: the legend-hidden line opens ticked although its column is gone")
    if "Hidden with the chart legend" not in row:
        errors.append(f"L1: the row does not say the legend hid it: {row!r}")
    call = page.text_content("#v2Popover [data-group='pub'] .v2-call") or ""
    if call.strip() != "Select all":
        errors.append(f"L1: the group control reads {call.strip()!r}, so there is no Select all to bring the line back")
    page.click("#v2Popover [data-group='pub'] .v2-call")
    if not page.evaluate(f"() => document.querySelector(\"#v2Popover [data-series='{SERIES}']\").checked"):
        errors.append("L1: Select all did not tick the legend-hidden line")
    _done(page)
    errors += _back(page, "L1 Select all + Done")
    if page.errors:
        errors.append(f"page errors: {page.errors[:2]}")
    return errors


def check_l2_reset(page):
    errors = _hide_with_legend(page)
    if errors:
        return errors
    _customize(page)
    page.click("#v2Popover .v2-preset")
    _done(page)
    return errors + _back(page, "L2 Reset to default + Done")


def check_l3_tick_row(page):
    errors = _hide_with_legend(page)
    if errors:
        return errors
    _customize(page)
    page.click(f"#v2Popover [data-series='{SERIES}']")
    _done(page)
    return errors + _back(page, "L3 tick the row + Done")


def check_l4_reload(page):
    errors = _hide_with_legend(page)
    if errors:
        return errors
    page.reload(wait_until="networkidle")
    page.wait_for_selector("#v2Table tbody tr")
    page.wait_for_timeout(600)
    return errors + _back(page, "L4 reload")


class CustomizeLegendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise _render_env.unavailable("playwright is not installed")
        exe = _render_env.chromium_executable()
        if exe is None and not _render_env.required():
            raise _render_env.unavailable("no browser")
        cls._stack = contextlib.ExitStack()
        cls.base = cls._stack.enter_context(_served())
        cls.pw = cls._stack.enter_context(sync_playwright())
        cls.browser = cls.pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
        cls.js = V2_JS.read_text(encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls._stack.close()

    def run_check(self, check, js=None):
        page = _open(self.browser, self.base, js)
        try:
            return check(page)
        except Exception as error:   # a control the check needs is missing: a failure, not a pass
            return [f"{check.__name__} raised {type(error).__name__}: {str(error).splitlines()[0][:160]}"]
        finally:
            page.close()

    def assertCaught(self, check, js, label):
        # A guard catches the bug only through a finding; a check that raised (a timeout, a missing control) is not a catch.
        errors = self.run_check(check, js)
        self.assertTrue(errors and not any(e.startswith(check.__name__) for e in errors), f"the guard did not catch: {label} ({errors})")

    def mutate(self, old, new):
        self.assertEqual(self.js.count(old), 1, f"stale mutation anchor: {old[:60]!r}")
        return self.js.replace(old, new)

    DRAFT_NEW = "const draft = new Set(onValues ? view.active.filter(key => key === view.rankKey || !state.hiddenSeries.has(key)) : pageKeys(page));"
    DRAFT_OLD = "const draft = new Set(onValues ? view.active : pageKeys(page));"
    CLEAR = "state.hiddenSeries.clear();   // JEG-907: the draft is the whole state; a legend hide never survives Done"

    def test_l1_select_all_brings_a_legend_hidden_line_back(self):
        self.assertEqual(self.run_check(check_l1_select_all), [])

    def test_l1_guard_catches_the_old_draft(self):
        js = self.mutate(self.DRAFT_NEW, self.DRAFT_OLD)
        self.assertCaught(check_l1_select_all, js, "the legend-hidden line opens ticked")

    def test_l2_reset_brings_a_legend_hidden_line_back(self):
        self.assertEqual(self.run_check(check_l2_reset), [])

    def test_l2_guard_catches_a_reset_that_keeps_the_hide(self):
        js = self.mutate(self.CLEAR, "")
        self.assertCaught(check_l2_reset, js, "Reset keeps a legend hide")

    def test_l3_ticking_the_row_brings_it_back(self):
        self.assertEqual(self.run_check(check_l3_tick_row), [])

    def test_l3_guard_catches_a_tick_that_keeps_the_hide(self):
        js = self.mutate(self.CLEAR, "")
        self.assertCaught(check_l3_tick_row, js, "ticking the row keeps a legend hide")

    def test_l4_a_legend_hide_does_not_survive_a_reload(self):
        self.assertEqual(self.run_check(check_l4_reload), [])


if __name__ == "__main__":
    unittest.main()
