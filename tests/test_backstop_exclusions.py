"""Two-tier cohort exclusion tests for JEG-242 backstop.

2026-10-03: PR 54's backstop fail-closed on any sub-min_sources player in the
league cohort, but Jeremy's methodology call distinguishes two cases:
  Tier 1 (rank): a player's best rank across sources exceeds the roster size
    -> no source considers them rosterable at this league size; exclude.
  Tier 2 (sources): a rank-eligible player in fewer than min_sources is
    excluded when low-value, or fail-closes when high-value (a high-value
    single-source player must never silently disappear).

These tests pin both tiers, the fail-closed path, the exclusion record
shape, and the reason-string formats.
"""
import importlib.util
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent


def _load_backstop():
    spec = importlib.util.spec_from_file_location(
        "backstop_shallow_sources",
        REPO / "pipelines" / "backstop_shallow_sources.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _entries(source, vorp, group="RB|bench"):
    return (source, float(vorp), group)


class TestExcludeByRankAndSources(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.b = _load_backstop()

    def _fixture(self):
        """Two deep sources (A, B) + one shallow source (C).

        Ranks with roster_size=4:
          A: p1(1) p2(2) p3(3) p4(4) p_deep(5)
          B: p1(1) p2(2) p3(3) p4(4)
          C: p_single_low(1) p_other(2)
        """
        return {
            "p1": [_entries("a", 100), _entries("b", 95)],
            "p2": [_entries("a", 90), _entries("b", 85)],
            "p3": [_entries("a", 80), _entries("b", 75)],
            "p4": [_entries("a", 70), _entries("b", 65)],
            "p_deep": [_entries("a", 5.0)],
            "p_single_low": [_entries("c", 4.0)],
            "p_other": [_entries("c", 3.0)],
        }

    def test_tier1_excludes_player_no_source_ranks_within_roster(self):
        """p_deep's best rank is 5 in source A; roster_size=4 -> Tier 1."""
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            self._fixture(), roster_size=4, min_sources=2
        )
        self.assertNotIn("p_deep", kept)
        rec = next(e for e in exclusions if e["player"] == "p_deep")
        self.assertEqual(rec["tier"], 1)
        self.assertEqual(rec["best_rank"], 5)
        self.assertIn("rank 5 exceeds 4-player roster size", rec["reason"])

    def test_tier1_uses_best_rank_across_sources(self):
        """A player ranked 5th in A but 2nd in B has best rank 2 -> survives."""
        players = {
            "p1": [_entries("a", 100), _entries("b", 95)],
            "p2": [_entries("a", 90), _entries("b", 85)],
            "p3": [_entries("a", 80), _entries("b", 75)],
            "p4": [_entries("a", 70), _entries("b", 65)],
            "p_flex": [_entries("a", 1.0), _entries("b", 66.0)],
        }
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            players, roster_size=4, min_sources=2
        )
        # p_flex: rank 5 in A, rank 4 in B -> best rank 4 <= 4, two sources.
        self.assertIn("p_flex", kept)
        self.assertEqual(exclusions, [])

    def test_tier2_excludes_low_value_single_source(self):
        """p_single_low: rank 1 in C (<= 4), one source, VORP 4.0 < 10."""
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            self._fixture(), roster_size=4, min_sources=2
        )
        self.assertNotIn("p_single_low", kept)
        self.assertNotIn("p_other", kept)
        rec = next(e for e in exclusions if e["player"] == "p_single_low")
        self.assertEqual(rec["tier"], 2)
        self.assertEqual(rec["n_sources"], 1)
        self.assertEqual(
            rec["reason"],
            "single-source (c only), not consensus rosterable, "
            "value 4.0 deep bench",
        )

    def test_tier2_fail_closed_on_high_value_single_source(self):
        """A lone source ranking a 50-VORP player must raise, never drop."""
        players = {
            "p1": [_entries("a", 100), _entries("b", 95)],
            "p_star": [_entries("c", 50.0)],
        }
        with self.assertRaises(ValueError) as ctx:
            self.b.exclude_by_rank_and_sources(
                players, roster_size=4, min_sources=2
            )
        self.assertIn("p_star", str(ctx.exception))
        self.assertIn("refusing to silently drop", str(ctx.exception))

    def test_tier2_threshold_boundary(self):
        """Mean VORP exactly at high_value_vorp still fail-closes (>=)."""
        players = {"p_edge": [_entries("c", 10.0)]}
        with self.assertRaises(ValueError):
            self.b.exclude_by_rank_and_sources(
                players, roster_size=4, min_sources=2, high_value_vorp=10.0
            )
        # Just below the threshold excludes instead of raising.
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            {"p_edge": [_entries("c", 9.9)]},
            roster_size=4, min_sources=2, high_value_vorp=10.0,
        )
        self.assertNotIn("p_edge", kept)
        self.assertEqual(exclusions[0]["tier"], 2)

    def test_consensus_players_pass_through_untouched(self):
        """p1..p4 keep both entries and byte-identical entry tuples."""
        fixture = self._fixture()
        kept, _exclusions = self.b.exclude_by_rank_and_sources(
            fixture, roster_size=4, min_sources=2
        )
        for pkey in ("p1", "p2", "p3", "p4"):
            self.assertIn(pkey, kept)
            self.assertEqual(kept[pkey], fixture[pkey])

    def test_exclusion_records_carry_diagnostics(self):
        """Every exclusion record has player/tier/reason plus diagnostics."""
        _kept, exclusions = self.b.exclude_by_rank_and_sources(
            self._fixture(), roster_size=4, min_sources=2
        )
        by_player = {e["player"]: e for e in exclusions}
        self.assertEqual(
            sorted(by_player), ["p_deep", "p_other", "p_single_low"]
        )
        for rec in exclusions:
            for key in ("player", "tier", "reason", "sources", "mean_vorp"):
                self.assertIn(key, rec)
        self.assertEqual(by_player["p_deep"]["sources"], ["a"])
        self.assertEqual(by_player["p_single_low"]["sources"], ["c"])

    def test_no_exclusions_when_all_pass(self):
        """Full-consensus fixture returns everything with no exclusions."""
        players = {
            "p1": [_entries("a", 100), _entries("b", 95)],
            "p2": [_entries("a", 90), _entries("b", 85)],
        }
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            players, roster_size=4, min_sources=2
        )
        self.assertEqual(set(kept), {"p1", "p2"})
        self.assertEqual(exclusions, [])

    def test_custom_roster_size_and_min_sources(self):
        """roster_size=2: only top-2 per source survive Tier 1."""
        kept, exclusions = self.b.exclude_by_rank_and_sources(
            self._fixture(), roster_size=2, min_sources=2
        )
        # p3/p4: best rank 3..4 > 2 -> Tier 1; p_deep rank 5 -> Tier 1.
        tiers = {e["player"]: e["tier"] for e in exclusions}
        self.assertEqual(tiers["p3"], 1)
        self.assertEqual(tiers["p4"], 1)
        self.assertEqual(tiers["p_deep"], 1)
        self.assertIn("p1", kept)
        self.assertIn("p2", kept)


if __name__ == "__main__":
    unittest.main()
