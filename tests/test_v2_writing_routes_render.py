"""v2 Writing tab routes (JEG-855), rendered: the old routes still land in the right place.

Loads the built dist/v2 headless and checks that each old route redirects into its
Writing section and rewrites the address in place:

  * #manifesto, #how-values, #research and #research/<slug> (set after load, and as the
    landing address) end at #writing/manifesto, #writing/how-values, #writing/research
    and #writing/research/<slug>, with the Writing tab and the matching section current
    and only the matching page shown;
  * the redirect replaces the history entry: Back from an old route goes to the page
    before it, not into a loop back to the old route;
  * JEG-905: every in-page hash link in the built DOM (every route, hidden pages included)
    targets a route the page defines (a tab, a Writing or auditing sub-tab, a published
    post) and never an old route, and no built script carries an old-route literal
    outside the redirect map (the Trade targets popover builds its link in JS).

Discrimination: test_guard_fails_on_broken_builds drops each old redirect and the
address rewrite and points the popover link at the old route;
test_link_guard_fails_on_broken_html points a sub-tab at the old route and a link at
a route that does not exist. Each must fail the checks.
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

V2_JS = ROOT / "app" / "v2" / "v2.js"
POSTS = {
    "bench-share": ({"title": "Bench share, explained", "summary": "Why the bench adds value.", "date": "2026-10-12", "published": True},
                    "<p>Body of the bench share post.</p>"),
}
# old route -> (new address, page id shown, section slug)
ROUTES = {
    "#manifesto": ("#writing/manifesto", "v2Manifesto", "manifesto"),
    "#how-values": ("#writing/how-values", "v2How", "how-values"),
    "#research": ("#writing/research", "v2Research", "research"),
    "#research/bench-share": ("#writing/research/bench-share", "v2Research", "research"),
}
PAGES = ("v2Main", "v2Targets", "v2Risers", "v2Compare", "v2How", "v2Manifesto", "v2Research")

READ = """() => {
  const shown = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden; };
  return {hash: location.hash,
    tab: [...document.querySelectorAll('.v2-tab')].filter(t => t.getAttribute('aria-current') === 'page').map(t => t.dataset.view),
    section: [...document.querySelectorAll('#v2WritingTabs .v2-subtab')].filter(a => a.getAttribute('aria-current') === 'page').map(a => a.dataset.writing),
    pages: %s.filter(shown),
    post: [...document.querySelectorAll('#v2Research .v2-rs-post')].filter(a => !a.hidden).map(a => a.dataset.slug),
    html: document.documentElement.outerHTML};
}""" % repr(list(PAGES)).replace("'", '"')


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _built_dist(html_mutation=None):
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        research = Path(tmp) / "research"
        research.mkdir()
        import json
        for slug, (meta, body) in POSTS.items():
            (research / f"{slug}.html").write_text(f"<!--post {json.dumps(meta)} -->\n{body}\n", encoding="utf-8")
        build_v2_page.build(dist, research_dir=research)
        if html_mutation is not None:
            index = dist / "v2" / "index.html"
            html = index.read_text(encoding="utf-8")
            old, new = html_mutation
            assert html.count(old) == 1, f"stale mutation anchor: {old[:60]!r}"
            index.write_text(html.replace(old, new, 1), encoding="utf-8")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(dist))) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def check_landed(snap, old, tag) -> list[str]:
    new, page, section = ROUTES[old]
    errors = []
    if snap["hash"] != new:
        errors.append(f"{tag}{old}: address is {snap['hash']!r}, want {new!r}")
    if snap["tab"] != ["writing"] or snap["section"] != [section]:
        errors.append(f"{tag}{old}: current tab {snap['tab']} section {snap['section']}, want Writing / {section}")
    if snap["pages"] != [page]:
        errors.append(f"{tag}{old}: pages shown {snap['pages']}, want only {page}")
    if old.startswith("#research/") and snap["post"] != [old.split("/")[1]]:
        errors.append(f"{tag}{old}: post shown {snap['post']}, want the post")
    return errors


def run_checks(v2_js=None, html_mutation=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist(html_mutation) as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            def open_page(width, hash_=""):
                page = browser.new_page(viewport={"width": width, "height": 844})
                page.on("pageerror", lambda e: errors.append(f"page error {e}"))
                page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
                if v2_js is not None:
                    page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=v2_js))
                page.goto(base + hash_, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                return page

            for width in (1440, 390):
                page = open_page(width)
                for old in ROUTES:
                    page.evaluate("() => { location.hash = '#player-values'; }")
                    page.wait_for_timeout(150)
                    page.evaluate("h => { location.hash = h; }", old)
                    page.wait_for_timeout(300)
                    errors += check_landed(page.evaluate(READ), old, f"[{width}px set] ")
                # Back skips the old route: it was replaced, so it is not in the history.
                page.evaluate("() => { location.hash = '#trade-targets'; }")
                page.wait_for_timeout(150)
                page.evaluate("() => { location.hash = '#how-values'; }")
                page.wait_for_timeout(300)
                page.go_back()
                page.wait_for_timeout(300)
                snap = page.evaluate(READ)
                if snap["hash"] != "#trade-targets" or snap["tab"] != ["targets"]:
                    errors.append(f"[{width}px] Back from #how-values landed at {snap['hash']!r} / {snap['tab']}, want #trade-targets")
                page.close()
            for old in ROUTES:
                page = open_page(1440, old)
                errors += check_landed(page.evaluate(READ), old, "[landing] ")
                page.close()
            # JEG-905: in-page links use the new routes directly; the redirects are a safety net.
            page = open_page(1440)
            errors += check_in_page_links(page, v2_js)
            page.close()
        finally:
            browser.close()
    return errors


LEGACY_LINK = re.compile(r'^(?:v2/)?#(?:manifesto|how-values|research)(?:/|$)')
# Hash literals a script may build a link from. The redirect map in v2.js is the one allowed place for an old route.
JS_HASH_LITERAL = re.compile(r'["\'`]((?:v2/)?#(?:manifesto|how-values|research)(?:/[^"\'`]*)?)["\'`]')
REDIRECT_CODE = (
    'const LEGACY_ROUTES = {"#manifesto": "#writing/manifesto", "#how-values": "#writing/how-values", "#research": "#writing/research"};',
    'base.startsWith("#research/")',
)


def check_in_page_links(page, v2_js=None) -> list[str]:
    """Every hash link in the built DOM (all routes, hidden pages included) points at a route the page
    defines (a tab, a Writing or auditing sub-tab, or a published post), never at a legacy route; and no
    built script carries a legacy-route literal outside the redirect map (the popover link is built in JS)."""
    errors = []
    links = {}
    for hash_ in ("#trade-targets", "#player-values", "#risers-fallers", "#compare-trade", "#writing/manifesto",
                  "#writing/how-values", "#writing/research", "#writing/research/bench-share", "#values-auditing"):
        page.evaluate("h => { location.hash = h; }", hash_)
        page.wait_for_timeout(250)
        for href in page.evaluate("() => [...document.querySelectorAll('a[href]')].map(a => a.getAttribute('href'))"):
            if href.startswith("#") or href.startswith("v2/#"):
                links.setdefault(href, hash_)
    defined = page.evaluate("""() => [...document.querySelectorAll('.v2-tab[data-view], .v2-subtab, #v2Research .v2-rs-link')]
      .map(a => a.getAttribute('href').replace(/^v2\\//, '').split('?')[0])""")
    defined = set(defined) | {"#writing"}
    if not {"#writing/manifesto", "#writing/how-values", "#writing/research", "#writing/research/bench-share"} <= defined:
        errors.append(f"route definitions not found in the DOM: {sorted(defined)}")
    for href, seen_on in sorted(links.items()):
        if LEGACY_LINK.match(href):
            errors.append(f"in-page link {href!r} (on {seen_on}) points at a legacy route; link the Writing route directly")
        elif href.replace("v2/", "", 1).split("?")[0] not in defined:
            errors.append(f"in-page link {href!r} (on {seen_on}) targets no route the page defines")
    scripts = {"v2.js": v2_js} if v2_js is not None else {}
    for path in sorted((DIST / "v2").glob("*.js")):
        scripts.setdefault(path.name, path.read_text(encoding="utf-8"))
    for name, text in scripts.items():
        if name == "v2.js":
            for code in REDIRECT_CODE:
                if text.count(code) != 1:
                    errors.append(f"v2.js: the redirect code {code[:40]!r} moved; update REDIRECT_CODE in this test")
                text = text.replace(code, "")
        for literal in JS_HASH_LITERAL.findall(text):
            errors.append(f"{name}: legacy route literal {literal!r}; build links from the Writing routes")
    return errors


class WritingRoutesRenderTest(unittest.TestCase):
    def test_old_routes_land_in_writing(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        js = V2_JS.read_text(encoding="utf-8")
        broken = {
            "#how-values redirect removed": ('"#how-values": "#writing/how-values", ', ""),
            "#research redirect removed": ('"#research": "#writing/research"', '"#research": "#research"'),
            "#research/<slug> redirect removed": ('(base.startsWith("#research/") ? "#writing/" + base.slice(1) : base)', "base"),
            "address not rewritten": ('    if (next === base) return;\n', '    return;\n'),
            # JEG-905: a script-built link (the targets popover) pointing at the old route.
            "popover links the old route": ('link.href = "v2/#writing/how-values";', 'link.href = "v2/#how-values";'),
        }
        for name, (old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertEqual(js.count(old), 1, f"stale mutation anchor: {old[:60]!r}")
                self.assertNotEqual(run_checks(v2_js=js.replace(old, new, 1)), [], f"render checks did not catch: {name}")

    def test_link_guard_fails_on_broken_html(self):
        """JEG-905: an in-page link in the built HTML at a legacy route, or at a route the page does not define."""
        broken = {
            "sub-tab links the old route": ('href="#writing/how-values" data-writing="how-values"', 'href="#how-values" data-writing="how-values"'),
            # JEG-977 (57f1c1b2, 2026-10-25): in-app links lost their "↗" arrow; the How values link is the same link.
            "link to a route that no longer exists": ('href="v2/#compare-trade">Compare a trade</a>', 'href="v2/#trade-builder">Compare a trade</a>'),
        }
        for name, mutation in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(run_checks(html_mutation=mutation), [], f"link guard did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
