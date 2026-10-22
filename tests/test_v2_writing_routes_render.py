"""v2 Writing tab routes (JEG-855), rendered: the old routes still land in the right place.

Loads the built dist/v2 headless and checks that each old route redirects into its
Writing section and rewrites the address in place:

  * #manifesto, #how-values, #research and #research/<slug> (set after load, and as the
    landing address) end at #writing/manifesto, #writing/how-values, #writing/research
    and #writing/research/<slug>, with the Writing tab and the matching section current
    and only the matching page shown;
  * the redirect replaces the history entry: Back from an old route goes to the page
    before it, not into a loop back to the old route;
  * the built page links to no old route (no href to #manifesto, #how-values, #research).

Discrimination: test_guard_fails_on_broken_builds drops each old redirect and the
address rewrite, and requires the checks to fail on each.
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
def _built_dist():
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        research = Path(tmp) / "research"
        research.mkdir()
        import json
        for slug, (meta, body) in POSTS.items():
            (research / f"{slug}.html").write_text(f"<!--post {json.dumps(meta)} -->\n{body}\n", encoding="utf-8")
        build_v2_page.build(dist, research_dir=research)

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


def run_checks(v2_js=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    with _built_dist() as base, sync_playwright() as playwright:
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
                if width == 390 or old == "#manifesto":
                    html = page.evaluate(READ)["html"]
                    stale = re.findall(r'href="(?:v2/)?#(?:manifesto|how-values|research)[^"]*"', html)
                    if stale:
                        errors.append(f"the page still links to old routes: {sorted(set(stale))}")
                page.close()
        finally:
            browser.close()
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
        }
        for name, (old, new) in broken.items():
            with self.subTest(mutation=name):
                self.assertEqual(js.count(old), 1, f"stale mutation anchor: {old[:60]!r}")
                self.assertNotEqual(run_checks(v2_js=js.replace(old, new, 1)), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
