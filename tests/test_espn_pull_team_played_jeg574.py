"""JEG-574: the ESPN pull decides played weeks per team, not per week.

Bug (2026-10-10): the pull marked a week played once ESPN held 20 or more
actual-stat blocks for it. Thursday night alone yields 20-35 skill-player
blocks, so from Thursday night to the Tuesday pull the whole current week
counted as played for all 32 teams: every team's rest-of-season window
started a week late, rest-of-season totals left out ESPN's current-week
projection and games_remaining dropped by one.

Hermetic: no network, no Supabase.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


pull = _load("pull_espn_projections_jeg574", ROOT / "pipelines" / "pull_espn_projections.py")

TEAM_IDS = sorted(pull.TEAM_FALLBACK)           # 32 ESPN team ids
TEAMS = {tid: pull.TEAM_FALLBACK[tid] for tid in TEAM_IDS}
PLAYED_THURSDAY = TEAM_IDS[:2]                  # the Thursday-night game
BYE_WEEK = 9
PER_TEAM = 4                                    # players per team (>= MIN_TEAM_BLOCKS)


def _player(pid, team_id, actual_weeks, proj_weeks):
    stats = []
    for wk in actual_weeks:
        stats.append({"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1,
                      "scoringPeriodId": wk, "stats": {"24": 60.0}})
    for wk in proj_weeks:
        stats.append({"seasonId": 2026, "statSourceId": 1, "statSplitTypeId": 1,
                      "scoringPeriodId": wk, "stats": {"24": 50.0}})
    return {"player": {"fullName": f"Back {pid}", "defaultPositionId": 2,
                       "proTeamId": team_id, "stats": stats}}


def payload(week5_teams, source):
    """Weeks 1-4 played by every team; week 5 played only by `week5_teams`."""
    players = []
    for tid in TEAM_IDS:
        for k in range(PER_TEAM):
            actual = [1, 2, 3, 4] + ([5] if tid in week5_teams else [])
            proj = [w for w in range(1, 19) if w != BYE_WEEK]
            players.append(_player(f"{tid}-{k}", tid,
                                   actual if source == "acts" else [], proj))
    return players


class TeamPlayedWeeksTest(unittest.TestCase):
    def acts(self, week5_teams):
        return {"QB": [], "RB": payload(week5_teams, "acts"), "WR": [], "TE": []}

    def test_only_two_teams_with_week5_actuals_leaves_week5_unplayed_league_wide(self):
        by_team, league = pull.team_played_weeks(self.acts(PLAYED_THURSDAY), TEAMS)
        self.assertEqual([1, 2, 3, 4], league)  # old rule: [1..5] (8 blocks x 2 teams >= 20)
        for tid in PLAYED_THURSDAY:
            self.assertIn(5, by_team[TEAMS[tid]])
        others = [t for t in TEAM_IDS if t not in PLAYED_THURSDAY]
        for tid in others:
            self.assertNotIn(5, by_team[TEAMS[tid]])

    def test_full_slate_is_played_league_wide(self):
        _, league = pull.team_played_weeks(self.acts(TEAM_IDS), TEAMS)
        self.assertEqual([1, 2, 3, 4, 5], league)

    def test_stray_single_block_does_not_mark_a_game_played(self):
        acts = self.acts([])
        acts["RB"][0]["player"]["stats"].append(
            {"seasonId": 2026, "statSourceId": 0, "statSplitTypeId": 1,
             "scoringPeriodId": 5, "stats": {"24": 3.0}})
        by_team, _ = pull.team_played_weeks(acts, TEAMS)
        self.assertNotIn(5, by_team[TEAMS[TEAM_IDS[0]]])

    def test_past_bye_is_out_and_unplayed_game_stays_in(self):
        played = {1, 2, 3, 4, 5, 6, 7, 8, 10}
        wk_pts = {w: 5.0 for w in range(1, 19) if w != 9}
        # league has played through week 10; team had a bye in 9, so 9 is out.
        ros = pull.team_ros_weeks(played, set(range(1, 11)), wk_pts)
        self.assertEqual(list(range(11, 19)), ros)
        # a late game the league has otherwise played stays in (projected > 0).
        ros = pull.team_ros_weeks({1, 2, 3, 4}, {1, 2, 3, 4, 5}, {w: 5.0 for w in range(1, 19)})
        self.assertEqual(list(range(5, 19)), ros)


class PullMainPerTeamWindowTest(unittest.TestCase):
    def run_pull(self, week5_teams):
        acts = {"QB": [], "RB": payload(week5_teams, "acts"), "WR": [], "TE": []}
        proj = {"QB": [], "RB": payload(week5_teams, "proj"), "WR": [], "TE": []}

        def fetch(slot, source):
            pos = dict(pull.SLOTS)[slot]
            return (acts if source == 0 else proj)[pos]

        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "files").mkdir()
            (d / "hidden").mkdir()
            patches = {
                "FILES": d / "files", "HIDDEN": d / "hidden",
                "LOG": d / "hidden" / "runs.log",
                "SEASON_CSV": d / "files" / "season.csv",
                "WEEKLY_CSV": d / "files" / "weekly.csv",
                "META": d / "hidden" / "meta.json",
                "SIDECAR": d / "hidden" / "side.json",
                "WEEKLY_OUT": None, "FORCE": True,
            }
            with mock.patch.multiple(pull, **patches), \
                 mock.patch.object(pull, "fetch_position", fetch), \
                 mock.patch.object(pull, "load_team_map", lambda problems: dict(TEAMS)), \
                 mock.patch.object(pull, "canonical_registry", lambda problems: None), \
                 mock.patch.object(pull, "resolve_identity",
                                   lambda imap, name, pos, problems, registry=None: (name.lower(), name)), \
                 mock.patch.object(pull.time, "sleep", lambda s: None):
                self.assertEqual(0, pull.main())
            side = json.loads((d / "hidden" / "side.json").read_text())
            meta = json.loads((d / "hidden" / "meta.json").read_text())
            csv_text = (d / "files" / "season.csv").read_text()
        return side, meta, csv_text

    def test_thursday_teams_share_the_league_window(self):
        # JEG-624: JEG-574 gave Thursday teams "6-18" and the rest "5-18" in
        # one CSV; the bake (window_from_rows) failed closed on the mix.
        side, meta, _ = self.run_pull(PLAYED_THURSDAY)
        self.assertEqual([1, 2, 3, 4], meta["played_weeks"])
        by_team = {pl["team"]: pl for pl in side["players"].values()}
        for team, pl in by_team.items():
            self.assertEqual(list(range(5, 19)), pl["ros_weeks"], team)
            self.assertEqual(13, pl["games_remaining"], team)  # 14 weeks, one bye
            self.assertEqual(9, pl["bye_week"], team)
            # 50 rush yards x 0.1 = 5 half-PPR points per game week
            self.assertAlmostEqual(5.0 * pl["games_remaining"], pl["ros"]["half_ppr"], places=1)

    def test_csv_carries_a_single_weeks_covered_window(self):
        # JEG-624 guard: the real consumer accepts the pull's CSV.
        import csv
        import io
        import games_remaining as gr
        _, _, csv_text = self.run_pull(PLAYED_THURSDAY)
        rows = list(csv.DictReader(io.StringIO(csv_text)))
        self.assertEqual({"5-18"}, {r["weeks_covered"] for r in rows})
        self.assertEqual((5, 18), gr.window_from_rows(rows))

    def test_guard_fails_on_the_mixed_state(self):
        # Negative test: the pre-fix mix of per-team windows must be rejected.
        import games_remaining as gr
        with self.assertRaises(SystemExit):
            gr.window_from_rows([{"weeks_covered": "5-18"}, {"weeks_covered": "6-18"}])


if __name__ == "__main__":
    unittest.main()
