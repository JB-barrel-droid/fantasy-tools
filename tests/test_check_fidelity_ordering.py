"""
Tests for check_fidelity_ordering.py module.

These tests verify that the module correctly identifies ordering flips
between native and reindexed values. The tests use synthetic data
to prove the regression guard catches the bug it names.
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))
from check_fidelity_ordering import (
    get_native_and_reindexed,
    find_ordering_flips,
    check_source_flips,
)


class TestFindOrderingFlips(unittest.TestCase):
    """Test the flip detection logic with synthetic data."""

    def test_flip_detected_when_native_ranking_differs_from_reindexed(self):
        """
        Simulated flip: Player A ranks higher than B in native values,
        but B ranks higher than A in reindexed values.

        This is the core bug we're guarding against - a regression that
        would silently pass while checking nothing (the original bug).
        """
        native = {"player_a": 100.0, "player_b": 50.0, "player_c": 25.0}
        reindexed = {"player_a": 30.0, "player_b": 80.0, "player_c": 25.0}

        flips = find_ordering_flips(native, reindexed)

        # player_a > player_b in native (100 > 50), but player_b > player_a in reindexed (80 > 30)
        flip_pairs = {(f["player_a"], f["player_b"]) for f in flips}
        self.assertIn(("player_a", "player_b"), flip_pairs,
                      "Expected flip between player_a and player_b not found")

    def test_no_flip_when_rankings_match(self):
        """When native and reindexed rankings agree, no flips should be found."""
        native = {"player_a": 100.0, "player_b": 50.0, "player_c": 25.0}
        reindexed = {"player_a": 80.0, "player_b": 40.0, "player_c": 20.0}

        flips = find_ordering_flips(native, reindexed)

        self.assertEqual(len(flips), 0, "No flips expected when rankings match")

    def test_exact_ties_not_counted_as_flips(self):
        """
        Exact ties in reindexed values should NOT count as flips.
        Uses strict inequality (not >=).
        """
        native = {"player_a": 100.0, "player_b": 50.0}
        # Exact tie in reindexed - should NOT be a flip
        reindexed = {"player_a": 50.0, "player_b": 50.0}

        flips = find_ordering_flips(native, reindexed)

        # With strict inequality, a tie means player_a's reindexed rank could be
        # either 0 or 1 depending on sort stability, but neither is strictly > the other
        # The key is that equal values don't create a flip condition
        self.assertEqual(len(flips), 0,
                        "Exact ties should not count as flips with strict inequality")

    def test_multiple_flips_detected(self):
        """Multiple flips across a larger player pool should all be detected."""
        # Native: A > B > C > D
        # Reindexed: D > C > B > A (complete reversal)
        native = {"a": 40.0, "b": 30.0, "c": 20.0, "d": 10.0}
        reindexed = {"a": 10.0, "b": 20.0, "c": 30.0, "d": 40.0}

        flips = find_ordering_flips(native, reindexed)

        # Every pair is flipped in this scenario
        self.assertEqual(len(flips), 6, "Complete reversal should yield 6 flips (4 choose 2)")


class TestGetNativeAndReindexed(unittest.TestCase):
    """Test extraction from fixture-like data structures."""

    def test_extracts_direct_combo_level_values(self):
        """
        Current fixture format: native and reindexed stored directly under combo.
        This is the format that was broken before the fix.
        """
        data = {
            "sources": {
                "test_source": {
                    "combos": {
                        "full_12": {
                            "native": {"player_a": 100.0, "player_b": 50.0},
                            "reindexed": {"player_a": 30.0, "player_b": 80.0}
                        }
                    }
                }
            }
        }

        results = get_native_and_reindexed(data, "test_source")

        self.assertEqual(len(results), 1, "Should find 1 combo")
        self.assertEqual(results[0]["combo"], "full_12")
        self.assertEqual(results[0]["native"], {"player_a": 100.0, "player_b": 50.0})
        self.assertEqual(results[0]["reindexed"], {"player_a": 30.0, "player_b": 80.0})

    def test_extracts_fit_level_fallback(self):
        """
        Fallback format: native/reindexed under fit.flex_aware_pie.
        This tests backward compatibility.
        """
        data = {
            "sources": {
                "test_source": {
                    "combos": {
                        "full_12": {
                            "fit": {
                                "flex_aware_pie": {
                                    "native": {"player_a": 100.0, "player_b": 50.0},
                                    "reindexed": {"player_a": 30.0, "player_b": 80.0}
                                }
                            }
                        }
                    }
                }
            }
        }

        results = get_native_and_reindexed(data, "test_source")

        self.assertEqual(len(results), 1, "Should find 1 combo via fallback")

    def test_skips_combos_without_both_values(self):
        """Combos missing either native or reindexed should be skipped."""
        data = {
            "sources": {
                "test_source": {
                    "combos": {
                        "full_12": {
                            "native": {"player_a": 100.0}
                            # missing reindexed
                        },
                        "half_12": {
                            "reindexed": {"player_a": 50.0}
                            # missing native
                        },
                        "full_10": {
                            "native": {"player_a": 100.0},
                            "reindexed": {"player_a": 50.0}
                        }
                    }
                }
            }
        }

        results = get_native_and_reindexed(data, "test_source")

        self.assertEqual(len(results), 1, "Should only include combo with both values")
        self.assertEqual(results[0]["combo"], "full_10")

    def test_returns_empty_for_missing_source(self):
        """Should return empty list for non-existent source."""
        data = {"sources": {}}
        results = get_native_and_reindexed(data, "missing_source")
        self.assertEqual(results, [])


class TestCheckSourceFlips(unittest.TestCase):
    """Test the full flip checking pipeline for a source."""

    def test_flip_found_in_fixture_like_data(self):
        """
        Integration test: given fixture-shaped data with a flip,
        verify the flip is detected and counted.
        """
        data = {
            "sources": {
                "test_source": {
                    "combos": {
                        "full_12": {
                            "native": {
                                "jsn": 73.0,
                                "puka": 60.0,
                                "other": 50.0
                            },
                            "reindexed": {
                                "jsn": 40.0,
                                "puka": 55.0,
                                "other": 50.0
                            }
                        }
                    }
                }
            }
        }

        result = check_source_flips(data, "test_source")

        self.assertEqual(len(result["combos"]), 1)
        self.assertEqual(result["combos"][0]["flips_found"], 1,
                         "Should find exactly 1 flip (jsn vs puka)")
        flip = result["combos"][0]["flips"][0]
        self.assertEqual(flip["player_a"], "jsn")
        self.assertEqual(flip["player_b"], "puka")

    def test_no_flips_when_native_and_reindexed_match(self):
        """
        Flip-free dataset: when rankings are identical, exit should be 0.
        """
        data = {
            "sources": {
                "clean_source": {
                    "combos": {
                        "full_12": {
                            "native": {
                                "a": 100.0,
                                "b": 80.0,
                                "c": 60.0
                            },
                            "reindexed": {
                                "a": 50.0,
                                "b": 40.0,
                                "c": 30.0
                            }
                        }
                    }
                }
            }
        }

        result = check_source_flips(data, "clean_source")

        self.assertEqual(result["total_flips"], 0,
                         "Flip-free data should report 0 total flips")


class TestTieHandling(unittest.TestCase):
    """Explicit tests for tie-handling with strict inequality."""

    def test_strict_inequality_excludes_ties(self):
        """
        Verify that ties use strict inequality (not >=).
        If A and B have equal native values but different reindexed,
        it should still not count as a flip based on reindexed ties only.
        """
        # Same native ranking (both 100), different reindexed
        native = {"player_a": 100.0, "player_b": 100.0}
        # But reindexed values differ - this could go either way depending on sort stability
        # The important thing is: if reindexed values are EQUAL, no flip
        native_equal = {"player_a": 100.0, "player_b": 100.0}
        reindexed_equal = {"player_a": 50.0, "player_b": 50.0}

        flips = find_ordering_flips(native_equal, reindexed_equal)

        # When reindexed values are exactly equal, no flip should be counted
        # because neither is strictly greater than the other
        self.assertEqual(len(flips), 0,
                        "Equal reindexed values should not create flip with strict inequality")


if __name__ == "__main__":
    unittest.main()
