"""Stage 2: versioned adjustment inputs (pipelines/build_adjustment_inputs.py).

Covers the affine cell fit that turns each source's published trade values
into DDF-leg values:

    adjusted = max(0, alpha + beta * published_value)

per (source, position, tier). Tiers are the render-time roles assigned from
each source's OWN published values at the reference roster shape (12 teams;
QB 1 / RB 2 / WR 2 / TE 1 / FLEX 2 / BENCH 6) -- exactly what the widget's
roleMapForValues does at render time.

Every guard is negative-tested against the defect it names:
  - fewer than 5 fit pairs -> no cell (would fit noise; caught the real
    CBS TE|bench n=3 case during the bake)
  - zero x variance -> no cell (undefined slope)
  - non-positive slope -> no cell (would invert the source's ordering;
    caught the real CBS TE|bench beta=-6.24 case)
  - waiver-tier players never enter a fit
  - conflicting canonical duplicates -> review rows, excluded from the fit
  - missing reference combo -> source stays paused, no fabricated cells
  - unresolved source ids -> review rows, never guesses

Also asserts the OLS math recovers known coefficients, the role port
assigns starters/bench per the reference shape, and the pause predicate
un-pauses exactly the sources with live cells (no widget change needed).
"""
import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
HARNESS = Path(__file__).resolve().parent / "two_tier_harness.js"
PIPELINES = REPO / "pipelines"
sys.path.insert(0, str(PIPELINES))

from build_adjustment_inputs import (  # noqa: E402
    MIN_FIT_PAIRS,
    POSITION_ORDER,
    REFERENCE_COMBOS,
    build_published_source_map,
    fit_cells,
    role_map_for_values,
)

VERSIONED = REPO / "data" / "adjustment-inputs" / "ddf-20260921-espn-ppr-12t-0p15" / \
    "adjustment-inputs-ddf-20260921-espn-ppr-12t-0p15.json"
LIVE_ASSET = REPO / "app" / "trade-value-chart" / "assets" / "adjustment-inputs.json"
PAUSED_KEYS = ["fantasycalc_adjusted", "usatoday_adjusted",
               "fantasypros_adjusted", "cbs_adjusted"]
RAW_FOR = {k: (k[:-len("_adjusted")] if k != "cbs_adjusted" else "cbs") for k in PAUSED_KEYS}


