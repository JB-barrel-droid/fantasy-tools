"""JEG-242: completed Sheet oracle — formulas pinned, canonical player-key matching.

Supersedes the synthetic-ID oracle (tests/test_option_c_sheet_oracle.py), which
pinned only displayed values. This module pins:
  1. the approved CALC_Main formulas (role, group, alloc factor, imputed VORP),
     verified identical on rows 2, 3, 100 and 196 of the live workbook;
  2. canonical player_key matching for all 195 rows via
     pipelines/lib/canonical_players.py (reason == "ok": exactly one active
     position-matching candidate), cross-verified uniquely sufficient under the
     strict no-nickname plain norm;
  3. the pipeline reproducing the Sheet's group + full-precision imputed VORP
     keyed by canonical player_key (not synthetic enumeration IDs).

Excluded: OUT_Translated translated columns (position70 maxima, repeated
70/55 values, legacy #DIV/0 errors) and CALC_Main retired columns H/J are not
approved oracle material.
"""
import hashlib
import json
import math
import unittest
from pathlib import Path

from pipelines.build_imputed_vorps import RosterConfig, compute_imputed_vorps

ROOT = Path(__file__).resolve().parents[1]
ORACLE = ROOT / "docs/audits/jeg-242-sheet-oracle-complete.json"

EXPECTED_FORMULAS = {
    "role_E": '=IF($K{row},"Starter",IF($M{row},"Flex",IF($N{row},"Bench","Cut")))',
    "group_F": '=$A{row}&"|"&IF($E{row}="Flex","Starter",$E{row})',
    "alloc_factor_G": "=IFERROR(VLOOKUP($F{row},CALC_Params!$A$4:$F$11,6,FALSE),0)",
    "imputed_vorp_I": "=$D{row}*$G{row}",
}

GROUP_TARGETS = {
    ("QB", "starter"): 148.84, ("QB", "bench"): 26.27,
    ("RB", "starter"): 995.91, ("RB", "bench"): 175.75,
    ("WR", "starter"): 975.04, ("WR", "bench"): 172.07,
    ("TE", "starter"): 145.73, ("TE", "bench"): 23.38,
}


def load_oracle():
    return json.loads(ORACLE.read_text(encoding="utf-8"))


class SheetOracleCanonicalTests(unittest.TestCase):
    def test_oracle_file_and_source_capture_hashes(self):
        # The source value capture is the pinned input; its hash must match
        # the hash the earlier oracle test asserted, or this pin is not the
        # same Sheet read.
        oracle = load_oracle()
        self.assertEqual(oracle["schema"], "jeg242-sheet-oracle-complete-v1")
        cap_path = ROOT / oracle["source_capture"]["path"]
        self.assertEqual(
            hashlib.sha256(cap_path.read_bytes()).hexdigest(),
            "ee21497ce441ccde935a464fa03980b7657ab0b68818c2b9f3f625a9788357e0",
        )
        self.assertEqual(
            oracle["source_capture"]["sha256"],
            "ee21497ce441ccde935a464fa03980b7657ab0b68818c2b9f3f625a9788357e0",
        )

    def test_195_unique_canonical_keys(self):
        oracle = load_oracle()
        rows = oracle["rows"]
        self.assertEqual(len(rows), 195)
        keys = [r["player_key"] for r in rows]
        self.assertEqual(len(set(keys)), 195)
        for r in rows:
            self.assertIsInstance(r["player_key"], int)
            self.assertEqual(r["position"], r["position"].upper())
            self.assertIn(r["position"], ("QB", "RB", "WR", "TE"))

    def test_canonical_match_provenance(self):
        oracle = load_oracle()
        match = oracle["canonical_match"]
        self.assertEqual(match["matched"], 195)
        self.assertEqual(match["unmatched"], 0)
        self.assertEqual(match["ambiguous"], 0)
        self.assertEqual(match["position_conflict"], 0)

    def test_approved_formulas_pinned_verbatim(self):
        oracle = load_oracle()
        for key, formula in EXPECTED_FORMULAS.items():
            self.assertEqual(oracle["approved_formulas"][key], formula)

    def test_league_shape_matches_roster_config(self):
        oracle = load_oracle()
        shape = oracle["league_shape"]
        self.assertEqual(shape["teams"], 12)
        self.assertEqual(shape["flex_per_team"], 1)
        self.assertEqual(shape["bench_per_team"], 6)
        self.assertEqual(shape["starters_per_team"], {"QB": 1, "RB": 2, "WR": 3, "TE": 1})

    def test_pipeline_reproduces_oracle_by_canonical_key(self):
        oracle = load_oracle()
        values = {str(r["player_key"]): (r["position"], r["native_value"])
                  for r in oracle["rows"]}
        roster = RosterConfig(12, {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
                              1, 72, "half_ppr")
        out = compute_imputed_vorps(values, GROUP_TARGETS, roster,
                                    require_complete=True)
        mismatches = []
        for r in oracle["rows"]:
            key = str(r["player_key"])
            got = out[key]
            if (got["group"] != r["group"]
                    or not math.isclose(got["imputed_vorp"], r["imputed_vorp"],
                                        rel_tol=1e-12, abs_tol=1e-12)):
                mismatches.append(r["canonical_name"])
        self.assertEqual(mismatches, [])

    def test_perturbation_is_caught(self):
        # Discrimination: the pin is a real check, not a tautology. A fixture
        # copy with one row's imputed_vorp nudged must fail the reproduction
        # comparison.
        oracle = load_oracle()
        rows = [dict(r) for r in oracle["rows"]]
        rows[0]["imputed_vorp"] = rows[0]["imputed_vorp"] * 1.000001
        values = {str(r["player_key"]): (r["position"], r["native_value"])
                  for r in rows}
        roster = RosterConfig(12, {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
                              1, 72, "half_ppr")
        out = compute_imputed_vorps(values, GROUP_TARGETS, roster,
                                    require_complete=True)
        bad = [r for r in rows
               if not math.isclose(out[str(r["player_key"])]["imputed_vorp"],
                                   r["imputed_vorp"],
                                   rel_tol=1e-12, abs_tol=1e-12)]
        self.assertEqual(len(bad), 1)
        self.assertEqual(bad[0]["canonical_name"], rows[0]["canonical_name"])


if __name__ == "__main__":
    unittest.main()
