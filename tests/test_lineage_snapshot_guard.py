"""Lineage builder fail-closed regression tests.

2026-10-01: the Pages workflow rebuilds source-value-lineage.json in CI on
every deploy, but the source snapshots live under gitignored data/raw and are
absent there. The builder silently fell back to TRANSFORMED combo natives,
so the served lineage compared live raw values (e.g. FantasyPros Gibbs 75.1)
against transformed values (88.8) and reported 0/25 matches — a monitor
false-red caused by the build environment, not the data.

The builder must now refuse to write when a required snapshot is missing,
so the committed (locally built, correct) artifact survives the deploy.
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


class TestLineageSnapshotGuard(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def test_missing_snapshot_refuses_to_build(self):
        """Simulated CI state: no snapshots loadable. The builder must raise
        instead of writing a degraded lineage file. Proves the guard catches
        the 2026-10-01 false-red state."""
        with self.assertRaises(SystemExit) as ctx:
            self.b.require_snapshot_natives(
                {"fantasypros": {}, "usatoday": {}, "fantasycalc": {}}
            )
        self.assertIn("fantasypros", str(ctx.exception))

    def test_partial_snapshot_still_refuses(self):
        """One missing source is enough to refuse — a half-degraded file is
        still a degraded file."""
        with self.assertRaises(SystemExit):
            self.b.require_snapshot_natives(
                {"fantasypros": {"a": 1.0}, "usatoday": {}, "fantasycalc": {"b": 2.0}}
            )

    def test_all_snapshots_present_passes(self):
        """Normal local state: all snapshots loaded, builder may proceed."""
        self.b.require_snapshot_natives(
            {"fantasypros": {"a": 1.0}, "usatoday": {"b": 2.0}, "fantasycalc": {"c": 3.0}}
        )  # must not raise

    @unittest.skipUnless(
        all(
            (REPO / p).exists()
            for p in (
                "data/raw/sources/fantasypros/2026-09-29/snapshot.json",
                "data/raw/sources/usatoday/2026-09-29/snapshot.json",
                "data/raw/sources/fantasycalc/week-4/snapshot.json",
            )
        ),
        "source snapshots are gitignored and absent (e.g. CI)",
    )
    def test_real_snapshots_satisfy_guard(self):
        """The actual local snapshots must satisfy the guard, or no local
        build could ever run. Skipped where snapshots are absent (CI): the
        guard's whole purpose is that CI lacks them."""
        natives = {
            src: self.b.load_snapshot_natives(src)
            for src in ("fantasypros", "usatoday", "fantasycalc")
        }
        for src, n in natives.items():
            self.assertTrue(n, f"expected local snapshot natives for {src}")
        self.b.require_snapshot_natives(natives)  # must not raise


