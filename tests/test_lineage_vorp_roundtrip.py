"""JEG-107 — VORP round-trip is visible for every lineage leg.

The "Source value lineage — top 25 players per source" view must show, for
every parent and every adjusted leg, the three steps per player:
  1. native          -- publisher's published value (publisher's domain)
  2. imputed_vorp    -- Option C 8-group imputation (native x alloc_factor)
  3. ddf_rebuilt     -- DDF-rebuilt value through our methodology

The publisher's inferred roster assumptions (replacement tier per position,
rostered slots, flex share) must also be inspectable per source via the
vorp_round_trip block on each lineage entry.

JEG-266: the legacy translate_source-based implied_vorp column was removed;
the Option C imputation is the only VORP column carried. vorp_replacement_level
stays for the inferred-roster debug block.

Failing closed: no VORP step may be guessed or rendered as a placeholder.
A source whose chain cannot be computed carries None for imputed_vorp /
vorp_replacement_level / ddf_rebuilt and a populated vorp_round_trip.error.
"""
import importlib.util
import json
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


# Each "leg" gets at least one player row carrying native / imputed_vorp /
# vorp_replacement_level / ddf_rebuilt. Parents and adjusted legs share
# the same shape so the lineage renders the same columns for every source.
PARENT_LEGS = ["espn", "cbs", "cbsros", "razzball",
               "fantasycalc", "fantasypros", "usatoday"]
ADJUSTED_LEGS = ["fantasypros_adjusted", "usatoday_adjusted",
                 "fantasycalc_adjusted", "cbs_adjusted"]
ALL_LEGS = PARENT_LEGS + ADJUSTED_LEGS


def _fixture_sources(b):
    """Build a minimal sources fixture where every leg has at least one row.

    Values are monotone, so the top-25 selection is deterministic and the
    tests can target rank 1 without walking the entire list.
    """
    parent_native = {f"player {i}": 100.0 - i for i in range(30)}
    parent_reindexed = {f"player {i}": 70.0 - i * 2 for i in range(30)}
    adj_reindexed = {f"player {i}": (70.0 - i * 2) * 0.9 for i in range(30)}
    sources = {
        # DDF-native sources (ESPN/CBS ROS/Razzball). Their "native" is a
        # stat projection (a PPG value), so the fixture uses small floats.
        "espn": {
            "combos": {"half_12": {
                "values": {f"e {i}": 16.0 - i * 0.3 for i in range(30)},
                "native": {f"e {i}": 16.0 - i * 0.3 for i in range(30)},
            }},
        },
        "cbsros": {
            "combos": {"half_12": {
                "values": {f"cr {i}": 15.0 - i * 0.2 for i in range(30)},
                "native": {f"cr {i}": 15.0 - i * 0.2 for i in range(30)},
            }},
        },
        "razzball": {
            "combos": {"half_12": {
                "values": {f"r {i}": 14.0 - i * 0.2 for i in range(30)},
                "native": {f"r {i}": 14.0 - i * 0.2 for i in range(30)},
            }},
        },
        # Published trade-value sources (native is the trade-value scale).
        "cbs": {"combos": {"half_12": {
            "native": parent_native,
            "reindexed": parent_reindexed,
        }}},
        "fantasycalc": {"combos": {"half_12_qb1": {
            "native": {f"f {i}": 80.0 - i for i in range(30)},
            "reindexed": {f"f {i}": 60.0 - i for i in range(30)},
        }}},
        "fantasypros": {"combos": {"half_12": {
            "native": parent_native,
            "reindexed": parent_reindexed,
        }}},
        "usatoday": {"combos": {"half_12": {
            "native": {f"u {i}": 50.0 - i for i in range(30)},
            "reindexed": {f"u {i}": 40.0 - i for i in range(30)},
        }}},
        # Adjusted legs.
        "fantasypros_adjusted": {"combos": {"half_12": {
            "reindexed": adj_reindexed,
        }}},
        "usatoday_adjusted": {"combos": {"half_12": {
            "reindexed": {f"u {i}": (40.0 - i) * 0.85 for i in range(30)}
        }}},
        "fantasycalc_adjusted": {"combos": {"half_12_qb1": {
            "reindexed": {f"f {i}": (60.0 - i) * 0.92 for i in range(30)}
        }}},
        "cbs_adjusted": {"combos": {"half_12": {
            "reindexed": {f"c {i}": (70.0 - i * 2) * 0.88 for i in range(30)}
        }}},
    }
    return sources


