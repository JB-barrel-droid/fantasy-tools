"""JEG-521 G6: pipelines/score_lineup_values.py scores value sets against realized
lineup points. Report only, never a gate. Pins the simulation pieces on
hand-built inputs and checks the committed weeks run end to end.
"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO))

import derive_lineup_parameters as dl  # noqa: E402
import expected_starts_model as es  # noqa: E402
import score_lineup_values as sl  # noqa: E402


class Spearman(unittest.TestCase):
    def test_perfect_reverse_and_ties(self):
        self.assertAlmostEqual(sl.spearman([1, 2, 3, 4], [10, 20, 30, 40]), 1.0)
        self.assertAlmostEqual(sl.spearman([1, 2, 3, 4], [40, 30, 20, 10]), -1.0)
        self.assertIsNone(sl.spearman([1, 2], [2, 1]))
        # Ties get the average rank: (1, 2.5, 2.5, 4) against (1, 2, 3, 4) is positive but below 1.
        rho = sl.spearman([1, 2, 2, 3], [1, 2, 3, 4])
        self.assertTrue(0.9 < rho < 1.0, rho)


class DraftAndLineup(unittest.TestCase):
    def setUp(self):
        self.pos_of = {}
        self.values = {}
        key = 1
        for pos, n, top in (("QB", 6, 60), ("RB", 12, 50), ("WR", 14, 45), ("TE", 6, 30)):
            for i in range(n):
                self.pos_of[key] = pos
                self.values[key] = top - i
                key += 1

    def test_snake_draft_respects_caps_and_order(self):
        rosters = sl.snake_draft(self.values, self.pos_of, teams=2, caps={"QB": 1, "RB": 3, "WR": 3, "TE": 1},
                                 roster_size=8)
        self.assertEqual(len(rosters), 2)
        for r in rosters:
            self.assertEqual(len(r), 8)
            counts = {}
            for k in r:
                counts[self.pos_of[k]] = counts.get(self.pos_of[k], 0) + 1
            self.assertEqual(counts, {"QB": 1, "RB": 3, "WR": 3, "TE": 1})
        # Team 1 picks first (the best QB, value 60), team 2 picks next (second QB, 59) then first again.
        self.assertEqual(rosters[0][0], 1)
        self.assertEqual(rosters[1][0], 2)
        picked = {k for r in rosters for k in r}
        self.assertEqual(len(picked), 16)

    def test_lineup_fills_dedicated_then_flex_among_available(self):
        roster = [1, 7, 8, 9, 19, 20, 21, 22, 33, 34]  # QB 1; RB 7, 8, 9; WR 19-22; TE 33, 34
        proj = {k: self.values[k] for k in roster}
        available = set(roster) - {7}  # the best RB is out
        starters = sl.lineup(roster, self.pos_of, proj, available)
        self.assertEqual(len(starters), 8)
        self.assertNotIn(7, starters)
        self.assertIn(8, starters)
        self.assertIn(9, starters)
        # Flex: the best remaining of RB/WR/TE among available: WR 22 (value 42) beats TE 34 (29).
        self.assertIn(22, starters)
        self.assertNotIn(34, starters)

    def test_usable_points_count_only_started_weeks(self):
        values = {1: 10.0, 2: 9.0, 3: 8.0, 4: 7.0}
        pos_of = {1: "RB", 2: "RB", 3: "RB", 4: "RB"}
        acts = {1: {1: 20.0, 2: 15.0, 3: 30.0, 4: 1.0}, 2: {1: 5.0, 3: 12.0, 4: 2.0}}  # player 2 out in week 2
        proj = {1: values, 2: values}
        out = sl.usable_points(values, pos_of, teams=1, weekly_actuals=acts, weekly_projection=proj, weeks=[1, 2])
        # One team, RB slots 2 + flex 1: week 1 starts 1, 2, 3; week 2 starts 1, 3, 4 (2 is out).
        self.assertEqual(out[1]["starts"], 2)
        self.assertAlmostEqual(out[1]["usable"], 25.0)
        self.assertEqual(out[2]["starts"], 1)
        self.assertEqual(out[2]["weeks_available"], 1)
        self.assertAlmostEqual(out[3]["usable"], 42.0)
        self.assertEqual(out[4]["starts"], 1)
        self.assertAlmostEqual(out[4]["usable"], 2.0)
        self.assertAlmostEqual(out[4]["total"], 3.0)


class Calibration(unittest.TestCase):
    def test_start_worthy_bins_and_missed_games(self):
        pos_of = {1: "QB", 2: "QB", 3: "QB"}
        team = {1: "AAA", 2: "AAA", 3: "BBB"}
        sched = {"AAA": [1, 2, 3], "BBB": [1, 2, 3]}
        acts = {1: {1: 20.0, 2: 10.0, 3: 15.0}, 2: {1: 22.0, 3: 5.0}, 3: {1: 18.0, 2: 12.0, 3: 9.0}}
        rows = sl.start_worthy_calibration({1: 0.9, 2: 0.5, 3: 0.1}, pos_of, acts, [1, 2, 3], {"QB": 1}, team, sched)
        by = {tuple(r["bin"]): r for r in rows}
        self.assertEqual(by[(0.8, 1.0)]["team_games"], 3)
        self.assertAlmostEqual(by[(0.8, 1.0)]["realized_start_worthy_rate"], 1.0)  # player 1 is QB1 every week
        self.assertEqual(by[(0.4, 0.6)]["team_games"], 3)
        self.assertAlmostEqual(by[(0.4, 0.6)]["realized_start_worthy_rate"], 0.0)
        m = sl.missed_game_calibration({1: 3.0, 2: 2.0, 3: 1.0}, pos_of, {"QB": 2}, acts, [1, 2, 3], team, sched,
                                       {"QB": {"m": 0.1}})
        self.assertEqual(m["QB"]["team_games"], 6)
        self.assertEqual(m["QB"]["missed"], 1)


class Committed(unittest.TestCase):
    def test_runs_on_the_stored_weeks(self):
        params = es.load_params()
        history = {}
        for path in sorted(dl.HISTORY.glob("week-*.json")):
            doc = json.loads(path.read_text(encoding="utf-8"))
            history[int(doc["week"])] = doc
        players = json.loads(dl.PLAYERS.read_text(encoding="utf-8"))["players"]
        doc = sl.run(2026, 12, "ppr", params, history, players, dl.load_actuals(), dl.load_schedule())
        self.assertEqual(doc["schema"], sl.SCHEMA)
        self.assertGreaterEqual(len(doc["valuation_weeks"]), 1)
        first = doc["valuation_weeks"][0]
        self.assertEqual(set(first["value_sets"]),
                         {"expected_starts_A", "vp_slices_OC2A", "plain_value_above_waivers", "mean_projection"})
        rho = first["value_sets"]["expected_starts_A"]["usable"]["ALL"]["spearman"]
        self.assertTrue(-1.0 <= rho <= 1.0)
        self.assertIn("# Value sets", sl.render_report(doc))


if __name__ == "__main__":
    unittest.main()


class ProjectedStarts(unittest.TestCase):
    """MR-23 / G4 b: calibration against projected starts and weekly projection error."""

    def setUp(self):
        # Two RB starters per week; keys 1-4 are RBs on team A, 5 is a QB.
        self.pos_of = {1: "RB", 2: "RB", 3: "RB", 4: "RB", 5: "QB"}
        self.proj = {1: {1: 15.0, 2: 12.0, 3: 11.0, 4: 0.0, 5: 20.0},
                     2: {1: 14.0, 3: 13.0, 2: 9.0, 5: 18.0}}  # 4 not projected in week 2 (out)
        self.starters = {"QB": 1, "RB": 2, "WR": 0, "TE": 0}

    def test_projected_starters_skip_zero_and_missing(self):
        chosen = sl.projected_starters(self.proj, self.pos_of, [1, 2], self.starters)
        self.assertEqual(chosen[1], {1, 2, 5})
        self.assertEqual(chosen[2], {1, 3, 5})

    def test_calibration_counts_team_games_and_projected_starts(self):
        sw = {1: 0.95, 2: 0.5, 3: 0.45, 4: 0.1}
        team = {k: "AAA" for k in sw}
        sched = {"AAA": [1, 2]}
        rows = sl.projected_start_calibration(sw, self.pos_of, self.proj, [1, 2, 3], self.starters, team, sched)
        by = {tuple(r["bin"]): r for r in rows}
        self.assertEqual(by[(0.8, 1.0)]["realized_projected_start_rate"], 1.0)   # key 1: 2 of 2
        self.assertEqual(by[(0.4, 0.6)]["team_games"], 4)                         # keys 2, 3: two games each
        self.assertEqual(by[(0.4, 0.6)]["realized_projected_start_rate"], 0.5)   # 2 wk1, 3 wk2
        self.assertEqual(by[(0.0, 0.2)]["realized_projected_start_rate"], 0.0)   # key 4 never
        self.assertIsNone(by[(0.2, 0.4)]["realized_projected_start_rate"])

    def test_projection_error_only_on_played_and_projected(self):
        acts = {1: {1: 20.0, 2: 10.0, 3: 11.0, 5: 25.0}, 2: {1: 10.0, 3: 13.0}}
        err = sl.projection_error(self.proj, acts, self.pos_of, [1, 2], self.starters)
        rb = err["RB"]
        # all: wk1 1:-5, 2:+2, 3:0; wk2 1:+4, 3:0 (2 has no stat line in wk2)
        self.assertEqual(rb["all"]["n"], 5)
        self.assertAlmostEqual(rb["all"]["mean_error"], 0.2)
        self.assertAlmostEqual(rb["all"]["mean_abs_error"], 2.2)
        # starters: wk1 1, 2; wk2 1, 3
        self.assertEqual(rb["starters"]["n"], 4)
        self.assertAlmostEqual(err["QB"]["all"]["mean_error"], -5.0)

    def test_load_weekly_projections_absent_and_present(self):
        import tempfile
        d, meta = sl.load_weekly_projections(Path("/nonexistent.csv"))
        self.assertEqual((d, meta), ({}, None))
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False) as f:
            f.write("season,week,player_key,pos,team,std,half_ppr,ppr,snapshot_at,pre_kickoff,basis\n"
                    "2026,5,10,RB,DET,10.0,11.0,12.0,2026-10-04T12:00:00+00:00,true,team_week\n"
                    "2026,4,10,RB,DET,9.0,10.0,11.0,2026-10-10T12:00:00+00:00,false,team_week\n"
                    "2025,4,10,RB,DET,1.0,1.0,1.0,2025-10-10T12:00:00+00:00,true,team_week\n")
        d, meta = sl.load_weekly_projections(Path(f.name), "half_ppr")
        self.assertEqual(d, {5: {10: 11.0}, 4: {10: 10.0}})
        self.assertEqual(meta, {"rows": 2, "pre_kickoff_false": 1})
