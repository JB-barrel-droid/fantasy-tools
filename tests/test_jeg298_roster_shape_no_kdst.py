"""JEG-298: roster-shape panel must not render dead K/DST inputs.

JEG-211 excluded K/DST from the chart entirely (POSITION_ORDER is
[QB, RB, WR, TE] everywhere). The roster-shape panel kept rendering K and DST
number inputs that were no-ops: setting them changed nothing on the chart
while implying a capability the chart no longer has.

This test guards the honest exclusion end-to-end at the source level:
1. makeRosterControls() must not build roster inputs for K/DST.
2. setRosterSpot() must not carry K/DST min/max branches.
3. The panel itself (and QB/RB/WR/TE/FLEX/BENCH inputs) must stay intact.
"""
from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WIDGET = ROOT / "app" / "trade-value-chart" / "assets" / "curve-widget.js"


def read_widget() -> str:
    return WIDGET.read_text(encoding="utf-8")


class TestJeg298RosterShapeNoKdst(unittest.TestCase):
    def test_make_roster_controls_has_no_k_dst(self) -> None:
        src = read_widget()
        m = re.search(
            r"function makeRosterControls\(\)\s*\{(.*?)\n  function ",
            src,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "makeRosterControls() not found")
        body = m.group(1)
        self.assertNotRegex(body, r'\[\s*"K"\s*,\s*"K"\s*\]',
                            "makeRosterControls still builds a K roster input")
        self.assertNotRegex(body, r'\[\s*"DST"\s*,\s*"DST"\s*\]',
                            "makeRosterControls still builds a DST roster input")

    def test_make_roster_controls_keeps_skill_positions(self) -> None:
        src = read_widget()
        for key in ("QB", "RB", "WR", "TE", "FLEX", "BENCH"):
            self.assertRegex(src, rf'\[\s*"{key}"\s*,',
                             f"makeRosterControls lost the {key} roster input")

    def test_set_roster_spot_has_no_k_dst_branches(self) -> None:
        src = read_widget()
        m = re.search(
            r"function setRosterSpot\(key, raw, publish = true\)\s*\{(.*?)\n  function ",
            src,
            re.DOTALL,
        )
        self.assertIsNotNone(m, "setRosterSpot() not found")
        body = m.group(1)
        self.assertNotIn('"K"', body, "setRosterSpot still has K-specific min/max logic")
        self.assertNotIn('"DST"', body, "setRosterSpot still has DST-specific min/max logic")
        # The rosterShape key guard must remain (rejects unknown keys like K/DST).
        self.assertIn("hasOwnProperty.call(rosterShape, key)", body)

    def test_jeg211_honest_exclusion_intact(self) -> None:
        """The JEG-292 commit 49cd201 reintroduced the pre-JEG-211 K/DST
        apparatus from a stale base (SPECIALIST_POSITIONS, includeSpecialists,
        specialist toggle wiring, CHART_POSITIONS with specialists). JEG-211's
        honest exclusion must hold: no chart surface admits K/DST."""
        src = read_widget()
        self.assertNotRegex(src, r'const SPECIALIST_POSITIONS\s*=',
                            "SPECIALIST_POSITIONS reintroduced")
        self.assertNotIn("includeSpecialists", src,
                         "includeSpecialists toggle state reintroduced")
        self.assertNotIn("specialistProjection", src,
                         "specialist projection path reintroduced in buildCanonicalMap")
        self.assertRegex(src, r"const CHART_POSITIONS = \[\.\.\.POSITION_ORDER\];",
                         "CHART_POSITIONS must be the skill positions only (JEG-211)")


if __name__ == "__main__":
    unittest.main()
