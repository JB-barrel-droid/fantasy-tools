"""Launch front door (Jeremy, 2026-10-08).

- v2 is the front door: the site root serves the v2 page itself (no redirect
  hop); /v2/ keeps working as the same page with a canonical to the root; the
  chart dashboard moves to /classic/ with a canonical to itself.
- The "Dashboard health" box is hidden on public pages (its checks still run).
- Monitor pages under modules/ are deployed but linked from no public page.
- The "Chart build" stamp sits in the footer.
- Titles carry the brand: v2 is "Data Driven Football"; the classic dashboard is "Trade Value · Data Driven Football".

The static tests run against the builders and sources; the rendered test
serves the built dist/ under /fantasy-tools/ (as GitHub Pages does) and needs
`make sync` plus Playwright with a Chromium (CHROMIUM_PATH or Playwright's).
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import os
import re
import shutil
import socketserver
import sys
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import build_v2_page  # noqa: E402
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


APP = ROOT / "app" / "trade-value-chart"
DIST = ROOT / "dist"
SITE = "https://jb-barrel-droid.github.io/fantasy-tools/"
BRAND_TITLE = "<title>Trade Value · Data Driven Football</title>"
# v2 carries the brand alone (Jeremy, 2026-10-08); the classic dashboard keeps BRAND_TITLE.
V2_TITLE = "Data Driven Football"
PUBLIC_SOURCES = [APP / "index.html", APP / "404.html", ROOT / "app" / "v2" / "shell.html",
                  ROOT / "waiver_wire" / "dashboard" / "index.html",
                  ROOT / "weekly_vegas" / "dashboard" / "index.html"]


def _sync_module():
    import sync_dashboard_artifacts
    return sync_dashboard_artifacts


def head_of(html: str) -> str:
    return html[:html.index("</head>")]


def monitor_links(html: str) -> list:
    return [h for h in re.findall(r'href="([^"]*)"', html) if re.search(r'(^|/)modules/', h)]


def health_box_hidden(html: str) -> bool:
    match = re.search(r'<div class="health-cluster"[^>]*>', html)
    return bool(match) and re.search(r'\shidden(\s|>|=)', match.group(0)) is not None


def chart_build_in_footer(html: str) -> bool:
    footer = re.search(r"<footer\b.*?</footer>", html, re.S)
    return bool(footer) and 'id="asOfDate"' in footer.group(0) and 'id="buildStamp"' in footer.group(0)


class FrontDoorBuildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app_html = (APP / "index.html").read_text(encoding="utf-8")
        cls.shell = (ROOT / "app" / "v2" / "shell.html").read_text(encoding="utf-8")
        cls.classic = _sync_module().classic_page_html(cls.app_html)
        cls.root = build_v2_page.build_v2_html(cls.classic, cls.shell, at_root=True)
        cls.v2 = build_v2_page.build_v2_html(cls.classic, cls.shell)

    def test_root_page_is_v2_without_base(self):
        head = head_of(self.root)
        self.assertIn('<body class="v2">', self.root)
        self.assertNotIn("<base", head)
        self.assertIn(f'<link rel="canonical" href="{SITE}">', head)
        self.assertNotIn('name="robots"', head)
        self.assertIn(f"<title>{V2_TITLE}</title>", head)
        self.assertNotIn("every source on one scale", head)  # classic description/og copy
        # Tabs stay on the root page; no static link sends a visitor to /v2/.
        self.assertNotIn('href="v2/#', self.root.split('<div id="legacyEngine"')[0])
        self.assertIn('href="#trade-targets"', self.root)

    def test_v2_path_is_same_page_canonical_to_root(self):
        head = head_of(self.v2)
        self.assertEqual(1, head.count("<base "))
        self.assertIn('<base href="../">', head)
        self.assertIn(f'<link rel="canonical" href="{SITE}">', head)
        self.assertNotIn(f"{SITE}classic/", head)
        self.assertNotIn('name="robots"', head)
        self.assertIn('href="v2/#trade-targets"', self.v2)

    def test_classic_page_head_and_links(self):
        head = head_of(self.classic)
        self.assertIn('<base href="../">', head)
        self.assertIn(f'<link rel="canonical" href="{SITE}classic/">', head)
        self.assertIn('<meta name="robots" content="noindex, follow">', head)
        # A bare "#x" link under <base href="../"> would jump to the root page.
        self.assertNotRegex(self.classic, r'href="#')

    def test_build_reads_classic_and_writes_root(self):
        sync_src = (ROOT / "pipelines" / "sync_dashboard_artifacts.py").read_text(encoding="utf-8")
        self.assertNotRegex(sync_src, r'for name in \([^)]*"index\.html"',
                            "sync must not publish the chart dashboard at the site root")
        self.assertEqual(Path("classic") / "index.html", build_v2_page.CLASSIC_INPUT)

    def test_main_page_title_health_box_and_footer(self):
        self.assertIn(BRAND_TITLE, self.app_html)
        self.assertTrue(health_box_hidden(self.app_html), "Dashboard health box must be hidden")
        self.assertTrue(chart_build_in_footer(self.app_html), "Chart build stamp must be in the footer")
        # The checks keep running: the elements they write to are still in the page.
        for element_id in ("chartHealthBadge", "chartHealthList", "datasetHealthRows", "dataHealthTitle"):
            self.assertIn(f'id="{element_id}"', self.app_html)
        # Negative: the pre-launch header is caught.
        old = ('<div class="health-cluster" aria-label="Dashboard health"><div class="vintage-item">'
               '<span>Chart build</span><strong id="asOfDate">—</strong></div></div>'
               '<footer><span id="buildStamp">Build x</span></footer>')
        self.assertFalse(health_box_hidden(old))
        self.assertFalse(chart_build_in_footer(old))

    def test_no_public_page_links_monitor_pages(self):
        for path in PUBLIC_SOURCES:
            self.assertEqual([], monitor_links(path.read_text(encoding="utf-8")), str(path))
        for html in (self.root, self.v2, self.classic):
            self.assertEqual([], monitor_links(html))
        self.assertEqual(["modules/status.html"], monitor_links('<a href="modules/status.html">Status</a>'))


def _chromium_executable(playwright):
    return _render_env.chromium_executable(playwright)


@contextlib.contextmanager
def _pages_server(dist: Path):
    """Serve dist/ under /fantasy-tools/ with dist/404.html for misses, like Pages."""
    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send_error(self, code, message=None, explain=None):
            if code == 404:
                body = (dist / "404.html").read_bytes()
                self.send_response(404)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            super().send_error(code, message, explain)

        def translate_path(self, path):
            prefix = "/fantasy-tools/"
            if not path.startswith(prefix):
                return str(dist / "__outside_project__")
            return super().translate_path("/" + path[len(prefix):])

    handler = functools.partial(Handler, directory=str(dist))
    with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
        server.daemon_threads = True
        threading.Thread(target=server.serve_forever, daemon=True).start()
        try:
            yield f"http://127.0.0.1:{server.server_address[1]}/fantasy-tools/"
        finally:
            server.shutdown()


ROWS_JS = """() => window.TradeValueCurveControls.getAllRows()
  .map(r => [r.key || r.player_key || r.name, JSON.stringify(r.values)]).sort()"""


class FrontDoorRenderedTests(unittest.TestCase):
    def test_rendered_front_door(self):
        if not (DIST / "classic" / "index.html").exists():
            raise _render_env.unavailable("dist/classic/index.html is not built (run make sync)")
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:
            raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
        with _pages_server(DIST) as base, sync_playwright() as playwright:
            executable = _chromium_executable(playwright)
            if not executable:
                raise _render_env.unavailable("Chromium is not available")
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=executable)
            try:
                def open_page(url):
                    page = browser.new_page(viewport={"width": 1440, "height": 1000})
                    errors = []
                    page.on("pageerror", lambda e: errors.append(str(e)))
                    page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                    response = page.goto(url, wait_until="networkidle", timeout=120000)
                    return page, errors, response

                def engine_ready(page):
                    page.wait_for_function("() => window.TradeValueCurveControls"
                                           " && window.TradeValueCurveControls.getAllRows().length > 0",
                                           timeout=60000)

                # Root: the v2 page itself, branded, canonical, no page errors.
                page, errors, _ = open_page(base)
                engine_ready(page)
                # Landing tab is Trade targets (Jeremy, 2026-10-08).
                page.wait_for_selector("#v2Targets:not([hidden])", timeout=60000)
                self.assertEqual([], errors)
                self.assertEqual(V2_TITLE, page.title())
                self.assertEqual(SITE, page.eval_on_selector('link[rel="canonical"]', "e => e.href"))
                v2_rows = page.evaluate(ROWS_JS)
                self.assertGreater(len(v2_rows), 100)
                # A tab click stays on the root page.
                page.click('.v2-tab[data-view="values"]')
                page.wait_for_selector("#v2Main:not([hidden])", timeout=30000)
                self.assertEqual(base + "#player-values", page.url)
                # Links v2.js builds at runtime as "v2/#view" (the drawer's
                # "Open Compare a trade") also stay on the root page.
                page.evaluate("""() => { const a = document.createElement('a');
                    a.id = 'shimProbe'; a.href = 'v2/#compare-trade'; a.textContent = 'probe';
                    document.body.prepend(a); }""")
                page.evaluate("() => document.getElementById('shimProbe').click()")
                page.wait_for_selector("#v2Compare:not([hidden])", timeout=30000)
                self.assertEqual(base + "#compare-trade", page.url)
                self.assertTrue(page.evaluate("() => !!document.getElementById('shimProbe')"),
                                "the root page reloaded instead of switching tabs")
                page.close()

                # /v2/ and its deep links still work.
                for url, shown in ((base + "v2/", "#v2Targets"), (base + "v2/#player-values", "#v2Main")):
                    page, errors, response = open_page(url)
                    self.assertEqual(200, response.status, url)
                    page.wait_for_selector(f"{shown}:not([hidden])", timeout=60000)
                    self.assertEqual([], errors, url)
                    self.assertEqual(SITE, page.eval_on_selector('link[rel="canonical"]', "e => e.href"))
                    page.close()

                # /classic/: the chart dashboard, same engine rows as v2.
                page, errors, response = open_page(base + "classic/")
                self.assertEqual(200, response.status)
                engine_ready(page)
                self.assertEqual([], errors)
                self.assertEqual("Trade Value · Data Driven Football", page.title())
                self.assertTrue(page.is_visible("#curvePlayerSearch") or page.is_visible(".topbar"))
                self.assertFalse(page.is_visible(".health-cluster"), "Dashboard health box is visible")
                self.assertFalse(page.is_visible("#chartHealthBtn"))
                self.assertTrue(page.is_visible("footer #asOfDate"))
                self.assertRegex(page.inner_text("footer"), r"Chart build .*Build tv-")
                self.assertEqual(v2_rows, page.evaluate(ROWS_JS), "classic rows differ from v2's engine rows")
                # The in-page link stays on /classic/.
                href = page.eval_on_selector('a[href$="#weightsSection"]', "e => e.href")
                self.assertEqual(base + "classic/#weightsSection", href)
                self.assertEqual([], page.eval_on_selector_all(
                    'a[href*="modules/"]', "els => els.map(e => e.href)"))
                page.close()

                # Retired pages and the 404 page lead back to the front door.
                for url in (base + "waiver-dashboard/", base + "weekly-signals/", base + "no-such-page/"):
                    page, _, response = open_page(url)
                    self.assertEqual(404 if "no-such" in url else 200, response.status, url)
                    targets = page.eval_on_selector_all("a[href]", "els => els.map(e => e.href)")
                    self.assertIn(base, targets, url)
                    self.assertEqual([], [t for t in targets if "modules/" in t], url)
                    page.close()
            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
