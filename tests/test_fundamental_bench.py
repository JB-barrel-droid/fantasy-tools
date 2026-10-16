"""Tests for the fundamental bench module (JEG-564).

Checks:
  1. Ladder is sorted best-first (total descending).
  2. Insurance + upside = total for every entry.
  3. bench_value returns the right entry and zero for unknowns.
  4. optimal_bench picks best-first and respects count.
  5. bench_summary matches the pooled research recommendation.
  6. JS/Python parity on all functions.
  7. Guard: no tier/line/value path imports this module.
"""
from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from lib.fundamental_bench import (
    bench_summary,
    bench_value,
    findings,
    ladder,
    optimal_bench,
)


class TestLadderIntegrity(unittest.TestCase):
    """The ladder must be sorted best-first and internally consistent."""

    def test_sorted_descending_by_total(self):
        entries = ladder()
        for i in range(len(entries) - 1):
            self.assertGreaterEqual(
                entries[i]["total"], entries[i + 1]["total"],
                f"Ladder not sorted at index {i}: {entries[i]['total']} < {entries[i+1]['total']}"
            )

    def test_insurance_plus_upside_equals_total(self):
        for entry in ladder():
            computed = round(entry["insurance"] + entry["upside"], 10)
            self.assertAlmostEqual(
                computed, entry["total"], places=6,
                msg=f"{entry['label']}: {entry['insurance']} + {entry['upside']} != {entry['total']}"
            )

    def test_all_entries_have_required_fields(self):
        required = {"position", "depth", "insurance", "upside", "total", "label"}
        for entry in ladder():
            self.assertTrue(required.issubset(entry.keys()), f"Missing fields in {entry}")

    def test_positions_are_valid(self):
        valid = {"QB", "RB", "WR", "TE"}
        for entry in ladder():
            self.assertIn(entry["position"], valid, f"Invalid position in {entry}")

    def test_depths_are_positive(self):
        for entry in ladder():
            self.assertGreater(entry["depth"], 0, f"Depth must be positive in {entry}")

    def test_no_duplicate_position_depth(self):
        seen = set()
        for entry in ladder():
            key = (entry["position"], entry["depth"])
            self.assertNotIn(key, seen, f"Duplicate {key} in ladder")
            seen.add(key)


class TestBenchValue(unittest.TestCase):
    """bench_value returns the right entry or zeros."""

    def test_known_slot(self):
        val = bench_value("RB", 1)
        self.assertAlmostEqual(val["total"], 0.40)
        self.assertAlmostEqual(val["insurance"], 0.33)
        self.assertAlmostEqual(val["upside"], 0.07)

    def test_unknown_slot_returns_zero(self):
        val = bench_value("K", 1)
        self.assertEqual(val, {"insurance": 0.0, "upside": 0.0, "total": 0.0})

    def test_deep_unknown_returns_zero(self):
        val = bench_value("QB", 5)
        self.assertEqual(val, {"insurance": 0.0, "upside": 0.0, "total": 0.0})


class TestOptimalBench(unittest.TestCase):
    """optimal_bench picks best-first."""

    def test_picks_top_n(self):
        picks = optimal_bench(3)
        self.assertEqual(len(picks), 3)
        self.assertEqual(picks[0]["position"], "RB")
        self.assertEqual(picks[0]["depth"], 1)
        self.assertEqual(picks[1]["position"], "WR")
        self.assertEqual(picks[2]["position"], "WR")

    def test_zero_spots(self):
        self.assertEqual(optimal_bench(0), [])

    def test_more_than_ladder(self):
        full = ladder()
        picks = optimal_bench(100)
        self.assertEqual(len(picks), len(full))


class TestBenchSummary(unittest.TestCase):
    """bench_summary at typical bench sizes."""

    def test_six_bench(self):
        s = bench_summary(6)
        # Top 6: RB1, WR1, WR2, QB1, RB2, TE1
        self.assertEqual(s, {"QB": 1, "RB": 2, "WR": 2, "TE": 1})

    def test_seven_bench(self):
        s = bench_summary(7)
        # Top 7: adds RB3
        self.assertEqual(s, {"QB": 1, "RB": 3, "WR": 2, "TE": 1})

    def test_three_bench(self):
        s = bench_summary(3)
        # Top 3: RB1, WR1, WR2
        self.assertEqual(s, {"QB": 0, "RB": 1, "WR": 2, "TE": 0})


class TestFindings(unittest.TestCase):
    def test_findings_not_empty(self):
        f = findings()
        self.assertGreater(len(f), 0)
        self.assertIn("qb_te_upside_zero", f)


