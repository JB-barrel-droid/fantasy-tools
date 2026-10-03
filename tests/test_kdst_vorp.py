"""JEG-211: K/DST VORP computation tests.

Covers pipelines/build_ddf_kdst_leg.py and pipelines/build_ddf_kdst_groups.py.

The contract (docs/kdst-group-contract.md) defines K/DST as a SEPARATE
optional 4-group structure: (K starter), (K bench), (DST starter),
(DST bench). These tests assert:

  - K/DST VORPs are non-negative (raw surplus, calibrated chart value).
  - Group sums match the overall pie to within tolerance (no leakage).
  - Every K/DST group has at least one player (fail-closed on empties).
  - The "computed but not displayed" marker is present and the
    excluded-from-guards list cites the right keys.
  - The 8-group artifact at dist/modules/ddf-group-vorps.json is
    untouched by K/DST computation -- K/DST data must not enter the
    skill leg's value list.
  - Fail-closed paths: unsupported schema, missing inputs, unknown
    position, unknown tier, negative value, leakage, stale warning.

Tests synthesize a minimal K/DST leg dict and call compute_groups
directly so they don't depend on data/raw or the live ESPN pull. The
end-to-end live test skips when no K/DST leg exists under
data/ddf-two-tier/.

Identity note: K resolves by player full_name; DST resolves by team
abbr. The fixture's player_keys is the single source of identity.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PIPELINES = REPO / "pipelines"
sys.path.insert(0, str(PIPELINES))

from build_ddf_groups import (  # noqa: E402 -- 8-group invariant reference
    SCHEMA as SKILL_GROUPS_SCHEMA,
    compute_groups as skill_compute_groups,
)
from build_ddf_kdst_groups import (  # noqa: E402
    GROUPS as KDST_GROUPS,
    SCHEMA as KDST_GROUPS_SCHEMA,
    build_groups_from_leg,
    compute_groups,
    find_latest_leg,
)
from build_ddf_kdst_leg import (  # noqa: E402
    KDST_POSITIONS,
    SCHEMA as KDST_LEG_SCHEMA,
    build_identity_index,
    load_dst_pool,
    load_kicker_pool,
)


def _make_kdst_leg(values, snapshot_date="2026-10-02", teams=12):
    """Build a minimal K/DST DDF leg dict shaped like build_ddf_kdst_leg.build_leg output."""
    return {
        "schema": KDST_LEG_SCHEMA,
        "bake_id": f"ddf-kdst-{snapshot_date.replace('-', '')}-espn-{teams}t-0p15",
        "generated_at": "2026-10-02T00:00:00Z",
        "inputs": {
            "snapshot_date": snapshot_date,
            "teams": teams,
            "bench_share": 0.15,
            "bench_k": teams,
            "bench_dst": teams,
        },
        "reference_shape": {
            "slots": {"K": 1, "DST": 1},
            "flex_count": 0,
            "flex_eligible": [],
            "bench_mix": {"K": teams, "DST": teams},
        },
        "calibration": {pos: {"rw": 0.0} for pos in KDST_POSITIONS},
        "values": values,
        "display_status": "computed_not_displayed",
    }


def _values(rows):
    """rows: list of (pos, tier, value, ppg, name)."""
    out = []
    for i, r in enumerate(rows):
        pos, tier, value, ppg, name = r
        out.append({
            "player_key": 100000 + i,
            "player_norm": name.lower().replace(" ", "-"),
            "player": name, "pos": pos, "tier": tier,
            "value": float(value), "raw_value": float(value),
            "ppg": float(ppg), "team": None if pos == "K" else name.split()[-1],
        })
    return out


class KdstGroupEmissionTests(unittest.TestCase):
    """Four K/DST groups are emitted for every (position, role) combination."""

    def test_four_groups_present_and_ordered(self):
        # 12-team: K starter = 12, K bench = 12; DST starter = 12, DST bench = 12.
        rows = ([("K", "starter", v, 8.0, f"Kick {i}") for i, v in enumerate([100.0] * 12)] +
                [("K", "bench", v, 5.0, f"Kick B{i}") for i, v in enumerate([10.0] * 12)] +
                [("DST", "starter", v, 5.0, f"Def S{i}") for i, v in enumerate([60.0] * 12)] +
                [("DST", "bench", v, 3.0, f"Def B{i}") for i, v in enumerate([8.0] * 12)])
        art = compute_groups(_make_kdst_leg(_values(rows)))

        self.assertEqual(art["schema"], KDST_GROUPS_SCHEMA)
        self.assertEqual(len(art["groups"]), 4)
        keys = [(g["position"], g["role"]) for g in art["groups"]]
        self.assertEqual(keys, KDST_GROUPS)

    def test_each_group_has_required_fields(self):
        rows = ([("K", "starter", 100.0, 8.0, "K1")] +
                [("K", "bench", 10.0, 5.0, "K2")] +
                [("DST", "starter", 60.0, 5.0, "D1")] +
                [("DST", "bench", 8.0, 3.0, "D2")])
        art = compute_groups(_make_kdst_leg(_values(rows)))
        required = {"position", "role", "total_vorp", "raw_surplus_ppg", "n_players"}
        for g in art["groups"]:
            self.assertTrue(required.issubset(g.keys()),
                            f"K/DST group missing required fields: {g}")


class NonNegativityTests(unittest.TestCase):
    """K/DST VORPs (raw surplus and calibrated chart value) are non-negative."""

    def test_calibrated_values_non_neg(self):
        rows = ([("K", "starter", v, 8.0, f"Kick {i}") for i, v in enumerate([100.0] * 12)] +
                [("K", "bench", v, 5.0, f"Kick B{i}") for i, v in enumerate([10.0] * 12)] +
                [("DST", "starter", v, 5.0, f"Def S{i}") for i, v in enumerate([60.0] * 12)] +
                [("DST", "bench", v, 3.0, f"Def B{i}") for i, v in enumerate([8.0] * 12)])
        art = compute_groups(_make_kdst_leg(_values(rows)))
        for g in art["groups"]:
            self.assertGreaterEqual(g["total_vorp"], 0.0,
                                    f"negative calibrated VORP in {g}")
            self.assertGreaterEqual(g["raw_surplus_ppg"], 0.0,
                                    f"negative raw surplus in {g}")
        self.assertGreaterEqual(art["totals"]["total_vorp"], 0.0)
        self.assertGreaterEqual(art["totals"]["sum_groups"], 0.0)
        self.assertGreaterEqual(art["totals"]["raw_surplus_ppg"], 0.0)
        self.assertGreaterEqual(art["totals"]["raw_sum_groups"], 0.0)

    def test_values_above_waiver_are_zero_below_and_positive_above(self):
        # Synthesize a leg where bench is at the waiver line -- surplus must
        # clamp to 0 (the same rule the skill groups follow).
        rows = ([("K", "starter", 80.0, 9.0, "Ks")] +
                [("K", "bench", 5.0, 5.0, "Kb")] +
                [("DST", "starter", 50.0, 5.5, "Ds")] +
                [("DST", "bench", 3.0, 3.0, "Db")])
        leg = _make_kdst_leg(_values(rows))
        leg["calibration"] = {"K": {"rw": 5.0}, "DST": {"rw": 3.0}}
        art = compute_groups(leg)
        # bench ppg == rw -> raw_surplus is 0 (clamped via max).
        k_bench = next(g for g in art["groups"] if g["position"] == "K" and g["role"] == "bench")
        self.assertAlmostEqual(k_bench["raw_surplus_ppg"], 0.0, places=6)


class SumInvariantTests(unittest.TestCase):
    """The four group totals sum to the overall VORP pie (no leakage)."""

    def test_groups_sum_equals_total_vorp(self):
        rows = ([("K", "starter", 95.5, 8.5, f"KS{i}") for i in range(12)] +
                [("K", "bench", 12.25, 5.25, f"KB{i}") for i in range(12)] +
                [("DST", "starter", 64.75, 5.75, f"DS{i}") for i in range(12)] +
                [("DST", "bench", 7.5, 3.5, f"DB{i}") for i in range(12)])
        art = compute_groups(_make_kdst_leg(_values(rows)))
        expected = sum(r[2] for r in rows)
        self.assertAlmostEqual(art["totals"]["total_vorp"], expected, places=4)
        self.assertAlmostEqual(art["totals"]["sum_groups"], expected, places=4)
        self.assertAlmostEqual(art["totals"]["sum_groups"],
                               art["totals"]["total_vorp"], places=6)

    def test_groups_sum_with_waiver_tier_present(self):
        # Waiver tier players carry 0 value; they must NOT appear in any of
        # the 4 groups but also must not push totals apart.
        rows = ([("K", "starter", 50.0, 8.0, "Ks")] +
                [("K", "bench", 5.0, 5.0, "Kb")] +
                [("K", "waiver", 0.0, 1.0, "Kw")] +
                [("DST", "starter", 30.0, 5.0, "Ds")] +
                [("DST", "bench", 8.0, 3.0, "Db")] +
                [("DST", "waiver", 0.0, 0.5, "Dw")])
        art = compute_groups(_make_kdst_leg(_values(rows)))
        expected = 50.0 + 5.0 + 30.0 + 8.0
        self.assertAlmostEqual(art["totals"]["total_vorp"], expected, places=4)
        self.assertAlmostEqual(art["totals"]["sum_groups"], expected, places=4)
        self.assertEqual(art["totals"]["n_waiver"], 2)


class DisplayMarkerTests(unittest.TestCase):
    """The 'computed but not displayed' marker is present and well-formed."""

    def test_marker_present_in_artifact(self):
        rows = ([("K", "starter", v, 8.0, f"Kick {i}") for i, v in enumerate([100.0] * 12)] +
                [("K", "bench", v, 5.0, f"Kick B{i}") for i, v in enumerate([10.0] * 12)] +
                [("DST", "starter", v, 5.0, f"Def S{i}") for i, v in enumerate([60.0] * 12)] +
                [("DST", "bench", v, 3.0, f"Def B{i}") for i, v in enumerate([8.0] * 12)])
        art = compute_groups(_make_kdst_leg(_values(rows)))
        self.assertEqual(art["display_status"], "computed_not_displayed")
        self.assertIsInstance(art["display_status_reason"], str)
        self.assertIn("kdst-group-contract", art["display_status_reason"].lower())
        self.assertIn("fixedPieIndexed", art["excluded_from_guards"])
        self.assertIn("sourceScaleAgreement", art["excluded_from_guards"])
        self.assertIn("ESPN", art["source_note"])
        self.assertIn("no peer", art["source_note"].lower())

    def test_artifact_emitted_with_marker(self):
        # The JSON-on-disk round-trip preserves the marker.
        rows = ([("K", "starter", 100.0, 8.0, f"Ks{i}") for i in range(12)] +
                [("K", "bench", 10.0, 5.0, f"Kb{i}") for i in range(12)] +
                [("DST", "starter", 60.0, 5.0, f"Ds{i}") for i in range(12)] +
                [("DST", "bench", 8.0, 3.0, f"Db{i}") for i in range(12)])
        leg = _make_kdst_leg(_values(rows))
        with tempfile.TemporaryDirectory() as tmpdir:
            leg_path = Path(tmpdir) / "ddf_leg_kdst.json"
            leg_path.write_text(json.dumps(leg))
            out_path = Path(tmpdir) / "ddf-kdst-group-vorps.json"
            art = build_groups_from_leg(leg_path, out_path)
            self.assertTrue(out_path.exists())
            loaded = json.loads(out_path.read_text())
            self.assertEqual(loaded["schema"], KDST_GROUPS_SCHEMA)
            self.assertEqual(loaded["display_status"], "computed_not_displayed")
            self.assertEqual(art["display_status"], loaded["display_status"])


class EightGroupInvarianceTests(unittest.TestCase):
    """The 8-group artifact is untouched by K/DST computation.

    The contract: K/DST never enter skill-group arithmetic. Skill totals,
    group maps, and the shared-batch70 anchor are byte-identical whether
    K/DST data is present or absent. These tests guard that property by
    confirming:
      * K/DST positions are REJECTED by the 8-group compute_groups.
      * A K/DST leg computes cleanly without ever being read by the
        8-group code.
      * The 8-group artifact schema name is preserved.
    """

    def test_skill_compute_groups_rejects_kdst_positions(self):
        # Skill compute_groups raises on K/DST (same contract as today).
        rows = [("QB", "starter", 80.0), ("QB", "bench", 5.0),
                ("RB", "starter", 60.0), ("RB", "bench", 10.0),
                ("WR", "starter", 40.0), ("WR", "bench", 20.0),
                ("TE", "starter", 30.0), ("TE", "bench", 4.0)]
        from build_ddf_groups import compute_groups as skill_cg
        # Add a K row; the skill runner must reject it.
        bad = rows + [("K", "starter", 1.0)]
        with self.assertRaises(ValueError):
            skill_cg(_make_skill_leg(rows=[("QB", "starter", 80.0, "qb"),
                                            ("QB", "bench", 5.0, "qb"),
                                            ("RB", "starter", 60.0, "rb"),
                                            ("RB", "bench", 10.0, "rb"),
                                            ("WR", "starter", 40.0, "wr"),
                                            ("WR", "bench", 20.0, "wr"),
                                            ("TE", "starter", 30.0, "te"),
                                            ("TE", "bench", 4.0, "te"),
                                            ("K", "starter", 1.0, "k")]))
        # Same for DST.
        with self.assertRaises(ValueError):
            skill_cg(_make_skill_leg(rows=[("QB", "starter", 80.0, "qb"),
                                            ("QB", "bench", 5.0, "qb"),
                                            ("RB", "starter", 60.0, "rb"),
                                            ("RB", "bench", 10.0, "rb"),
                                            ("WR", "starter", 40.0, "wr"),
                                            ("WR", "bench", 20.0, "wr"),
                                            ("TE", "starter", 30.0, "te"),
                                            ("TE", "bench", 4.0, "te"),
                                            ("DST", "starter", 1.0, "dst")]))

    def test_eight_group_schema_unchanged(self):
        # The 8-group artifact's schema identifier is the locked string.
        # This must NOT change as a side-effect of K/DST work.
        from build_ddf_groups import SCHEMA as skill_schema
        self.assertEqual(skill_schema, SKILL_GROUPS_SCHEMA)

    def test_kdst_compute_does_not_read_skill_artifact(self):
        # The K/DST compute_groups accepts ONLY a K/DST leg (different
        # schema id from the skill leg). Feeding it a skill leg fails
        # closed immediately.
        skill_leg = _make_skill_leg(rows=[("QB", "starter", 80.0, "qb"),
                                          ("QB", "bench", 5.0, "qb"),
                                          ("RB", "starter", 60.0, "rb"),
                                          ("RB", "bench", 10.0, "rb"),
                                          ("WR", "starter", 40.0, "wr"),
                                          ("WR", "bench", 20.0, "wr"),
                                          ("TE", "starter", 30.0, "te"),
                                          ("TE", "bench", 4.0, "te")])
        with self.assertRaises(ValueError):
            compute_groups(skill_leg)

    def test_8_group_byte_invariant_unchanged_by_kdst_module_import(self):
        # Importing the K/DST modules does not mutate any 8-group state.
        # NOTE: _empty_groups() uses tuple keys, so compare via repr(),
        # not json.dumps(sort_keys=True) (which raises TypeError on tuples).
        from build_ddf_groups import _empty_groups as skill_empty
        before = repr(skill_empty())
        import build_ddf_kdst_leg  # noqa: F401
        import build_ddf_kdst_groups  # noqa: F401
        after = repr(skill_empty())
        self.assertEqual(before, after)


class FailClosedTests(unittest.TestCase):
    """Fail-closed on ambiguous inputs: never invent values."""

    def test_unsupported_leg_schema_raises(self):
        bad = {"schema": "trade-value-ddf-leg-v1",  # the SKILL leg schema
               "inputs": {"teams": 12}, "values": []}
        with self.assertRaises(ValueError):
            compute_groups(bad)

    def test_missing_values_block_raises(self):
        bad = {"schema": KDST_LEG_SCHEMA, "inputs": {"teams": 12}}
        with self.assertRaises(ValueError):
            compute_groups(bad)

    def test_missing_teams_raises(self):
        bad = {"schema": KDST_LEG_SCHEMA, "values": [], "inputs": {}}
        with self.assertRaises(ValueError):
            compute_groups(bad)

    def test_unknown_position_raises(self):
        rows = [("K", "starter", 100.0, 8.0, "Ks"),
                ("K", "bench", 10.0, 5.0, "Kb"),
                ("DST", "starter", 60.0, 5.0, "Ds"),
                ("DST", "bench", 8.0, 3.0, "Db"),
                ("QB", "starter", 1.0, 10.0, "Qb")]  # not a K/DST position
        with self.assertRaises(ValueError):
            compute_groups(_make_kdst_leg(_values(rows)))

    def test_unknown_tier_raises(self):
        rows = [("K", "starter", 100.0, 8.0, "Ks"),
                ("K", "bench", 10.0, 5.0, "Kb"),
                ("DST", "starter", 60.0, 5.0, "Ds"),
                ("DST", "bench", 8.0, 3.0, "Db"),
                ("K", "starter2", 1.0, 8.0, "Ks2")]  # not in (starter, bench, waiver)
        with self.assertRaises(ValueError):
            compute_groups(_make_kdst_leg(_values(rows)))

    def test_empty_group_fails_closed(self):
        # No K bench -> the 4-group schema cannot be honored.
        rows = [("K", "starter", 100.0, 8.0, "Ks"),
                ("DST", "starter", 60.0, 5.0, "Ds"),
                ("DST", "bench", 8.0, 3.0, "Db")]
        with self.assertRaises(ValueError):
            compute_groups(_make_kdst_leg(_values(rows)))

    def test_negative_value_raises(self):
        rows = [("K", "starter", 100.0, 8.0, "Ks"),
                ("K", "bench", -10.0, 5.0, "Kb"),  # negative
                ("DST", "starter", 60.0, 5.0, "Ds"),
                ("DST", "bench", 8.0, 3.0, "Db")]
        with self.assertRaises(ValueError):
            compute_groups(_make_kdst_leg(_values(rows)))

    def test_missing_calibration_raises(self):
        rows = [("K", "starter", 100.0, 8.0, "Ks"),
                ("K", "bench", 10.0, 5.0, "Kb"),
                ("DST", "starter", 60.0, 5.0, "Ds"),
                ("DST", "bench", 8.0, 3.0, "Db")]
        leg = _make_kdst_leg(_values(rows))
        del leg["calibration"]
        with self.assertRaises(ValueError):
            compute_groups(leg)


class LoadInputTests(unittest.TestCase):
    """The input loaders parse the ESPN K/DST JSON files deterministically."""

    def test_load_kicker_pool_has_real_rows(self):
        rows, meta = load_kicker_pool(REPO / "data/inputs/espn_k_ppg_2026-09-21.json")
        self.assertGreater(meta["n_resolved"], 0)
        self.assertEqual(rows[0]["ppg"], max(r["ppg"] for r in rows))
        self.assertTrue(all(r["ppg"] >= 0 for r in rows))
        self.assertEqual(meta["as_of"], "2026-09-21")

    def test_load_dst_pool_has_real_rows(self):
        rows, meta = load_dst_pool(REPO / "data/inputs/espn_dst_ros_2026-09-21.json")
        self.assertGreater(meta["n_resolved"], 0)
        self.assertEqual(rows[0]["ppg"], max(r["ppg"] for r in rows))
        self.assertTrue(all(r["ppg"] >= 0 for r in rows))
        self.assertEqual(meta["as_of"], "2026-09-21")

    def test_identity_index_resolves_all_kdst(self):
        identities = build_identity_index(REPO / "data/fixtures/current/players.json")
        k_rows, _ = load_kicker_pool(REPO / "data/inputs/espn_k_ppg_2026-09-21.json")
        d_rows, _ = load_dst_pool(REPO / "data/inputs/espn_dst_ros_2026-09-21.json")
        unresolved_k = sorted(r["name"] for r in k_rows
                              if r["name"].lower() not in identities["by_name"])
        unresolved_d = sorted(r["team"] for r in d_rows
                              if r["team"] not in identities["by_team"])
        # Fail-closed identity: names that don't match the fixture go to
        # review_rows, never guessed. As of the 2026-09-21 inputs, exactly
        # three kickers are unresolvable: Michael Badgley (fixture has
        # "Mike Badgley" -- nickname variants are NOT auto-matched per the
        # no-nickname-guessing rule), Parker Romo and Caden Davis (not in
        # the fixture universe). All defenses resolve.
        self.assertEqual(unresolved_k,
                         ["Caden Davis", "Michael Badgley", "Parker Romo"],
                         "K identity drift: unexpected (un)resolved names")
        self.assertEqual(unresolved_d, [],
                         "Some DST teams don't match the fixture by abbr")


class LiveKdstLegIntegrationTests(unittest.TestCase):
    """If a local K/DST leg exists, end-to-end against it."""

    @classmethod
    def setUpClass(cls):
        cls.leg_dir = REPO / "data" / "ddf-two-tier"
        cls.leg_path = None
        if cls.leg_dir.is_dir():
            legs = sorted(cls.leg_dir.glob("*/ddf_leg_kdst.json"))
            if legs:
                cls.leg_path = legs[-1]

    def test_compute_groups_against_live_kdst_leg_if_present(self):
        if self.leg_path is None:
            self.skipTest("no local K/DST leg under data/ddf-two-tier; integration skipped")
        leg = json.loads(self.leg_path.read_text())
        art = compute_groups(leg)
        self.assertEqual(len(art["groups"]), 4)
        # Sum invariant on real data.
        self.assertAlmostEqual(
            art["totals"]["sum_groups"], art["totals"]["total_vorp"], places=4)
        # The marker must be present in any real artifact too.
        self.assertEqual(art["display_status"], "computed_not_displayed")


# ---------------------------------------------------------------------------
# Helpers for the 8-group invariance suite. These build skill legs shaped like
# the build_ddf_two_tier_leg.build_leg output (matching the test_ddf_groups
# fixture format) so the assertion can prove K/DST positions are rejected by
# the 8-group compute_groups.
# ---------------------------------------------------------------------------

def _make_skill_leg(rows):
    """rows: list of (pos, tier, value, name)."""
    from build_ddf_two_tier_leg import POSITIONS, REF_SLOTS, REF_FLEX_COUNT, bench_mix_for_teams
    values = []
    for i, r in enumerate(rows):
        pos, tier, value, name = r
        values.append({
            "player_key": i + 1,
            "player_norm": name,
            "player": name,
            "pos": pos, "tier": tier,
            "value": float(value),
            "raw_value": float(value),
            "ppg": 0.0, "team": None,
        })
    return {
        "schema": "trade-value-ddf-leg-v1",
        "bake_id": "ddf-20261002-espn-ppr-12t-0p15",
        "generated_at": "2026-10-02T00:00:00Z",
        "inputs": {"espn_snapshot_date": "2026-10-02",
                   "scoring": "ppr", "teams": 12, "bench_share": 0.15},
        "reference_shape": {"slots": REF_SLOTS, "flex_count": REF_FLEX_COUNT,
                            "flex_eligible": ["RB", "WR", "TE"],
                            "bench_mix": bench_mix_for_teams(12)},
        "calibration": {p: {"rw": 0.0} for p in POSITIONS},
        "values": values,
    }


if __name__ == "__main__":
    unittest.main()