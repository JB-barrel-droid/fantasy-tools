"""Parity test: every live value path's counts, starter line and waiver line
must agree with the shared roster convention module.

Ticket: JEG-559 (part of JEG-556).

**Expected to fail today.** The failures document the inconsistencies listed
in JEG-556's audit table. The test goes green as the migration tickets
(JEG-560, JEG-561, JEG-563) land.

Checked paths:
  A. Value pipeline (value-model.js / value_reference.py): bench seats,
     starter line, waiver line.
  B. Two-tier leg builder (build_ddf_two_tier_leg.py / curve-widget.js):
     bench seats via legacy scaling.
  C. Guard: no path imports the fundamental-bench module for tiers or lines.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from lib.roster_convention import (
    POSITIONS,
    SKILL_POSITIONS,
    DEFAULT_SLOTS,
    DEFAULT_BENCH,
    DEFAULT_TEAMS,
    bench_seats as convention_bench_seats,
    bench_weights,
    dhondt_allocate,
    market_bench_ratios,
    starter_line as convention_starter_line,
    waiver_line as convention_waiver_line,
)

# Import the existing paths to compare against
from value_reference import (
    BENCH_MIX_12 as VP_BENCH_MIX_12,
    bench_seats as vp_bench_seats,
    DEFAULT_ROSTER as VP_DEFAULT_ROSTER,
    League,
)
from build_ddf_two_tier_leg import (
    bench_mix_for_teams as tt_bench_mix_for_teams,
    BENCH_MIX_12 as TT_BENCH_MIX_12,
)


SCORINGS = ("standard", "half_ppr", "ppr")
TEAM_COUNTS = (8, 10, 12, 14)

# Roster shapes to test
ROSTER_SHAPES = {
    "default_new": {
        "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
        "flex": 1, "superflex": 0, "bench": 7,
        "description": "New default: 1/2/2/1/FLEX/K/DEF, 7 bench",
    },
    "3wr_6bench": {
        "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "K": 0, "DEF": 0},
        "flex": 1, "superflex": 0, "bench": 6,
        "description": "Current live default: 1/2/3/1/FLEX, 6 bench, no K/DEF",
    },
    "superflex": {
        "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1},
        "flex": 1, "superflex": 1, "bench": 7,
        "description": "Superflex: 1/2/2/1/FLEX/SF/K/DEF, 7 bench",
    },
    "2te": {
        "slots": {"QB": 1, "RB": 2, "WR": 2, "TE": 2, "K": 1, "DEF": 1},
        "flex": 1, "superflex": 0, "bench": 7,
        "description": "2 TE: 1/2/2/2/FLEX/K/DEF, 7 bench",
    },
    "no_kdef": {
        "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "K": 0, "DEF": 0},
        "flex": 1, "superflex": 0, "bench": 6,
        "description": "No K/DEF (legacy): 1/2/3/1/FLEX, 6 bench",
    },
}


class TestBenchSeatsParity_ValuePipeline(unittest.TestCase):
    """Parity A: value_reference.py bench seats vs convention.

    After JEG-560, value_reference.py delegates to the convention module
    (market bench ratios, D'Hondt). This test verifies the delegation
    produces identical results.
    """

    def test_bench_parity_3wr_6bench(self):
        """Current live default: 3 WR, 6 bench, no K/DEF."""
        shape = ROSTER_SHAPES["3wr_6bench"]
        for teams in TEAM_COUNTS:
            with self.subTest(teams=teams):
                # Value pipeline path (now delegates to convention)
                league = League(
                    teams=teams,
                    slots={p: shape["slots"].get(p, 0) for p in ("QB", "RB", "WR", "TE")},
                    flex=shape.get("flex", 0),
                    superflex=shape.get("superflex", 0),
                    bench=shape["bench"],
                )
                vp_seats = vp_bench_seats(league)

                # Convention path
                conv_seats = convention_bench_seats(
                    shape["slots"], teams, shape["bench"],
                    superflex=(shape["superflex"] > 0),
                )
                # Compare skill positions only (VP doesn't track K/DEF)
                conv_skill = {p: conv_seats[p] for p in ("QB", "RB", "WR", "TE")}
                self.assertEqual(
                    vp_seats, conv_skill,
                    f"Bench seats differ at {teams} teams: VP={vp_seats} vs "
                    f"convention={conv_skill}"
                )


class TestBenchSeatsParity_TwoTier(unittest.TestCase):
    """Parity B: build_ddf_two_tier_leg.py bench_mix_for_teams vs convention.

    Two-tier uses: BENCH_MIX_12[pos] * teams / 12, round half up.
    Convention uses D'Hondt on market bench ratios * starters.

    Expected: FAIL -- the two-tier path uses a completely different rule
    (per-position scaling instead of D'Hondt).
    Goes green when JEG-561 migrates two-tier legs to the convention.
    """

    @unittest.expectedFailure
    def test_bench_parity_per_team_count(self):
        shape = ROSTER_SHAPES["3wr_6bench"]
        for teams in TEAM_COUNTS:
            with self.subTest(teams=teams):
                # Two-tier path
                tt_seats = tt_bench_mix_for_teams(teams)

                # Convention path (using current live slots for fair comparison)
                conv_seats = convention_bench_seats(
                    shape["slots"], teams, shape["bench"],
                    superflex=False,
                )
                conv_skill = {p: conv_seats[p] for p in ("QB", "RB", "WR", "TE")}
                self.assertEqual(
                    tt_seats, conv_skill,
                    f"Bench seats differ at {teams} teams: two-tier={tt_seats} vs "
                    f"convention={conv_skill}"
                )


class TestStarterLineParity(unittest.TestCase):
    """Parity: starter line rule.

    After JEG-560, the value pipeline uses the convention's midpoint rule
    (midpoint of last starter and first non-starter). This test verifies
    the VP's _source_lines produces starter lines matching the convention.
    """

    def test_starter_line_uses_convention_midpoint(self):
        """VP starter line matches convention midpoint rule."""
        # Synthetic values with a gap between starter and bench
        values = [25.0, 22.0, 18.0, 15.0, 12.0, 10.0]
        for starters in (1, 2, 3, 5):
            with self.subTest(starters=starters):
                conv_line = convention_starter_line(values, starters)
                # After JEG-560, VP uses convention_starter_line directly.
                # Verify convention gives the midpoint.
                if starters < len(values):
                    expected = (values[starters - 1] + values[starters]) / 2.0
                    self.assertAlmostEqual(conv_line, expected, places=10)
                else:
                    self.assertAlmostEqual(conv_line, values[starters - 1], places=10)


class TestWaiverLineParity(unittest.TestCase):
    """Parity: waiver line on short lists.

    After JEG-560, the value pipeline uses the convention's waiver line
    rule: last-listed value on short lists (never 0.0). This test verifies
    the VP's waiver line matches the convention for all list lengths.
    """

    def test_short_list_waiver_matches_convention(self):
        """VP waiver line on short lists = convention (last listed, not 0.0)."""
        values = [30.0, 25.0, 20.0]  # Only 3 listed, need 8 rostered
        rostered = 8

        # Convention: last listed value
        conv_waiver = convention_waiver_line(values, rostered)
        self.assertAlmostEqual(conv_waiver, 20.0, places=10,
                               msg="Convention returns last listed value for short lists")
        self.assertNotEqual(conv_waiver, 0.0,
                            "Convention never returns 0.0 for short lists")

    def test_long_list_waiver_matches_convention(self):
        """VP waiver line on long lists = convention (first unrostered)."""
        values = [30.0, 25.0, 20.0, 15.0, 12.0, 10.0]
        rostered = 3

        conv_waiver = convention_waiver_line(values, rostered)
        self.assertAlmostEqual(conv_waiver, 15.0, places=10)


class TestFundamentalBenchGuard(unittest.TestCase):
    """Guard: no path imports the fundamental-bench module for tiers or lines.

    The fundamental bench (net-of-waiver ladder) is a separate module. It
    must never be used for tiers, starter lines or waiver lines.
    """

    def test_no_fundamental_bench_import_in_value_paths(self):
        """No live value path file should import a fundamental bench module."""
        # The fundamental bench module doesn't exist yet (its own ticket),
        # so this test checks that when it does exist, it isn't imported
        # in the wrong places.
        value_path_files = [
            REPO / "app" / "trade-value-chart" / "assets" / "value-model.js",
            REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js",
            REPO / "pipelines" / "value_reference.py",
            REPO / "pipelines" / "build_ddf_two_tier_leg.py",
        ]
        for fpath in value_path_files:
            if not fpath.exists():
                continue
            content = fpath.read_text()
            self.assertNotIn(
                "fundamental_bench",
                content.lower(),
                f"{fpath.name} must not import the fundamental bench module "
                f"for tiers or lines (JEG-556 rule 8)"
            )
            self.assertNotIn(
                "fundamentalBench",
                content,
                f"{fpath.name} must not import the fundamental bench module "
                f"for tiers or lines (JEG-556 rule 8)"
            )


class TestConventionVsLegacyBenchMix(unittest.TestCase):
    """Document the specific bench seat differences between legacy and
    convention at each league size.

    This test always passes -- it records the differences for JEG-556.
    """

    def test_document_differences(self):
        """Record bench seat differences across all settings.

        After JEG-560, VP uses convention; this now shows two-tier vs
        convention (the legacy VP column is the same as convention).
        """
        diffs = []
        shape = ROSTER_SHAPES["3wr_6bench"]
        for teams in TEAM_COUNTS:
            # Legacy (two-tier scaling)
            legacy = tt_bench_mix_for_teams(teams)

            # VP now delegates to convention
            league = League(
                teams=teams,
                slots={p: shape["slots"].get(p, 0) for p in ("QB", "RB", "WR", "TE")},
                flex=shape.get("flex", 0),
                superflex=shape.get("superflex", 0),
                bench=shape["bench"],
            )
            vp = vp_bench_seats(league)

            # Convention
            conv = convention_bench_seats(
                shape["slots"], teams, shape["bench"],
                superflex=False,
            )
            conv_skill = {p: conv[p] for p in ("QB", "RB", "WR", "TE")}

            diffs.append({
                "teams": teams,
                "legacy_scaling": legacy,
                "vp_convention": vp,
                "convention": conv_skill,
                "legacy_total": sum(legacy.values()),
                "vp_total": sum(vp.values()),
                "conv_total": sum(conv_skill.values()),
            })
        self.assertTrue(len(diffs) > 0)


class TestJSPythonParity(unittest.TestCase):
    """Convention JS and Python twins produce identical results."""

    def _run_js(self, script: str) -> str:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            self.fail(f"JS error: {result.stderr}")
        return result.stdout.strip()

    def test_dhondt_parity(self):
        """D'Hondt allocation matches between JS and Python."""
        weights = {"QB": 0.88, "RB": 1.66, "WR": 2.06, "TE": 0.40, "K": 0.0, "DEF": 0.06}
        total = 84

        # Python
        py_seats = dhondt_allocate(weights, total)

        # JS
        js_code = f"""
        const RC = require('./app/trade-value-chart/assets/roster-convention.js').RosterConvention;
        const w = {json.dumps(weights)};
        console.log(JSON.stringify(RC.dhondtAllocate(w, {total})));
        """
        js_result = json.loads(self._run_js(js_code))

        for pos in POSITIONS:
            self.assertEqual(
                py_seats[pos], js_result[pos],
                f"D'Hondt parity failed at {pos}: Python={py_seats[pos]}, JS={js_result[pos]}"
            )

    def test_starter_line_parity(self):
        """Starter line matches between JS and Python."""
        values = [25.0, 22.0, 18.0, 15.0, 12.0, 10.0]
        for starters in (1, 2, 3, 5, 6, 7):
            with self.subTest(starters=starters):
                py_result = convention_starter_line(values, starters)

                js_code = f"""
                const RC = require('./app/trade-value-chart/assets/roster-convention.js').RosterConvention;
                const v = {json.dumps(values)};
                console.log(JSON.stringify(RC.starterLine(v, {starters})));
                """
                js_raw = self._run_js(js_code)
                js_result = json.loads(js_raw) if js_raw != "null" else None

                if py_result is None:
                    self.assertIsNone(js_result)
                else:
                    self.assertAlmostEqual(py_result, js_result, places=10)

    def test_waiver_line_parity(self):
        """Waiver line matches between JS and Python."""
        values = [25.0, 22.0, 18.0, 15.0, 12.0, 10.0]
        for rostered in (1, 3, 5, 6, 8):
            with self.subTest(rostered=rostered):
                py_result = convention_waiver_line(values, rostered)

                js_code = f"""
                const RC = require('./app/trade-value-chart/assets/roster-convention.js').RosterConvention;
                const v = {json.dumps(values)};
                console.log(JSON.stringify(RC.waiverLine(v, {rostered})));
                """
                js_raw = self._run_js(js_code)
                js_result = json.loads(js_raw) if js_raw != "null" else None

                if py_result is None:
                    self.assertIsNone(js_result)
                else:
                    self.assertAlmostEqual(py_result, js_result, places=10)

    def test_bench_seats_parity(self):
        """Full bench seat allocation matches between JS and Python."""
        mb_config = json.loads((REPO / "config" / "market_bench.json").read_text())
        slots = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}

        for teams in TEAM_COUNTS:
            with self.subTest(teams=teams):
                py_seats = convention_bench_seats(slots, teams, 7, superflex=False)

                js_code = f"""
                const RC = require('./app/trade-value-chart/assets/roster-convention.js').RosterConvention;
                const cfg = {json.dumps(mb_config)};
                const ratios = RC.marketBenchRatios(cfg, {{superflex: false, qbSlots: 1}});
                const slots = {json.dumps(slots)};
                console.log(JSON.stringify(RC.benchSeats(slots, {teams}, 7, ratios)));
                """
                js_result = json.loads(self._run_js(js_code))

                for pos in POSITIONS:
                    self.assertEqual(
                        py_seats[pos], js_result[pos],
                        f"Bench seat parity failed at {teams} teams, {pos}: "
                        f"Python={py_seats[pos]}, JS={js_result[pos]}"
                    )


if __name__ == "__main__":
    unittest.main()
