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
# Covers ALL as-published combos (not just half-PPR): the 2026-10-02 follow-up
# found the flip persisting in Full PPR (the chart default) and in
# usatoday/fantasypros/cbs because JSN had no translated row for those grains.
# qb2 combos are deliberately excluded: they fall back to reindex by design
# (grain has no qb dimension; see _qb_divergent_siblings).
ORDERING_CASES = [
    ("fantasycalc", "half_12_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "full_12_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "full_10_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "full_14_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "full_8_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "half_10_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "half_14_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "half_8_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "standard_10_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "standard_12_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "standard_14_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "standard_8_qb1", "jaxon smithnjigba", "puka nacua"),
    ("usatoday", "full_12", "jaxon smithnjigba", "puka nacua"),
    ("usatoday", "half_12", "jaxon smithnjigba", "puka nacua"),
    ("usatoday", "standard_12", "jaxon smithnjigba", "puka nacua"),
    ("fantasypros", "full_12", "jaxon smithnjigba", "puka nacua"),
    ("fantasypros", "half_12", "jaxon smithnjigba", "puka nacua"),
    ("fantasypros", "standard_12", "jaxon smithnjigba", "puka nacua"),
    ("cbs", "full_12", "jaxon smithnjigba", "puka nacua"),
    ("cbs", "half_12", "jaxon smithnjigba", "puka nacua"),
    ("cbs", "standard_12", "jaxon smithnjigba", "puka nacua"),
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


class TestCanonicalIdentityResolution(unittest.TestCase):
    """VORP translation must resolve names through the canonical naming table.

    Regression for the 2026-10-02 follow-up: the fixture slug
    'jaxon smithnjigba' (no hyphen) did not match players.json
    'Jaxon Smith-Njigba', so JSN was silently excluded from every VORP
    translation grain except one -- and every as-published source fell back
    to the old quantile reindex for him, flipping Puka > JSN against native.
    """

    def test_hyphenless_slug_resolves_to_canonical_key(self):
        import sys
        sys.path.insert(0, str(REPO / "pipelines"))
        from vorp_translation.unified import load_native_values

        by_pos, key_by_name = load_native_values("fantasycalc", "ppr", 12)
        from canonical_players import norm_player_name
        key = key_by_name.get(norm_player_name("jaxon smithnjigba"))
        self.assertEqual(
            "3247", key,
            "JSN's fixture slug must resolve to canonical player_key 3247; "
            "an unresolved identity silently drops the player from VORP "
            "translation and flips orderings downstream.",
        )
        wr_names = [n for n, _ in by_pos["WR"]]
        self.assertTrue(
            any("njigba" in n for n in wr_names),
            "JSN must appear in the WR translation input.",
        )


if __name__ == "__main__":
    unittest.main()
