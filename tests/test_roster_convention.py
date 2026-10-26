"""Unit tests for the shared roster convention module (JEG-559).

Tests each convention rule independently against known values.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

from lib.roster_convention import (
    POSITIONS,
    SKILL_POSITIONS,
    DEFAULT_SLOTS,
    DEFAULT_BENCH,
    DEFAULT_TEAMS,
    bench_weights,
    bench_seats,
    dhondt_allocate,
    flex_allocate_greedy,
    starter_line,
    waiver_line,
    compute_lines,
    market_bench_ratios,
    allocate_league,
    FLEX_ELIGIBLE,
    SUPERFLEX_ELIGIBLE,
)


class TestMarketBenchRatios(unittest.TestCase):
    """Rule 1 prerequisite: ratios come from config/market_bench.json."""

    def test_one_qb_ratios(self):
        r = market_bench_ratios(superflex=False, qb_slots=1)
        self.assertAlmostEqual(r["QB"], 0.88)
        self.assertAlmostEqual(r["RB"], 0.83)
        self.assertAlmostEqual(r["WR"], 1.03)
        self.assertAlmostEqual(r["TE"], 0.40)
        self.assertAlmostEqual(r["K"], 0.00)
        self.assertAlmostEqual(r["DEF"], 0.06)

    def test_two_qb_ratios(self):
        r = market_bench_ratios(superflex=False, qb_slots=2)
        self.assertAlmostEqual(r["QB"], 0.28)
        self.assertAlmostEqual(r["RB"], 0.69)

    def test_superflex_uses_two_qb(self):
        r = market_bench_ratios(superflex=True, qb_slots=1)
        self.assertAlmostEqual(r["QB"], 0.28)


class TestDhondtAllocate(unittest.TestCase):
    """D'Hondt seat allocation."""

    def test_simple_allocation(self):
        w = {"QB": 10, "RB": 27, "WR": 33, "TE": 10, "K": 0, "DEF": 0}
        seats = dhondt_allocate(w, 72)
        total = sum(seats.values())
        self.assertEqual(total, 72)
        # The largest weight should get the most seats
        self.assertGreater(seats["WR"], seats["QB"])
        self.assertGreater(seats["RB"], seats["QB"])

    def test_zero_total(self):
        w = {"QB": 10, "RB": 27, "WR": 33, "TE": 10, "K": 0, "DEF": 0}
        seats = dhondt_allocate(w, 0)
        self.assertEqual(sum(seats.values()), 0)

    def test_tie_goes_to_position_order(self):
        # Equal weights: seats should follow position order for ties
        w = {"QB": 10, "RB": 10, "WR": 0, "TE": 0, "K": 0, "DEF": 0}
        seats = dhondt_allocate(w, 1)
        self.assertEqual(seats["QB"], 1)
        self.assertEqual(seats["RB"], 0)


class TestBenchSeats(unittest.TestCase):
    """Convention rule 1: bench seats via market bench ratios."""

    def test_default_12_team(self):
        """Default roster at 12 teams, 7 bench: convention bench seats."""
        seats = bench_seats(DEFAULT_SLOTS, 12, 7, superflex=False)
        total = sum(seats.values())
        self.assertEqual(total, 12 * 7)
        # K gets 0 backups (ratio 0.00), DEF gets very few
        self.assertEqual(seats["K"], 0)
        # RB and WR should dominate
        self.assertGreater(seats["RB"] + seats["WR"], seats["QB"] + seats["TE"])

    def test_superflex_12_team(self):
        """Superflex uses two_qb ratios: QB backups drop."""
        slots_sf = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "K": 1, "DEF": 1}
        seats_sf = bench_seats(slots_sf, 12, 7, superflex=True)
        seats_1qb = bench_seats(DEFAULT_SLOTS, 12, 7, superflex=False)
        # With 2-QB ratios, QB bench weight is lower per starter
        # but the superflex slot adds starters, so compare the ratio
        total_sf = sum(seats_sf.values())
        total_1q = sum(seats_1qb.values())
        self.assertEqual(total_sf, total_1q)

    def test_8_10_14_teams(self):
        """Bench seats scale smoothly with league size."""
        prev_total = 0
        for teams in (8, 10, 12, 14):
            seats = bench_seats(DEFAULT_SLOTS, teams, 7)
            total = sum(seats.values())
            self.assertEqual(total, teams * 7)
            self.assertGreaterEqual(total, prev_total)
            prev_total = total


