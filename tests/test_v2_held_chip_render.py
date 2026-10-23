"""JEG-870: a held source never shows the green in-range check; its chip is the hold marker.

Headless against a temp copy of dist/ with the pinned holds (tests/_holds.py: CBS held) and source_divergence
putting CBS inside its usual range (the state that drew the check next to "Paused this week" on the live site,
build tv-20261022-2012-1795eb2, FantasyCalc). Two cases, checked on Customize > Chart lines (since JEG-804 the DDF blend
tab lists projections only, and the test requires that no trade chart row or chip is there):

  * red hold (the pinned hold, no hold_level): no `.v2-ok-mark` anywhere on CBS; the chip reads "Paused" (glyph next
    to the row's "Paused this week" note), data-status "held";
  * amber (lag) hold: CBS stays in play (legend, table heads, Customize), and every CBS chip is the amber flag
    "Lagging", never the check.

test_guard_fails_on_broken_build serves a v2.js that ignores holds in the chip helper and requires the check back.
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

from tests import _render_env
from tests._holds import pin_holds_in_dist
from tests.test_published_league_settings_render import _chromium_executable
from tests.test_v2_targets_render import DIST, build_v2_page, engine_path

ROOT = Path(__file__).resolve().parents[1]
V2_JS = ROOT / "app" / "v2" / "v2.js"
HELD = "cbs"
DIVERGENCE = {
    HELD: {"status": "warn", "message": "CBS disagrees with the other charts on 44% of players this week (usually 44%). Under review.",
           "resolution_issue": None, "outlier_rate": 0.44, "usual_outlier_rate": 0.44},
    "fantasypros": {"status": "warn", "message": "FantasyPros disagrees with the other charts on 49% of players this week (usually 47%). Under review.",
                    "resolution_issue": None, "outlier_rate": 0.49, "usual_outlier_rate": 0.47},
}
CHIPS = """() => [...document.querySelectorAll('.v2-div-chip')].filter(c => c.offsetParent !== null).map(c => ({
  src: c.dataset.divergence, status: c.dataset.status, hold: c.dataset.hold || '', text: c.textContent.trim(),
  mark: Boolean(c.querySelector('svg.v2-ok-mark')), aria: c.getAttribute('aria-label') || '',
  row: (c.closest('label') || {}).textContent, where: c.closest('#v2Popover') ? 'customize' : c.closest('thead') ? 'head'
    : c.closest('#v2ShowingLegend') ? 'legend' : 'other'}))"""


def setUpModule():
    _render_env.ensure_built()


@contextlib.contextmanager
def _served(level):
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist, ignore=shutil.ignore_patterns("v2"))
        pin_holds_in_dist(dist)
        sources_path = dist / "assets" / "comparison-sources-data.json"
        doc = json.loads(sources_path.read_text(encoding="utf-8"))
        if level == "amber":
            doc["sources"][HELD]["validationHold"]["hold_level"] = "amber"
        sources_path.write_text(json.dumps(doc, separators=(",", ":")), encoding="utf-8")
        fresh_path = dist / "assets" / "reference-freshness.json"
        fresh = json.loads(fresh_path.read_text(encoding="utf-8"))
        fresh["source_divergence"] = DIVERGENCE
        fresh_path.write_text(json.dumps(fresh), encoding="utf-8")
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


def read_chips(level, v2_js=None) -> dict:
    """{'page': chips on Player values, 'lines': Customize Chart lines chips, 'blend': DDF blend chips, 'errors': [...]}"""
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except Exception as exc:
        raise _render_env.unavailable(f"Playwright is not available: {exc}") from exc
    out = {"errors": []}
    with _served(level) as url, sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(args=_render_env.HERMETIC_ARGS, executable_path=_chromium_executable(pw))
        except PlaywrightError as exc:
            raise _render_env.unavailable(f"Chromium is not available: {exc}") from exc
        try:
            page = browser.new_page(viewport={"width": 1440, "height": 1000})
            page.on("pageerror", lambda e: out["errors"].append(str(e)))
            page.route(lambda u: not u.startswith("http://127.0.0.1"), lambda route: route.abort())
            if v2_js is not None:
                page.route("**/v2/v2.js*", lambda route: route.fulfill(status=200, content_type="text/javascript", body=v2_js))
            page.goto(url, wait_until="networkidle")
            page.wait_for_function("() => window.TradeValueV2 && document.querySelector('#v2Table tbody tr') && document.querySelector('#v2ShowingLegend li')", timeout=60000)
            page.wait_for_timeout(500)
            out["page"] = page.evaluate(CHIPS)
            page.click("#v2EditSources")
            page.wait_for_timeout(600)
            out["lines"] = [c for c in page.evaluate(CHIPS) if c["where"] == "customize"]
            page.click("#v2Popover [role=tab]:nth-of-type(2)")
            page.wait_for_timeout(400)
            out["blend"] = [c for c in page.evaluate(CHIPS) if c["where"] == "customize"]
            out["blend_text"] = page.evaluate("() => document.querySelector('#v2Popover').innerText")
        finally:
            browser.close()
    return out


CHART_LABELS = ("USA Today", "FantasyCalc", "FantasyPros", "CBS Sports")


def problems(got, level) -> list[str]:
    errors = list(got["errors"])
    # JEG-804 (#814, Jeremy 2026-10-22 "Out of DDF Value"): the DDF blend tab lists projections only, so no trade chart
    # (held or open) has a row or a chip there; the chart chips are on Chart lines.
    charts_in_blend = [label for label in CHART_LABELS if label in got["blend_text"]]
    if charts_in_blend or got["blend"]:
        errors.append(f"[blend] trade charts are not DDF Value inputs, yet the blend tab shows {charts_in_blend or got['blend']}")
    if "Projections" not in got["blend_text"]:
        errors.append(f"[blend] the blend tab does not list the projection inputs: {got['blend_text'][:200]!r}")
    for where in ("lines",):
        held = [c for c in got[where] if c["src"] == HELD]
        if not held:
            errors.append(f"[{where}] the held source carries no chip at all (its row should say why it is out)")
        for c in held:
            if c["mark"]:
                errors.append(f"[{where}] {HELD}: the in-range check on a held source: {c}")
            if c["status"] != "held" or c["hold"] != level:
                errors.append(f"[{where}] {HELD}: chip is not the {level} hold marker: {c}")
            if level == "red" and (not c["aria"].startswith("Paused: ") or "Paused this week" not in (c["row"] or "")):
                errors.append(f"[{where}] {HELD}: a red hold reads 'Paused' beside the row's 'Paused this week': {c}")
            if level == "amber" and (c["text"] != "⚑ Lagging" or not c["aria"].startswith("Lagging: ")):
                errors.append(f"[{where}] {HELD}: a lag hold is the amber flag 'Lagging': {c}")
        open_marks = [c for c in got[where] if c["src"] == "fantasypros" and c["mark"]]
        if not open_marks:
            errors.append(f"[{where}] an open in-range source (FantasyPros) lost its check: {got[where]}")
    if level == "amber":
        on_page = [c for c in got["page"] if c["src"] == HELD]
        if {c["where"] for c in on_page} != {"legend", "head"}:
            errors.append(f"[amber] a lagging source stays in play, flagged in the legend and the table head: {on_page}")
        for c in on_page:
            if c["mark"] or c["text"] != "⚑ Lagging":
                errors.append(f"[amber] {c['where']}: {c}")
    else:
        on_page = [c for c in got["page"] if c["src"] == HELD]
        if on_page:
            errors.append(f"[red] a held source is hidden from the page, so nothing should flag it there: {on_page}")
    return errors


def check(level, v2_js=None) -> list[str]:
    return problems(read_chips(level, v2_js), level)


class HeldChipRenderTest(unittest.TestCase):
    def test_red_hold_shows_paused_not_the_check(self):
        self.assertEqual(check("red"), [])

    def test_amber_hold_shows_the_lag_flag_not_the_check(self):
        self.assertEqual(check("amber"), [])

    def test_guard_fails_when_a_chart_is_in_the_blend_tab(self):
        """A chart row or chip in the blend tab (the pre-JEG-804 shape) is reported."""
        for level in ("red", "amber"):
            got = read_chips(level)
            self.assertEqual(problems(got, level), [], "premise: the unmodified page is clean")
            self.assertTrue(problems({**got, "blend_text": got["blend_text"] + "\nCBS Sports"}, level), level)
            self.assertTrue(problems({**got, "blend": got["lines"]}, level), level)

    def test_guard_fails_on_broken_build(self):
        v2 = V2_JS.read_text(encoding="utf-8")
        anchor = "    const held = heldReason(view && view.infoByKey && view.infoByKey[key]);\n"
        self.assertIn(anchor, v2, "stale mutation anchor")
        broken = v2.replace(anchor, "    const held = false;\n", 1)
        broken = broken.replace("const level = held ? (sourceHoldLevel(publisher) === \"amber\" ? \"amber\" : \"red\") : sourceHoldLevel(publisher);",
                                "const level = null;", 1)
        self.assertNotEqual(broken, v2)
        errors = check("red", v2_js=broken)
        self.assertTrue(any("the in-range check on a held source" in e for e in errors), f"the broken build was not caught: {errors}")


if __name__ == "__main__":
    unittest.main()
