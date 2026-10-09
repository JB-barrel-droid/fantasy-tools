"""JEG-521 G2/G3: the expected-starts parameters come from data, not assumptions.

pipelines/derive_lineup_parameters.py measures the missed-game hazard from
realized player-games (2024-2026), the bye share from the schedule, and sigma
from the cross-source spread and the week-to-week movement of the per-game
projections. These tests pin the estimators on hand-built inputs and check the
committed data files agree with each other.
"""
from __future__ import annotations

import json
import math
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import derive_lineup_parameters as dl  # noqa: E402


def _row(season, week, key, pos, team, pts):
    return {"season": season, "week": week, "player_key": key, "pos": pos, "team": team,
            "pts": {"standard": pts, "half_ppr": pts, "ppr": pts}}


def _schedule(season=2024, bye=None):
    """Two teams, 17 weeks each, optional {team: bye_week}."""
    bye = bye or {}
    return {season: {t: [w for w in range(1, 18) if w != bye.get(t)] for t in ("AAA", "BBB")}}


TWO_TEAM = {p: {"starters": 2, "bench": 1, "rostered": 3} for p in dl.POSITIONS}


class PoolSizes(unittest.TestCase):
    def test_default_roster_at_12_teams(self):
        s = dl.pool_sizes(12)
        # VP-2.2d: round(12 x 6) = 72 seats by D'Hondt over BENCH_MIX_12 (not the
        # legacy two-tier mix, which scales to 80 at 12 teams).
        self.assertEqual({p: s[p]["bench"] for p in dl.POSITIONS}, {"QB": 9, "RB": 24, "WR": 30, "TE": 9})
        self.assertEqual(s["QB"]["starters"], 12)
        self.assertEqual(s["RB"]["starters"] + s["WR"]["starters"] + s["TE"]["starters"], 12 * (2 + 3 + 1) + 12)
        self.assertEqual(sum(v["rostered"] for v in s.values()), 12 * (8 + 6))


class MissedGameRates(unittest.TestCase):
    def test_exact_rate_and_bye_not_counted(self):
        # Two QBs on AAA (bye week 9) and two on BBB. Selection weeks 1-4;
        # measure weeks 5-8. QB 1 misses weeks 6 and 7 and returns (temporary);
        # QB 2 plays every game; QB 3 misses 7 and 8 and does not return.
        rows = []
        for w in range(1, 9):
            if w not in (6, 7):
                rows.append(_row(2024, w, 1, "QB", "AAA", 20))
            rows.append(_row(2024, w, 2, "QB", "BBB", 18))
            if w < 7:
                rows.append(_row(2024, w, 3, "QB", "AAA", 10))
        sched = _schedule(bye={"AAA": 9})
        r = dl.missed_game_rates(rows, sched, 2024, (1, 4), (5, 8), TWO_TEAM)["QB"]
        self.assertEqual(r["starters"]["games"], 8)
        self.assertEqual(r["starters"]["missed"], 2)
        self.assertAlmostEqual(r["starters"]["rate"], 0.25)
        self.assertEqual(r["starters"]["temporary"], 2)
        self.assertEqual(r["bench"]["season_ending"], 2)
        self.assertAlmostEqual(r["rostered"]["rate"], 4 / 12)

    def test_bye_week_in_measurement_window_is_not_a_missed_game(self):
        rows = [_row(2024, w, 1, "RB", "AAA", 15) for w in range(1, 18) if w != 6]
        rows += [_row(2024, w, 2, "RB", "BBB", 14) for w in range(1, 18)]
        sched = _schedule(bye={"AAA": 6})
        r = dl.missed_game_rates(rows, sched, 2024, (1, 4), (5, 8), TWO_TEAM)["RB"]
        self.assertEqual(r["starters"]["games"], 7)  # AAA plays 3 of weeks 5-8, BBB 4
        self.assertEqual(r["starters"]["missed"], 0)

    def test_healthy_at_valuation_excludes_a_player_out_in_the_last_selection_week(self):
        rows = [_row(2024, w, 1, "WR", "AAA", 15) for w in (1, 2, 3)]  # out in week 4
        rows += [_row(2024, w, 2, "WR", "BBB", 12) for w in range(1, 9)]
        rows += [_row(2024, w, 3, "WR", "BBB", 11) for w in range(1, 9)]
        sched = _schedule()
        healthy = dl.missed_game_rates(rows, sched, 2024, (1, 4), (5, 8), TWO_TEAM)["WR"]
        self.assertEqual(healthy["starters"]["players"], 2)
        self.assertEqual(healthy["starters"]["missed"], 0)
        everyone = dl.missed_game_rates(rows, sched, 2024, (1, 4), (5, 8), TWO_TEAM,
                                        healthy_at_valuation=False)["WR"]
        self.assertEqual(everyone["starters"]["players"], 2)
        self.assertEqual(everyone["starters"]["missed"], 4)  # player 1 ranks first and misses all of 5-8

    def test_pooled_rates_sum_cells_and_give_an_interval(self):
        rows = [_row(2024, w, 1, "TE", "AAA", 9) for w in range(1, 18) if w != 12]
        rows += [_row(2024, w, 2, "TE", "BBB", 8) for w in range(1, 18)]
        pooled = dl.pooled_rates(rows, _schedule(), TWO_TEAM, seasons=(2024,), windows=((1, 5), (1, 9)))
        st = pooled["pooled"]["TE"]["starters"]
        self.assertEqual(st["games"], 2 * 12 + 2 * 8)
        self.assertEqual(st["missed"], 2)
        self.assertAlmostEqual(st["rate"], 2 / 40)
        self.assertLess(st["ci95"][0], st["rate"])
        self.assertGreater(st["ci95"][1], st["rate"])
        self.assertEqual(len(pooled["cells"]), 2)


