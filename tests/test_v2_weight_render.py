"""v2 page weight, rendered: one download per JSON file, no layout for the hidden engine.

Builds dist/v2 into a temp copy of the built dist/ and loads the root headless:

  * every same-origin .json file is requested over the network at most once
    (comparison-sources-data.json, 2.3 MB, used to be fetched three times);
  * the shared fetch keeps per-caller semantics: two callers get their own
    readable bodies, and a caller whose abort signal fires is rejected with an
    AbortError while the other caller still resolves;
  * the off-screen engine container is display: none, so its 16,000+ nodes are
    never laid out;
  * the classic page's fonts (Archivo, IBM Plex Mono) are not requested;
  * hiding the engine changes no number: getAllRows(), getSourceInfo() and
    getZones() are identical to a load with the old off-screen (laid out)
    container, at two league settings;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves the page without the
fetch-sharing script, with the classic font link put back, and with the old
off-screen engine rule, and requires each to fail.
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

from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

V2_CSS = ROOT / "app" / "v2" / "v2.css"
HIDE_RULE = ".legacy-engine { display: none !important; }"
OLD_RULE = (".legacy-engine { position: absolute !important; left: -20000px !important; top: 0 !important;"
            " width: 1200px !important; visibility: hidden; pointer-events: none; }")
FONT_LINK = ('<link href="https://fonts.googleapis.com/css2?family=Archivo:wght@400;500;600;700;800'
             '&family=IBM+Plex+Mono:wght@500;600&display=swap" rel="stylesheet">')

ENGINE = """async () => { const C = window.TradeValueCurveControls; const out = {};
  for (const [s, t] of [["ppr", 12], ["half_ppr", 10]]) {
    C.setScoring(s); C.setTeams(t); await new Promise(r => setTimeout(r, 50));
    out[s + t] = JSON.stringify([C.getAllRows().map(r => [r.player_key, r.values]), C.getSourceInfo(), C.getZones()]);
  }
  C.setScoring("ppr"); C.setTeams(12); return out; }"""

SEMANTICS = """async () => {
  const url = 'assets/adjustment-inputs.json';
  const a = await fetch(url); const b = await fetch(url);
  const both = [(await a.json()) !== null, (await b.json()) !== null];
  const ctl = new AbortController(); ctl.abort();
  let aborted = null;
  try { await fetch(url, {signal: ctl.signal}); aborted = 'resolved'; } catch (e) { aborted = e.name; }
  const after = await fetch(url).then(r => r.ok);
  return {both, aborted, after}; }"""


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist():
    if not (DIST / "index.html").exists():
        raise unittest.SkipTest("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/", dist
            finally:
                server.shutdown()


def run_checks(root_html=None, v2_css=None, compare_values=True) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise unittest.SkipTest(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as (base, dist), sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise unittest.SkipTest(f"Chromium is not available: {exc}") from exc

        def load(html=None, css=None):
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors, requests = [], []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.on("request", lambda r: requests.append(r.url))
            page.route(lambda u: not u.startswith("http://127.0.0.1") and "fonts." not in u, lambda route: route.abort())
            page.route(lambda u: "fonts." in u, lambda route: route.fulfill(status=200, body=""))
            if html is not None:
                page.route(lambda u: u.split("#")[0] == base, functools.partial(_serve, html, "text/html"))
            if css is not None:
                page.route("**/v2/v2.css*", functools.partial(_serve, css, "text/css"))
            page.goto(base, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2TTable tbody tr')", timeout=60000)
            return page, page_errors, requests

        try:
            css = v2_css if v2_css is not None else V2_CSS.read_text(encoding="utf-8")
            page, page_errors, requests = load(root_html, v2_css)
            page.wait_for_timeout(1500)
            json_hits = {}
            for url in requests:
                if url.startswith(base) and ".json" in url:
                    key = url.split("#")[0]
                    json_hits[key] = json_hits.get(key, 0) + 1
            repeated = {k.replace(base, ""): n for k, n in json_hits.items() if n > 1}
            if repeated:
                errors.append(f"JSON downloaded more than once: {repeated}")
            if any("Archivo" in u or "IBM+Plex" in u for u in requests):
                errors.append("the classic page's fonts are still requested")
            display = page.evaluate("() => getComputedStyle(document.getElementById('legacyEngine')).display")
            if display != "none":
                errors.append(f"engine container is laid out (display {display!r})")
            sem = page.evaluate(SEMANTICS)
            if sem != {"both": [True, True], "aborted": "AbortError", "after": True}:
                errors.append(f"shared fetch lost per-caller behaviour: {sem}")
            if compare_values:
                hidden = page.evaluate(ENGINE)
                old_page, old_errors, _ = load(root_html, css.replace(HIDE_RULE, OLD_RULE, 1))
                shown = old_page.evaluate(ENGINE)
                for key in hidden:
                    if hidden[key] != shown[key]:
                        errors.append(f"{key}: engine values differ when the engine container is hidden")
                page_errors += old_errors
                old_page.close()
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


class WeightRenderTest(unittest.TestCase):
    def test_weight_and_values(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        css = V2_CSS.read_text(encoding="utf-8")
        self.assertIn(HIDE_RULE, css, "hide rule anchor is stale")
        with _built_dist() as (_, dist):
            root = (dist / "index.html").read_text(encoding="utf-8")
        shim = root[root.index("  <script>\n  (function () {\n    var nativeFetch"):]
        shim = shim[:shim.index("</script>") + len("</script>")]
        broken = {
            "no fetch sharing": {"root_html": root.replace(shim, "", 1)},
            "classic fonts back": {"root_html": root.replace("</head>", FONT_LINK + "</head>", 1)},
            "engine laid out": {"v2_css": css.replace(HIDE_RULE, OLD_RULE, 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(run_checks(compare_values=False, **kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
