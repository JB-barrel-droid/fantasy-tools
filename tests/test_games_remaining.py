"""GAP-GAMES-REMAINING-STALE: per-game rates divide ESPN's rest-of-season
points by the games each team plays inside ESPN's own ROS window.

Before 2026-10-08 the players bake counted games whose Supabase
public.games.status was not 'final'. Nothing kept that column current: on
2026-10-07 only weeks 1-2 were final (LA-NYG week 2 not even that), so most
teams got 15 games and LA/NYG 16 while ESPN's ROS covered weeks 5-18 = 13
games for every team. The baked ESPN DDF leg divided by a flat 16. Both are
replaced by pipelines/lib/games_remaining.py (window from the CSV's
weeks_covered, byes from data/inputs/nfl_byes_2026.json).

Discrimination (verified 2026-10-08, see docs/claude-log/2026-10-08-games-remaining.md):
- Restoring the status-count logic in bake_players.team_games_remaining
  turns test_stale_statuses_do_not_change_games and
  test_window_after_bye_week red (15/16 and 17 instead of 13 and 11).
- Restoring the flat /16 in build_ddf_two_tier_leg.load_espn_lists turns
  test_bye_week_counts_in_leg red, and on the committed data
  test_players_json_matches_leg_per_game red.
- The origin/main players.json (ROS/15, LA/NYG ROS/16) fails
  test_players_json_matches_leg_per_game and test_players_json_games_match_window.
"""
import csv
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import games_remaining as gr  # noqa: E402
import bake_players  # noqa: E402
from build_ddf_two_tier_leg import (  # noqa: E402
    DEFAULT_CSV, DEFAULT_FIXTURE, POSITIONS, load_espn_lists, resolve_identities,
)

BYES, SEASON_WEEKS = gr.load_byes()
PLAYERS_JSON = ROOT / "data" / "fixtures" / "current" / "players.json"

HEADER = ("player,player_norm,pos,team,has_espn_projection,eligible,"
          "r_pass_yds,r_pass_tds,r_rush_yds,r_rush_tds,r_receptions,"
          "r_rec_yds,r_rec_tds,ros_half_ppr,weeks_covered,"
          "season_block_half_ppr,espn_snapshot_date")


def schedule_from_byes(byes, status_final_through=0):
    """A full 18-week schedule consistent with the bye table, as Supabase
    rows, with games through `status_final_through` marked final and the
    rest 'scheduled' (the stale state the old bake counted)."""
    team_ids = {t: f"id-{t}" for t in byes}
    rows = []
    for week in range(SEASON_WEEKS[0], SEASON_WEEKS[1] + 1):
        playing = sorted(t for t, b in byes.items() if b != week)
        assert len(playing) % 2 == 0
        for home, away in zip(playing[0::2], playing[1::2]):
            rows.append({"week": week, "home_team_id": team_ids[home],
                         "away_team_id": team_ids[away],
                         "status": "final" if week <= status_final_through else "scheduled"})
    return rows, {v: k for k, v in team_ids.items()}


