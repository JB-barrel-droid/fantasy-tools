#!/usr/bin/env python3
"""Unit tests for the compare helpers in tools/value_three_way.py (JEG-1166).

Small inline dicts only; main() is never run (it needs live dumps). Importing
value_three_way is side-effect free.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "tools"))

import value_three_way as vtw  # noqa: E402


class DiffMapsTest(unittest.TestCase):
    def test_identical_maps_no_mismatch(self):
        d = vtw.diff_maps({"1": 1.0, "2": 2.0}, {"1": 1.0, "2": 2.0}, 0.05)
        self.assertEqual(d["mismatches"], 0)
        self.assertEqual(d["compared"], 2)
        self.assertEqual(d["max_abs_diff"], 0.0)
        self.assertEqual(d["examples"], [])

    def test_diff_exactly_tol_is_not_a_mismatch(self):
        # 0.25 is exact in binary; 1.0 vs 1.25 differs by exactly tol.
        d = vtw.diff_maps({"1": 1.0}, {"1": 1.25}, 0.25)
        self.assertEqual(d["mismatches"], 0)
        self.assertEqual(d["max_abs_diff"], 0.25)

    def test_diff_just_above_tol_is_a_mismatch(self):
        d = vtw.diff_maps({"1": 1.0}, {"1": 1.5}, 0.25)
        self.assertEqual(d["mismatches"], 1)
        self.assertEqual(d["examples"][0]["player"], "1")

    def test_key_only_in_one_map_is_a_mismatch(self):
        d = vtw.diff_maps({"1": 1.0}, {}, 0.05)
        self.assertEqual(d["compared"], 1)
        self.assertEqual(d["mismatches"], 1)

    def test_both_none_counted_but_not_a_mismatch(self):
        d = vtw.diff_maps({"1": None}, {"1": None}, 0.05)
        self.assertEqual(d["compared"], 1)
        self.assertEqual(d["mismatches"], 0)
        self.assertEqual(d["max_abs_diff"], 0.0)

    def test_bool_is_not_a_number(self):
        # True is not treated as a number, so True vs 1.0 is a mismatch ...
        d = vtw.diff_maps({"1": True}, {"1": 1.0}, 0.05)
        self.assertEqual(d["mismatches"], 1)
        # ... and True vs None is two non-numbers, no mismatch.
        d2 = vtw.diff_maps({"1": True}, {"1": None}, 0.05)
        self.assertEqual(d2["mismatches"], 0)

    def test_max_abs_diff_is_largest_numeric_diff(self):
        d = vtw.diff_maps({"1": 1.0, "2": 10.0, "3": 1.0}, {"1": 1.2, "2": 12.0, "3": 1.0}, 0.05)
        self.assertEqual(d["max_abs_diff"], 2.0)

    def test_at_most_three_examples(self):
        a = {str(i): 1.0 for i in range(1, 8)}
        b = {str(i): 9.0 for i in range(1, 8)}
        d = vtw.diff_maps(a, b, 0.05)
        self.assertEqual(d["mismatches"], 7)
        self.assertEqual(len(d["examples"]), 3)

    def test_examples_iterate_in_integer_order(self):
        a = {"1": 1.0, "2": 1.0, "9": 1.0, "10": 1.0, "11": 1.0}
        b = {"1": 9.0, "2": 9.0, "9": 9.0, "10": 9.0, "11": 9.0}
        d = vtw.diff_maps(a, b, 0.05)
        self.assertEqual([e["player"] for e in d["examples"]], ["1", "2", "9"])


class SeriesOfTest(unittest.TestCase):
    def setUp(self):
        self.views = {
            "indexed": {
                "1": {"ddf": 10.0, "vorp": 1.0},
                "2": {"ddf": 20.0},
            }
        }

    def test_picks_one_series_and_skips_rows_without_it(self):
        self.assertEqual(vtw.series_of(self.views, "indexed", "ddf"), {"1": 10.0, "2": 20.0})
        self.assertEqual(vtw.series_of(self.views, "indexed", "vorp"), {"1": 1.0})

    def test_missing_view_is_empty(self):
        self.assertEqual(vtw.series_of(self.views, "vorp", "ddf"), {})

    def test_missing_series_is_empty(self):
        self.assertEqual(vtw.series_of(self.views, "indexed", "nope"), {})


class ReadoutOfTest(unittest.TestCase):
    def test_none_and_empty_are_none(self):
        self.assertIsNone(vtw.readout_of(None))
        self.assertIsNone(vtw.readout_of({}))

    def test_prefers_bench_share_over_bench_share_readout(self):
        p = {"benchShare": {"QB": 1.0}, "bench_share_readout": {"QB": 2.0}}
        self.assertEqual(vtw.readout_of(p), {"QB": 1.0})

    def test_falls_back_to_bench_share_readout(self):
        self.assertEqual(vtw.readout_of({"bench_share_readout": {"QB": 2.0}}), {"QB": 2.0})

    def test_non_dict_value_is_none(self):
        self.assertIsNone(vtw.readout_of({"benchShare": 1.0}))
        self.assertIsNone(vtw.readout_of({"bench_share_readout": "x"}))


class CompareReadoutsTest(unittest.TestCase):
    def test_both_none_no_mismatch(self):
        d = vtw.compare_readouts(None, None)
        self.assertEqual(d["mismatches"], 0)
        self.assertIsNone(d["max_abs_diff"])

    def test_one_none_is_one_mismatch(self):
        self.assertEqual(vtw.compare_readouts({"QB": 1.0}, None)["mismatches"], 1)
        self.assertEqual(vtw.compare_readouts(None, {"QB": 1.0})["mismatches"], 1)

    def test_diff_beyond_readout_tol_counts(self):
        a = {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0, "overall": 1.0}
        b = {"QB": 1.5, "RB": 1.0, "WR": 1.0, "TE": 1.0, "overall": 1.0}
        d = vtw.compare_readouts(a, b)
        self.assertEqual(d["mismatches"], 1)
        self.assertEqual(d["max_abs_diff"], 0.5)

    def test_key_missing_on_one_side_counts_missing_on_both_does_not(self):
        a = {"QB": 1.0, "RB": 1.0}
        b = {"RB": 1.0}
        d = vtw.compare_readouts(a, b)
        self.assertEqual(d["mismatches"], 1)
        # Both sides missing the remaining READOUT_KEYS: no extra mismatches.
        self.assertEqual(vtw.compare_readouts({"QB": 1.0}, {"QB": 1.0})["mismatches"], 0)

    def test_max_abs_diff_is_worst_diff(self):
        a = {"QB": 1.0, "RB": 1.0, "WR": 1.0, "TE": 1.0, "overall": 1.0}
        b = {"QB": 1.5, "RB": 3.0, "WR": 1.0, "TE": 1.0, "overall": 1.0}
        d = vtw.compare_readouts(a, b)
        self.assertEqual(d["mismatches"], 2)
        self.assertEqual(d["max_abs_diff"], 2.0)


if __name__ == "__main__":
    unittest.main()
