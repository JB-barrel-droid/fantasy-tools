"""JEG-521 G4: the ESPN weekly store, the repo export and the status history.

Pins, on hand-built inputs:
  - espn_weekly.weekly_rows keeps 2026 split-1 blocks of the asked source only,
    first block per (player, week), the block's own team, skips empty actuals
    and position-slot mismatches, maps WSH/LAR to the teams-table spelling;
  - stored points use public.v_player_game_actuals' formula (interceptions -2),
    and the export reproduces the view's rounded values on 16 real rows and
    the exact text of the 2026-10-09 ES-A export;
  - player ids resolve by sleeper id, gsis id and ESPN id before any name, and
    an ambiguous id or a position clash is refused;
  - the actuals plan inserts new games, updates ESPN's own rows, never touches
    another writer's row (compares it instead) and reports what did not resolve;
  - the projections plan is change-only;
  - the projections export takes the last snapshot before kickoff, else the
    earliest one flagged pre_kickoff=false;
  - the status history keeps team or injured QB/RB/WR/TE and nobody else;
  - the pull writes both weekly files.
"""
import csv
import json
import sys
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import espn_weekly as ew  # noqa: E402
import export_weekly_store as ex  # noqa: E402
import save_espn_weekly as sv  # noqa: E402
import save_player_status_history as sh  # noqa: E402
from player_key_index import PlayerIndex  # noqa: E402

SAMPLE = json.loads((ROOT / "tests/fixtures/v_player_game_actuals_sample.json").read_text())["rows"]
TEAM_MAP = {8: "DET", 28: "WSH", 14: "LAR", 9: "GB"}


def block(week, source, stats, season=2026, split=1, team=None):
    b = {"seasonId": season, "statSourceId": source, "statSplitTypeId": split,
         "scoringPeriodId": week, "stats": stats}
    if team is not None:
        b["proTeamId"] = team
    return b


def entry(pid, name, pos_id, team, stats):
    return {"id": pid, "player": {"id": pid, "fullName": name, "defaultPositionId": pos_id,
                                  "proTeamId": team, "stats": stats}}


PAYLOAD = {
    "RB": [
        entry(1, "Jahmyr Gibbs", 2, 8, [
            block(1, 0, {"24": 80, "25": 1, "53": 3, "42": 20}),
            block(1, 0, {"24": 999}),                      # duplicate week: first wins
            block(2, 0, {}),                                # empty actual: not a stat line
            block(3, 0, {"24": 50}, season=2025),           # other season
            block(1, 1, {"24": 90}),                        # projection, other source
            block(0, 0, {"24": 1000}, split=0),             # season block
            block(4, 0, {"24": 10}, team=28),               # traded: block's team wins
        ]),
        entry(2, "Not An RB", 3, 9, [block(1, 0, {"42": 50})]),  # slot mismatch
    ],
    "QB": [entry(3, "Matthew Stafford", 1, 14, [block(1, 0, {"3": 250, "4": 2, "20": 1})])],
}

PLAYERS = [
    {"id": "u-gibbs", "player_key": 10, "full_name": "Jahmyr Gibbs", "position": "RB",
     "active": True, "metadata": {"gsis_id": "00-1"}},
    {"id": "u-staff", "player_key": 20, "full_name": "Matthew Stafford", "position": "QB",
     "active": True, "metadata": {"sleeper_id": "s20"}},
    {"id": "u-allen-qb", "player_key": 30, "full_name": "Josh Allen", "position": "QB",
     "active": True, "metadata": {"gsis_id": "00-3"}},
    {"id": "u-namesake", "player_key": 40, "full_name": "Sam Twin", "position": "WR",
     "active": True, "metadata": {"gsis_id": "00-4"}},
    {"id": "u-namesake2", "player_key": 41, "full_name": "Sam Twin", "position": "WR",
     "active": True, "metadata": {"gsis_id": "00-4"}},
    {"id": "u-name", "player_key": 50, "full_name": "Only By Name", "position": "TE",
     "active": True, "metadata": {}},
]
BASE = {"by_sleeper_id": {
    "s10": {"name": "Jahmyr Gibbs", "pos": "RB", "gsis_id": "00-1", "espn_id": "1"},
    "s20": {"name": "Matthew Stafford", "pos": "QB", "espn_id": "3"},
    "s30": {"name": "Josh Allen", "pos": "QB", "gsis_id": "00-3", "espn_id": "3918298"},
    "s40": {"name": "Sam Twin", "pos": "WR", "gsis_id": "00-4", "espn_id": "4"},
}}