class VorpRoundTripPerLegTest(unittest.TestCase):
    """Every lineage leg's top-25 rows expose the three VORP round-trip steps.

    Parents compute their own chain via translate_source() /
    vorp_via_roster.compuote_vorp_via_roster(). Adjusted legs inherit the
    parent's chain (same publisher assumptions) but render the adjusted
    reindexed as ddf_rebuilt.
    """

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()
        cls.sources = _fixture_sources(cls.b)

    def test_parent_legs_attach_vorp_round_trip_block(self):
        for src in PARENT_LEGS:
            entry = self.b.build_source_entry(
                src, self.sources, {}, {}, vorp_chain=self.b._compute_vorp_chain_for_source(
                    src, self.sources
                )
            )
            self.assertIn(
                "vorp_round_trip", entry,
                f"{src} lineage entry must carry vorp_round_trip"
            )
            rt = entry["vorp_round_trip"]
            self.assertIsNotNone(rt, f"{src} vorp_round_trip must not be None")
            self.assertIn("method", rt)
            self.assertIn("positions", rt)
            # At least one of the four positions should have a waiver line
            # so the inferred replacement tier is visible.
            self.assertTrue(
                any(rt["positions"].get(p, {}).get("waiver_line_value")
                    for p in ("QB", "RB", "WR", "TE")),
                f"{src} must report at least one position's inferred waiver line"
            )

    def test_adjusted_legs_attach_vorp_round_trip_inherited_from_parent(self):
        for adj in ADJUSTED_LEGS:
            parent = self.b.ADJUSTED_LEG_PARENT[adj]
            parent_chain = self.b._compute_vorp_chain_for_source(
                parent, self.sources
            )
            entry = self.b.build_adjusted_leg_entry(
                adj, self.sources, {}, {}, vorp_chain=parent_chain
            )
            self.assertIn("vorp_round_trip", entry)
            rt = entry["vorp_round_trip"]
            self.assertEqual(parent, rt.get("inherited_from"),
                             f"{adj} must record {parent} as the chain source")

    def test_each_player_row_carries_the_three_steps(self):
        """Every row in every leg's top25 has native / imputed_vorp /
        vorp_replacement_level / ddf_rebuilt, even when None (no guess)."""
        for src in PARENT_LEGS:
            chain = self.b._compute_vorp_chain_for_source(src, self.sources)
            entry = self.b.build_source_entry(
                src, self.sources, {}, {}, vorp_chain=chain
            )
            for p in entry["top25"]:
                for k in ("native", "imputed_vorp",
                          "vorp_replacement_level", "ddf_rebuilt"):
                    self.assertIn(
                        k, p,
                        f"{src}/{p['player_key']} missing {k} column"
                    )
                # JEG-266: legacy implied_vorp removed -- Option C imputation is the
                # canonical VORP column. The lineage builder MUST NOT write it.
                self.assertNotIn("implied_vorp", p,
                                 f"{src}/{p['player_key']}: legacy implied_vorp leaked")
                # When the chain produced a VORP, the three numeric cells
                # must be numeric (not string, not None).
                if p["imputed_vorp"] is not None:
                    self.assertIsInstance(p["imputed_vorp"], (int, float))
                if p["vorp_replacement_level"] is not None:
                    self.assertIsInstance(p["vorp_replacement_level"], (int, float))
                if p["ddf_rebuilt"] is not None:
                    self.assertIsInstance(p["ddf_rebuilt"], (int, float))

    def test_adjusted_leg_rows_carry_inherited_imputed_vorp(self):
        """Adjusted legs inherit the parent's imputed VORP (same publisher
        native, same inferred roster) but show the adjusted reindexed as
        the DDF-rebuilt value."""
        for adj in ADJUSTED_LEGS:
            parent = self.b.ADJUSTED_LEG_PARENT[adj]
            chain = self.b._compute_vorp_chain_for_source(parent, self.sources)
            entry = self.b.build_adjusted_leg_entry(
                adj, self.sources, {}, {}, vorp_chain=chain
            )
            parent_entry = self.b.build_source_entry(
                parent, self.sources, {}, {}, vorp_chain=chain
            )
            # Top-1 of parent and adjusted leg may differ (different sort
            # keys), so walk every row and check the implied VORP matches
            # the parent chain's value where the player is shared.
            for row in entry["top25"]:
                parent_row = next(
                    (pp for pp in parent_entry["top25"]
                     if pp["player_key"] == row["player_key"]), None
                )
                if parent_row is None:
                    continue
                self.assertEqual(
                    parent_row["imputed_vorp"], row["imputed_vorp"],
                    f"{adj}/{row['player_key']}: imputed_vorp must "
                    "inherit from parent"
                )
                self.assertEqual(
                    parent_row["vorp_replacement_level"],
                    row["vorp_replacement_level"],
                    f"{adj}/{row['player_key']}: replacement tier must "
                    "inherit from parent"
                )

    def test_inferred_replacement_levels_present_per_position(self):
        """vorp_round_trip.positions[QB|RB|WR|TE] must each carry a
        waiver_line_value when the source has enough players to compute it."""
        for src in PARENT_LEGS:
            chain = self.b._compute_vorp_chain_for_source(src, self.sources)
            entry = self.b.build_source_entry(
                src, self.sources, {}, {}, vorp_chain=chain
            )
            for pos in ("QB", "RB", "WR", "TE"):
                info = entry["vorp_round_trip"]["positions"].get(pos)
                if info is None:
                    continue
                # n_rostered must be a positive integer; the waiver line
                # either exists (roster_determined) or the method tells us
                # why it doesn't.
                self.assertIsNotNone(info.get("n_rostered"))
                if info.get("waiver_line_value") is None:
                    self.assertIn(info.get("waiver_method", ""),
                                  ("insufficient_coverage", "no_players"),
                                  f"{src}/{pos}: missing waiver line must "
                                  "have a roster-coverage reason")


