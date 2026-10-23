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
    # FantasyCalc saves only the 12-team, 1-QB setups (decision league-settings-001,
    # 2026-10-06); the 8/10/14-team blocks were retired from the fixture.
    ("fantasycalc", "half_12_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "full_12_qb1", "jaxon smithnjigba", "puka nacua"),
    ("fantasycalc", "standard_12_qb1", "jaxon smithnjigba", "puka nacua"),
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


def ordering_inversions(native: dict, reindexed: dict) -> list[tuple[str, str, float, float, float, float]]:
    """Adjacent pairs (by native value, descending) where the higher native player's
    reindexed value is below the lower native player's: an ordering flip."""
    common = [slug for slug in reindexed if slug in native
              and isinstance(native[slug], (int, float)) and isinstance(reindexed[slug], (int, float))]
    by_native = sorted(common, key=lambda slug: -native[slug])
    return [(a, b, native[a], native[b], reindexed[a], reindexed[b])
            for a, b in zip(by_native, by_native[1:])
            if native[a] > native[b] and reindexed[a] < reindexed[b]]


class TestVorpWiring(unittest.TestCase):
    def test_ordering_preserved(self):
        """VORP-translated values must preserve native player ordering.

        JEG-916 (2026-10-22): the named pair (JSN over Nacua) no longer holds in the
        fixture's natives (USA Today lists Nacua 78 over JSN 77 since the 2026-10-22
        refresh), so the check walks every adjacent native pair of the combo instead
        of pinning one pair whose order the publisher can change."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        for source, combo_key, _higher, _lower in ORDERING_CASES:
            with self.subTest(source=source, combo=combo_key):
                combo = fixture["sources"][source]["combos"][combo_key]
                native, reindexed = combo["native"], combo["reindexed"]
                self.assertGreater(len(set(native) & set(reindexed)), 20, "too few translated rows to test")
                flips = ordering_inversions(native, reindexed)
                self.assertEqual(flips, [], "ORDERING FLIP (higher native, lower reindexed): "
                                 + "; ".join(f"{a} {na:.0f}>{nb:.0f} but {ra:.1f}<{rb:.1f} {b}"
                                             for a, b, na, nb, ra, rb in flips[:5]))

    def test_ordering_check_catches_a_flip(self):
        """The guard fails on a simulated flip: two reindexed values swapped."""
        fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
        combo = fixture["sources"]["usatoday"]["combos"]["full_12"]
        native, reindexed = combo["native"], dict(combo["reindexed"])
        self.assertEqual(ordering_inversions(native, reindexed), [])
        top = sorted((s for s in reindexed if s in native), key=lambda s: -native[s])
        a, b = next((a, b) for a, b in zip(top, top[1:]) if native[a] > native[b] and reindexed[a] > reindexed[b])
        reindexed[a], reindexed[b] = reindexed[b], reindexed[a]
        self.assertEqual([(x, y) for x, y, *_ in ordering_inversions(native, reindexed)], [(a, b)])


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

    def test_legacy_loader_resolves_hyphenless_slug(self):
        # The legacy roster-math loader (vorp_via_roster.load_ranked_values)
        # had the same exact-lowercase identity bug: JSN was silently dropped
        # from the legacy ranked lists while unified.load_native_values
        # included him, breaking unified-vs-legacy flex parity
        # (test_unified_custom_capacity_and_legacy_parity, 6 != 5).
        # JEG-75: every loader resolves through the canonical naming table.
        import sys
        sys.path.insert(0, str(REPO / "pipelines"))
        sys.path.insert(0, str(REPO / "pipelines" / "vorp_translation"))
        from vorp_via_roster import load_ranked_values

        ranked = load_ranked_values("usatoday", "half_12")
        wr_names = [n for n, _ in ranked["WR"]]
        self.assertTrue(
            any("njigba" in n for n in wr_names),
            "JSN's hyphenless fixture slug must resolve in the legacy "
            "loader too; a silent drop breaks parity with the unified path.",
        )


if __name__ == "__main__":
    unittest.main()
