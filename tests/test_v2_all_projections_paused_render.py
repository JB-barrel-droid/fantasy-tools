"""JEG-921, mirrored by JEG-1073: with every source of a DDF Value version paused, it shows no value and says why.

Jeremy (2026-10-23): when every source behind DDF Value is held there is nothing to blend and no fallback to the other
family: it must show a plain em dash and a short plain-English note, never a made-up number. DDF Value was the
projections (JEG-804) then; since JEG-1073 (Jeremy, 2026-10-25: "Keep adj trade chart avg as the main ddf and
projections as an alt") it is the four trade charts, so the premise here is every trade chart held (the pinned CBS hold
plus USA Today, FantasyPros and FantasyCalc). The projections alternate gets its own check: holding all three projections
empties ddf_value_projections only, and DDF Value keeps its numbers.

Headless against a temp copy of dist/ with the pinned fixture (tests/_holds.py) plus the extra holds:

  * the engine blends no series (getCompositeInputs().series is empty);
  * the default Player values view lists no player and its empty state says every trade chart source is paused;
  * searching shows the player with a DDF Value cell that is "—" plus the same note, no digit as a value.

test_guard_fails_on_broken_build serves a v2.js that drops the note (empty state and cell) and requires the checks to fail.
"""
from __future__ import annotations

import contextlib
import functools
import http.server
import re
import shutil
import socketserver
import tempfile
import threading
import unittest
from pathlib import Path

from tests import _render_env
from tests._holds import pin_holds_in_dist
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_targets_render import DIST, build_v2_page, engine_path

ROOT = Path(__file__).resolve().parents[1]
V2_JS = ROOT / "app" / "v2" / "v2.js"
PROJECTIONS = ("espn", "cbsros", "razzball")
CHARTS = ("usatoday", "fantasypros", "fantasycalc", "cbs")   # cbs is held by the pinned fixture already
NOTE = "Every trade chart source is paused this week"


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served(extra_held=("usatoday", "fantasypros", "fantasycalc")):
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist, extra_held=extra_held)
        build_v2_page.build(dist)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def translate_path(self, path):
                return engine_path(path) or super().translate_path(path)
        handler = functools.partial(Quiet, directory=str(dist))
        with socketserver.ThreadingTCPServer(("127.0.0.1", 0), handler) as server:
            server.daemon_threads = True
            threading.Thread(target=server.serve_forever, daemon=True).start()
            try:
                yield f"http://127.0.0.1:{server.server_address[1]}/v2/#player-values"
            finally:
                server.shutdown()


def read_page(v2_js=None, extra_held=("usatoday", "fantasypros", "fantasycalc")) -> dict:
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {"errors": []}
    with _served(extra_held) as url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda e: out["errors"].append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table')", timeout=60000)
            page.wait_for_timeout(600)
            out["series"] = page.evaluate("() => window.TradeValueCurveControls.getCompositeInputs().series")
            out["inputs"] = page.evaluate("() => window.TradeValueCurveControls.getCompositeInputs().inputs")
            out["proj_series"] = page.evaluate("() => window.TradeValueCurveControls.getCompositeInputs('ddf_value_projections').series")
            out["rows"] = page.evaluate("() => document.querySelectorAll('#v2Table tbody tr').length")
            out["empty_shown"] = page.evaluate("() => !document.querySelector('#v2Empty').hidden")
            out["empty_text"] = page.evaluate("() => document.querySelector('#v2EmptyText').textContent")
            page.fill("#v2Search", "a")
            page.wait_for_timeout(600)
            out["cells"] = page.evaluate("""() => [...document.querySelectorAll('#v2Table tbody tr')].slice(0, 5)
              .map(r => r.lastElementChild.innerText.replace(/\\s+/g, ' ').trim())""")
        finally:
            browser.close()
    return out


def problems(got) -> list[str]:
    errors = list(got["errors"])
    if got["series"] or sorted(got["inputs"]) != sorted(CHARTS):
        errors.append(f"premise: expected the four trade charts held, none blended: inputs {got['inputs']}, series {got['series']}")
    if got["rows"] or not got["empty_shown"]:
        errors.append(f"default view must list no player (rows {got['rows']}, empty state shown {got['empty_shown']})")
    if NOTE not in got["empty_text"]:
        errors.append(f"empty state does not say every trade chart source is paused: {got['empty_text']!r}")
    if not got["cells"]:
        errors.append("searching listed no player to check the DDF Value cell on")
    for cell in got["cells"]:
        if not cell.startswith("—") or re.search(r"\d", cell) or NOTE not in cell:
            errors.append(f"DDF Value cell must be a plain em dash plus the note, no number: {cell!r}")
    return errors


class AllProjectionsPausedRenderTest(unittest.TestCase):
    def test_all_paused_shows_dash_and_note(self):
        self.assertEqual(problems(read_page()), [])

    def test_projections_paused_leaves_ddf_value_alone(self):
        """JEG-1073: DDF Value is the charts, so holding the three projections empties only the alternate."""
        got = read_page(extra_held=PROJECTIONS)
        self.assertEqual(got["errors"], [])
        self.assertTrue(got["series"], "DDF Value must keep its trade chart inputs when only projections are held")
        self.assertFalse(got["proj_series"], f"the projections alternate must be empty: {got['proj_series']}")
        self.assertTrue(got["rows"], "the default view must still list players")
        self.assertFalse(got["empty_shown"])

    def test_guard_fails_on_broken_build(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        anchor = 'const ALL_CHARTS_PAUSED = "Every trade chart source is paused this week";'
        self.assertIn(anchor, v2, "stale mutation anchor")
        broken = v2.replace(anchor, 'const ALL_CHARTS_PAUSED = "No source prices this player";', 1)
        errors = problems(read_page(broken))
        self.assertTrue(any("does not say every trade chart source is paused" in e for e in errors), errors)
        self.assertTrue(any("em dash plus the note" in e for e in errors), errors)


if __name__ == "__main__":
    unittest.main()
