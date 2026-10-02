"""Deep pool tails must not inflate the pie, reprice retained players, or drop anyone.

JEG-67 (reverts JEG-52/JEG-60 pool cap): the 3x-starters pool cap was proven a
value no-op on real snapshots (2026-10-02 discrimination: capping changed zero
of 252 shared Razzball values, calibration byte-identical in all 4 positions,
while dropping 217 players from leg outputs). The invariant below is what the
cap was *supposed* to guarantee -- it holds by construction, because the DDF
surplus sums only players above the waiver line and the waiver line is set by
the fixed roster shape (starters + bench mix), never by pool depth. Tail
players below the line price to exactly 0.0 and are retained in outputs.
"""

import copy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
import build_ddf_two_tier_leg as builder


def projection_pool(teams, tail=0):
    pools = {}
    for index, pos in enumerate(builder.POSITIONS):
        cap = builder.REF_SLOTS[pos] * teams * 3
        pools[pos] = [
            {
                "player_key": index * 1000 + rank + 1,
                "id": f"{pos.lower()}-{rank}",
                "name": f"{pos} Player {rank}",
                "team": "TEST",
                "x": 40.0 - rank * 0.2 if rank < cap else 0.01,
            }
            for rank in range(cap + tail)
        ]
    return pools


def build_with_pool(pools, scoring, teams):
    meta = {"espn_snapshot_date": "2026-10-01", "csv_rows": sum(map(len, pools.values()))}
    with patch.object(builder, "load_espn_lists", return_value=({}, meta, [])), \
         patch.object(builder, "load_pies", return_value=({pos: 1.0 for pos in builder.POSITIONS}, {})), \
         patch.object(builder, "resolve_identities", return_value=(copy.deepcopy(pools), [], [])), \
         patch.object(builder, "sha256_file", return_value="test-hash"):
        return builder.build_leg(Path("input.csv"), Path("pies.json"), Path("fixture.json"),
                                 scoring, teams, builder.DEFAULT_BENCH_SHARE)


class PoolDepthInvarianceTest(unittest.TestCase):
    def test_deep_tail_is_value_neutral_and_nobody_is_dropped(self):
        """A 100-deep tail per position must not move calibration, reprice
        anyone, or drop anyone: tail players are retained at exactly 0.0."""
        for scoring in ("standard", "half_ppr", "ppr"):
            for teams in (8, 10, 12, 14):
                with self.subTest(scoring=scoring, teams=teams):
                    pools = projection_pool(teams, tail=100)
                    base = build_with_pool(projection_pool(teams), scoring, teams)
                    deep = build_with_pool(pools, scoring, teams)

                    # Calibration is identical with and without the tail (compare the
                    # value-determining keys; n_pool/n_starters/n_bench are
                    # pool-size diagnostics and legitimately differ).
                    cal_keys = ("rw", "rs", "tau", "pie", "pb", "ps",
                                "bench_share_used",
                                "bench_raw", "starter_raw")
                    for pos in builder.POSITIONS:
                        for key in cal_keys:
                            self.assertEqual(deep["calibration"][pos][key],
                                             base["calibration"][pos][key],
                                             f"{pos}.{key}")
                    self.assertEqual(deep["scale_70_over_max"], base["scale_70_over_max"])

                    # Every retained player's value is unchanged...
                    base_vals = {v["player_key"]: v["value"] for v in base["values"]}
                    deep_vals = {v["player_key"]: v["value"] for v in deep["values"]}
                    for key, value in base_vals.items():
                        self.assertIn(key, deep_vals)
                        self.assertEqual(deep_vals[key], value)

                    # ...and every tail player is present, priced at exactly 0.0.
                    for pos in builder.POSITIONS:
                        cap = builder.REF_SLOTS[pos] * teams * 3
                        for rank in range(cap, cap + 100):
                            key = pools[pos][rank]["player_key"]
                            self.assertIn(key, deep_vals)
                            self.assertEqual(deep_vals[key], 0.0)

                    # No pool_cap review rows: the cap is gone.
                    self.assertFalse(any(r["reason"] == "pool_cap"
                                         for r in deep["review_rows"]))

    def test_results_are_independent_of_input_order(self):
        pools = projection_pool(12, tail=2)
        forward = build_with_pool(pools, "ppr", 12)
        reverse = build_with_pool({pos: list(reversed(rows)) for pos, rows in pools.items()}, "ppr", 12)
        self.assertEqual(forward["values"], reverse["values"])
        self.assertEqual(forward["calibration"], reverse["calibration"])


if __name__ == "__main__":
    unittest.main()