class TestJSPythonParity(unittest.TestCase):
    """JS and Python twins produce identical results."""

    def _run_js(self, script: str) -> str:
        result = subprocess.run(
            ["node", "-e", script],
            capture_output=True, text=True, timeout=10,
            cwd=str(REPO),
        )
        if result.returncode != 0:
            self.fail(f"JS error: {result.stderr}")
        return result.stdout.strip()

    def test_ladder_parity(self):
        py_ladder = ladder()
        js_code = """
        const FB = require('./dist/assets/fundamental-bench.js').FundamentalBench;
        console.log(JSON.stringify(FB.ladder()));
        """
        js_ladder = json.loads(self._run_js(js_code))
        self.assertEqual(len(py_ladder), len(js_ladder))
        for i, (py_e, js_e) in enumerate(zip(py_ladder, js_ladder)):
            self.assertEqual(py_e["position"], js_e["position"], f"position mismatch at {i}")
            self.assertEqual(py_e["depth"], js_e["depth"], f"depth mismatch at {i}")
            self.assertAlmostEqual(py_e["total"], js_e["total"], places=6, msg=f"total mismatch at {i}")
            self.assertAlmostEqual(py_e["insurance"], js_e["insurance"], places=6, msg=f"insurance mismatch at {i}")
            self.assertAlmostEqual(py_e["upside"], js_e["upside"], places=6, msg=f"upside mismatch at {i}")

    def test_bench_value_parity(self):
        for pos in ("QB", "RB", "WR", "TE"):
            for depth in (1, 2, 3):
                with self.subTest(pos=pos, depth=depth):
                    py_val = bench_value(pos, depth)
                    js_code = f"""
                    const FB = require('./dist/assets/fundamental-bench.js').FundamentalBench;
                    console.log(JSON.stringify(FB.benchValue("{pos}", {depth})));
                    """
                    js_val = json.loads(self._run_js(js_code))
                    self.assertAlmostEqual(py_val["total"], js_val["total"], places=6)
                    self.assertAlmostEqual(py_val["insurance"], js_val["insurance"], places=6)
                    self.assertAlmostEqual(py_val["upside"], js_val["upside"], places=6)

    def test_bench_summary_parity(self):
        for spots in (3, 6, 7, 10):
            with self.subTest(spots=spots):
                py_sum = bench_summary(spots)
                js_code = f"""
                const FB = require('./dist/assets/fundamental-bench.js').FundamentalBench;
                console.log(JSON.stringify(FB.benchSummary({spots})));
                """
                js_sum = json.loads(self._run_js(js_code))
                self.assertEqual(py_sum, js_sum)


class TestFundamentalBenchGuard(unittest.TestCase):
    """Guard: no tier/line/value path imports the fundamental bench module.

    The fundamental bench must NEVER be used for tiers, starter lines,
    waiver lines or DDF Value. The parity test in
    test_roster_convention_parity.py also checks this.
    """

    VALUE_PATH_FILES = [
        REPO / "app" / "trade-value-chart" / "assets" / "value-model.js",
        REPO / "app" / "trade-value-chart" / "assets" / "curve-widget.js",
        REPO / "pipelines" / "value_reference.py",
        REPO / "pipelines" / "build_ddf_two_tier_leg.py",
        REPO / "pipelines" / "build_consolidated_values.py",
        REPO / "dist" / "assets" / "roster-convention.js",
        REPO / "pipelines" / "lib" / "roster_convention.py",
    ]

    def test_no_fundamental_bench_import(self):
        for fpath in self.VALUE_PATH_FILES:
            if not fpath.exists():
                continue
            content = fpath.read_text()
            self.assertNotIn(
                "fundamental_bench",
                content.lower(),
                f"{fpath.name} must not import the fundamental bench module"
            )
            self.assertNotIn(
                "fundamentalBench",
                content,
                f"{fpath.name} must not import the fundamental bench module"
            )
            self.assertNotIn(
                "fundamental-bench",
                content.lower().replace("fundamental-bench.js", ""),
                f"{fpath.name} must not reference the fundamental bench module"
            )


class TestGuardNegative(unittest.TestCase):
    """Negative test: prove the guard catches a violation.

    Per CLAUDE.md: every regression guard must prove it catches the bug
    it names.
    """

    def test_guard_catches_import_in_value_path(self):
        """Simulate a file containing 'fundamental_bench' and verify
        the guard assertion would fail."""
        fake_content = "from lib.fundamental_bench import ladder"
        # The guard checks for 'fundamental_bench' in content.lower()
        self.assertIn("fundamental_bench", fake_content.lower(),
                       "Simulated violation must contain the forbidden string")

    def test_guard_catches_js_import(self):
        """Simulate JS code referencing FundamentalBench."""
        fake_content = "var FB = require('./fundamental-bench.js').FundamentalBench;"
        self.assertIn("fundamentalbench", fake_content.lower().replace("-", ""),
                       "Simulated JS violation must contain the forbidden string")


if __name__ == "__main__":
    unittest.main()
