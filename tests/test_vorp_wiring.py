"""Test that VORP translation is truly wired through to the fixture.

Regression test for the Puka/JSN ordering flip (2026-10-02):
- FantasyCalc native: JSN 9914 > Puka 7386
- Old reindexed (per-bucket scaling): Puka 53.3 > JSN 48.1 (WRONG - flipped)
- VORP-translated: JSN 55.0 > Puka 41.0 (CORRECT)

This test ensures the fixture's reindexed values preserve native ordering,
proving the VORP wiring is actually connected, not just implemented.
"""
import json
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
FIXTURE = REPO / "data" / "fixtures" / "current" / "comparison-sources-data.json"

# (source, combo_key, higher_native_name, lower_native_name)
# If native higher > native lower, then reindexed higher must > reindexed lower.
ORDERING_CASES = [
    ("fantasycalc", "half_12_qb1", "jaxon smithnjigba", "puka nacua"),
]


class TestVorpWiring(unittest.TestCase):
    def test_ordering_preserved(self):
        """VORP-translated values must preserve native player ordering."""
        fixture = json.loads(FIXTURE.read_text())

        for source, combo_key, higher_name, lower_name in ORDERING_CASES:
            with self.subTest(source=source, combo=combo_key):
                combo = fixture["sources"][source]["combos"][combo_key]
                native = combo["native"]
                reindexed = combo["reindexed"]

                higher_slug = next(s for s in reindexed if higher_name in s.lower())
                lower_slug = next(s for s in reindexed if lower_name in s.lower())

                higher_native = native[higher_slug]
                lower_native = native[lower_slug]
                self.assertGreater(
                    higher_native, lower_native,
                    f"Test premise wrong: native {higher_name} should > {lower_name}"
                )

                higher_trans = reindexed[higher_slug]
                lower_trans = reindexed[lower_slug]
                self.assertGreater(
                    higher_trans, lower_trans,
                    f"ORDERING FLIP: {higher_name} native={higher_native:.0f} > "
                    f"{lower_name} native={lower_native:.0f}, but "
                    f"reindexed {higher_trans:.1f} <= {lower_trans:.1f}. "
                    f"VORP wiring is broken."
                )


if __name__ == "__main__":
    unittest.main()