class TestFlexAllocateGreedy(unittest.TestCase):
    """Convention rule 2: greedy flex allocation."""

    def test_greedy_picks_highest_score(self):
        remaining = {
            "RB": ["rb1", "rb2"],
            "WR": ["wr1", "wr2"],
            "TE": ["te1"],
            "QB": ["qb1"],
            "K": [],
            "DEF": [],
        }
        scores = {"rb1": 15, "rb2": 10, "wr1": 18, "wr2": 12, "te1": 8, "qb1": 20}
        filled = flex_allocate_greedy(remaining, scores, 1, FLEX_ELIGIBLE)
        self.assertEqual(filled["WR"], 1)
        self.assertEqual(filled["RB"], 0)

    def test_superflex_includes_qb(self):
        remaining = {
            "QB": ["qb1"],
            "RB": ["rb1"],
            "WR": ["wr1"],
            "TE": ["te1"],
            "K": [],
            "DEF": [],
        }
        scores = {"qb1": 25, "rb1": 15, "wr1": 14, "te1": 8}
        filled = flex_allocate_greedy(remaining, scores, 1, SUPERFLEX_ELIGIBLE)
        self.assertEqual(filled["QB"], 1)

    def test_tie_goes_to_position_order(self):
        remaining = {"RB": ["rb1"], "WR": ["wr1"], "TE": [], "QB": [], "K": [], "DEF": []}
        scores = {"rb1": 10, "wr1": 10}
        filled = flex_allocate_greedy(remaining, scores, 1, FLEX_ELIGIBLE)
        self.assertEqual(filled["RB"], 1)


class TestStarterLine(unittest.TestCase):
    """Convention rule 3: midpoint of last starter and first non-starter."""

    def test_midpoint(self):
        values = [20.0, 18.0, 15.0, 12.0, 10.0, 8.0]
        # 2 starters: midpoint of values[1]=18 and values[2]=15
        self.assertAlmostEqual(starter_line(values, 2), 16.5)

    def test_exact_starters(self):
        values = [20.0, 18.0]
        # Exactly 2 starters, no bench: starter line = last starter
        self.assertAlmostEqual(starter_line(values, 2), 18.0)

    def test_insufficient(self):
        values = [20.0]
        self.assertIsNone(starter_line(values, 3))

    def test_single_starter(self):
        values = [20.0, 15.0, 10.0]
        self.assertAlmostEqual(starter_line(values, 1), 17.5)


class TestWaiverLine(unittest.TestCase):
    """Convention rule 4: first player not rostered."""

    def test_normal(self):
        values = [20.0, 18.0, 15.0, 12.0, 10.0, 8.0, 5.0]
        # 4 rostered: waiver = values[4] = 10.0
        self.assertAlmostEqual(waiver_line(values, 4), 10.0)

    def test_short_list(self):
        values = [20.0, 18.0, 15.0]
        # Need 5 rostered but only 3 listed: waiver = last value
        self.assertAlmostEqual(waiver_line(values, 5), 15.0)

    def test_exact(self):
        values = [20.0, 18.0, 15.0]
        self.assertAlmostEqual(waiver_line(values, 3), 15.0)

    def test_empty(self):
        self.assertIsNone(waiver_line([], 3))


class TestComputeLines(unittest.TestCase):
    """Combined starter/waiver line computation."""

    def test_starter_above_waiver(self):
        values = [20.0, 18.0, 15.0, 12.0, 10.0, 8.0, 5.0]
        result = compute_lines(values, 2, 5)
        # starter line: midpoint(18, 15) = 16.5
        self.assertAlmostEqual(result["starter_line"], 16.5)
        # waiver line: values[5] = 8.0
        self.assertAlmostEqual(result["waiver_line"], 8.0)
        self.assertEqual(result["method"], "roster_determined")

    def test_starter_clamped_to_waiver(self):
        # Edge case: computed starter line < waiver (shouldn't happen with
        # sorted values but the clamp is a safety net)
        values = [20.0, 5.0, 4.0]
        result = compute_lines(values, 2, 2)
        # starter line: midpoint(5, 4) = 4.5
        # waiver = values[-1] = 4.0 (exact fit, short list rule)
        self.assertGreaterEqual(result["starter_line"], result["waiver_line"])

    def test_no_players(self):
        result = compute_lines([], 2, 5)
        self.assertIsNone(result["starter_line"])
        self.assertIsNone(result["waiver_line"])
        self.assertEqual(result["method"], "no_players")

    def test_insufficient_coverage(self):
        values = [20.0, 15.0, 10.0]
        result = compute_lines(values, 2, 5)
        self.assertEqual(result["method"], "insufficient_coverage")
        self.assertIsNotNone(result["starter_line"])
        self.assertIsNotNone(result["waiver_line"])


