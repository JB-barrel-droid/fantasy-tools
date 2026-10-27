"""v2 Research tab (JEG-543), rendered.

Builds dist/v2 from a temp research folder (one published post, one draft) into
a temp copy of the built dist/ and loads it headless at 1440 and 390 px, and checks:

  * "Research" is the third section of the Writing tab (after Manifesto and How
    values work) and routes at #writing/research; the page is only the Research
    page (no league bar, no Showing bar). The old route #research (JEG-855)
    redirects there;
  * the index lists exactly the published posts, in date order, and a draft
    never reaches the page (not in the index, not as an article, no route);
  * every published post routes at #writing/research/<slug> (the old
    #research/<slug> redirects to it and lands on the post) with its title, no page
    errors and no horizontal overflow at 390 px, and an unknown slug falls
    back to the index;
  * the reading column is about 70 characters wide (like the Manifesto).

Discrimination: test_guard_fails_on_broken_builds builds with the draft marked
published, with a published post dropped, with the Writing route removed, and
with the old #research/<slug> redirect removed, and requires the checks to fail on each.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
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
    _render_env.ensure_built()


V2_JS = ROOT / "app" / "v2" / "v2.js"

POSTS = {
    "bench-share": ({"title": "Bench share, explained", "summary": "Why the bench adds value.", "date": "2026-10-12", "published": True},
                    "<p>Body of the bench share post.</p>"),
    "older-post": ({"title": "An older post", "summary": "Written earlier.", "date": "2026-10-01", "published": True},
                   "<p>Body of the older post.</p>"),
    "secret-draft": ({"title": "Secret draft", "summary": "Not approved.", "date": "2026-10-13", "published": False},
                     "<p>DRAFT-ONLY-TEXT</p>"),
}
PUBLISHED = ["bench-share", "older-post"]   # date order, newest first

READ = """() => {
  const shown = id => { const n = document.getElementById(id); return Boolean(n) && !n.hidden; };
  const rs = document.getElementById('v2Research');
  const visible = rs ? [...rs.querySelectorAll('article')].filter(a => !a.hidden) : [];
  return {
    tabs: [...document.querySelectorAll('.v2-tab')].map(t => ({view: t.dataset.view, label: t.querySelector('.v2-tab-full')?.textContent || '',
      current: t.getAttribute('aria-current') === 'page'})),
    research: shown('v2Research'),
    others: ['v2Main', 'v2Targets', 'v2Risers', 'v2Compare', 'v2FindTrade', 'v2How', 'v2Manifesto', 'v2Audit'].filter(shown),
    sections: [...document.querySelectorAll('#v2WritingTabs .v2-subtab')].map(a => ({slug: a.dataset.writing, label: a.textContent.trim(),
      current: a.getAttribute('aria-current') === 'page'})),
    sectionsShown: shown('v2Writing'),
    hash: location.hash,
    league: shown('v2Context'), methods: shown('v2Context'),  // JEG-1119: one context row
    indexLinks: rs ? [...rs.querySelectorAll('.v2-rs-list a')].map(a => a.getAttribute('href')) : [],
    visible: visible.map(a => a.dataset.slug || 'index'),
    h1: visible.map(a => a.querySelector('h1')?.textContent.trim()),
    html: document.documentElement.outerHTML,
    colWidth: visible[0] ? visible[0].getBoundingClientRect().width : 0,
    fontPx: visible[0] ? parseFloat(getComputedStyle(visible[0]).fontSize) : 0,
    overflow: document.documentElement.scrollWidth - innerWidth,
  };
}"""


def write_posts(folder: Path, posts: dict) -> None:
    for slug, (meta, body) in posts.items():
        (folder / f"{slug}.html").write_text(f"<!--post {json.dumps(meta)} -->\n{body}\n", encoding="utf-8")


@contextlib.contextmanager
def _built_dist(posts: dict):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        research = Path(tmp) / "research"
        research.mkdir()
        write_posts(research, posts)
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        build_v2_page.build(dist, research_dir=research)

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


def check_sections(snap, tag, want_hash) -> list[str]:
    errors = []
    views = [t["view"] for t in snap["tabs"]]
    if any(view in views for view in ("research", "how", "manifesto")):
        errors.append(f"{tag}Manifesto, How values work and Research are no longer top-level tabs; tabs {views}")
    if [t["view"] for t in snap["tabs"] if t["current"]] != ["writing"]:
        errors.append(f"{tag}Writing is not the current tab")
    if [s["slug"] for s in snap["sections"]] != ["manifesto", "how-values", "research"] or not snap["sectionsShown"]:
        errors.append(f"{tag}Writing sections {snap['sections']} (shown {snap['sectionsShown']}), want Manifesto, How values work, Research in order")
    if [s["slug"] for s in snap["sections"] if s["current"]] != ["research"]:
        errors.append(f"{tag}Research is not the current section")
    if snap["hash"] != want_hash:
        errors.append(f"{tag}address is {snap['hash']!r}, want {want_hash!r}")
    return errors


def check_index(snap, width, hash_="#writing/research", old=False) -> list[str]:
    tag = f"[{width}px {'old ' if old else ''}{hash_}] "
    errors = check_sections(snap, tag, "#writing/research")
    if not snap["research"] or snap["others"]:
        errors.append(f"{tag}pages shown: research={snap['research']} others={snap['others']}")
    if snap["league"] or snap["methods"]:
        errors.append(f"{tag}league bar {snap['league']} / Showing bar {snap['methods']} should be hidden")
    if snap["indexLinks"] != [f"#writing/research/{slug}" for slug in PUBLISHED]:
        errors.append(f"{tag}index links {snap['indexLinks']}, want exactly {PUBLISHED}")
    if "DRAFT-ONLY-TEXT" in snap["html"] or "secret-draft" in snap["html"]:
        errors.append(f"{tag}a draft post reached the page")
    if snap["visible"] != ["index"]:
        errors.append(f"{tag}visible articles {snap['visible']}, want just the index")
    errors += check_layout(snap, width, tag)
    return errors


def check_layout(snap, width, tag) -> list[str]:
    errors = []
    if width <= 390 and snap["overflow"] > 0:
        errors.append(f"{tag}horizontal overflow {snap['overflow']}px")
    if width >= 1000 and not (500 <= snap["colWidth"] <= 900):
        errors.append(f"{tag}reading column {snap['colWidth']}px wide, want about 70 characters")
    return errors


def check_post(snap, width, slug, title, old=False) -> list[str]:
    tag = f"[{width}px {'old #research' if old else '#writing/research'}/{slug}] "
    errors = check_sections(snap, tag, f"#writing/research/{slug}")
    if snap["visible"] != [slug]:
        errors.append(f"{tag}visible articles {snap['visible']}")
    if snap["h1"] != [title]:
        errors.append(f"{tag}h1 {snap['h1']}, want {title!r}")
    if snap["league"] or snap["methods"]:
        errors.append(f"{tag}wrong bars shown")
    errors += check_layout(snap, width, tag)
    return errors


def run_checks(posts=None, remove_route=False, remove_redirect=False) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    errors = []
    js = V2_JS.read_text(encoding="utf-8")
    if remove_route:
        route = '(base === "#writing" || base.startsWith("#writing/")) ? "writing"'
        assert route in js
        js = js.replace(route, 'false ? "writing"', 1)
    if remove_redirect:
        redirect = '(base.startsWith("#research/") ? "#writing/" + base.slice(1) : base)'
        assert redirect in js
        js = js.replace(redirect, "base", 1)
    with _built_dist(POSTS if posts is None else posts) as base, sync_playwright() as playwright:
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
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
                page.goto(base, wait_until="networkidle")
                page.wait_for_function("() => window.TradeValueV2", timeout=40000)
                page.evaluate("() => { location.hash = '#writing/research'; }")
                page.wait_for_timeout(300)
                errors += check_index(page.evaluate(READ), width)
                for slug in PUBLISHED:
                    page.evaluate("s => { location.hash = '#writing/research/' + s; }", slug)
                    page.wait_for_timeout(300)
                    errors += check_post(page.evaluate(READ), width, slug, POSTS[slug][0]["title"])
                # Old routes (JEG-855) redirect into the section, and the address is rewritten.
                page.evaluate("() => { location.hash = '#research'; }")
                page.wait_for_timeout(300)
                errors += check_index(page.evaluate(READ), width, "#research", old=True)
                for slug in PUBLISHED:
                    page.evaluate("s => { location.hash = '#research/' + s; }", slug)
                    page.wait_for_timeout(300)
                    errors += check_post(page.evaluate(READ), width, slug, POSTS[slug][0]["title"], old=True)
                page.evaluate("() => { location.hash = '#writing/research/secret-draft'; }")
                page.wait_for_timeout(300)
                snap = page.evaluate(READ)
                if snap["visible"] != ["index"]:
                    errors.append(f"[{width}px] a draft route showed {snap['visible']}, want the index")
                if page_errors:
                    errors.append(f"[{width}px] page errors {page_errors}")
                page.close()
        finally:
            browser.close()
    return errors


class ResearchRenderTest(unittest.TestCase):
    def test_research_tab(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        draft_published = {**POSTS, "secret-draft": ({**POSTS["secret-draft"][0], "published": True}, POSTS["secret-draft"][1])}
        dropped = {slug: value for slug, value in POSTS.items() if slug != "older-post"}
        for name, kwargs in {"draft published": {"posts": draft_published}, "published post dropped": {"posts": dropped},
                             "route removed": {"remove_route": True},
                             "old #research/<slug> redirect removed": {"remove_redirect": True}}.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(run_checks(**kwargs), [], f"render checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