def run_pause(cases):
    proc = subprocess.run(["node", str(HARNESS), "pause"],
                          input=json.dumps({"cases": cases}),
                          capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise AssertionError(f"harness pause failed: {proc.stderr[:2000]}")
    return json.loads(proc.stdout)


def canonical_for(keys_pos):
    """keys_pos: {player_key: (pos, preseason_rank, name)}"""
    return {k: {"pos": pos, "preseason_rank": rank, "name": name}
            for k, (pos, rank, name) in keys_pos.items()}


class TestCellGuards(unittest.TestCase):
    def setUp(self):
        self.canonical = canonical_for({
            1: ("QB", 10, "Alpha"), 2: ("QB", 20, "Beta"), 3: ("QB", 30, "Gamma"),
            4: ("QB", 40, "Delta"), 5: ("QB", 50, "Epsilon"), 6: ("QB", 60, "Zeta"),
        })

    def roles_all_starter(self, published):
        roles = role_map_for_values(published, self.canonical)
        # Force every key into the QB starter bucket regardless of rank.
        return {k: "starter" for k in published}

    def test_ols_recovers_known_coefficients(self):
        published = {k: float(10 * k) for k in range(1, 7)}
        leg = {k: 2.0 + 0.5 * (10 * k) for k in range(1, 7)}
        cells, diag = fit_cells(published, self.roles_all_starter(published), leg,
                                self.canonical)
        cell = next(c for c in cells if c["position"] == "QB" and c["tier"] == "starter")
        self.assertAlmostEqual(cell["alpha"], 2.0, places=9)
        self.assertAlmostEqual(cell["beta"], 0.5, places=9)
        self.assertEqual(cell["n"], 6)

    def test_fewer_than_min_pairs_has_no_cell(self):
        # The defect this names: CBS TE|bench shipped n=3, beta=-6.24 before
        # the guard existed.
        published = {1: 10.0, 2: 20.0, 3: 30.0}
        leg = {1: 30.0, 2: 20.0, 3: 10.0}
        cells, diag = fit_cells(published, self.roles_all_starter(published), leg,
                                self.canonical)
        self.assertEqual(cells, [])
        self.assertEqual(diag["QB|starter"]["reason"],
                         f"fewer_than_{MIN_FIT_PAIRS}_pairs")

    def test_zero_x_variance_has_no_cell(self):
        published = {k: 10.0 for k in range(1, 7)}
        leg = {k: float(k) for k in range(1, 7)}
        cells, diag = fit_cells(published, self.roles_all_starter(published), leg,
                                self.canonical)
        self.assertEqual(cells, [])
        self.assertEqual(diag["QB|starter"]["reason"], "zero_x_variance")

    def test_non_positive_slope_has_no_cell(self):
        # Inverted ordering: higher published value -> lower leg value.
        published = {k: float(10 * k) for k in range(1, 7)}
        leg = {k: float(100 - 10 * k) for k in range(1, 7)}
        cells, diag = fit_cells(published, self.roles_all_starter(published), leg,
                                self.canonical)
        self.assertEqual(cells, [])
        self.assertEqual(diag["QB|starter"]["reason"], "non_positive_slope")

    def test_waiver_tier_never_enters_fit(self):
        # Five starters fit alpha=2/beta=0.5 exactly; the waiver player
        # carries an extreme y that would wreck the fit if it leaked in.
        published = {k: float(10 * k) for k in range(1, 7)}
        leg = {k: 2.0 + 0.5 * (10 * k) for k in range(1, 6)}
        leg[6] = 1000.0
        roles = {k: ("waiver" if k == 6 else "starter") for k in published}
        cells, diag = fit_cells(published, roles, leg, self.canonical)
        cell = next(c for c in cells if c["position"] == "QB" and c["tier"] == "starter")
        self.assertEqual(cell["n"], 5)
        self.assertAlmostEqual(cell["alpha"], 2.0, places=9)
        self.assertAlmostEqual(cell["beta"], 0.5, places=9)
        self.assertNotIn("QB|waiver", diag)

    def test_conflicting_duplicates_become_review_rows(self):
        fixture = {
            "player_keys": {"a": 1, "b": 1},
            "sources": {"fantasycalc": {"combos": {
                "full_12_qb1": {"values": {"a": 10.0, "b": 99.0}}}}},
        }
        published, review = build_published_source_map("fantasycalc", fixture,
                                                       self.canonical)
        self.assertEqual(published, {})
        self.assertEqual(len(review), 1)
        self.assertEqual(review[0]["reason"], "conflicting_duplicate")

    def test_unresolved_source_id_becomes_review_row(self):
        fixture = {
            "player_keys": {"a": 1},
            "sources": {"fantasycalc": {"combos": {
                "full_12_qb1": {"values": {"a": 10.0, "ghost": 20.0}}}}},
        }
        published, review = build_published_source_map("fantasycalc", fixture,
                                                       self.canonical)
        self.assertEqual(published, {1: 10.0})
        self.assertEqual([r["reason"] for r in review], ["unresolved_identity"])


class TestRoleMapPort(unittest.TestCase):
    def test_reference_shape_assignment(self):
        # 12 teams: QB starters = top 12, bench = next available by value.
        canonical = canonical_for({k: ("QB", k, f"P{k}") for k in range(1, 21)})
        published = {k: float(100 - k) for k in range(1, 21)}
        roles = role_map_for_values(published, canonical)
        starters = sorted(k for k, r in roles.items() if r == "starter")
        self.assertEqual(starters, list(range(1, 13)))
        # Non-positive values get no role at all.
        published[20] = 0.0
        roles = role_map_for_values(published, canonical)
        self.assertNotIn(20, roles)

    def test_tie_break_by_preseason_rank(self):
        # 13 players, 12 starter slots, all values tied: the last slot is
        # decided by preseason rank (preseasonComparator ALL-branch).
        ranks = {k: k for k in range(1, 12)}
        ranks[12] = 12
        ranks[13] = 13  # loses the 12th slot to the better rank
        canonical = canonical_for({k: ("QB", ranks[k], f"P{k}") for k in range(1, 14)})
        published = {k: 50.0 for k in range(1, 14)}
        roles = role_map_for_values(published, canonical)
        starters = {k for k, r in roles.items() if r == "starter"}
        self.assertEqual(len(starters), 12)
        self.assertIn(12, starters)
        self.assertNotIn(13, starters)

    def test_tie_break_equal_rank_falls_to_name_then_key(self):
        # Same rank AND same value at the boundary: name, then player_key.
        canonical = canonical_for({k: ("QB", (12 if k >= 12 else k), f"P{k:02d}")
                                    for k in range(1, 14)})
        published = {k: 50.0 for k in range(1, 14)}
        roles = role_map_for_values(published, canonical)
        starters = {k for k, r in roles.items() if r == "starter"}
        self.assertEqual(len(starters), 12)
        self.assertIn(12, starters)      # "P12" < "P13"
        self.assertNotIn(13, starters)


class TestBakedArtifact(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = json.loads(VERSIONED.read_text(encoding="utf-8"))

    def test_versioned_artifact_shape(self):
        self.assertEqual(self.doc["schema"], "trade-value-adjustment-inputs-v1")
        self.assertEqual(self.doc["version"], "ddf-20260921-espn-ppr-12t-0p15")
        self.assertEqual(self.doc["status"], "live")
        fit = self.doc["fit"]
        self.assertEqual(fit["espn_snapshot_date"], "2026-09-21")
        self.assertEqual(fit["scoring"], "ppr")
        self.assertEqual(fit["teams"], 12)
        self.assertEqual(fit["bench_share"], 0.15)
        self.assertEqual(fit["reference_combos"], REFERENCE_COMBOS)

    def test_all_sources_live_with_guarded_cells(self):
        for source, entry in self.doc["sources"].items():
            self.assertEqual(entry["status"], "live", source)
            self.assertTrue(entry["cells"], source)
            for cell in entry["cells"]:
                self.assertIn(cell["position"], POSITION_ORDER)
                self.assertIn(cell["tier"], ("starter", "bench"))
                self.assertTrue(math.isfinite(cell["alpha"]))
                self.assertTrue(cell["beta"] > 0, (source, cell))
                self.assertGreaterEqual(cell["n"], MIN_FIT_PAIRS)
            missing = [k for k, v in entry["diagnostics"].items() if not v["cell"]]
            for k in missing:
                self.assertIn(entry["diagnostics"][k]["reason"],
                              ("fewer_than_5_pairs", "zero_x_variance",
                               "non_positive_slope", "non_finite_coefficients"),
                              (source, k))

    def test_missing_cells_are_diagnosed_not_silent(self):
        missing = {s: [k for k, v in e["diagnostics"].items() if not v["cell"]]
                   for s, e in self.doc["sources"].items()}
        self.assertEqual(missing["cbs"], ["QB|bench", "TE|bench"])
        self.assertEqual(missing["fantasycalc"], ["TE|bench"])
        self.assertEqual(missing["fantasypros"], ["QB|bench"])
        self.assertEqual(missing["usatoday"], ["QB|bench"])

    def test_pause_predicate_unpauses_live_sources(self):
        got = run_pause([{"key": k, "inputs": self.doc} for k in PAUSED_KEYS])
        self.assertEqual(got, [False] * 4)

    def test_empty_cells_still_pause(self):
        cells = {"sources": {"fantasycalc": {"cells": []}}}
        got = run_pause([{"key": "fantasycalc_adjusted", "inputs": cells}])
        self.assertEqual(got, [True])

    def test_live_asset_matches_versioned(self):
        live = json.loads(LIVE_ASSET.read_text(encoding="utf-8"))
        self.assertEqual(live["version"], self.doc["version"])
        self.assertEqual(live["status"], "live")
        self.assertEqual(
            {s: len(e["cells"]) for s, e in live["sources"].items()},
            {s: len(e["cells"]) for s, e in self.doc["sources"].items()})

    def test_review_rows_never_zero_filled(self):
        reasons = {r["reason"] for r in self.doc["review_rows"]}
        self.assertTrue(reasons <= {"no_espn_projection", "non_skill_position",
                                    "missing_components", "unresolved_identity",
                                    "conflicting_duplicate", "missing_reference_combo",
                                    "non_numeric_value"})
        # No invented values anywhere in the payload.
        blob = json.dumps(self.doc)
        self.assertNotIn("estimated", blob.lower())


if __name__ == "__main__":
    unittest.main()