class WeeklyRowsTest(unittest.TestCase):
    def test_actual_rows(self):
        rows, notes = ew.weekly_rows(PAYLOAD, ew.ACTUAL, TEAM_MAP)
        got = {(r["espn_id"], r["week"]): r for r in rows}
        self.assertEqual(set(got), {("1", 1), ("1", 4), ("3", 1)})
        self.assertEqual(got[("1", 1)]["stats"]["rushing_yards"], 80)   # first block kept
        self.assertTrue(any("dup-block" in n for n in notes))
        self.assertEqual(got[("1", 4)]["team"], "WAS")                  # block team, WSH alias
        self.assertEqual(got[("1", 1)]["team"], "DET")
        self.assertEqual(got[("3", 1)]["team"], "LA")                   # LAR -> LA
        self.assertEqual(got[("3", 1)]["stats"]["interceptions"], 1)

    def test_projection_rows_use_source_one(self):
        rows, _ = ew.weekly_rows(PAYLOAD, ew.PROJECTION, TEAM_MAP)
        self.assertEqual([(r["espn_id"], r["week"], r["stats"]["rushing_yards"]) for r in rows],
                         [("1", 1, 90)])

    def test_points_match_the_view(self):
        for r in SAMPLE:
            for fmt, col in (("standard", "std"), ("half_ppr", "half"), ("full_ppr", "ppr")):
                self.assertAlmostEqual(ew.points(r["stats"], fmt), float(r[col]), places=6,
                                       msg=(r["player_key"], fmt))


class ExportFormatTest(unittest.TestCase):
    def test_view_points_and_text_match_the_es_a_export(self):
        csv_rows = {(int(x["season"]), int(x["week"]), int(x["player_key"])): x
                    for x in csv.DictReader((ROOT / "data/inputs/weekly_actuals_2024_2026.csv").read_text().splitlines())}
        for r in SAMPLE:
            std, half, ppr = ex.view_points(r["stats"])
            self.assertEqual((std.quantize(Decimal("0.01")), half.quantize(Decimal("0.01")),
                              ppr.quantize(Decimal("0.01"))),
                             (Decimal(r["std"]), Decimal(r["half"]), Decimal(r["ppr"])))
            line = csv_rows[(r["season"], r["week"], r["player_key"])]
            self.assertEqual([ex.fmt(std), ex.fmt(half), ex.fmt(ppr)],
                             [line["std"], line["half_ppr"], line["ppr"]], msg=r["player_key"])

    def test_actual_rows_sorted_and_skill_positions_only(self):
        pgs = [
            {"stats": {"rushing_yards": 15}, "game": {"season": 2026, "week": 2},
             "player": {"player_key": 9, "position": "RB"}, "team": {"abbreviation": "DET"}},
            {"stats": {"passing_yards": 100}, "game": {"season": 2026, "week": 1},
             "player": {"player_key": 30, "position": "QB"}, "team": {"abbreviation": "BUF"}},
            {"stats": {"sacks": 2}, "game": {"season": 2026, "week": 1},
             "player": {"player_key": 5, "position": "LB"}, "team": {"abbreviation": "BUF"}},
        ]
        self.assertEqual(ex.actual_rows(pgs), [[2026, 1, 30, "QB", "BUF", "4.0", "4.0", "4.0"],
                                               [2026, 2, 9, "RB", "DET", "1.5", "1.5", "1.5"]])

    def test_fmt_rounds_half_away_from_zero(self):
        self.assertEqual(ex.fmt(Decimal("2.345")), "2.35")
        self.assertEqual(ex.fmt(Decimal("-0.125")), "-0.13")
        self.assertEqual(ex.fmt(Decimal("4")), "4.0")


class PlayerIndexTest(unittest.TestCase):
    def setUp(self):
        self.ix = PlayerIndex(PLAYERS, BASE)

    def test_sleeper_id_then_gsis(self):
        self.assertEqual(self.ix.resolve_sleeper("s20")[0]["player_key"], 20)
        self.assertEqual(self.ix.resolve_sleeper("s20")[1], "sleeper_id")
        self.assertEqual(self.ix.resolve_sleeper("s10")[0]["player_key"], 10)
        self.assertEqual(self.ix.resolve_sleeper("s10")[1], "gsis_id")

    def test_espn_id_through_sleeper(self):
        e, how = self.ix.resolve_espn("3918298", "Josh Allen", "QB")
        self.assertEqual((e["player_key"], how), (30, "espn_id->gsis_id"))

    def test_ambiguous_id_refused_not_guessed(self):
        e, why = self.ix.resolve_espn("4", "", "WR")
        self.assertIsNone(e)

    def test_position_clash_refused(self):
        e, why = self.ix.resolve_sleeper("s10", "", "WR")
        self.assertIsNone(e)
        self.assertIn("position", why)

    def test_name_is_the_last_resort(self):
        e, how = self.ix.resolve_espn("999", "Only By Name", "TE")
        self.assertEqual((e["player_key"], how), (50, "name"))
        self.assertIsNone(self.ix.resolve_espn("998", "Nobody", "TE")[0])