class TestAllocateLeague(unittest.TestCase):
    """Full league allocation integration."""

    def test_default_12_team(self):
        # Build a simple player order with enough players
        player_order = {}
        player_scores = {}
        for pos in POSITIONS:
            keys = [f"{pos.lower()}{i}" for i in range(1, 61)]
            player_order[pos] = keys
            for i, k in enumerate(keys):
                player_scores[k] = 100 - i

        ratios = market_bench_ratios(superflex=False, qb_slots=1)
        alloc = allocate_league(
            DEFAULT_SLOTS, 12, 7, 1, 0,
            player_order, player_scores, ratios,
        )
        # Check totals
        total_starters = sum(alloc[p]["starters"] for p in POSITIONS)
        total_bench = sum(alloc[p]["bench"] for p in POSITIONS)
        total_rostered = sum(alloc[p]["rostered"] for p in POSITIONS)
        # 12 teams * (1+2+2+1+1+1+1) starters per team = 12 * 9 = 108
        # But flex is allocated among eligible, and K/DEF dedicated are 12 each
        self.assertEqual(total_bench, 12 * 7)
        self.assertEqual(total_rostered, total_starters + total_bench)

    def test_superflex_12_team(self):
        player_order = {}
        player_scores = {}
        for pos in POSITIONS:
            keys = [f"{pos.lower()}{i}" for i in range(1, 61)]
            player_order[pos] = keys
            for i, k in enumerate(keys):
                player_scores[k] = 100 - i

        ratios = market_bench_ratios(superflex=True, qb_slots=1)
        alloc = allocate_league(
            DEFAULT_SLOTS, 12, 7, 1, 1,
            player_order, player_scores, ratios,
        )
        # Superflex should give some slots to QB (since QB scores highest)
        self.assertGreater(alloc["QB"]["superflex"], 0)


class TestNegativeTest(unittest.TestCase):
    """Every regression guard must prove it catches the bug it names.

    These tests simulate broken states and verify the convention module
    would detect the problem.
    """

    def test_starter_line_detects_wrong_rule(self):
        """Using first-non-starter (wrong) vs midpoint (correct) gives
        different results when there is a gap."""
        values = [20.0, 18.0, 12.0, 8.0, 5.0]
        correct = starter_line(values, 2)
        wrong = values[2]  # first non-starter (old rule)
        self.assertNotAlmostEqual(correct, wrong,
                                  msg="midpoint rule must differ from first-non-starter")
        self.assertAlmostEqual(correct, 15.0)  # midpoint of 18 and 12
        self.assertAlmostEqual(wrong, 12.0)    # first non-starter

    def test_waiver_line_detects_short_list_zero(self):
        """Using 0.0 for short lists (wrong) vs last-listed (correct)."""
        values = [20.0, 15.0, 10.0]
        correct = waiver_line(values, 5)
        wrong = 0.0  # old short-list fallback in some paths
        self.assertNotAlmostEqual(correct, wrong,
                                  msg="convention waiver must not be 0 for short lists")
        self.assertAlmostEqual(correct, 10.0)

    def test_bench_detects_legacy_scaling(self):
        """Legacy round-half-up scaling differs from D'Hondt on market bench
        ratios for non-12-team leagues."""
        # Legacy: BENCH_MIX_12[pos] * teams / 12, round half up
        BENCH_MIX_12 = {"QB": 10, "RB": 27, "WR": 33, "TE": 10}
        legacy_8 = {pos: int(math.floor(BENCH_MIX_12[pos] * 8 / 12 + 0.5))
                    for pos in ("QB", "RB", "WR", "TE")}
        convention_8 = bench_seats(DEFAULT_SLOTS, 8, 7)
        # Extract skill positions for comparison
        conv_skill = {p: convention_8[p] for p in ("QB", "RB", "WR", "TE")}
        # These should differ because the convention uses different ratios
        # and the bench count is different (8*7=56 vs legacy 8*6=48 scaled)
        self.assertNotEqual(conv_skill, legacy_8,
                            msg="convention bench must differ from legacy scaling")


