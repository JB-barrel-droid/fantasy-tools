"""JEG-555: Razzball per-game rates far below ESPN/CBS are held, not priced.

On the 2026-10-10 snapshot Razzball published 7.1 ppg for Lamar Jackson (health
"O", snaps/game 15 vs 61 a day earlier) and 10.5 for Mahomes (snaps/game 45)
against ESPN 21.39/20.05 and CBS ROS 23.03/20.75. That is Razzball's own
expected-missed-games discount, not a parse or match error, and it priced both
QB1s at about 0 on the Razzball line. The bake now holds such a rate.
"""
import inspect
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "pipelines"))

import bake_players  # noqa: E402


def flat(v):
    return {"standard": v, "half_ppr": v, "ppr": v}


class RazzballOutlierGuard(unittest.TestCase):
    def test_lamar_and_mahomes_are_held(self):
        for rz, espn, cbs in ((7.1, 21.39, 23.025), (10.5, 20.054615, 20.746)):
            reason = bake_players.razzball_outlier_reason(flat(rz), flat(espn), flat(cbs))
            self.assertIsNotNone(reason, rz)
            self.assertIn("missed-games", reason)

    def test_healthy_spread_is_kept(self):
        self.assertIsNone(bake_players.razzball_outlier_reason(flat(21.5), flat(23), flat(22)))
        self.assertIsNone(bake_players.razzball_outlier_reason(flat(13.0), flat(20), flat(20)))

    def test_boundary_is_60_percent(self):
        self.assertIsNone(bake_players.razzball_outlier_reason(flat(12.0), flat(20), flat(20)))
        self.assertIsNotNone(bake_players.razzball_outlier_reason(flat(11.9), flat(20), flat(20)))

    def test_one_reference_is_enough_none_is_not(self):
        self.assertIsNotNone(bake_players.razzball_outlier_reason(flat(5), flat(20), None))
        self.assertIsNotNone(bake_players.razzball_outlier_reason(flat(5), None, flat(20)))
        self.assertIsNone(bake_players.razzball_outlier_reason(flat(5), None, None))

    def test_low_reference_players_are_not_judged(self):
        self.assertIsNone(bake_players.razzball_outlier_reason(flat(0.1), flat(2.5), flat(2.0)))

    def test_one_scoring_is_enough(self):
        rz = {"standard": 20.0, "half_ppr": 20.0, "ppr": 5.0}
        self.assertIsNotNone(bake_players.razzball_outlier_reason(rz, flat(20), flat(20)))

    def test_bake_holds_instead_of_pricing(self):
        src = inspect.getsource(bake_players.bake)
        self.assertIn("razzball_outlier_reason(", src)
        self.assertIn('row["rz_held"]', src)
        self.assertIn('row["rz_complete"] = False', src)


if __name__ == "__main__":
    unittest.main()