TEAMS = [{"id": "t-det", "abbreviation": "DET"}, {"id": "t-gb", "abbreviation": "GB"},
         {"id": "t-la", "abbreviation": "LA"}, {"id": "t-sf", "abbreviation": "SF"},
         {"id": "t-was", "abbreviation": "WAS"}, {"id": "t-nyg", "abbreviation": "NYG"}]
GAMES = [{"id": "g1", "week": 1, "home_team_id": "t-det", "away_team_id": "t-gb",
          "starts_at": "2026-09-13T17:00:00+00:00"},
         {"id": "g2", "week": 1, "home_team_id": "t-la", "away_team_id": "t-sf",
          "starts_at": "2026-09-13T20:25:00+00:00"},
         {"id": "g4", "week": 4, "home_team_id": "t-was", "away_team_id": "t-nyg",
          "starts_at": "2026-10-04T17:00:00+00:00"}]


class PlanActualsTest(unittest.TestCase):
    def test_insert_update_compare(self):
        ix = PlayerIndex(PLAYERS, BASE)
        games = sv.game_index(TEAMS, GAMES)
        rows, _ = ew.weekly_rows(PAYLOAD, ew.ACTUAL, TEAM_MAP)
        rows.append({"espn_id": "777", "name": "Ghost Player", "pos": "WR", "team": "DET",
                     "week": 1, "season": 2026, "stats": {}})
        existing = [
            # nflverse row for Stafford week 1: compared, never written
            {"game_id": "g2", "player_id": "u-staff",
             "stats": {"passing_yards": 250, "passing_tds": 2, "interceptions": 1}},
            # ESPN's own earlier row for Gibbs week 4: updated (stat correction)
            {"game_id": "g4", "player_id": "u-gibbs", "stats": {"rushing_yards": 5, "source": "espn"}},
        ]
        ups, rep = sv.plan_actuals(rows, ix, games, existing)
        keyed = {(u["game_id"], u["player_id"]): u for u in ups}
        self.assertEqual(set(keyed), {("g1", "u-gibbs"), ("g4", "u-gibbs")})
        self.assertEqual(keyed[("g1", "u-gibbs")]["team_id"], "t-det")
        self.assertEqual(keyed[("g1", "u-gibbs")]["stats"]["source"], "espn")
        self.assertEqual(keyed[("g1", "u-gibbs")]["fantasy_points"], 16.0)
        self.assertEqual(keyed[("g4", "u-gibbs")]["team_id"], "t-was")
        cmp_ = rep["comparison_with_existing"]["by_position"]["QB"]
        self.assertEqual((cmp_["n"], cmp_["within_0.01"]), (1, 1))
        self.assertEqual(rep["n_unresolved"], 1)
        self.assertEqual(rep["unresolved"][0]["name"], "Ghost Player")


class PlanProjectionsTest(unittest.TestCase):
    def test_change_only(self):
        ix = PlayerIndex(PLAYERS, BASE)
        games = sv.game_index(TEAMS, GAMES)
        rows = [{"espn_id": "1", "name": "Jahmyr Gibbs", "pos": "RB", "team": "DET",
                 "week": 1, "season": 2026, "stats": {"rushing_yards": 100, "receptions": 4}},
                {"espn_id": "1", "name": "Jahmyr Gibbs", "pos": "RB", "team": "DET",
                 "week": 9, "season": 2026, "stats": {"rushing_yards": 100}}]
        latest = {(10, 1, "standard"): 10.0, (10, 1, "half_ppr"): 11.5}
        ins, rep = sv.plan_projections(rows, ix, games, latest, {1}, "2026-10-10T00:00:00+00:00", "b")
        self.assertEqual([(r["week"], r["scoring_format"], r["projected_points"]) for r in ins],
                         [(1, "half_ppr", 12.0), (1, "full_ppr", 14.0)])
        self.assertEqual(rep["unchanged_skipped"], 1)
        self.assertIn("basis=team_week", ins[0]["vintage_note"])
        self.assertEqual(ins[0]["game_id"], "g1")

    def test_bye_week_is_skipped_not_written_without_a_game(self):
        # projection_snapshots.game_id is NOT NULL: a row with no scheduled game
        # (bye, or a team the schedule does not know) fails the whole insert
        # chunk, so it is counted and skipped, never sent with game_id None.
        ix = PlayerIndex(PLAYERS, BASE)
        games = sv.game_index(TEAMS, GAMES)
        rows = [{"espn_id": "1", "name": "Jahmyr Gibbs", "pos": "RB", "team": "DET",
                 "week": 4, "season": 2026, "stats": {}}]
        ins, rep = sv.plan_projections(rows, ix, games, {}, {4}, "2026-10-10T00:00:00+00:00", "b")
        self.assertEqual(ins, [])
        self.assertEqual(rep["no_game_skipped"], 1)

    def test_weeks_are_played_plus_next(self):
        self.assertEqual(sv.projection_weeks([1, 2, 3, 4, 5], [6, 7, 8]), {1, 2, 3, 4, 5, 6})