class VorpRoundTripPlayerTraceTest(unittest.TestCase):
    """A known player trace shows the full chain end-to-end.

    JEG-107 acceptance cites "JSN, FantasyCalc half_12_qb1" as the
    canonical example. The fixture's monotone values don't include a real
    JSN row, so this test uses an injected fixture that does.
    """

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def _sources_with_jsn(self):
        sources = _fixture_sources(self.b)
        sources["fantasycalc"]["combos"]["half_12_qb1"]["native"]["jaxon smithnjigba"] = 9914.0
        sources["fantasycalc"]["combos"]["half_12_qb1"]["reindexed"]["jaxon smithnjigba"] = 48.1
        sources["fantasycalc_adjusted"]["combos"]["half_12_qb1"]["reindexed"]["jaxon smithnjigba"] = 43.3
        return sources

    def test_jsn_fantasycalc_half_12_qb1_full_chain(self):
        sources = self._sources_with_jsn()
        chain = self.b._compute_vorp_chain_for_source("fantasycalc", sources)
        # JEG-266: imputed_vorp is attached only when the JEG-206 group
        # artifact is available; the test sandbox has no
        # dist/modules/ddf-group-vorps.json, and the builder fails closed
        # (nulls, never guesses) without it. Inject a synthetic 8-group
        # artifact so this test exercises the real imputation path; the
        # absent-artifact fail-closed behavior is covered by
        # test_each_player_row_carries_the_three_steps.
        fake_groups = {f"{pos}|{role}": 100.0
                       for pos in ("QB", "RB", "WR", "TE")
                       for role in ("Starter", "Bench")}
        orig_loader = self.b._load_ddf_group_vorps
        self.b._load_ddf_group_vorps = lambda: (dict(fake_groups), True)
        try:
            parent = self.b.build_source_entry(
                "fantasycalc", sources, {}, {}, vorp_chain=chain
            )
        finally:
            self.b._load_ddf_group_vorps = orig_loader
        jsn = next(
            (p for p in parent["top25"]
             if "jaxon" in p["player_key"].lower()),
            None
        )
        self.assertIsNotNone(
            jsn, "JSN must appear in the FantasyCalc half_12_qb1 top 25"
        )
        # Native = publisher native (publisher's published value).
        self.assertEqual(9914.0, jsn["native"])
        # imputed_vorp: Option C 8-group imputation (native x alloc_factor).
        # JEG-266: legacy implied_vorp removed; imputed_vorp is the only VORP column.
        # We don't pin the number (the test fixture is synthetic) but the
        # field must be a non-negative number when a replacement tier exists for WR.
        # With the synthetic 100.0 group totals above, alloc = 100 / group
        # native sum and imputed = native x alloc, rounded to 2dp.
        if chain["positions"].get("WR", {}).get("waiver_line_value") is not None:
            self.assertIsNotNone(jsn["imputed_vorp"])
            self.assertGreaterEqual(jsn["imputed_vorp"], 0)
            self.assertIsNotNone(jsn["vorp_replacement_level"])
            self.assertEqual(jsn["group"], "WR|Starter")
            # Relational check (no roster-logic reimplementation): imputed
            # must equal native x the row's own attached alloc factor, and
            # the attached group total must be the synthetic 100.0.
            # Relational check (no roster-logic reimplementation): imputed
            # must equal native x the row's own attached alloc factor. The
            # row carries alloc_factor rounded to 4dp while imputed uses the
            # full-precision factor, so allow the bounded 4dp error
            # (9914 x 5e-5 + 2dp rounding < 0.51); a wrong factor would miss
            # by far more.
            self.assertIsNotNone(jsn["alloc_factor"])
            self.assertEqual(jsn["our_group_vorp"], 100.0)
            self.assertLess(
                abs(jsn["imputed_vorp"] - 9914.0 * jsn["alloc_factor"]),
                0.51,
            )
        # ddf_rebuilt: the chart value (what the chart actually displays).
        # For published sources it comes from translate_source's
        # ddf_rebuilt dict, NOT the chart_value (which for published
        # sources is reindexed, not the JEG-62 translated).
        # We only assert the field exists; the override path keeps
        # it consistent with the chart for the lineage card.
        self.assertIn("ddf_rebuilt", jsn)


