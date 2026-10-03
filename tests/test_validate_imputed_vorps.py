"""Tests for JEG-212 validate_imputed_vorps.

Each of the 5 checks has a positive case (passes) and a negative case
(fails / warns / flags correctly):
  0. input_completeness         -- FAIL on vacuous inputs (fail-closed)
  1. group_total_reconciliation  -- FAIL on mismatch
  2. non_negative                 -- FAIL on negative imputed_vorp
  3. ordering_sanity              -- WARN on inversion (never fails gate)
  4. divergence_flags             -- FLAG on >50% divergence (never fails)

Plus a smoke test for the standalone CLI runner (exit code wiring).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys

# Make pipelines/ importable without an install step.
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "pipelines"))

import validate_imputed_vorps as val  # noqa: E402
import unittest


# --- Fixtures ---------------------------------------------------------------

# A canonical group-totals document: sum of every group matches the
# publisher-natives in the valid artifact below.
VALID_GROUP_TOTALS = {
    "groups": {
        "QB|Starter": 200.0,
        "QB|Bench": 60.0,
        "RB|Starter": 350.0,
        "RB|Bench": 120.0,
        "WR|Starter": 320.0,
        "WR|Bench": 130.0,
        "TE|Starter": 110.0,
        "TE|Bench": 40.0,
    }
}

# Publisher-natives for the 8-group valid artifact. Totals are chosen so
# every alloc_factor is exactly 1.0 (simplifies the expected sums).
_NATIVE = {
    "QB|Starter": [("qb_a", 80.0), ("qb_b", 70.0), ("qb_c", 50.0)],  # sum 200
    "QB|Bench":   [("qb_d", 30.0), ("qb_e", 30.0)],                # sum 60
    "RB|Starter": [("rb_a", 100.0), ("rb_b", 90.0), ("rb_c", 80.0),
                   ("rb_d", 80.0)],                                  # sum 350
    "RB|Bench":   [("rb_e", 60.0), ("rb_f", 60.0)],                 # sum 120
    "WR|Starter": [("wr_a", 90.0), ("wr_b", 80.0), ("wr_c", 80.0),
                   ("wr_d", 70.0)],                                  # sum 320
    "WR|Bench":   [("wr_e", 70.0), ("wr_f", 60.0)],                 # sum 130
    "TE|Starter": [("te_a", 60.0), ("te_b", 50.0)],                 # sum 110
    "TE|Bench":   [("te_c", 25.0), ("te_d", 15.0)],                 # sum 40
}

# DDF values that match imputed exactly (no divergence -> no flags).
_DDF = {pkey: float(native) for group in _NATIVE.values() for pkey, native in group}


def _make_artifact(group_to_iter=None,
                  natives=None,
                  ddf=None,
                  imputed_override=None,
                  artifact_shape="lineage"):
    """Build a synthetic imputed VORP artifact.

    group_to_iter: defaults to _NATIVE; pass a modified dict to inject bugs.
    natives / ddf: override the per-player native / ddf_rebuilt maps.
    imputed_override: optional {pkey: float} to replace computed imputed_vorp.
    artifact_shape: "lineage" -> {sources: {src: {top25: [...]}}} (default),
                    "flat"    -> {src: [player_records]}
    """
    if group_to_iter is None:
        group_to_iter = _NATIVE
    if natives is None:
        natives = {pkey: float(nat) for group in group_to_iter.values()
                   for pkey, nat in group}
    if ddf is None:
        ddf = dict(_DDF)

    players = []
    for group_label, members in group_to_iter.items():
        # alloc_factor = our_group_vorp / sum_publisher_values_in_group
        sum_pub = sum(nat for _, nat in members)
        our_vorp = VALID_GROUP_TOTALS["groups"][group_label]
        af = our_vorp / sum_pub if sum_pub else None
        for pkey, nat in members:
            if imputed_override and pkey in imputed_override:
                imputed = imputed_override[pkey]
            else:
                imputed = round(nat * af, 2) if af is not None else None
            players.append({
                "player_key": pkey,
                "group": group_label,
                "native": float(nat),
                "alloc_factor": round(af, 4) if af is not None else None,
                "our_group_vorp": our_vorp,
                "imputed_vorp": imputed,
                "ddf_rebuilt": ddf.get(pkey),
            })

    if artifact_shape == "flat":
        return {"fantasypros": players}
    return {"sources": {"fantasypros": {"top25": players}}}


# --- Check 0: input completeness (fail-closed) --------------------------------
def _write_totals(doc):
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json", prefix="jeg212-totals-")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f)
    return path


# --- CLI runner ------------------------------------------------------------


def _artifact_path(artifact_dict):
    """Write an artifact dict to a temp file and return the path.

    Returns the path so callers can hand it to the CLI / loader.
    """
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json", prefix="jeg212-")
    with os.fdopen(fd, "w") as f:
        json.dump(artifact_dict, f)
    return path


def _totals_path():
    import tempfile
    fd, path = tempfile.mkstemp(suffix=".json", prefix="jeg212-totals-")
    with os.fdopen(fd, "w") as f:
        json.dump(VALID_GROUP_TOTALS, f)
    return path





class InputCompletenessTests(unittest.TestCase):
    def test_check0_positive_complete_inputs(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, details = val.check_input_completeness(
            loaded, VALID_GROUP_TOTALS["groups"]
        )
        self.assertTrue(passed)
        self.assertEqual(viol, [])
        self.assertGreater(details["per_source"]["fantasypros"]["assignable_players"], 0)
        self.assertEqual(details["missing_groups"], [])

    def test_check0_negative_empty_artifact_fails(self):
        # {"sources": {}} previously passed every check vacuously (exit 0).
        loaded = val.load_imputed_artifact(_artifact_path({"sources": {}}))
        passed, viol, _ = val.check_input_completeness(
            loaded, VALID_GROUP_TOTALS["groups"]
        )
        self.assertFalse(passed)
        self.assertTrue(any(v["kind"] == "empty_artifact" for v in viol))
        report = val.run_validation(loaded, VALID_GROUP_TOTALS["groups"])
        self.assertFalse(report["overall_pass"])
        self.assertFalse(report["checks"]["input_completeness"]["passed"])

    def test_check0_negative_source_with_no_players_fails(self):
        loaded = val.load_imputed_artifact(
            _artifact_path({"sources": {"fantasypros": {"top25": []}}}))
        passed, viol, _ = val.check_input_completeness(
            loaded, VALID_GROUP_TOTALS["groups"]
        )
        self.assertFalse(passed)
        self.assertTrue(any(v["kind"] == "empty_source" for v in viol))
        report = val.run_validation(loaded, VALID_GROUP_TOTALS["groups"])
        self.assertFalse(report["overall_pass"])

    def test_check0_negative_missing_group_totals_fails(self):
        # Empty totals previously let check 1 pass vacuously (missing groups
        # recorded as None matches, no violations). Now fail-closed.
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, _ = val.check_input_completeness(loaded, {})
        self.assertFalse(passed)
        self.assertEqual(len([v for v in viol if v["kind"] == "missing_group_total"]), 8)
        report = val.run_validation(loaded, {})
        self.assertFalse(report["overall_pass"])

    def test_check0_negative_partial_group_totals_fails(self):
        partial = dict(VALID_GROUP_TOTALS["groups"])
        del partial["TE|Bench"]
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, details = val.check_input_completeness(loaded, partial)
        self.assertFalse(passed)
        self.assertEqual(details["missing_groups"], ["TE|Bench"])


    # --- Check 1: group-total reconciliation ------------------------------------


class GroupReconciliationTests(unittest.TestCase):
    def test_check1_positive_totals_match(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, details = val.check_group_total_reconciliation(
            loaded, VALID_GROUP_TOTALS["groups"], tolerance=0.01
        )
        self.assertTrue(passed)
        self.assertEqual(viol, [])
        # Every group should match.
        for src in ("fantasypros",):
            for g, m in details["per_source"][src]["matches"].items():
                self.assertTrue(m, f"group {g} should match")

    def test_check1_negative_totals_mismatch(self):
        # Bump WR|Starter imputed values so the sum drifts > tolerance.
        overrides = {}
        # Scale WR|Starter natives up by 50% -> imputed sums way over 320.
        for pkey, nat in _NATIVE["WR|Starter"]:
            overrides[pkey] = round(nat * 1.50, 2)
        artifact = _make_artifact(imputed_override=overrides)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, details = val.check_group_total_reconciliation(
            loaded, VALID_GROUP_TOTALS["groups"], tolerance=0.01
        )
        self.assertFalse(passed)
        self.assertTrue(any(v["group"] == "WR|Starter" for v in viol))
        wr = next(v for v in viol if v["group"] == "WR|Starter")
        self.assertGreater(wr["actual"], wr["expected"])
        self.assertGreater(wr["diff_relative"], 0.01)

    def test_check1_negative_within_tolerance_still_passes(self):
        # Tiny drift (0.5%) must pass with the default 1% tolerance.
        overrides = {}
        for pkey, nat in _NATIVE["WR|Starter"]:
            overrides[pkey] = round(nat * 1.005, 2)
        artifact = _make_artifact(imputed_override=overrides)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, _ = val.check_group_total_reconciliation(
            loaded, VALID_GROUP_TOTALS["groups"], tolerance=0.01
        )
        self.assertTrue(passed)
        self.assertEqual(viol, [])


    # --- Check 2: non-negative --------------------------------------------------


class NonNegativeTests(unittest.TestCase):
    def test_check2_positive_all_non_negative(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, _ = val.check_non_negative(loaded)
        self.assertTrue(passed)
        self.assertEqual(viol, [])

    def test_check2_negative_finds_negatives(self):
        overrides = {"rb_a": -5.0, "wr_b": -1.0}
        artifact = _make_artifact(imputed_override=overrides)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, viol, details = val.check_non_negative(loaded)
        self.assertFalse(passed)
        self.assertEqual(len(viol), 2)
        bad_keys = {v["player_key"] for v in viol}
        self.assertEqual(bad_keys, {"rb_a", "wr_b"})
        for v in viol:
            self.assertLess(v["imputed_vorp"], 0)


    # --- Check 3: ordering sanity (warn-only) -----------------------------------


class OrderingSanityTests(unittest.TestCase):
    def test_check3_positive_ordering_preserved(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, warns, _ = val.check_ordering_sanity(loaded)
        # Valid artifact: no inversions, check still "passes".
        self.assertTrue(passed)
        self.assertEqual(warns, [])

    def test_check3_negative_warns_on_inversion(self):
        # rb_b and rb_c have swapped imputed values relative to native.
        overrides = {"rb_b": 200.0, "rb_c": 10.0}
        artifact = _make_artifact(imputed_override=overrides)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, warns, details = val.check_ordering_sanity(loaded)
        # The check warns but does NOT fail.
        self.assertTrue(passed)
        self.assertGreaterEqual(len(warns), 1)
        inv = details["per_source"]["fantasypros"]["inversions"][0]
        self.assertEqual(inv["group"], "RB|Starter")
        # An inversion exists in RB|Starter (rb_b's inflated imputed value
        # disrupts the native ordering). The specific pair depends on
        # implementation details; we just verify the group is flagged.
        self.assertIn("higher_imputed_player", inv)
        self.assertIn("lower_imputed_player", inv)


    # --- Check 4: divergence flags (flag-only) ----------------------------------


class DivergenceFlagTests(unittest.TestCase):
    def test_check4_positive_no_divergence(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, flags, _ = val.check_divergence_flags(loaded)
        self.assertTrue(passed)
        self.assertEqual(flags, [])

    def test_check4_negative_flags_high_divergence(self):
        # Override DDF for one player so |imputed - ddf| / ddf > 50%.
        # rb_a has native 100, imputed 100 (alloc_factor 1.0). Make ddf_rebuilt = 10.
        ddf = dict(_DDF)
        ddf["rb_a"] = 10.0
        artifact = _make_artifact(ddf=ddf)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        passed, flags, details = val.check_divergence_flags(loaded)
        # Flag-only: check "passes" but surfaces the name.
        self.assertTrue(passed)
        self.assertEqual(len(flags), 1)
        self.assertEqual(flags[0]["player_key"], "rb_a")
        self.assertGreater(flags[0]["divergence_pct"], 50.0)

    def test_check4_exact_threshold_does_not_flag(self):
        # Boundary: exactly 50% divergence should NOT flag (strict greater-than).
        # rb_a: imputed=100, set ddf=200 -> |100-200|/200 = 0.5 = exactly 50%.
        ddf = dict(_DDF)
        ddf["rb_a"] = 200.0
        artifact = _make_artifact(ddf=ddf)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        _passed, flags, _ = val.check_divergence_flags(loaded)
        # strict >, so exactly 50.0% is clean
        self.assertEqual(flags, [])


    # --- run_validation: overall pass/fail wiring -------------------------------


class RunValidationTests(unittest.TestCase):
    def test_run_validation_all_clean_passes(self):
        artifact = _make_artifact()
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        report = val.run_validation(loaded, VALID_GROUP_TOTALS["groups"])
        self.assertTrue(report["overall_pass"])
        self.assertTrue(report["checks"]["group_total_reconciliation"]["passed"])
        self.assertTrue(report["checks"]["non_negative"]["passed"])
        self.assertTrue(report["checks"]["ordering_sanity"]["passed"])
        self.assertTrue(report["checks"]["divergence_flags"]["passed"])
        self.assertEqual(report["summary"]["total_violations"], 0)

    def test_run_validation_fail_check_overrides_warn_and_flag(self):
        # A negative imputed_vorp (fail-check) must drive overall_pass=False,
        # even though the warn-check and flag-check are clean.
        artifact = _make_artifact(imputed_override={"qb_a": -1.0})
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        report = val.run_validation(loaded, VALID_GROUP_TOTALS["groups"])
        self.assertFalse(report["overall_pass"])
        self.assertFalse(report["checks"]["non_negative"]["passed"])
        # warn/flag checks stay passing.
        self.assertTrue(report["checks"]["ordering_sanity"]["passed"])
        self.assertTrue(report["checks"]["divergence_flags"]["passed"])

    def test_run_validation_warn_and_flag_alone_does_not_fail(self):
        # Ordering inversion + divergence flag: both are non-failing severities.
        # Sum-preserving swap (rb_b 90->80, rb_c 80->90): inverts the imputed
        # ordering vs native without breaking the group-total reconciliation.
        overrides = {"rb_b": 80.0, "rb_c": 90.0}
        ddf = dict(_DDF)
        ddf["wr_a"] = 10.0
        artifact = _make_artifact(imputed_override=overrides, ddf=ddf)
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        report = val.run_validation(loaded, VALID_GROUP_TOTALS["groups"])
        self.assertTrue(report["overall_pass"])
        self.assertGreaterEqual(report["summary"]["total_warnings"], 1)
        self.assertGreaterEqual(report["summary"]["total_flags"], 1)
        self.assertEqual(report["summary"]["total_violations"], 0)


    # --- Artifact loader -------------------------------------------------------


class LoaderTests(unittest.TestCase):
    def test_loader_accepts_lineage_shape(self):
        artifact = _make_artifact(artifact_shape="lineage")
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        self.assertIn("fantasypros", loaded)
        self.assertTrue(isinstance(loaded["fantasypros"], list))
        self.assertGreater(len(loaded["fantasypros"]), 0)
        # First record has the required imputed_vorp / group fields.
        rec = loaded["fantasypros"][0]
        self.assertIn("imputed_vorp", rec)
        self.assertIn("group", rec)

    def test_loader_accepts_flat_shape(self):
        artifact = _make_artifact(artifact_shape="flat")
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        self.assertIn("fantasypros", loaded)
        self.assertTrue(isinstance(loaded["fantasypros"], list))

    def test_loader_prefers_players_over_top25(self):
        artifact = {
            "sources": {
                "fantasypros": {
                    "players": [{"player_key": "x", "group": "QB|Starter",
                                  "imputed_vorp": 1.0}],
                    "top25": [{"player_key": "y", "group": "RB|Starter",
                                "imputed_vorp": 2.0}],
                }
            }
        }
        loaded = val.load_imputed_artifact(_artifact_path(artifact))
        keys = [r["player_key"] for r in loaded["fantasypros"]]
        # "players" wins over "top25"
        self.assertEqual(keys, ["x"])


    # --- Group-totals loader (JEG-206 shape variants) -------------------------


class GroupTotalsLoaderTests(unittest.TestCase):
    def test_group_totals_loader_accepts_dict_shorthand(self):
        # Dict shorthand: {"groups": {"QB|Starter": 200.0, ...}}
        path = _write_totals({"groups": dict(VALID_GROUP_TOTALS["groups"])})
        try:
            loaded = val.load_group_totals(path)
            self.assertEqual(loaded["QB|Starter"], 200.0)
            self.assertEqual(loaded["TE|Bench"], 40.0)
            self.assertEqual(len(loaded), 8)
        finally:
            os.unlink(path)

    def test_group_totals_loader_accepts_jeg206_list_shape(self):
        # JEG-206 canonical: {"groups": [{"position": "QB", "role": "starter",
        #                                  "total_vorp": 200.0}, ...]}
        rows = [
            {"position": pos, "role": role, "total_vorp": v}
            for (pos, role), v in zip(
                [("QB", "starter"), ("QB", "bench"),
                 ("RB", "starter"), ("RB", "bench"),
                 ("WR", "starter"), ("WR", "bench"),
                 ("TE", "starter"), ("TE", "bench")],
                [200.0, 60.0, 350.0, 120.0, 320.0, 130.0, 110.0, 40.0],
            )
        ]
        path = _write_totals({"groups": rows})
        try:
            loaded = val.load_group_totals(path)
            self.assertEqual(loaded["QB|Starter"], 200.0)
            self.assertEqual(loaded["TE|Bench"], 40.0)
            self.assertEqual(len(loaded), 8)
        finally:
            os.unlink(path)







class CliRunnerTests(unittest.TestCase):
    def test_cli_exits_zero_on_clean(self):
        artifact = _make_artifact()
        art_path = _artifact_path(artifact)
        tot_path = _totals_path()
        try:
            result = subprocess.run(
                [sys.executable,
                 os.path.join(REPO, "pipelines", "validate_imputed_vorps.py"),
                 "--imputed-artifact", art_path,
                 "--group-totals", tot_path,
                 "--output", os.path.join(os.path.dirname(art_path), "rep.json")],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, f"expected exit 0 on clean run, got {result.returncode}\n" f"stdout={result.stdout}\nstderr={result.stderr}")
            # Report should be valid JSON with overall_pass=True.
            report = json.load(open(os.path.join(os.path.dirname(art_path), "rep.json")))
            self.assertTrue(report["overall_pass"])
        finally:
            for p in (art_path, tot_path,
                      os.path.join(os.path.dirname(art_path), "rep.json")):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def test_cli_exits_nonzero_on_fail(self):
        artifact = _make_artifact(imputed_override={"qb_a": -1.0})
        art_path = _artifact_path(artifact)
        tot_path = _totals_path()
        try:
            result = subprocess.run(
                [sys.executable,
                 os.path.join(REPO, "pipelines", "validate_imputed_vorps.py"),
                 "--imputed-artifact", art_path,
                 "--group-totals", tot_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1, f"expected exit 1 on negative imputed_vorp, got {result.returncode}\n" f"stdout={result.stdout}\nstderr={result.stderr}")
            # Stdout should still contain a valid JSON report.
            report = json.loads(result.stdout)
            self.assertFalse(report["overall_pass"])
            self.assertFalse(report["checks"]["non_negative"]["passed"])
        finally:
            for p in (art_path, tot_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def test_cli_exits_nonzero_on_group_mismatch(self):
        overrides = {pkey: round(nat * 2.0, 2)
                     for pkey, nat in _NATIVE["RB|Starter"]}
        artifact = _make_artifact(imputed_override=overrides)
        art_path = _artifact_path(artifact)
        tot_path = _totals_path()
        try:
            result = subprocess.run(
                [sys.executable,
                 os.path.join(REPO, "pipelines", "validate_imputed_vorps.py"),
                 "--imputed-artifact", art_path,
                 "--group-totals", tot_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertFalse(report["checks"]["group_total_reconciliation"]["passed"])
        finally:
            for p in (art_path, tot_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def test_cli_exits_zero_with_only_warnings_and_flags(self):
        # Ordering inversion (warn) + divergence flag (flag) -- no fail checks.
        # Sum-preserving swap keeps group totals intact (see above).
        overrides = {"rb_b": 80.0, "rb_c": 90.0}
        ddf = dict(_DDF)
        ddf["wr_a"] = 10.0
        artifact = _make_artifact(imputed_override=overrides, ddf=ddf)
        art_path = _artifact_path(artifact)
        tot_path = _totals_path()
        try:
            result = subprocess.run(
                [sys.executable,
                 os.path.join(REPO, "pipelines", "validate_imputed_vorps.py"),
                 "--imputed-artifact", art_path,
                 "--group-totals", tot_path],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, f"warn+flag must not affect exit code; got {result.returncode}\n" f"stderr={result.stderr}")
            report = json.loads(result.stdout)
            self.assertTrue(report["overall_pass"])
            self.assertGreaterEqual(report["summary"]["total_warnings"], 1)
            self.assertGreaterEqual(report["summary"]["total_flags"], 1)
        finally:
            for p in (art_path, tot_path):
                try:
                    os.unlink(p)
                except OSError:
                    pass



if __name__ == '__main__':
    unittest.main()
