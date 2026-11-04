"""Hermetic standalone page checks; no sync, live dashboard or external inputs."""
from __future__ import annotations

import functools
import http.server
import os
from pathlib import Path
import tempfile
import threading
import unittest

from tests import _render_env
from tests.test_versus_vegas import build_view, partial_fixture, render_html


class VersusVegasRender(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise _render_env.unavailable(str(exc))
        cls.playwright = sync_playwright().start()
        try:
            cls.browser = cls.playwright.chromium.launch(
                headless=True, executable_path=_render_env.chromium_executable(cls.playwright),
                args=_render_env.HERMETIC_ARGS)
        except Exception as exc:
            cls.playwright.stop()
            raise _render_env.unavailable(str(exc))
        cls.directory = tempfile.TemporaryDirectory()
        doc = partial_fixture()
        doc["players"][0]["name"] = '<img src=x onerror="alert(1)">'
        view = build_view(doc)
        for layout, filename in (("compact", "index.html"), ("analysis", "analysis.html")):
            (Path(cls.directory.name) / filename).write_text(render_html(
                view, layout, "Synthetic fixture · layout review only"))
        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *_args):
                pass
        handler = functools.partial(Quiet, directory=cls.directory.name)
        cls.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.url = f"http://127.0.0.1:{cls.server.server_port}/index.html"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()
        cls.browser.close()
        cls.playwright.stop()
        cls.directory.cleanup()

    def test_filter_url_reload_back_and_no_external_requests(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        requests, errors = [], []
        page.on("request", lambda req: requests.append(req.url))
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(self.url + '?scoring=ppr&position=QB&coverage=partial&sort=difference&keep=yes')
        self.assertEqual(page.locator('#players tr').count(), 1)
        self.assertIn('Reception market missing', page.locator('#players').inner_text())
        self.assertEqual(page.locator('#players img').count(), 0)
        page.locator('#players details summary').click()
        identity = page.locator('#players .identity').inner_text()
        for value in ('9000101', 'espn_player_id', '101', 'sleeper_id', 'S9000101'):
            self.assertIn(value, identity)
        self.assertEqual(page.locator('#players .identity img').count(), 0)
        self.assertEqual(page.locator('.direction').count(), 0)
        page.select_option('#position', 'WR')
        self.assertIn('keep=yes', page.url)
        self.assertIn('position=WR', page.url)
        self.assertTrue(page.locator('#empty').is_visible())
        page.go_back()
        self.assertEqual(page.locator('#position').input_value(), 'QB')
        self.assertEqual(page.locator('#players tr').count(), 1)
        page.reload()
        self.assertEqual(page.locator('#scoring').input_value(), 'ppr')
        self.assertIn('Verified plays await', page.locator('#plays').inner_text())
        self.assertEqual(errors, [])
        self.assertTrue(all(url.startswith(self.url.rsplit('/', 1)[0] + '/') for url in requests), requests)

    def test_mobile_layout_and_all_rows_default(self):
        page = self.browser.new_page()
        self.addCleanup(page.close)
        for layout in ('compact', 'analysis'):
            for width in (390, 1280):
                with self.subTest(layout=layout, width=width):
                    page.set_viewport_size({"width": width, "height": 844 if width == 390 else 900})
                    page.goto(self.url if layout == 'compact' else self.url.replace('index.html', 'analysis.html'))
                    page.evaluate('document.fonts.ready')
                    self.assertEqual(page.locator('#players tr').count(), 4)
                    self.assertIn('4 players shown', page.locator('#summary').inner_text())
                    self.assertIn('3 comparable', page.locator('#summary').inner_text())
                    self.assertEqual(page.locator('.direction').count(), 3)
                    self.assertEqual(page.evaluate('document.documentElement.scrollWidth <= innerWidth'), True)
                    self.assertEqual(page.locator('nav span').all_text_contents(),
                        ['Home', 'Build a Trade', 'Trade Recommendations', 'Values', 'More'])
                    self.assertEqual(page.locator('nav a').count(), 0)
                    self.assertEqual(page.locator('#players tr').nth(3).locator('td').nth(1).inner_text(), '0 pts')
                    self.assertLess(page.locator('#players tr').first.bounding_box()['y'], page.viewport_size['height'])
                    styles = page.evaluate('''() => ({
                        width: document.querySelector('main').getBoundingClientRect().width,
                        gutter: getComputedStyle(document.querySelector('main')).paddingLeft,
                        card: getComputedStyle(document.querySelector('.health article')).borderRadius,
                        control: getComputedStyle(document.querySelector('select')).borderRadius,
                        face: getComputedStyle(document.querySelector('h1')).fontFamily
                    })''')
                    self.assertLessEqual(styles['width'], 1184)
                    self.assertEqual(styles['gutter'], '16px' if width == 390 else '32px')
                    self.assertEqual(styles['card'], '16px')
                    self.assertEqual(styles['control'], '9px')
                    self.assertIn('Fraunces', styles['face'])
                    for selector in ('#scoring', '#position', '#coverage', '#sort'):
                        self.assertGreaterEqual(page.locator(selector).bounding_box()["height"], 44)
                    screenshot_dir = os.environ.get('VERSUS_SCREENSHOT_DIR')
                    if screenshot_dir:
                        Path(screenshot_dir).mkdir(parents=True, exist_ok=True)
                        page.screenshot(path=str(Path(screenshot_dir) / f'{layout}-{width}.png'), full_page=True)
                    screenshot = os.environ.get('VERSUS_SCREENSHOT_PATH')
                    if screenshot and layout == 'compact' and width == 390:
                        page.screenshot(path=screenshot, full_page=True)
                    page.select_option('#coverage', 'comparable')
                    self.assertEqual(page.locator('#players tr').count(), 3)


if __name__ == '__main__':
    unittest.main()
