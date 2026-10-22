"""v2 JEG-826: honesty banner when DDF Value is built from the same charts
it is compared against.

Two states:
  1. Independent (pinned fixture: 3 charts + 3 projections open) — no banner on
     Trade targets, Compare verdict or How values work.
  2. Circular (all projections also held: only charts in the blend) — the banner
     is visible on Trade targets and Compare verdict, the DDF Value definition on
     How values work carries the inline note, and "every source agrees" / deal
     read copy is softened.

Discrimination: the banner must NOT appear when independent sources exist
(the pinned fixture has projections open).
"""
from __future__ import annotations

import contextlib
import copy
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

from tests import _render_env  # noqa: E402
from tests.test_published_league_settings_render import _chromium_executable  # noqa: E402
from tests._holds import pin_holds_in_dist, HOLD_FIELDS  # noqa: E402


def _hold_projections_in_dist(dist):
    """Additionally hold all projection sources (espn, cbsros, razzball) so the
    blend is charts-only, making it circular."""
    path = Path(dist) / "assets" / "comparison-sources-data.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    for root in ("espn", "cbsros", "razzball"):
        for sec in (root, f"{root}_adjusted", f"{root}_vorp"):
            section = data.get("sources", {}).get(sec)
            if isinstance(section, dict):
                section["validationHold"] = {
                    "reason": "chain hold: fidelity check",
                    "root": root,
                    "stage": "fidelity",
                }
    path.write_text(json.dumps(data, separators=(",", ":")), encoding="utf-8")


@contextlib.contextmanager
def _served(hold_projections=False):
    if not (DIST / "index.html").exists():
        raise _render_env.unavailable("dist/index.html is not built")
    with tempfile.TemporaryDirectory() as tmp:
        dist = Path(tmp) / "dist"
        shutil.copytree(DIST, dist)
        pin_holds_in_dist(dist)
        if hold_projections:
            _hold_projections_in_dist(dist)

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


# JS snippet: read the banner state and independence check from the page.
READ_TARGETS = """() => {
  const banner = document.getElementById('v2TCircularBanner');
  const text = document.getElementById('v2TCircularText');
  const check = window.TradeValueV2.blendIndependenceCheck('ddf_value');
  const sellMeta = document.getElementById('v2TSellMeta').textContent;
  const buyMeta = document.getElementById('v2TBuyMeta').textContent;
  return {
    bannerHidden: banner.hidden,
    bannerText: text.textContent,
    circular: check ? check.circular : null,
    independent: check ? check.independent : null,
    blendSources: check ? check.blendSources : null,
    sellMeta, buyMeta
  };
}"""

READ_COMPARE = """() => {
  const banner = document.getElementById('v2CCircularBanner');
  const text = document.getElementById('v2CCircularText');
  const dealText = document.getElementById('v2CDealText');
  const storyTitle = document.querySelector('#v2CStory summary') || {};
  const verdictText = document.getElementById('v2CVerdictText');
  return {
    bannerHidden: banner.hidden,
    bannerText: text.textContent,
    dealText: dealText ? dealText.textContent : '',
    storyTitle: storyTitle.textContent || '',
    verdictText: verdictText ? verdictText.textContent : ''
  };
}"""

READ_HOW = """() => {
  const note = document.getElementById('v2HowCircular');
  return {
    noteHidden: note.hidden,
    noteText: note.textContent
  };
}"""

# Pick a trade from the top engine rows (deterministic).
PICK_TRADE = """() => {
  const rows = window.TradeValueCurveControls.getRows();
  const priced = rows.filter(r => r.values && Number.isFinite(r.values.ddf_value));
  if (priced.length < 4) return null;
  const sorted = priced.sort((a, b) => b.values.ddf_value - a.values.ddf_value);
  return {give: [sorted[0].player_key, sorted[2].player_key],
          get: [sorted[1].player_key, sorted[3].player_key]};
}"""


def setUpModule():
    _render_env.ensure_built()


