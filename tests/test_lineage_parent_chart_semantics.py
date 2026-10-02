"""JEG-106: Parent lineage entries - chart column semantics for adjusted sources.

For the four parent sources that have an adjusted leg (cbs, fantasycalc,
fantasypros, usatoday), the parent chart column must not compare against
itself and claim a false green. The chart actually displays the adjusted
leg's value, not the parent's indexed value.

Three options were proposed:
- a: Use actual adjusted chart value in parent and compare meaningfully
- b: N/A in parent chart column with pointer to adjusted leg (implemented)
- c: Leave green but that's misleading

This test verifies option b:
1. Parent sources with an adjusted leg: chart_value is None/null, chart_matches_indexed is None
2. Parent sources include has_adjusted_leg flag and adjusted_leg_pointer
3. Adjusted legs compare chart (adjusted) vs parent's indexed meaningfully
4. Sources without adjusted legs continue to work unchanged
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_source_value_lineage",
        REPO / "pipelines" / "build_source_value_lineage.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestParentChartSemantics(unittest.TestCase):
    """Tests for JEG-106 parent lineage chart column semantics."""

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def _sources_with_adjusted(self):
        """Create sources with parent + adjusted for all 4 pairs."""
        parent_native = {f"player {i}": 100.0 - i for i in range(30)}
        parent_reindexed = {f"player {i}": 70.0 - i * 2 for i in range(30)}
        # Adjusted is a strict monotone shift of indexed by 0.9x
        adj_reindexed = {f"player {i}": (70.0 - i * 2) * 0.9 for i in range(30)}

        return {
            "fantasypros": {
                "combos": {"half_12": {
                    "native": parent_native,
                    "reindexed": parent_reindexed,
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "fantasypros_adjusted": {
                "combos": {"half_12": {"reindexed": adj_reindexed}},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "usatoday": {
                "combos": {"half_12": {
                    "native": {f"u {i}": 50.0 - i for i in range(30)},
                    "reindexed": {f"u {i}": 40.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "usatoday_adjusted": {
                "combos": {"half_12": {
                    "reindexed": {f"u {i}": (40.0 - i) * 0.85 for i in range(30)}
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "fantasycalc": {
                "combos": {"half_12_qb1": {
                    "native": {f"f {i}": 80.0 - i for i in range(30)},
                    "reindexed": {f"f {i}": 60.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "fantasycalc_adjusted": {
                "combos": {"half_12_qb1": {
                    "reindexed": {f"f {i}": (60.0 - i) * 0.92 for i in range(30)}
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "cbs": {
                "combos": {"half_12": {
                    "native": {f"c {i}": 90.0 - i for i in range(30)},
                    "reindexed": {f"c {i}": 65.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "cbs_adjusted": {
                "combos": {"half_12": {
                    "reindexed": {f"c {i}": (65.0 - i) * 0.88 for i in range(30)}
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
        }

    def _sources_without_adjusted(self):
        """Create sources without adjusted legs (ESPN, CBS ROS, Razzball)."""
        return {
            "espn": {
                "combos": {"half_12": {
                    "values": {f"e {i}": 100.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "cbsros": {
                "combos": {"half_12": {
                    "values": {f"cr {i}": 80.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
            "razzball": {
                "combos": {"half_12": {
                    "values": {f"r {i}": 70.0 - i for i in range(30)},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
        }

    def test_parent_chart_value_null_when_adjusted_exists(self):
        """Parent sources with an adjusted leg should have chart_value = None."""
        sources = self._sources_with_adjusted()
        live_data = {}  # No live data for this test
        snapshot_natives = {}  # No snapshot natives

        # Test each parent source
        for parent in ("fantasypros", "usatoday", "fantasycalc", "cbs"):
            entry = self.b.build_source_entry(
                parent, sources, live_data, snapshot_natives, vorp_chain=None
            )
            top25 = entry["top25"]

            # All rows should have chart_value = None
            for row in top25:
                self.assertIsNone(
                    row.get("chart_value"),
                    f"{parent}: chart_value should be None when adjusted leg exists, got {row.get('chart_value')}"
                )

    def test_parent_chart_matches_indexed_null_when_adjusted_exists(self):
        """Parent sources with an adjusted leg should have chart_matches_indexed = None."""
        sources = self._sources_with_adjusted()
        live_data = {}
        snapshot_natives = {}

        for parent in ("fantasypros", "usatoday", "fantasycalc", "cbs"):
            entry = self.b.build_source_entry(
                parent, sources, live_data, snapshot_natives, vorp_chain=None
            )
            top25 = entry["top25"]

            for row in top25:
                self.assertIsNone(
                    row.get("chart_matches_indexed"),
                    f"{parent}: chart_matches_indexed should be None when adjusted leg exists"
                )

    def test_parent_has_adjusted_leg_flag(self):
        """Parent sources with an adjusted leg should have has_adjusted_leg = True."""
        sources = self._sources_with_adjusted()
        live_data = {}
        snapshot_natives = {}

        for parent in ("fantasypros", "usatoday", "fantasycalc", "cbs"):
            entry = self.b.build_source_entry(
                parent, sources, live_data, snapshot_natives, vorp_chain=None
            )
            top25 = entry["top25"]

            for row in top25:
                self.assertTrue(
                    row.get("has_adjusted_leg"),
                    f"{parent}: has_adjusted_leg should be True"
                )

    def test_parent_adjusted_leg_pointer(self):
        """Parent sources should have adjusted_leg_pointer field."""
        sources = self._sources_with_adjusted()
        live_data = {}
        snapshot_natives = {}

        expected = {
            "fantasypros": "fantasypros_adjusted",
            "usatoday": "usatoday_adjusted",
            "fantasycalc": "fantasycalc_adjusted",
            "cbs": "cbs_adjusted",
        }

        for parent, expected_adj in expected.items():
            entry = self.b.build_source_entry(
                parent, sources, live_data, snapshot_natives, vorp_chain=None
            )
            self.assertEqual(
                entry.get("adjusted_leg_pointer"),
                expected_adj,
                f"{parent}: adjusted_leg_pointer should be {expected_adj}"
            )

    def test_adjusted_leg_compares_meaningfully(self):
        """Adjusted legs should compare chart (adjusted) vs parent's indexed meaningfully.

        The adjusted leg's chart_matches_indexed should compare against the parent's
        indexed value, showing the actual difference. It should NOT always be True.
        """
        sources = self._sources_with_adjusted()
        live_data = {}
        snapshot_natives = {}

        for adj in ("fantasypros_adjusted", "usatoday_adjusted",
                    "fantasycalc_adjusted", "cbs_adjusted"):
            entry = self.b.build_adjusted_leg_entry(
                adj, sources, live_data, snapshot_natives, vorp_chain=None
            )
            top25 = entry["top25"]

            # At least some rows should have chart_matches_indexed = False
            # because adjusted != indexed (by construction in _sources_with_adjusted)
            false_count = sum(1 for row in top25 if row.get("chart_matches_indexed") is False)
            self.assertGreater(
                false_count, 0,
                f"{adj}: should have at least some rows where chart != indexed"
            )

    def test_sources_without_adjusted_unchanged(self):
        """Sources without adjusted legs should work unchanged."""
        sources = self._sources_without_adjusted()
        live_data = {}
        snapshot_natives = {}

        for src in ("espn", "cbsros", "razzball"):
            entry = self.b.build_source_entry(
                src, sources, live_data, snapshot_natives, vorp_chain=None
            )
            top25 = entry["top25"]

            # These sources use "values" not "reindexed" as chart_val
            for row in top25:
                # chart_value should not be None for sources without adjusted
                self.assertIsNotNone(
                    row.get("chart_value"),
                    f"{src}: chart_value should not be None"
                )
                # has_adjusted_leg should be False or absent
                self.assertFalse(
                    row.get("has_adjusted_leg", False),
                    f"{src}: has_adjusted_leg should be False"
                )
            # adjusted_leg_pointer should be None
            self.assertIsNone(
                entry.get("adjusted_leg_pointer"),
                f"{src}: adjusted_leg_pointer should be None"
            )

    def test_numeric_zero_distinguishable_from_missing(self):
        """Numeric zero should be distinguishable from missing (None).

        This tests that when a player has chart_value = 0, it's rendered
        as "0" not "N/A".
        """
        # Create a source with a zero value
        sources = {
            "cbs": {
                "combos": {"half_12": {
                    "native": {"player zero": 0.0, "player ten": 10.0},
                    "reindexed": {"player zero": 0.0, "player ten": 10.0},
                }},
                "fetched_at": "2026-10-01T00:00:00Z",
            },
        }

        entry = self.b.build_source_entry(
            "cbs", sources, {}, {}, vorp_chain=None
        )

        # Find the zero player row
        zero_row = next(r for r in entry["top25"] if r["player_key"] == "player zero")
        ten_row = next(r for r in entry["top25"] if r["player_key"] == "player ten")

        # Zero should be rendered as 0, not None
        self.assertEqual(zero_row.get("chart_value"), 0.0)
        self.assertEqual(ten_row.get("chart_value"), 10.0)


class TestFantasyCalcComboKey(unittest.TestCase):
    """Verify FantasyCalc uses half_12_qb1 combo key."""

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def test_fantasycalc_uses_half_12_qb1(self):
        """FantasyCalc should use half_12_qb1 combo key."""
        self.assertEqual(
            self.b.COMBO_KEYS["fantasycalc"],
            "half_12_qb1",
        )


if __name__ == "__main__":
    unittest.main()
