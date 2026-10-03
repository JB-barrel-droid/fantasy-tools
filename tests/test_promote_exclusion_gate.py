"""JEG-275: D2 exclusion gate must not drop valid published natives.

Regression test: the gate's MAX_VALID_VALUE=200 cap is calibrated to the
reindexed 0-70 display scale. FantasyCalc publishes native trade values in
the thousands (JSN 9914, Gibbs 10825). Applying the cap to natives dropped
154 valid FantasyCalc rows at promotion (chain run c04ad96), breaking
test_vorp_wiring with native/reindexed key mismatches.

Contract under test:
- native (as-published) values: null-identity, null-value, type, and >= 0
  checks apply; NO upper bound (units are source-specific).
- reindexed (0-70 scale) values: the full check including the 200 cap.
"""
import copy
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from promote_comparison_section import (
    MAX_VALID_VALUE,
    apply_exclusion_gate,
    validate_row,
)


def _section(native: dict, reindexed: dict) -> dict:
    return {
        "source_key": "fantasycalc",
        "combos": {
            "half_12_qb1": {
                "native": dict(native),
                "reindexed": dict(reindexed),
                "player_keys": {slug: f"key-{i}" for i, slug in enumerate(native)},
            }
        },
    }


class TestNativeUpperBound(unittest.TestCase):
    def test_thousands_scale_natives_survive(self):
        """FantasyCalc-scale natives (thousands) are valid published units."""
        section = _section(
            {"jaxon smithnjigba": 9914.0, "puka nacua": 7386.0, "jahmyr gibbs": 10825.0},
            {"jaxon smithnjigba": 55.0, "puka nacua": 41.0, "jahmyr gibbs": 70.0},
        )
        cleaned, hidden = apply_exclusion_gate(section, {})
        self.assertEqual(hidden, 0, "valid published natives must not be hidden")
        self.assertEqual(len(cleaned["combos"]["half_12_qb1"]["native"]), 3)

    def test_native_above_cap_passes_validation_directly(self):
        ok, reason = validate_row("jsn", 9914.0, "3247", check_upper_bound=False)
        self.assertTrue(ok, f"thousands-scale native rejected: {reason}")

    def test_native_negative_still_dropped(self):
        """The >= 0 lower bound still applies to natives."""
        section = _section({"bad player": -5.0}, {"bad player": 10.0})
        cleaned, hidden = apply_exclusion_gate(section, {})
        self.assertNotIn("bad player", cleaned["combos"]["half_12_qb1"]["native"])
        self.assertEqual(hidden, 1)

    def test_native_null_identity_still_dropped(self):
        section = _section({"ghost": 9914.0}, {"ghost": 55.0})
        section["combos"]["half_12_qb1"]["player_keys"] = {}
        cleaned, hidden = apply_exclusion_gate(section, {})
        self.assertNotIn("ghost", cleaned["combos"]["half_12_qb1"]["native"])
        self.assertEqual(hidden, 1)


class TestReindexedUpperBound(unittest.TestCase):
    def test_reindexed_above_cap_still_dropped(self):
        """The 200 cap remains a corruption check on the 0-70 reindexed scale."""
        section = _section({"good": 100.0}, {"good": MAX_VALID_VALUE + 50})
        cleaned, hidden = apply_exclusion_gate(section, {})
        self.assertIn("good", cleaned["combos"]["half_12_qb1"]["native"],
                      "native must survive even when its reindexed twin is corrupt")
        self.assertNotIn("good", cleaned["combos"]["half_12_qb1"]["reindexed"])
        self.assertEqual(hidden, 1)

    def test_reindexed_at_cap_boundary_passes(self):
        section = _section({"good": 100.0}, {"good": 70.0})
        cleaned, hidden = apply_exclusion_gate(section, {})
        self.assertEqual(hidden, 0)
        self.assertIn("good", cleaned["combos"]["half_12_qb1"]["reindexed"])


class TestGateDoesNotMutateInput(unittest.TestCase):
    def test_input_section_unchanged(self):
        section = _section({"jsn": 9914.0}, {"jsn": 999.0})
        before = copy.deepcopy(section)
        apply_exclusion_gate(section, {})
        self.assertEqual(section, before)


if __name__ == "__main__":
    unittest.main()
