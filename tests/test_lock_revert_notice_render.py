"""Rendered regression for the QA-003 lock-revert notice (JEG-45).

The old code appended ``.lock-revert-notice`` and then immediately replaced
``#curve-status.innerHTML`` during the same settings change, so this browser
path failed before the notice ever painted.
"""

import functools
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


class LockRevertNoticeRenderTest(unittest.TestCase):
    def test_force_revert_notice_paints_then_auto_dismisses(self):
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
                        page.goto(url, wait_until="networkidle")
                        page.wait_for_function(
                            """() => window.TradeValueCurveControls
                              && document.querySelector("#curveLockOrder option[value='usatoday']")""",
                            timeout=15000,
                        )
                        page.evaluate(
                            """() => {
                              const controls = window.TradeValueCurveControls;
                              controls.setScoring("ppr");
                              controls.setTeams(12);
                              controls.setLockOrder("usatoday");
                              controls.setScoring("standard");
                              controls.setTeams(8);
                            }"""
                        )

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
                    finally:
                        browser.close()
            finally:
                server.shutdown()


if __name__ == "__main__":
    unittest.main()