class ByeShare(unittest.TestCase):
    def test_share_counts_only_byes_inside_the_window(self):
        byes = {"A": 5, "B": 7, "C": 12, "D": 14}
        b = dl.bye_share(byes, 6, 18)
        self.assertEqual(b["teams_with_bye_in_window"], 3)
        self.assertAlmostEqual(b["share"], 3 / (4 * 13))

    def test_2026_table_matches_the_schedule(self):
        byes = json.loads((REPO / "data/inputs/nfl_byes_2026.json").read_text(encoding="utf-8"))["byes"]
        sched = dl.load_schedule()[2026]
        for team, bye in byes.items():
            self.assertEqual(set(range(1, 19)) - set(sched[team]), {bye}, team)


class Sigma(unittest.TestCase):
    def test_cross_source_spread_is_sample_sd_over_mean_and_skips_unavailable(self):
        sizes = {p: {"starters": 2, "bench": 1, "rostered": 3} for p in dl.POSITIONS}
        players = [
            {"player_key": 1, "pos": "RB", "espn_ppg": {"ppr": 20}, "cbsros_ppg": {"ppr": 22}, "rz_ppg": {"ppr": 18}},
            {"player_key": 2, "pos": "RB", "espn_ppg": {"ppr": 10}, "cbsros_ppg": {"ppr": 10}},
            {"player_key": 3, "pos": "RB", "espn_ppg": {"ppr": 8}, "rz_ppg": {"ppr": 6}},
            {"player_key": 4, "pos": "RB", "espn_ppg": {"ppr": 2}, "rz_ppg": {"ppr": 1}},
            {"player_key": 5, "pos": "RB", "espn_ppg": {"ppr": 3}, "rz_ppg": {"ppr": 30}, "injury_status": "IR"},
            {"player_key": 6, "pos": "RB", "espn_ppg": {"ppr": 9}},
        ]
        out = dl.cross_source_sigma(players, sizes, "ppr")["RB"]
        self.assertEqual(out["players_with_two_sources"], 5)
        self.assertEqual(out["healthy"], 4)
        rel3 = math.sqrt(2) / 7  # sd of (8, 6) = sqrt(2), mean 7
        # band = ranks (starters/2 .. rostered) = players 2, 3 -> median of (0, rel3)
        self.assertAlmostEqual(out["sigma_rel"], rel3 / 2)
        # floor = median absolute sd below the starter count = players 3, 4
        self.assertAlmostEqual(out["sigma_floor"], (math.sqrt(2) + math.sqrt(0.5)) / 2)
        self.assertAlmostEqual(out["unavailable_median_rel"], math.sqrt(2) * 27 / 2 / 16.5)

    def test_week_to_week_demeans_a_level_shift(self):
        # Every player moves +20% between weeks (a denominator shift); one
        # player moves +50%. The robust sd must ignore the common shift.
        pos_of = {k: "WR" for k in range(1, 9)}
        a = {str(k): [0, 0, 10.0 + k] for k in range(1, 9)}
        b = {str(k): [0, 0, (10.0 + k) * 1.2] for k in range(1, 9)}
        b["8"] = [0, 0, 18.0 * 1.5]
        mv = dl.week_to_week_sigma({3: {"espn": a}, 4: {"espn": b}}, pos_of)
        cell = mv["espn"]["WR"][0]
        self.assertEqual(cell["players"], 8)
        self.assertAlmostEqual(cell["median_shift"], 0.2)
        self.assertAlmostEqual(cell["robust_sd"], 0.0)
        summary = dl.summarize_movement(mv, 6.5)
        self.assertAlmostEqual(summary["WR"]["horizon_rel_sd"], 0.0)

    def test_horizon_scaling_is_square_root(self):
        mv = {"espn": {"RB": [{"robust_sd": 0.1}], }}
        s = dl.summarize_movement(mv, 4.0)["RB"]
        self.assertAlmostEqual(s["horizon_rel_sd"], 0.2)


class CommittedData(unittest.TestCase):
    def test_actuals_file_is_well_formed(self):
        rows = dl.load_actuals()
        self.assertGreater(len(rows), 10000)
        self.assertEqual({r["season"] for r in rows}, {2024, 2025, 2026})
        self.assertEqual({r["pos"] for r in rows}, set(dl.POSITIONS))
        sched = dl.load_schedule()
        for r in rows[:2000]:
            self.assertIn(r["week"], sched[r["season"]][r["team"]], r)

    def test_derivation_runs_and_lands_in_range(self):
        actuals = dl.load_actuals()
        sched = dl.load_schedule()
        byes = json.loads(dl.BYES.read_text(encoding="utf-8"))
        players = json.loads(dl.PLAYERS.read_text(encoding="utf-8"))["players"]
        hist = dl.load_history()
        doc = dl.derive(actuals, sched, byes, players, hist, 12, "ppr")
        self.assertEqual(doc["schema"], dl.SCHEMA)
        for pos in dl.POSITIONS:
            r = doc["recommended"][pos]
            self.assertTrue(0.03 < r["m"] < 0.30, (pos, r["m"]))
            self.assertTrue(0.03 < r["sigma_rel_now"] < 0.40, (pos, r["sigma_rel_now"]))
            self.assertTrue(0.0 < r["sigma_floor"] < 3.0, (pos, r["sigma_floor"]))
            self.assertGreater(doc["missed_games"]["pooled"][pos]["starters"]["games"], 300)
        self.assertAlmostEqual(doc["bye_share"]["share"], 30 / (32 * 13))
        self.assertIn("# Expected-starts parameters", dl.render_report(doc))


if __name__ == "__main__":
    unittest.main()