class CircularBannerRenderTest(unittest.TestCase):
    """Banner shown when circular, hidden when independent."""

    def test_independent_no_banner(self):
        """With projections open (pinned fixture), no banner appears."""
        from playwright.sync_api import sync_playwright
        with _served(hold_projections=False) as url, sync_playwright() as pw:
            exe = _chromium_executable(pw)
            if not exe:
                self.skipTest("No Chromium executable found")
            browser = pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                page.goto(url + "#trade-targets", wait_until="networkidle", timeout=30000)
                page.wait_for_selector("#v2TSellTitle", timeout=15000)
                page.wait_for_timeout(500)

                targets = page.evaluate(READ_TARGETS)
                self.assertTrue(targets["bannerHidden"], "Banner should be hidden when blend has independent sources")
                self.assertFalse(targets["circular"], "Blend should not be circular with projections open")
                self.assertGreater(targets["independent"], 0, "Should have independent sources")
                self.assertIn("Offer them", targets["sellMeta"], "Sell copy should be normal when independent")
                self.assertIn("Ask for them", targets["buyMeta"], "Buy copy should be normal when independent")

                # How values work: no inline note
                page.goto(url + "#how-values", wait_until="networkidle", timeout=15000)
                page.wait_for_selector("#v2HowNamesTitle", timeout=15000)
                page.wait_for_timeout(500)
                how = page.evaluate(READ_HOW)
                self.assertTrue(how["noteHidden"], "How-values note should be hidden when independent")

            finally:
                browser.close()

    def test_circular_banner_shown(self):
        """With all projections held (charts-only blend), the banner appears."""
        from playwright.sync_api import sync_playwright
        with _served(hold_projections=True) as url, sync_playwright() as pw:
            exe = _chromium_executable(pw)
            if not exe:
                self.skipTest("No Chromium executable found")
            browser = pw.chromium.launch(executable_path=exe, args=_render_env.HERMETIC_ARGS)
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            try:
                page.goto(url + "#trade-targets", wait_until="networkidle", timeout=30000)
                page.wait_for_selector("#v2TSellTitle", timeout=15000)
                page.wait_for_timeout(500)

                targets = page.evaluate(READ_TARGETS)
                self.assertFalse(targets["bannerHidden"], "Banner should be visible when blend is circular")
                self.assertTrue(targets["circular"], "Blend should be circular with all projections held")
                self.assertEqual(targets["independent"], 0, "Should have no independent sources")
                self.assertIn("same trade charts", targets["bannerText"],
                              "Banner text should mention same trade charts")
                self.assertIn("Projection sources are updating", targets["bannerText"])
                # Softened copy
                self.assertNotIn("Offer them", targets["sellMeta"],
                                 "Sell copy should be softened when circular")
                self.assertNotIn("Ask for them", targets["buyMeta"],
                                 "Buy copy should be softened when circular")

                # Compare: open a trade and check the compare banner
                trade = page.evaluate(PICK_TRADE)
                if trade:
                    give = ",".join(str(k) for k in trade["give"])
                    get = ",".join(str(k) for k in trade["get"])
                    page.goto(url + f"#compare-trade?give={give}&get={get}",
                              wait_until="networkidle", timeout=15000)
                    page.wait_for_selector("#v2CVerdictTitle", timeout=15000)
                    page.wait_for_timeout(500)

                    compare = page.evaluate(READ_COMPARE)
                    self.assertFalse(compare["bannerHidden"],
                                     "Compare banner should be visible when circular")
                    self.assertIn("same trade charts", compare["bannerText"])
                    # Deal read should have the "(same inputs)" parenthetical
                    if compare["dealText"]:
                        self.assertIn("not an independent check", compare["dealText"],
                                      "Deal read should note the shared inputs")

                # How values work
                page.goto(url + "#how-values", wait_until="networkidle", timeout=15000)
                page.wait_for_selector("#v2HowNamesTitle", timeout=15000)
                page.wait_for_timeout(500)
                how = page.evaluate(READ_HOW)
                self.assertFalse(how["noteHidden"], "How-values note should be visible when circular")
                self.assertIn("built entirely from trade charts", how["noteText"])

            finally:
                browser.close()


if __name__ == "__main__":
    unittest.main()