class TestLineageAdjustedLegs(unittest.TestCase):
    """JEG-98: 4 VORP-translated adjusted legs get standalone top-25 audit
    tables. Each inherits publisher native + indexed + live scrape from its
    parent and renders the adjusted reindexed as chart value. Fails closed
    when an adjusted leg cannot be built."""

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def _sources(self):
        parent_native = {f"player {i}": 100.0 - i for i in range(30)}
        parent_reindexed = {f"player {i}": 70.0 - i * 2 for i in range(30)}
        # Adjusted is a strict monotone down-shift of indexed by 0.9x
        adj_reindexed = {f"player {i}": (70.0 - i * 2) * 0.9 for i in range(30)}
        return {
            "fantasypros": {
                "combos": {"half_12": {
                    "native": parent_native,
                    "reindexed": parent_reindexed,
                }},
            },
            "fantasypros_adjusted": {
                "combos": {"half_12": {"reindexed": adj_reindexed}},
            },
            "usatoday": {
                "combos": {"half_12": {
                    "native": {f"u {i}": 50.0 - i for i in range(30)},
                    "reindexed": {f"u {i}": 40.0 - i for i in range(30)},
                }},
            },
            "usatoday_adjusted": {
                "combos": {"half_12": {
                    "reindexed": {f"u {i}": (40.0 - i) * 0.85 for i in range(30)}
                }},
            },
            "fantasycalc": {
                "combos": {"half_12_qb1": {
                    "native": {f"f {i}": 80.0 - i for i in range(30)},
                    "reindexed": {f"f {i}": 60.0 - i for i in range(30)},
                }},
            },
            "fantasycalc_adjusted": {
                "combos": {"half_12_qb1": {
                    "reindexed": {f"f {i}": (60.0 - i) * 0.92 for i in range(30)}
                }},
            },
            "cbs": {
                "combos": {"half_12": {
                    "native": {f"c {i}": 90.0 - i for i in range(30)},
                    "reindexed": {f"c {i}": 65.0 - i for i in range(30)},
                }},
            },
            "cbs_adjusted": {
                "combos": {"half_12": {
                    "reindexed": {f"c {i}": (65.0 - i) * 0.88 for i in range(30)}
                }},
            },
        }

    def test_all_four_adjusted_legs_are_declared(self):
        # Regression guard: if someone drops an adjusted leg from the map
        # the corresponding top-25 table silently disappears.
        self.assertEqual(
            {"fantasypros_adjusted", "usatoday_adjusted",
             "fantasycalc_adjusted", "cbs_adjusted"},
            set(self.b.ALL_ADJUSTED_LEGS),
        )
        for adj in self.b.ALL_ADJUSTED_LEGS:
            self.assertIn(adj, self.b.ADJUSTED_LEG_PARENT)

    def test_builds_adjusted_leg_with_full_transformation_chain(self):
        entry = self.b.build_adjusted_leg_entry(
            "fantasypros_adjusted", self._sources(), {}, {},
        )
        self.assertEqual(25, len(entry["top25"]))
        first = entry["top25"][0]
        # Full transformation chain present
        for k in ("rank", "player_key", "live_value", "native",
                  "live_matches_native", "index_mult", "indexed",
                  "reweight_mult", "reweighted", "chart_value",
                  "chart_matches_indexed"):
            self.assertIn(k, first, f"missing column {k}")
        # Ranked by adjusted (chart) value, descending
        self.assertEqual("player 0", first["player_key"])
        # chart_value == reweighted (the bias-adjusted value renders)
        self.assertEqual(first["reweighted"], first["chart_value"])
        # chart_matches_indexed compares the adjusted chart value against
        # the PARENT's indexed value (JEG-106 lineage semantics): the
        # synthetic adjusted leg is a 0.9x down-shift of the parent, so the
        # check is False by construction here -- a red X means the chart
        # value genuinely differs from what the parent published. The old
        # "green by construction" expectation predates JEG-106 (c413d95),
        # which changed the builder without updating this pin.
        self.assertFalse(first["chart_matches_indexed"])
        # live_matches_native is None: no own live page, red icon.
        self.assertIsNone(first["live_matches_native"])
        # live_scraped=False per contract (no own live page).
        self.assertFalse(entry["live_scraped"])
        self.assertEqual("fantasypros", entry["parent_source"])
        self.assertEqual("fantasypros", entry["live_inherits_from"])

    def test_chart_matches_indexed_true_when_adjusted_equals_parent(self):
        """Positive companion (JEG-106 semantics): when the adjusted leg's
        reindexed value equals the parent's indexed value, the check is
        True. Proves the column is a live comparison, not constant False."""
        sources = self._sources()
        parent_reindexed = sources["fantasypros"]["combos"]["half_12"]["reindexed"]
        sources["fantasypros_adjusted"]["combos"]["half_12"]["reindexed"] = dict(
            parent_reindexed
        )
        entry = self.b.build_adjusted_leg_entry(
            "fantasypros_adjusted", sources, {}, {},
        )
        first = entry["top25"][0]
        self.assertEqual(first["chart_value"], first["indexed"])
        self.assertTrue(first["chart_matches_indexed"])

    def test_inherits_publisher_native_indexed_and_live_from_parent(self):
        live_data = {"fantasypros": {"player 0": 100.0, "player 1": 99.0}}
        entry = self.b.build_adjusted_leg_entry(
            "fantasypros_adjusted", self._sources(), live_data, {},
        )
        top = entry["top25"][0]
        # Native = parent publisher native (snapshot override path)
        self.assertEqual(100.0, top["native"])
        # Indexed = parent combo's reindexed
        self.assertEqual(70.0, top["indexed"])
        # Live = inherited from parent live_data (not from a fresh scrape)
        self.assertEqual(100.0, top["live_value"])
        # Chart value = adjusted reindexed (0.9x of indexed)
        self.assertAlmostEqual(63.0, top["chart_value"], places=2)
        # VORP-translation mult = adjusted / indexed = 0.9
        self.assertAlmostEqual(0.9, top["reweight_mult"], places=3)

    def test_top25_is_capped_at_25(self):
        entry = self.b.build_adjusted_leg_entry(
            "fantasypros_adjusted", self._sources(), {}, {},
        )
        self.assertEqual(25, len(entry["top25"]))

    def test_summary_counters_count_adjusted_legs(self):
        """The dashboard summary iterates the source list and sums top25
        lengths; the artifact must contain 25 rows per adjusted leg so
        tracedPlayers and liveMismatches count them automatically."""
        sources = self._sources()
        artifact = {"sources": {}}
        for adj in self.b.ALL_ADJUSTED_LEGS:
            artifact["sources"][adj] = self.b.build_adjusted_leg_entry(
                adj, sources, {}, {},
            )
        # Every adjusted leg has 25 rows, all unverifiable (live_scraped=False).
        total_rows = sum(len(artifact["sources"][s]["top25"]) for s in artifact["sources"])
        unverifiable_rows = sum(
            1 for s in artifact["sources"]
            for _ in artifact["sources"][s]["top25"]
            if not artifact["sources"][s]["live_scraped"]
        )
        self.assertEqual(4 * 25, total_rows)
        self.assertEqual(4 * 25, unverifiable_rows)
        # Mirror the dashboard counter contract: unverifiable rows count as
        # both liveChecked and liveMismatches (FAIL RED, not skipped).
        self.assertEqual(unverifiable_rows, total_rows)

    def test_fails_closed_when_adjusted_combo_missing(self):
        sources = self._sources()
        del sources["fantasypros_adjusted"]["combos"]["half_12"]
        with self.assertRaises(ValueError) as ctx:
            self.b.build_adjusted_leg_entry(
                "fantasypros_adjusted", sources, {}, {},
            )
        self.assertIn("fantasypros_adjusted", str(ctx.exception))
        self.assertIn("partial output", str(ctx.exception))

    def test_fails_closed_when_adjusted_combo_empty(self):
        sources = self._sources()
        sources["fantasypros_adjusted"]["combos"]["half_12"]["reindexed"] = {}
        with self.assertRaises(ValueError):
            self.b.build_adjusted_leg_entry(
                "fantasypros_adjusted", sources, {}, {},
            )

    def test_fails_closed_when_adjusted_leg_missing_from_fixture(self):
        sources = {"fantasypros": self._sources()["fantasypros"]}
        with self.assertRaises(ValueError):
            self.b.build_adjusted_leg_entry(
                "fantasypros_adjusted", sources, {}, {},
            )

    def test_fails_closed_for_unknown_adjusted_leg(self):
        with self.assertRaises(ValueError):
            self.b.build_adjusted_leg_entry(
                "not_an_adjusted_leg", self._sources(), {}, {},
            )


if __name__ == "__main__":
    unittest.main()
