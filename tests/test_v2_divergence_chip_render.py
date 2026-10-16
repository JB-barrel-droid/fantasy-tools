"""v2 source divergence "Check" chip (JEG-609, data from JEG-460), rendered.

Serves the built page with assets/reference-freshness.json's source_divergence set to known statuses and checks:

  * warn and investigate show a "Check" chip next to the source name, with the published message as its tooltip
    and in its accessible name; ok and n/a show nothing;
  * reviewed shows "Reviewed" and links to the resolution issue (a JEG-NNN id becomes its Linear issue link);
    in a table column header, which is itself a button, it is not a link;
  * the chip sits on Trade targets column heads, the Showing legend, Player values column heads and the Customize
    rows, and never hides or disables the source: every flagged source's column, legend entry and row is still there;
  * our own DDF Value and VORP columns carry no chip;
  * no page errors.

Discrimination: test_guard_fails_on_broken_builds serves v2.js that flags ok sources, drops the tooltip, and links
inside the header button, and requires failures.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import json
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
V2_JS = ROOT / "app" / "v2" / "v2.js"

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402

MESSAGES = {
    "usatoday": "USA Today disagrees with the other charts on 38% of players this week (usually 20%).",
    "fantasycalc": "FantasyCalc disagrees with the other charts on 47% of players this week (usually 46%). Under review.",
    "fantasypros": "FantasyPros was reviewed on 2026-10-14: its ordering is unusual but correct.",
}
DIVERGENCE = {
    "usatoday": {"status": "warn", "message": MESSAGES["usatoday"], "resolution_issue": None},
    "fantasycalc": {"status": "investigate", "message": MESSAGES["fantasycalc"], "resolution_issue": None},
    "fantasypros": {"status": "reviewed", "message": MESSAGES["fantasypros"], "resolution_issue": "JEG-123"},
    "cbs": {"status": "ok", "message": "CBS disagrees with the other charts on 14% of players this week.", "resolution_issue": None},
    "espn": {"status": "n/a", "message": "", "resolution_issue": None},
}
EXPECT = {"usatoday": "Check", "fantasycalc": "Check", "fantasypros": "Reviewed"}

CHIPS = """() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.offsetParent !== null).map(c => ({
  src: c.dataset.divergence, status: c.dataset.status, text: c.textContent.trim(), title: c.title, aria: c.getAttribute('aria-label') || '',
  tag: c.tagName, href: c.getAttribute('href') || '', inButton: Boolean(c.closest('button')), in: c.closest('#v2TDivergence') ? 'note' : c.closest('thead') ? 'head' : c.closest('#v2ShowingLegend') ? 'legend'
  : c.closest('#v2Popover, #v2Sources, .v2-popover') ? 'customize' : 'other'}))"""


@contextlib.contextmanager
def _served():
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)
        path = dist / "assets" / "reference-freshness.json"
        doc = json.loads(path.read_text(encoding="utf-8"))
        doc["source_divergence"] = DIVERGENCE
        path.write_text(json.dumps(doc), encoding="utf-8")

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, format, *args):
                pass
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/"
            finally:
                server.shutdown()


def check_chips(chips: list[dict], where: str, place: str, allow_link: bool) -> list[str]:
    errors = []
    mine = [c for c in chips if c["in"] == place]
    seen = {c["src"]: c for c in mine}
    if set(seen) != set(EXPECT):
        errors.append(f"[{where}] chips on {sorted(seen)}, want exactly {sorted(EXPECT)} (ok and n/a show none)")
    for src, word in EXPECT.items():
        c = seen.get(src)
        if not c:
            continue
        if c["text"].lstrip("⚑✓ ").strip() != word:
            errors.append(f"[{where}] {src}: chip says {c['text']!r}, want {word!r}")
        if c["title"] != MESSAGES[src] or MESSAGES[src] not in c["aria"]:
            errors.append(f"[{where}] {src}: tooltip {c['title']!r} / name {c['aria']!r}, want the published message")
        linked = c["tag"] == "A"
        if src == "fantasypros":
            if allow_link and (not linked or c["href"] != "https://linear.app/jegabee/issue/JEG-123"):
                errors.append(f"[{where}] reviewed chip should link to the resolution issue: {c['tag']} {c['href']!r}")
            if not allow_link and linked:
                errors.append(f"[{where}] a link inside a column-header button: {c['href']!r}")
        elif linked:
            errors.append(f"[{where}] {src}: only a reviewed chip links")
        if c["inButton"] and linked:
            errors.append(f"[{where}] {src}: interactive chip inside a button")
    return errors


def run_checks(patch=None) -> list[str]:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    js = V2_JS.read_text(encoding="utf-8")
    if patch:
        old, new = patch
        assert old in js, f"patch anchor missing: {old!r}"
        js = js.replace(old, new, 1)
    errors: list[str] = []
    with _served() as base, sync_playwright() as playwright:
        try:
            browser = playwright.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(playwright))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page_errors: list[str] = []
            page.on("pageerror", lambda e: page_errors.append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if patch:
                page.route("**/v2/v2.js*", lambda route, *_: route.fulfill(status=200, content_type="text/javascript", body=js))
            # Trade targets column heads.
            page.goto(base + "#trade-targets", wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && window.TradeValueV2.targets() && document.querySelector('#v2TTable thead th[data-chart]')", timeout=60000)
            page.wait_for_function("() => document.querySelector('.v2-div-chip')", timeout=20000)
            chips = page.evaluate(CHIPS)
            errors += check_chips(chips, "trade targets note", "note", True)
            note = page.evaluate("() => document.getElementById('v2TDivergence').textContent")
            for message in MESSAGES.values():
                if message not in note:
                    errors.append(f"[trade targets] the note does not say: {message!r}")
            page.set_viewport_size({"width": 1100, "height": 1000})
            page.wait_for_timeout(400)
            errors += check_chips(page.evaluate(CHIPS), "trade targets heads at 1100", "head", True)
            page.set_viewport_size({"width": 1440, "height": 1000})
            heads = page.evaluate("() => [...document.querySelectorAll('#v2TTable thead th[data-chart]')].map(th => th.dataset.chart)")
            for src in EXPECT:
                if src not in heads:
                    errors.append(f"[trade targets] flagged source {src} lost its column: {heads}")
            # Player values: the Showing legend and the column heads.
            page.evaluate("() => { location.hash = '#player-values'; }")
            page.wait_for_function("() => document.querySelector('#v2Table thead th') && document.querySelector('#v2ShowingLegend li')", timeout=40000)
            page.wait_for_timeout(500)
            chips = page.evaluate(CHIPS)
            errors += check_chips(chips, "player values legend", "legend", True)
            errors += check_chips(chips, "player values heads", "head", False)
            heads = page.evaluate("() => [...document.querySelectorAll('#v2Table thead th')].map(th => th.textContent)")
            for name in ("USA Today", "FantasyCalc", "FantasyPros"):
                if not any(name in h for h in heads):
                    errors.append(f"[player values] flagged source {name} lost its column")
            vorp = page.evaluate("() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.closest('th') && /VORP/.test(c.closest('th').textContent)).length")
            if vorp:
                errors.append("[player values] a VORP column carries a divergence chip")
            ddf = page.evaluate("() => [...document.querySelectorAll('#v2ShowingLegend li')].filter(li => /DDF Value/.test(li.textContent) && li.querySelector('.v2-div-chip')).length")
            if ddf:
                errors.append("[player values] DDF Value carries a divergence chip")
            # Customize rows.
            page.click("#v2EditSources")
            page.wait_for_timeout(600)
            chips = page.evaluate("""() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.offsetParent !== null && c.closest('label'))
              .map(c => ({src: c.dataset.divergence, status: c.dataset.status, text: c.textContent.trim(), title: c.title, aria: c.getAttribute('aria-label') || '',
                tag: c.tagName, href: c.getAttribute('href') || '', inButton: Boolean(c.closest('button')), in: 'customize'}))""")
            seen = {c["src"] for c in chips}
            if seen != set(EXPECT):
                errors.append(f"[customize] chips on {sorted(seen)}, want {sorted(EXPECT)}")
            if page_errors:
                errors.append(f"page errors {page_errors}")
            page.close()
        finally:
            browser.close()
    return errors


PATCHES = {
    "ok sources flagged": ('if (status !== "warn" && status !== "investigate" && status !== "reviewed") return null;',
                           'if (status === "n/a") return null;'),
    "tooltip dropped": ("    chip.title = message;\n", "    chip.title = '';\n"),
    "link inside the header button": ('const href = status === "reviewed" && !(opts && opts.noLink) ? resolutionHref(entry.resolution_issue) : "";',
                                      'const href = status === "reviewed" ? resolutionHref(entry.resolution_issue) : "";'),
    "reviewed shown as check": ('const word = status === "reviewed" ? "Reviewed" : "Check";', 'const word = "Check";'),
}


class DivergenceChipRenderTest(unittest.TestCase):
    def test_chip(self):
        self.assertEqual(run_checks(), [])

    def test_guard_fails_on_broken_builds(self):
        for name, patch in PATCHES.items():
            with self.subTest(patch=name):
                self.assertNotEqual(run_checks(patch), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