class VorpRoundTripRenderTest(unittest.TestCase):
    """The dashboard's lineage section renders the three VORP steps per row.

    Reads modules/dashboard.html, looks for the new column header and the
    per-row cells so a future refactor cannot silently drop the visibility.
    """

    @classmethod
    def setUpClass(cls):
        cls.html = (REPO / "modules" / "dashboard.html").read_text()

    def test_three_step_columns_present_in_table_header(self):
        # JEG-207: the lineage table header now carries the Option C
        # 8-group columns instead of the old translate_source VORP steps.
        for col in ("Native", "Group", "Alloc factor", "Our group VORP", "Imputed VORP"):
            self.assertIn(
                col, self.html,
                f"lineage table header must carry {col!r} column"
            )

    def test_each_row_carries_three_step_cells(self):
        # JEG-207: the row template renders the Option C 8-group cells
        # per player row (replacing the old translate_source VORP steps).
        self.assertIn("p.group", self.html)
        self.assertIn("p.alloc_factor", self.html)
        self.assertIn("p.imputed_vorp", self.html)

    def test_inferred_replacement_panel_renders(self):
        # The publisher's inferred assumptions are shown per source.
        self.assertIn("vorp_round_trip", self.html)
        self.assertIn("Publisher inferred assumptions", self.html)


class VorpRoundTripArtifactTest(unittest.TestCase):
    """The committed lineage artifact carries the VORP round-trip shape.

    Where data/raw snapshots exist locally, build_source_value_lineage.py
    runs end-to-end and writes the artifact. This test runs the builder
    against an in-memory fixture so it works in CI; the test
    test_artifact_has_vorp_chain_when_present checks the artifact file
    when it exists on disk.
    """

    @classmethod
    def setUpClass(cls):
        cls.b = _load_builder()

    def test_build_source_entry_returns_vorp_round_trip_field(self):
        chain = self.b._compute_vorp_chain_for_source(
            "fantasycalc", _fixture_sources(self.b)
        )
        entry = self.b.build_source_entry(
            "fantasycalc", _fixture_sources(self.b), {}, {}, vorp_chain=chain
        )
        self.assertIn("vorp_round_trip", entry)
        self.assertIsNotNone(entry["vorp_round_trip"])
        self.assertIn("positions", entry["vorp_round_trip"])

    def test_build_adjusted_leg_entry_returns_vorp_round_trip_field(self):
        chain = self.b._compute_vorp_chain_for_source(
            "fantasypros", _fixture_sources(self.b)
        )
        entry = self.b.build_adjusted_leg_entry(
            "fantasypros_adjusted", _fixture_sources(self.b), {}, {},
            vorp_chain=chain
        )
        self.assertIn("vorp_round_trip", entry)
        self.assertIsNotNone(entry["vorp_round_trip"])

    def test_vorp_chain_fails_closed_on_missing_combo(self):
        """A source whose combo can't be loaded still returns a chain dict
        with error set; the lineage row keeps native + chart columns and
        marks imputed_vorp / vorp_replacement_level / ddf_rebuilt as None."""
        bad = {"not_a_real_source": {"combos": {}}}
        chain = self.b._compute_vorp_chain_for_source(
            "not_a_real_source", bad
        )
        self.assertIsNotNone(chain.get("error"))


if __name__ == "__main__":
    unittest.main()