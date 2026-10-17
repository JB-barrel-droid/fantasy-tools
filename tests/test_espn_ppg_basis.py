"""JEG-702 Q3: ESPN's per-game rate is per TEAM game again; the JEG-555
Razzball hold still compares against ESPN per game PLAYED.

Jeremy, 2026-10-16: "Undo the per-game change (JEG-535) for ESPN." Follow-up,
same day: "Undo ESPN only; hold keeps comparing per game played
(Recommended)".

- The bake publishes espn_ppg / blend_ppg = ROS / games_remaining (the team's
  games inside ESPN's ROS window, bye excluded), never ROS /
  espn_expected_games. A 1-game backup no longer shows a starter's rate.
- The ESPN DDF leg divides by the same team games, so the chart's ESPN pool
  and players.json agree.
- The Razzball hold reads ESPN per game played, so Razzball's held set (and
  therefore its published values) does not move with the ESPN undo.

Fails without the change: on the JEG-535 code the part-timer's espn_ppg is
ROS / 1 and the leg's x is ROS / 1 (the first two tests); and if the hold were
switched to the published per-team-game rate, the part-timer's Razzball rate
would be priced instead of held (the third test).
"""
import csv
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))
sys.path.insert(0, str(ROOT / "tests"))

import bake_players  # noqa: E402
from build_ddf_two_tier_leg import load_espn_lists  # noqa: E402
import test_bake_today_unboundlocal as harness  # noqa: E402

ESPN_COLS = ["player", "pos", "team", "eligible", "espn_snapshot_date",
             "r_pass_yds", "r_pass_tds", "r_rush_yds", "r_rush_tds",
             "r_receptions", "r_rec_yds", "r_rec_tds", "weeks_covered",
             "ros_half_ppr", "espn_projected_games", "has_espn_projection"]


def _write_espn_csv(path, today):
    # Test Player: a backup ESPN projects for ONE game (300 yds, 2 TD = 20
    # points). Other Player: a full-time RB (ESPN projects every team game).
    rows = [
        {"player": "Test Player", "pos": "QB", "team": "BUF", "eligible": "True",
         "espn_snapshot_date": today, "r_pass_yds": "300.0", "r_pass_tds": "2.0",
         "r_receptions": "0.0",
         "weeks_covered": "5-18", "ros_half_ppr": "20.00",
         "espn_projected_games": "1", "has_espn_projection": "True"},
        {"player": "Other Player", "pos": "RB", "team": "LA", "eligible": "True",
         "espn_snapshot_date": today, "r_rush_yds": "800.0", "r_rush_tds": "6.0",
         "r_receptions": "20.0", "r_rec_yds": "150.0", "r_rec_tds": "1.0",
         "weeks_covered": "5-18", "ros_half_ppr": "167.00",
         "espn_projected_games": "13", "has_espn_projection": "True"},
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=ESPN_COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in ESPN_COLS})


def _write_razzball_csv(path):
    # Razzball prices the backup at 5 ppg: 25% of ESPN per game played (20),
    # far above ESPN per team game (20/13 = 1.5, below the hold's 3.0 floor).
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["player", "pos", "team", "rz_std_ppg", "rz_half_ppr_ppg", "rz_ppr_ppg"])
        w.writerow(["Test Player", "QB", "BUF", "5.0", "5.0", "5.0"])


class EspnPerTeamGameBake(harness.BakeTodayUnboundLocalTest):
    """Reuses the hermetic bake harness (no Supabase, stubbed schedule)."""

    def _bake_rows(self):
        args = harness._args(self.tmpdir)
        today = harness._real_date.today().isoformat()
        _write_espn_csv(args.espn_csv, today)
        _write_razzball_csv(args.razzball_csv)
        with harness.patch.object(bake_players, "load_registry",
                                  return_value=harness._test_registry()), \
             harness.patch.object(bake_players, "query_all",
                                  side_effect=harness._fake_query_all), \
             harness.patch.object(bake_players, "load_preseason_ecr_ranks",
                                  return_value=({}, {"resolved": 0, "unmatched": 0})), \
             harness.patch.object(bake_players, "annotate_rows", lambda players, ranks: None), \
             harness.patch.object(bake_players, "build_dataset_status",
                                  side_effect=harness._stub_dataset_status):
            bake_players.bake(args)
        payload = harness.json.loads(
            (bake_players.FIXTURE_DIR / "players.json").read_text(encoding="utf-8"))
        return {p["name"]: p for p in payload["players"]}

    def test_espn_ppg_is_per_team_game(self):
        rows = self._bake_rows()
        qb = rows["Test Player"]
        gr = qb["games_remaining"]
        self.assertEqual(gr, 13)                       # BUF: weeks 5-18, bye 7
        self.assertEqual(qb["espn_expected_games"], 1)  # recorded, not the divisor
        for s in ("standard", "half_ppr", "ppr"):
            want = round(qb["espn_ros"][s] / gr, bake_players.PPG_DECIMALS)
            self.assertEqual(qb["espn_ppg"][s], want, s)
            self.assertEqual(qb["blend_ppg"][s],
                             round(qb["blend_ros"][s] / gr, bake_players.PPG_DECIMALS), s)
        self.assertLess(qb["espn_ppg"]["ppr"], 2.0)    # not ROS / 1 = 20

    def test_razzball_hold_still_reads_espn_per_game_played(self):
        qb = self._bake_rows()["Test Player"]
        self.assertIn("rz_held", qb, "held against ESPN per game played (20 ppg)")
        self.assertNotIn("rz_ppg", qb)
        self.assertFalse(qb["rz_complete"])

    # The setUp/tearDown of the harness class are reused; its own tests are
    # not re-run here.
    test_prior_snapshot_selected_with_existing_snapshot = None
    test_prior_scan_skips_snapshots_dated_today_or_later = None
    test_prior_scan_picks_max_dated_snapshot = None
    test_bake_writes_players_json = None
    test_zero_espn_intake_fails_closed = None


class EspnPerTeamGameLeg(unittest.TestCase):
    def test_leg_divides_by_team_games_not_projected_games(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "espn.csv"
            _write_espn_csv(path, "2026-10-15")
            lists, _, _ = load_espn_lists(path, "half_ppr")
        x = {d["name"]: (d["x"], d["games"]) for pos in lists for d in lists[pos]}
        self.assertEqual(x["Test Player"], (20.0 / 13, 13))
        self.assertEqual(x["Other Player"], (167.0 / 13, 13))  # LA bye 11 inside 5-18


if __name__ == "__main__":
    unittest.main()
