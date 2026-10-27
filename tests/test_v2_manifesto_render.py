"""v2 Manifesto tab, rendered: Jeremy's text as a page in the v2 shell.

Builds dist/v2 into a temp copy of the built dist/ and loads it headless at
1440 and 390 px, and checks:

  * "Manifesto" is the first section of the Writing tab and routes at
    #writing/manifesto (Writing is the current tab, Manifesto the current
    section, the Manifesto page shows and every other page is hidden, as are the
    league bar and the Showing bar); the old route #manifesto redirects there
    and rewrites the address (JEG-855);
  * the landing tab is still Trade targets: /v2/ with no hash shows Trade
    targets, not the Manifesto (Jeremy, 2026-10-08 / 2026-10-09);
  * the h1 is the doc's title with the "Data Driven Football" eyebrow, and all
    12 numbered section headings are present as h2s, in order;
  * plain text only (Jeremy, 2026-10-09): no buttons, links or form controls
    on the tab;
  * copy rules on the tab: no "Vegas", no "VORP";
  * no page errors and no horizontal overflow at 390 px.

Discrimination: test_guard_fails_on_broken_builds serves a page with section 7
dropped, a page with Manifesto after How values work in the Writing sections, a page with a
link added to the text, v2.js landing on Writing, and v2.js without the old #manifesto redirect, and requires the
checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
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
from tests import _render_env  # noqa: E402


def setUpModule():
    # Build app/ and dist/ from the committed fixtures first, so the
    # test never reads a stale committed build (GAP-APP-ASSETS-LAG).
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"
SHELL = ROOT / "app" / "v2" / "shell.html"
LANDING = 'const currentView = () => viewFor(hashBase()) || "targets";'

TITLE = "Fantasy Football Manifesto"
SECTIONS = [
    "1. A player does not have one value",
    "2. The fantasy market is relatively efficient, but not perfectly efficient",
    "3. Fundamental value begins with replacement",
    "4. Value Above Replacement is necessary, but not sufficient",
    "5. Bench players are options",
    "6. Portfolio construction changes player value",
    "7. Roster spots have opportunity cost",
    "8. Starter-grade weeks matter more than season totals",
    "9. Future fantasy value should be discounted",
    "10. The objective function changes during the season",
    "11. Market price creates the opportunity",
    "12. Winning is continuous portfolio optimization",
]
PAGES = ("v2Main", "v2Targets", "v2Risers", "v2Compare", "v2FindTrade", "v2How", "v2Manifesto", "v2Research", "v2Audit")

READ = """() => {
  const shown = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden; };
  const mf = document.getElementById('v2Manifesto');
  return {
    tabs: [...document.querySelectorAll('.v2-tab')].map(t => ({view: t.dataset.view, href: t.getAttribute('href'),
      label: t.querySelector('.v2-tab-full')?.textContent || '', current: t.getAttribute('aria-current') === 'page'})),
    pages: Object.fromEntries(%s.map(id => [id, shown(id)])),
    league: shown('v2Context'), methods: shown('v2Context'),  // JEG-1119: one context row
    sections: [...document.querySelectorAll('#v2WritingTabs .v2-subtab')].map(a => ({slug: a.dataset.writing, label: a.textContent.trim(),
      href: a.getAttribute('href'), current: a.getAttribute('aria-current') === 'page'})),
    hash: location.hash,
    h1: mf ? [...mf.querySelectorAll('h1')].map(h => h.textContent.trim()) : [],
    eyebrow: mf?.querySelector('.v2-mf-eyebrow')?.textContent.trim() || '',
    h2: mf ? [...mf.querySelectorAll('article h2')].map(h => h.textContent.trim()) : [],
    text: mf ? mf.textContent : '',
    controls: mf ? [...mf.querySelectorAll('a, button, input, select, textarea, details, summary')].map(n => n.tagName.toLowerCase()) : [],
    overflow: document.documentElement.scrollWidth - innerWidth,
  };
}""" % repr(list(PAGES)).replace("'", '"')


def _serve(body, content_type, route, *_):
    route.fulfill(status=200, content_type=content_type, body=body)


@contextlib.contextmanager
def _built_dist(shell_html=None):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist)
        if shell_html is not None:
            page = dist / "v2" / "index.html"
            built = page.read_text(encoding="utf-8")
            original = SHELL.read_text(encoding="utf-8")
            composed = build_v2_page.compose_shell(original, build_v2_page.load_posts())
            assert composed in built, "the built page no longer embeds shell.html verbatim"
            page.write_text(built.replace(composed, build_v2_page.compose_shell(shell_html, build_v2_page.load_posts()), 1), encoding="utf-8")

        class QuietHandler(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(QuietHandler, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def check_landing(snap) -> list[str]:
    errors = []
    current = [t["view"] for t in snap["tabs"] if t["current"]]
    if current != ["targets"]:
        errors.append(f"landing (no hash): current tab {current}, want Trade targets")
    if not snap["pages"]["v2Targets"] or snap["pages"]["v2Manifesto"]:
        errors.append(f"landing (no hash) should show Trade targets only: {snap['pages']}")
    return errors


def check_manifesto(snap, width, old=False) -> list[str]:
    tag = f"[{width}px{' old #manifesto' if old else ''}] "
    errors = []
    writing = [t for t in snap["tabs"] if t["view"] == "writing"]
    if len(writing) != 1 or writing[0]["label"] != "Writing" or not str(writing[0]["href"]).endswith("#writing"):
        errors.append(f"{tag}want one Writing tab at #writing, got {writing}")
    if any(t["view"] == "manifesto" for t in snap["tabs"]):
        errors.append(f"{tag}Manifesto is still a top-level tab")
    first = snap["sections"][0] if snap["sections"] else {}
    if (first.get("slug"), first.get("label")) != ("manifesto", "Manifesto") or first.get("href") != "#writing/manifesto":
        errors.append(f"{tag}first Writing section is {first}, want Manifesto at #writing/manifesto")
    if [t["view"] for t in snap["tabs"] if t["current"]] != ["writing"]:
        errors.append(f"{tag}#writing/manifesto: the Writing tab is not the current tab")
    if [s["slug"] for s in snap["sections"] if s["current"]] != ["manifesto"]:
        errors.append(f"{tag}the Manifesto section is not the current section")
    if snap["hash"] != "#writing/manifesto":
        errors.append(f"{tag}address is {snap['hash']!r}, want '#writing/manifesto'")
    shown = [page for page, on in snap["pages"].items() if on]
    if shown != ["v2Manifesto"]:
        errors.append(f"{tag}#writing/manifesto shows {shown}, want only the Manifesto")
    if snap["league"] or snap["methods"]:
        errors.append(f"{tag}league bar {snap['league']}, Showing bar {snap['methods']}; both should be hidden")
    if snap["h1"] != [TITLE]:
        errors.append(f"{tag}h1 {snap['h1']}, want [{TITLE!r}]")
    if snap["eyebrow"] != "Data Driven Football":
        errors.append(f"{tag}eyebrow {snap['eyebrow']!r}")
    if snap["h2"] != SECTIONS:
        missing = [s for s in SECTIONS if s not in snap["h2"]]
        errors.append(f"{tag}section headings differ from the 12 in order; missing {missing}, got {len(snap['h2'])}")
    if snap["controls"]:
        errors.append(f"{tag}the Manifesto is plain text; found controls {snap['controls']}")
    for word in ("Vegas", "VORP"):
        if re.search(word, snap["text"]):
            errors.append(f"{tag}copy rule: {word!r} on the Manifesto tab")
    if width <= 390 and snap["overflow"] > 0:
        errors.append(f"{tag}horizontal overflow {snap['overflow']}px")
    return errors


def run_checks(v2_js=None, shell_html=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist(shell_html) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            for width, height in ((1440, 900), (390, 844)):
                page = browser.new_page(viewport={"width": width, "height": height})
                page_errors = []
                page.on("pageerror", lambda e: page_errors.append(str(e)))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", functools.partial(_serve, v2_js, "text/javascript"))
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                if width == 1440:
                    errors += check_landing(page.evaluate(READ))
                page.evaluate("() => { location.hash = '#writing/manifesto'; }")
                page.wait_for_timeout(300)
                errors += check_manifesto(page.evaluate(READ), width)
                page.evaluate("() => { location.hash = '#trade-targets'; location.hash = '#manifesto'; }")
                page.wait_for_timeout(300)
                errors += check_manifesto(page.evaluate(READ), width, old=True)
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class ManifestoRenderTest(unittest.TestCase):
    def test_manifesto_tab(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        shell = SHELL.read_text(encoding="utf-8")
        tab = re.search(r'      <a class="v2-subtab" href="#writing/manifesto".*?</a>\n', shell).group(0)
        how_tab = re.search(r'      <a class="v2-subtab" href="#writing/how-values".*?</a>\n', shell).group(0)
        section7 = re.search(r'    <section class="v2-mf-sec" aria-labelledby="v2M7">.*?    </section>\n', shell, re.S).group(0)
        with_link = section7.replace("    </section>\n", '      <p><a href="v2/#trade-targets">Trade targets</a></p>\n    </section>\n')
        broken = {
            "section 7 dropped": {"shell_html": shell.replace(section7, "", 1)},
            "Manifesto not first section": {"shell_html": shell.replace(tab + how_tab, how_tab + tab, 1)},
            "link added to the text": {"shell_html": shell.replace(section7, with_link, 1)},
            "Writing is the landing tab": {"v2_js": js.replace(LANDING, LANDING.replace('"targets"', '"writing"'), 1)},
            "old #manifesto route removed": {"v2_js": js.replace('"#manifesto": "#writing/manifesto", ', "", 1)},
        }
        for name, kwargs in broken.items():
            with self.subTest(mutation=name):
                body = next(iter(kwargs.values()))
                self.assertNotIn(body, (js, shell), f"mutation anchor for {name!r} is stale")
                self.assertNotEqual(run_checks(**kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
