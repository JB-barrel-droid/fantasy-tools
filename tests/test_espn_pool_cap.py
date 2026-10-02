"""Deep ESPN tails must not inflate the pie or reprice retained players."""

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


class EspnPoolCapTest(unittest.TestCase):
    def test_deep_tail_cannot_inflate_values_across_all_12_configurations(self):
        for scoring in ("standard", "half_ppr", "ppr"):
            for teams in (8, 10, 12, 14):
                with self.subTest(scoring=scoring, teams=teams):
                    base = build_with_pool(projection_pool(teams), scoring, teams)
                    deep = build_with_pool(projection_pool(teams, tail=100), scoring, teams)
                    self.assertEqual(deep["values"], base["values"])
                    self.assertEqual(deep["calibration"], base["calibration"])
                    self.assertEqual(deep["scale_70_over_max"], base["scale_70_over_max"])
                    self.assertEqual(deep["inputs"]["espn_snapshot_date"], "2026-10-01")
                    caps = {row["pos"]: row for row in deep["review_rows"]
                            if row["reason"] == "pool_cap"}
                    self.assertEqual(set(caps), set(builder.POSITIONS))
                    for pos in builder.POSITIONS:
                        cap = builder.REF_SLOTS[pos] * teams * 3
                        self.assertEqual(deep["calibration"][pos]["n_pool"], cap)
                        self.assertEqual(caps[pos]["capped_from"], cap + 100)
                        self.assertEqual(caps[pos]["capped_to"], cap)
                    self.assertFalse(any(row["reason"] == "pool_cap" for row in base["review_rows"]))

    def test_ties_at_cutoff_are_independent_of_input_order(self):
        pools = projection_pool(12, tail=2)
        for pos in builder.POSITIONS:
            cap = builder.REF_SLOTS[pos] * 12 * 3
            cutoff = pools[pos][cap - 1]["x"]
            for row in pools[pos][cap - 1:]:
                row["x"] = cutoff
        forward = build_with_pool(pools, "ppr", 12)
        reverse = build_with_pool({pos: list(reversed(rows)) for pos, rows in pools.items()}, "ppr", 12)
        self.assertEqual(forward["values"], reverse["values"])
        retained = {row["player_key"] for row in forward["values"]}
        for pos in builder.POSITIONS:
            cap = builder.REF_SLOTS[pos] * 12 * 3
            self.assertIn(pools[pos][cap - 1]["player_key"], retained)
            self.assertNotIn(pools[pos][cap]["player_key"], retained)


if __name__ == "__main__":
    unittest.main()
