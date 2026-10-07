"""Rendered regression for the QA-003 lock-revert notice (JEG-45)
and the DEFECT 2 lock-caption invariant.

QA-003: the old code appended ``.lock-revert-notice`` and then immediately
replaced ``#curve-status.innerHTML`` during the same settings change, so this
browser path failed before the notice ever painted.

DEFECT 2: the old code re-rendered the "locked to ..." caption inside
``rebuildDomain()`` -- BEFORE the forced lock reset -- so the caption kept
the stale pre-reset lock label after a team-size change made the locked
source unavailable. The fix calls ``syncContext()`` after the reset, so the
caption must name the new lock order.
"""

import contextlib
import functools
import json
import http.server
import shutil
import socketserver
import threading
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"


def _chromium_executable(playwright):
    candidates = [
        Path(playwright.chromium.executable_path),
        Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
    ]
    chromium = shutil.which("chromium")
    if chromium:
        candidates.append(Path(chromium))
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return None


def _without_usatoday_standard(route):
    """Serve the fixture with USA Today's saved standard-scoring setup removed.

    JEG-332 (league-settings-001): published charts are now derived in the
    browser at 8/10/14 teams, so switching team size no longer makes USA
    Today unavailable -- the old trigger for this test. The one remaining way
    a published source becomes unavailable is a scoring with no saved 12-team
    setup, so the test simulates exactly that.
    """
    path = APP / "assets" / "comparison-sources-data.json"
    doc = json.loads(path.read_text(encoding="utf-8"))
    doc["sources"]["usatoday"]["combos"].pop("standard_12", None)
    route.fulfill(status=200, content_type="application/json", body=json.dumps(doc))


@contextlib.contextmanager
def _chart_page():
    """Serve the chart app and yield a Playwright page on it."""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc

    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

    handler = functools.partial(
        QuietHandler,
        directory=str(APP),
    )
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            url = f"http://127.0.0.1:{server.server_address[1]}/"
            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(
                        executable_path=_chromium_executable(playwright)
                    )
                except PlaywrightError as exc:
                    raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc
                try:
                    page = browser.new_page()
                    page.route("**/assets/comparison-sources-data.json*", _without_usatoday_standard)
                    page.goto(url, wait_until="networkidle")
                    page.wait_for_function(
                        """() => window.TradeValueCurveControls
                          && document.querySelector("#curveLockOrder option[value='usatoday']")""",
                        timeout=15000,
                    )
                    yield page
                finally:
                    browser.close()
        finally:
            server.shutdown()


def _drive_forced_reset(page):
    """Lock to USA Today, then switch to a scoring it has no saved setup for.

    Before JEG-332 the trigger was a team-size change (USA Today was saved at
    12 teams only); team sizes are now derived in the browser, so the forced
    reset is driven by the scoring _without_usatoday_standard removes.
    """
    # View tabs must be bound on initial load and changing settings in
    # another view must still rebuild Indexed data. JEG-392: this used to
    # wait on #viewModePending / #viewModeChartArea, placeholder panels from
    # the pre-JEG-210 design that the shipped page never renders (the VORP
    # and Adj views now draw in place), so the test timed out on every run.
    # Wait on the tab's own selected state instead.
    page.locator('#viewModeTabs [data-view-mode="vorp"]').click()
    page.wait_for_selector('#viewModeVorpTab[aria-selected="true"]', timeout=5000)
    page.evaluate('() => window.TradeValueCurveControls.setScoring("standard")')
    page.locator('#viewModeTabs [data-view-mode="indexed"]').click()
    page.wait_for_selector('#viewModeIndexedTab[aria-selected="true"]', timeout=5000)
    page.evaluate(
        """() => {
          const controls = window.TradeValueCurveControls;
          controls.setScoring("ppr");
          controls.setTeams(12);
          controls.setLockOrder("usatoday");
          controls.setScoring("standard");
        }"""
    )


class LockRevertNoticeRenderTest(unittest.TestCase):
    def test_force_revert_notice_paints_then_auto_dismisses(self):
        with _chart_page() as page:
            _drive_forced_reset(page)

            notice = page.wait_for_selector(".lock-revert-notice", timeout=2000)
            text = notice.inner_text()
            self.assertIn("Player lock order was reset", text)
            self.assertIn("USA Today", text)
            self.assertIn("ESPN adjusted", text)
            self.assertEqual(
                page.locator(".lock-revert-notice").count(),
                1,
                "force-revert should show exactly one visible notice",
            )

            page.wait_for_selector(".lock-revert-notice", state="detached", timeout=9000)

    def test_forced_lock_reset_updates_caption(self):
        """DEFECT 2: after a forced lock reset, the 'locked to ...' caption
        must name the NEW lock order, not the stale pre-reset source."""
        with _chart_page() as page:
            _drive_forced_reset(page)
            page.wait_for_selector(".lock-revert-notice", timeout=2000)

            caption = page.locator("#curveContext").inner_text()
            self.assertIn(
                "locked to ESPN adjusted value",
                caption,
                "caption must re-render with the post-reset lock order",
            )
            self.assertNotIn(
                "USA Today",
                caption,
                "caption must not keep the stale pre-reset lock label",
            )


if __name__ == "__main__":
    unittest.main()