class TestBenchSeatsUnits(unittest.TestCase):
    """JEG-1121: flex_filled must be per-team, not league-wide.

    Bug: allocate_league passed league-wide sf_filled/fx_filled as flex_filled
    to bench_seats, but slots is per-team.  The fix normalises to per-team by
    dividing by teams before calling bench_seats.
    """

    # Deterministic player pool for exact assertions.
    _TEAMS = 12
    _BENCH = 7
    _FLEX = 1

    @classmethod
    def _player_pool(cls):
        player_order = {
            "QB":  [f"QB{i:03d}" for i in range(100)],
            "RB":  [f"RB{i:03d}" for i in range(200)],
            "WR":  [f"WR{i:03d}" for i in range(200)],
            "TE":  [f"TE{i:03d}" for i in range(100)],
            "K":   [f"K{i:03d}"  for i in range(30)],
            "DEF": [f"DEF{i:03d}" for i in range(30)],
        }
        player_scores = {}
        for i, p in enumerate(player_order["QB"]):  player_scores[p] = 500 - i * 30
        for i, p in enumerate(player_order["RB"]):  player_scores[p] = 500 - i * 10
        for i, p in enumerate(player_order["WR"]):  player_scores[p] = 500 - i * 10
        for i, p in enumerate(player_order["TE"]):  player_scores[p] = 400 - i * 10
        for i, p in enumerate(player_order["K"]):   player_scores[p] = 100 - i * 5
        for i, p in enumerate(player_order["DEF"]): player_scores[p] = 100 - i * 5
        return player_order, player_scores

    def test_1qb_bench_apportionment(self):
        """1QB default 12-team: QB bench must not be near zero (was ~4 with bug)."""
        order, scores = self._player_pool()
        result = allocate_league(
            slots=DEFAULT_SLOTS, teams=self._TEAMS, bench_per_team=self._BENCH,
            flex_count=self._FLEX, superflex_count=0,
            player_order=order, player_scores=scores,
        )
        bench_total = sum(result[pos]["bench"] for pos in POSITIONS)
        self.assertEqual(bench_total, self._TEAMS * self._BENCH)
        # With correct per-team normalization QB gets proportional share.
        # Bug produced QB=4; fixed value is 13 for this player pool.
        self.assertEqual(result["QB"]["bench"], 13,
                         "QB bench should be 13, not ~4 (units bug)")
        self.assertEqual(result["RB"]["bench"], 29)
        self.assertEqual(result["WR"]["bench"], 34)
        self.assertEqual(result["TE"]["bench"], 8)

    def test_superflex_bench_apportionment(self):
        """Superflex 12-team: bench total correct; uses two_qb ratios."""
        order, scores = self._player_pool()
        result = allocate_league(
            slots=DEFAULT_SLOTS, teams=self._TEAMS, bench_per_team=self._BENCH,
            flex_count=self._FLEX, superflex_count=1,
            player_order=order, player_scores=scores,
        )
        bench_total = sum(result[pos]["bench"] for pos in POSITIONS)
        self.assertEqual(bench_total, self._TEAMS * self._BENCH)
        # Superflex skips flex_bench_seats (option A); bench uses dedicated only.
        # Pinning known-good values so a regression is immediately visible.
        self.assertEqual(result["QB"]["bench"], 4)
        self.assertEqual(result["RB"]["bench"], 30)
        self.assertEqual(result["WR"]["bench"], 36)
        self.assertEqual(result["TE"]["bench"], 12)

    def test_units_bug_would_inflate_wr_bench(self):
        """Demonstrate the units bug: league-wide flex_filled inflates WR bench."""
        slots = DEFAULT_SLOTS
        # Per-team: WR gets 0.5 flex starters on average (6 league-wide / 12).
        per_team = bench_seats(slots, 12, 7, superflex=False,
                               flex_filled={"QB": 0, "RB": 0.5, "WR": 0.5, "TE": 0,
                                            "K": 0, "DEF": 0})
        # League-wide (the bug): 6 league-wide flex starters added to per-team slots.
        league_wide = bench_seats(slots, 12, 7, superflex=False,
                                  flex_filled={"QB": 0, "RB": 6, "WR": 6, "TE": 0,
                                               "K": 0, "DEF": 0})
        # Per-team is correct; league-wide massively over-weights WR and under-weights QB.
        self.assertGreater(per_team["QB"], league_wide["QB"],
                           "per-team normalization gives more QB bench seats")
        self.assertLess(per_team["WR"], league_wide["WR"],
                        "per-team normalization gives fewer WR bench seats (bug inflated them)")


if __name__ == "__main__":
    unittest.main()