def write_csv(rows, window):
    path = Path(tempfile.mkdtemp()) / "espn.csv"
    lines = [HEADER] + [
        f"{name},{name.lower()},RB,{team},True,True,0,0,0,0,{rec},0,0,{ros},{window},0.00,2026-10-07"
        for name, team, ros, rec in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


class GamesInWindowTest(unittest.TestCase):
    def test_bye_still_ahead_is_excluded(self):
        # BUF bye week 7: weeks 5-18 is 14 weeks, 13 games.
        self.assertEqual(BYES["BUF"], 7)
        self.assertEqual(gr.games_in_window("BUF", (5, 18), BYES), 13)

    def test_bye_already_taken_is_not_subtracted(self):
        # Window 9-18 (week 8 played): BUF's week-7 bye is behind it, so
        # all 10 weeks are games; PIT's week-9 bye is inside (9 games).
        self.assertEqual(gr.games_in_window("BUF", (9, 18), BYES), 10)
        self.assertEqual(BYES["PIT"], 9)
        self.assertEqual(gr.games_in_window("PIT", (9, 18), BYES), 9)

    def test_window_after_week5_splits_teams(self):
        # Week 6 window: CAR/KC had their bye in week 5 -> 13 games left;
        # everyone else still has a bye ahead -> 12.
        counts = gr.games_by_team((6, 18), BYES)
        self.assertEqual({t for t, n in counts.items() if n == 13}, {"CAR", "KC"})
        self.assertEqual({n for t, n in counts.items() if t not in ("CAR", "KC")}, {12})

    def test_source_spellings_and_unknown_team(self):
        self.assertEqual(gr.games_in_window("LAR", (5, 18), BYES), 13)
        self.assertEqual(gr.games_in_window("WSH", (5, 18), BYES), 13)
        self.assertIsNone(gr.games_in_window("XXX", (5, 18), BYES))

    def test_window_must_be_single_and_parseable(self):
        with self.assertRaises(SystemExit):
            gr.window_from_rows([{"weeks_covered": "5-18"}, {"weeks_covered": "6-18"}])
        with self.assertRaises(SystemExit):
            gr.window_from_rows([{"weeks_covered": ""}])
        with self.assertRaises(SystemExit):
            gr.parse_window("0-18")
        self.assertEqual(gr.window_from_rows([{"weeks_covered": "5-18"}]), (5, 18))


class BakeGamesRemainingTest(unittest.TestCase):
    def test_stale_statuses_do_not_change_games(self):
        """The 2026-10-07 state: only weeks 1-2 final. ESPN covers 5-18."""
        rows, team_abbr = schedule_from_byes(BYES, status_final_through=2)
        csv_path = write_csv([("A Back", "BUF", 130.0, 0.0)], "5-18")
        games, window = bake_players.team_games_remaining(rows, team_abbr, csv_path)
        self.assertEqual(window, (5, 18))
        self.assertEqual(set(games.values()), {13})
        self.assertEqual(len(games), 32)

    def test_window_after_bye_week(self):
        rows, team_abbr = schedule_from_byes(BYES, status_final_through=0)
        csv_path = write_csv([("A Back", "CAR", 130.0, 0.0)], "8-18")
        games, _ = bake_players.team_games_remaining(rows, team_abbr, csv_path)
        self.assertEqual(games["CAR"], 11)   # bye 5, behind the window
        self.assertEqual(games["BUF"], 11)   # bye 7, behind the window
        self.assertEqual(games["HOU"], 10)   # bye 8, inside the window
        self.assertEqual(games["ARI"], 10)   # bye 14, ahead

    def test_schedule_disagreeing_with_bye_table_fails_closed(self):
        byes = dict(BYES)
        byes["BUF"], byes["KC"] = 5, 7   # swapped vs the real table
        rows, team_abbr = schedule_from_byes(byes)
        csv_path = write_csv([("A Back", "BUF", 130.0, 0.0)], "5-18")
        with self.assertRaises(SystemExit):
            bake_players.team_games_remaining(rows, team_abbr, csv_path)


class LegPerGameTest(unittest.TestCase):
    def test_bye_week_counts_in_leg(self):
        csv_path = write_csv([("Bye Ahead", "BUF", 120.0, 0.0),
                              ("Bye Behind", "CAR", 120.0, 0.0)], "6-18")
        lists, meta, _ = load_espn_lists(csv_path, "half_ppr")
        x = {d["name"]: d["x"] for d in lists["RB"]}
        self.assertAlmostEqual(x["Bye Ahead"], 120.0 / 12)   # BUF bye 7 inside 6-18
        self.assertAlmostEqual(x["Bye Behind"], 120.0 / 13)  # CAR bye 5 behind
        self.assertEqual(meta["ros_weeks"], "6-18")


class CommittedDataParityTest(unittest.TestCase):
    """players.json (the browser's live ESPN pool) and the baked ESPN leg
    divide the same committed CSV by the same per-team games."""

    @classmethod
    def setUpClass(cls):
        cls.players = json.loads(PLAYERS_JSON.read_text(encoding="utf-8"))["players"]
        with DEFAULT_CSV.open(newline="", encoding="utf-8") as f:
            cls.window = gr.window_from_rows(list(csv.DictReader(f)))

    def test_players_json_games_match_window(self):
        bad = []
        for p in self.players:
            if p["pos"] not in POSITIONS or not p.get("team"):
                continue
            want = gr.games_in_window(p["team"], self.window, BYES)
            if p.get("games_remaining") != want:
                bad.append((p["name"], p["team"], p.get("games_remaining"), want))
        self.assertEqual(bad[:5], [], f"{len(bad)} players with stale games_remaining")

    def test_players_json_matches_leg_per_game(self):
        lists, _, _ = load_espn_lists(DEFAULT_CSV, "ppr")
        resolved, _, _ = resolve_identities(lists, DEFAULT_FIXTURE)
        leg = {d["player_key"]: d["x"] for pos in POSITIONS for d in resolved[pos]}
        checked, bad = 0, []
        for p in self.players:
            ppg = (p.get("espn_ppg") or {}).get("ppr")
            if p["player_key"] not in leg or ppg is None:
                continue
            checked += 1
            if abs(round(leg[p["player_key"]], 2) - ppg) > 0.0051:
                bad.append((p["name"], ppg, round(leg[p["player_key"]], 2)))
        self.assertGreater(checked, 300)
        self.assertEqual(bad[:5], [], f"{len(bad)} players: players.json espn_ppg != leg per-game")


if __name__ == "__main__":
    unittest.main()
