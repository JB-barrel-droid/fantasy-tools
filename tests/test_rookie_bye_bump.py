"""Synthetic coverage for the rookie bye analysis (JEG-1168)."""
import random
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "tools"))

from rookie_bye_bump import changes, did  # noqa: E402


def actuals(player="player", season=2016, pos="RB", team="A",
            scores=((1, 2), (2, 4), (3, 6), (5, 8), (6, 10), (7, 12))):
    return [
        {"player_key": player, "season": season, "week": week,
         "pos": pos, "team": team, "pts": {"ppr": points}}
        for week, points in scores
    ]


class ChangesTests(unittest.TestCase):
    def setUp(self):
        # Week 8 is the final scheduled week, so last=7 and the bye is 4.
        self.schedule = {2016: {"A": [1, 2, 3, 5, 6, 7, 8]}}

    def test_first_season_is_rookie_and_prior_season_is_veteran(self):
        rows = actuals(player="rookie") + actuals(player="veteran", pos="WR")
        # Prior history comes last deliberately: classification uses season,
        # not input order. No schedule for 2015 is needed.
        rows += actuals(player="veteran", season=2015, pos="WR")
        result = changes(rows, self.schedule)
        self.assertEqual(len(result), 2)
        for row, rookie, pos in zip(result, (True, False), ("RB", "WR")):
            self.assertEqual(row["rookie"], rookie)
            self.assertEqual(row["pos"], pos)
            self.assertEqual(row["season"], 2016)
            self.assertEqual(row["bye"], 4)
            self.assertAlmostEqual(row["pre"], 4)
            self.assertAlmostEqual(row["post"], 10)

    def test_seasons_before_2016_are_skipped(self):
        self.assertEqual(changes(actuals(season=2015), {}), [])

    def test_qb_rows_are_ignored(self):
        self.assertEqual(changes(actuals(pos="QB"), self.schedule), [])

    def test_zero_or_two_byes_are_skipped(self):
        for weeks in ([1, 2, 3, 4, 5, 6, 7, 8], [1, 2, 3, 6, 7, 8]):
            with self.subTest(weeks=weeks):
                self.assertEqual(changes(actuals(), {2016: {"A": weeks}}), [])

    def test_two_pre_bye_games_are_skipped(self):
        rows = actuals(scores=((1, 2), (2, 4), (5, 8), (6, 10), (7, 12)))
        self.assertEqual(changes(rows, self.schedule), [])

    def test_two_post_bye_games_are_skipped(self):
        rows = actuals(scores=((1, 2), (2, 4), (3, 6), (5, 8), (6, 10)))
        self.assertEqual(changes(rows, self.schedule), [])

    def test_games_after_last_do_not_affect_post_mean(self):
        rows = actuals() + actuals(scores=((8, 1000), (9, 2000)))
        result = changes(rows, self.schedule)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["bye"], 4)
        self.assertAlmostEqual(result[0]["pre"], 4)
        self.assertAlmostEqual(result[0]["post"], 10)

    def test_games_after_last_do_not_satisfy_post_minimum(self):
        rows = actuals(scores=((1, 2), (2, 4), (3, 6), (5, 8), (6, 10), (8, 12)))
        self.assertEqual(changes(rows, self.schedule), [])

    def test_last_uses_maximum_scheduled_week_across_teams(self):
        schedule = {2016: {"A": [1, 2, 3, 5, 6, 7], "B": list(range(1, 9))}}
        result = changes(actuals(pos="TE"), schedule)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["pos"], "TE")
        self.assertEqual(result[0]["bye"], 4)
        self.assertAlmostEqual(result[0]["pre"], 4)
        self.assertAlmostEqual(result[0]["post"], 10)

    def test_team_with_most_rows_determines_bye(self):
        # Minority team B appears both first and last and has a different bye.
        rows = actuals(team="B", scores=((1, 2),))
        rows += actuals(scores=((2, 4), (3, 6), (5, 8), (6, 10)))
        rows += actuals(team="B", scores=((7, 12),))
        schedule = {2016: {"A": [1, 2, 3, 5, 6, 7, 8],
                           "B": [1, 2, 3, 4, 6, 7, 8]}}
        result = changes(rows, schedule)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["bye"], 4)
        self.assertAlmostEqual(result[0]["pre"], 4)
        self.assertAlmostEqual(result[0]["post"], 10)


class DidTests(unittest.TestCase):
    def test_hand_computed_estimates_and_seeded_interval(self):
        rows = [
            {"rookie": True, "pre": 2, "post": 6},
            {"rookie": True, "pre": 6, "post": 14},
            {"rookie": False, "pre": 4, "post": 2},
            {"rookie": False, "pre": 8, "post": 10},
            {"rookie": False, "pre": 12, "post": 18},
        ]
        result = did(rows, random.Random(1168), boot=50)
        # Rookie changes: 4, 8 -> 6; veteran changes: -2, 2, 6 -> 2.
        self.assertEqual(result["rookies"], 2)
        self.assertEqual(result["veterans"], 3)
        self.assertAlmostEqual(result["rookie_change"], 6)
        self.assertAlmostEqual(result["veteran_change"], 2)
        self.assertAlmostEqual(result["bump"], 4)
        self.assertAlmostEqual(result["rookie_pre"], 4)
        repeated = did(rows, random.Random(1168), boot=50)
        self.assertEqual(len(result["ci95"]), 2)
        self.assertEqual(result["ci95"], repeated["ci95"])
        self.assertLessEqual(result["ci95"][0], result["ci95"][1])


if __name__ == "__main__":
    unittest.main()