class ProjectionExportTest(unittest.TestCase):
    def test_last_before_kickoff_else_earliest(self):
        snaps = []
        for fmt, v in (("standard", 10), ("half_ppr", 11), ("full_ppr", 12)):
            snaps += [
                {"player_key": 10, "week": 1, "scoring_format": fmt, "projected_points": v,
                 "snapshot_at": "2026-09-12T12:00:00+00:00", "game_id": "g1"},
                {"player_key": 10, "week": 1, "scoring_format": fmt, "projected_points": v + 1,
                 "snapshot_at": "2026-09-13T16:00:00+00:00", "game_id": "g1"},
                {"player_key": 10, "week": 1, "scoring_format": fmt, "projected_points": v + 5,
                 "snapshot_at": "2026-09-13T18:00:00+00:00", "game_id": "g1"},  # after kickoff
                {"player_key": 20, "week": 1, "scoring_format": fmt, "projected_points": v,
                 "snapshot_at": "2026-10-10T12:00:00+00:00", "game_id": "g2"},
                {"player_key": 20, "week": 1, "scoring_format": fmt, "projected_points": v + 3,
                 "snapshot_at": "2026-10-11T12:00:00+00:00", "game_id": "g2"},
            ]
        kick = {g["id"]: g["starts_at"] for g in GAMES}
        out = ex.projection_rows(snaps, kick, {10: ("RB", "DET"), 20: ("QB", "LA")})
        self.assertEqual(out[0][:8], [2026, 1, 10, "RB", "DET", "11.0", "12.0", "13.0"])
        self.assertEqual(out[0][9], "true")
        self.assertEqual(out[1][5:10], ["10.0", "11.0", "12.0", "2026-10-10T12:00:00+00:00", "false"])
        self.assertEqual(out[1][10], "team_week")


class StatusHistoryTest(unittest.TestCase):
    def test_keeps_rostered_or_injured_skill_players(self):
        ix = PlayerIndex(PLAYERS, BASE)
        sleeper = {
            "s10": {"full_name": "Jahmyr Gibbs", "position": "RB", "team": "DET", "status": "Active",
                    "injury_status": "Questionable", "injury_body_part": "Ankle",
                    "depth_chart_position": "RB", "depth_chart_order": 1,
                    "news_updated": 1760000000000, "injury_start_date": None},
            "s99": {"full_name": "Free Agent Hurt", "position": "WR", "team": None,
                    "injury_status": "IR"},
            "s98": {"full_name": "Free Agent Fine", "position": "WR", "team": None},
            "s97": {"full_name": "A Linebacker", "position": "LB", "team": "DET"},
            "s96": {"full_name": "A Kicker", "position": "K", "team": "DET"},
        }
        rows, how = sh.build_rows(sleeper, ix, "2026-10-09", "2026-10-09T13:10:00+00:00")
        self.assertEqual([r["sleeper_id"] for r in rows], ["s10", "s99"])
        g = rows[0]
        self.assertEqual((g["player_key"], g["injury_status"], g["depth_chart_order"]), (10, "Questionable", 1))
        self.assertEqual(g["news_updated"][:10], "2025-10-09")
        self.assertIsNone(rows[1]["player_key"])   # kept, unresolved
        self.assertEqual(how.get("unresolved"), 1)


class PullWritesWeeklyFilesTest(unittest.TestCase):
    def test_write_weekly_blocks(self):
        import pull_espn_projections as pull
        with tempfile.TemporaryDirectory() as d:
            pull.write_weekly_blocks(Path(d), PAYLOAD, PAYLOAD, TEAM_MAP, [1, 2, 3, 4, 5], [6, 7])
            acts = json.loads((Path(d) / "espn_weekly_actuals.json").read_text())
            projs = json.loads((Path(d) / "espn_weekly_projections.json").read_text())
        self.assertEqual(len(acts["rows"]), 3)
        self.assertEqual(len(projs["rows"]), 1)
        self.assertEqual((acts["basis"], acts["played_weeks"], projs["ros_weeks"]),
                         ("team_week", [1, 2, 3, 4, 5], [6, 7]))


if __name__ == "__main__":
    unittest.main()
