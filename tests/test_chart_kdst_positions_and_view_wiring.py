"""Regression guards for the 2026-10-03 49cd201 stale-base clobber.

Commit 49cd201 (JEG-292, pushed from a stale working tree) silently reverted
two live fixes in app/trade-value-chart/assets/curve-widget.js:
  1. 112927d (JEG-211): the chart Position filter's POSITIONS constant lost its
     K/DST exclusion, so K/DST buttons reappeared on production.
  2. c1809bed (JEG-210): the entire Source Curves view-mode wiring
     (setViewMode/makeViewModeTabs/VIEW_MODE_DEFS/buildVorpViewSourceMap/
     sourceHasVorpView) was deleted, so the Indexed | Value above waivers |
     Adjusted values tabs became decorative dead buttons.

The JEG-298 repair (5af4259) fixed the specialist plumbing but missed both of
these, so neither had a failing test to catch the regression. These guards
pin the exact surface: the top-level POSITIONS constant (the one makeTabs()
reads) and the view-mode wiring. Each test is proven to FAIL against the
49cd201/5af4259 file state (verified by running against the pre-fix file).
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"
INDEX = ROOT / "app" / "trade-value-chart" / "index.html"


def top_level_positions(text):
    """Return the entries of the FIRST (top-level, makeTabs-driving) POSITIONS array."""
    m = re.search(r'^\s*const POSITIONS\s*=\s*\[([^\]]*)\];', text, re.M)
    if not m:
        return None
    return [e.strip().strip('"\'') for e in m.group(1).split(',') if e.strip()]


class ChartPositionsKdstExclusionTest(unittest.TestCase):
    """JEG-211: the chart Position filter must not offer K/DST."""

    def test_top_level_positions_excludes_kdst(self):
        """The makeTabs-driving POSITIONS constant must not contain K or DST.

        Jeremy 2026-10-03: 'get rid of it on the chart entirely' (honest
        exclusion). The 49cd201 stale-base push reintroduced them here while
        leaving CHART_POSITIONS clean, so this pins the exact constant.
        """
        entries = top_level_positions(WIDGET.read_text())
        self.assertIsNotNone(entries, "top-level POSITIONS constant not found in curve-widget.js")
        self.assertNotIn("K", entries, "POSITIONS must not contain K (JEG-211)")
        self.assertNotIn("DST", entries, "POSITIONS must not contain DST (JEG-211)")
        self.assertEqual(entries, ["ALL", "QB", "RB", "WR", "TE", "FLEX"],
                         "POSITIONS must be exactly the six chart positions")

    def test_no_specialist_position_arrays_in_widget(self):
        """No live SPECIALIST_POSITIONS / includeSpecialists code may remain."""
        text = WIDGET.read_text()
        # Strip comments so a historical note doesn't trip the guard.
        code = re.sub(r'//[^\n]*', '', text)
        code = re.sub(r'/\*.*?\*/', '', code, flags=re.S)
        self.assertNotIn("SPECIALIST_POSITIONS", code,
                         "SPECIALIST_POSITIONS must not exist in live code")
        self.assertNotIn("includeSpecialists", code,
                         "includeSpecialists must not exist in live code")


class ViewModeWiringTest(unittest.TestCase):
    """JEG-210: the Source Curves view tabs must be wired, not decorative."""

    def test_view_mode_plumbing_present(self):
        """All view-mode functions/constants must exist in curve-widget.js."""
        text = WIDGET.read_text()
        for name in ("VIEW_MODE_DEFS", "VIEW_MODE_ORDER",
                     "function setViewMode", "function makeViewModeTabs",
                     "function buildVorpViewSourceMap", "function sourceHasVorpView"):
            self.assertIn(name, text,
                          f"{name} must exist in curve-widget.js (view wiring)")

    def test_view_tabs_wired_in_init(self):
        """init() must call makeViewModeTabs() so the tab clicks do something."""
        text = WIDGET.read_text()
        self.assertRegex(text, r'makeViewModeTabs\(\);',
                         "init() must invoke makeViewModeTabs()")

    def test_tab_container_queried_by_widget(self):
        """The widget must query #viewModeTabs; otherwise the HTML tabs are dead."""
        text = WIDGET.read_text()
        self.assertIn("#viewModeTabs", text,
                      "curve-widget.js must reference #viewModeTabs")
        html = INDEX.read_text()
        self.assertIn('id="viewModeTabs"', html,
                      "index.html must contain the viewModeTabs container")

    def test_build_source_map_uses_view_values(self):
        """buildSourceMap must consult vorp_views for non-indexed views."""
        text = WIDGET.read_text()
        self.assertIn("buildVorpViewSourceMap(key, viewKey)", text,
                      "buildSourceMap must route non-indexed views through vorp_views")


class ViewModeSwitchesDisplayedSourcesTest(unittest.TestCase):
    """JEG-210 follow-up: the tabs must visibly change the chart, not just the tab state.

    The c1809bed wiring switched the *values* of the as-published sources but
    left the default selection (ESPN + the *_adjusted family, which carry no
    vorp views) untouched -- so every tab showed identical numbers. The fix
    makes setViewMode activate the view-capable sources on entry and restore
    the user's selection on return to Indexed.
    """

    def test_set_view_mode_activates_vorp_capable_sources(self):
        """Entering a non-indexed view must switch activeSources to the vorp_view keys."""
        text = WIDGET.read_text()
        self.assertIn("savedActiveSourcesForView", text,
                      "setViewMode must save/restore the user's source selection")
        # The non-indexed branch must filter AS_PUBLISHED_KEYS by vorp-view availability.
        self.assertRegex(
            text,
            r'\[\.\.\.AS_PUBLISHED_KEYS\]\.filter\(key => sourceHasVorpView\(key\)\)',
            "setViewMode must activate the vorp-view-capable published sources")

    def test_set_view_mode_restores_indexed_selection(self):
        """Returning to Indexed must restore the saved source selection."""
        text = WIDGET.read_text()
        self.assertRegex(
            text,
            r'if \(mode === "indexed"\) \{\s*if \(savedActiveSourcesForView\)',
            "setViewMode must restore the saved selection on return to Indexed")

    def test_agreement_check_reads_indexed_units(self):
        """The anchor-band health check must not compare VORP/adjusted units.

        In a non-indexed view the as-published source maps carry VORP/adjusted
        values; comparing those against the ESPN anchor would false-fail the
        0.8-1.25x band. agreementFor must read indexed units via
        indexedMapForAgreement.
        """
        text = WIDGET.read_text()
        self.assertIn("function indexedMapForAgreement", text,
                      "indexedMapForAgreement must exist")
        self.assertIn("indexedMapForAgreement(key)", text,
                      "agreementFor must read indexed units for the anchor band")


if __name__ == "__main__":
    unittest.main()
