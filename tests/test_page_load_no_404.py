"""GAP-CONSOLIDATED-PROBE-404: no page load requests a file that is not there.

consolidation-index.js probed assets/consolidated-values.json on every load.
The artifact is published at the site root, never under assets/, so every load
of /, /classic/ and /v2/ logged a 404, for data nothing reads (no caller of
ConsolidationIndex.lookup()). The probe is removed.

This test loads each page of the built dist/ and requires zero 4xx/5xx
responses. Discrimination (test_guard_catches_the_probe): with the pre-fix
consolidation-index.js (dac0ff2, read from git; skipped when absent) the same
check sees the 404.
"""
from __future__ import annotations

import subprocess
import unittest

from tests._dist_server import DIST, ROOT, chromium_executable, serve
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


PRE_FIX_COMMIT = "dac0ff2"
PAGES = ("/", "/classic/", "/v2/")


def failed_requests(overrides=None):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    bad = []
    with sync_playwright() as p:
        exe = chromium_executable(p)
        if exe is None:
            raise _render_env.unavailable("no Chromium available")
        browser = p.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=exe)
        try:
            with serve(DIST, overrides) as base:
                for path in PAGES:
                    page = browser.new_page()
                    page.on("response", lambda r, path=path: r.status >= 400
                            and bad.append((path, r.status, r.url.replace(base, ""))))
                    page.goto(base + path, wait_until="networkidle")
                    page.wait_for_function("() => window.TradeValueCurveDiagnostics", timeout=30000)
                    page.wait_for_timeout(500)
                    page.close()
        finally:
            browser.close()
    return bad


class PageLoadNo404Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not (DIST / "classic" / "index.html").exists():
            raise _render_env.unavailable("dist/ not built (run make sync)")

    def test_no_failed_requests(self):
        self.assertEqual(failed_requests(), [])

    def test_guard_catches_the_probe(self):
        proc = subprocess.run(["git", "show", f"{PRE_FIX_COMMIT}:app/trade-value-chart/assets/consolidation-index.js"],
                              cwd=ROOT, capture_output=True)
        if proc.returncode != 0:
            self.skipTest(f"{PRE_FIX_COMMIT} not in this clone")
        bad = failed_requests({"assets/consolidation-index.js": proc.stdout})
        self.assertTrue(any("consolidated-values.json" in url and status == 404 for _, status, url in bad), bad)


if __name__ == "__main__":
    unittest.main()
