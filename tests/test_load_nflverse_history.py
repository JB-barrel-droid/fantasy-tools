"""The nflverse history loader builds clean rows from the repo files and
verifies what it stored (JEG-532, from JEG-525 item e)."""
import contextlib
import io
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "pipelines"))
import load_nflverse_history as L  # noqa: E402


class LoadNflverseHistory(unittest.TestCase):
    def test_rows_match_the_repo_files_and_pass_the_checks(self):
        actuals, weeks = L.actual_rows(), L.team_week_rows()
        self.assertEqual(len(actuals), 61977)
        self.assertEqual(len({(r["season"], r["team"]) for r in weeks}), 352)
        self.assertEqual(L.check(actuals, weeks), [])

    def test_check_catches_a_duplicate_and_an_orphan_week(self):
        weeks = [{"season": 2020, "week": 1, "team": "BUF"}]
        row = {"season": 2020, "week": 1, "gsis_id": "00-1", "player_name": "x", "position": "RB",
               "team": "BUF", "actual_std": 1.0, "actual_half": 1.0, "actual_ppr": 1.0}
        self.assertTrue(any("duplicate" in p for p in L.check([row, dict(row)], weeks)))
        self.assertTrue(any("did not play" in p for p in L.check([{**row, "week": 2}], weeks)))

    def test_verify_flags_missing_and_extra_keys(self):
        actuals = [{"season": 2020, "week": 1, "gsis_id": "00-1"},
                   {"season": 2020, "week": 2, "gsis_id": "00-1"}]
        weeks = [{"season": 2020, "week": 1, "team": "BUF"}]
        self.assertEqual(L.verify(actuals, weeks, actuals, weeks), [])
        self.assertEqual(L.verify(actuals, weeks, actuals[:1], weeks), ["1 player-weeks missing"])
        extra = L.verify(actuals, weeks, actuals, weeks + [{"season": 2020, "week": 2, "team": "BUF"}])
        self.assertEqual(extra, ["1 team-weeks stored but not in the file"])

    def test_dry_run_writes_nothing(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(L.main([]), 0)
        self.assertIn("dry run", out.getvalue())


if __name__ == "__main__":
    unittest.main()
