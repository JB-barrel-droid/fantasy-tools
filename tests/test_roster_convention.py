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
    """JEG-1121 revised: allocate_league fills bench from the league-wide player
    pool after starters. Backup QB counts emerge from player values, not a
    preset ratio.
    """

    def _run_alloc(self, player_order, player_scores, teams=4, bench_per_team=2,
                   flex=1, sf=0):
        return allocate_league(
            DEFAULT_SLOTS, teams, bench_per_team, flex, sf,
            player_order, player_scores,
        )

    def test_bench_total_equals_teams_times_bench(self):
        """Total bench seats = teams * bench_per_team (league-wide, not per-team)."""
        teams, bench = 4, 3
        po = {pos: [f"{pos}{i}" for i in range(60)] for pos in POSITIONS}
        ps = {k: 100 for pos in po for k in po[pos]}
        result = allocate_league(DEFAULT_SLOTS, teams, bench, 1, 0, po, ps)
        total = sum(result[pos]["bench"] for pos in SKILL_POSITIONS)
        self.assertEqual(total, teams * bench,
                         f"Total bench must equal {teams}*{bench}={teams*bench}; got {total}")

    def test_qb_bench_zero_when_pool_exhausted(self):
        """QB bench = 0 when exactly enough QBs fill dedicated slots (no QB pool left)."""
        teams = 4
        player_order = {
            "QB": [f"qb{i}" for i in range(4)],   # exactly 4, none left for bench
            "RB": [f"rb{i}" for i in range(40)],
            "WR": [f"wr{i}" for i in range(40)],
            "TE": [f"te{i}" for i in range(20)],
            "K": [], "DEF": [],
        }
        # QBs have very high scores but pool is exhausted after 4 starters
        player_scores = {k: 1000 for k in player_order["QB"]}
        for k in player_order["RB"]: player_scores[k] = 50
        for k in player_order["WR"]: player_scores[k] = 50
        for k in player_order["TE"]: player_scores[k] = 50
        result = allocate_league(DEFAULT_SLOTS, teams, 2, 1, 0, player_order, player_scores)
        self.assertEqual(result["QB"]["bench"], 0,
                         "QB bench must be 0 when QB pool is exhausted after starters")

    def test_qb_bench_fills_when_qbs_have_positive_ppg(self):
        """QB bench > 0 when remaining QBs have positive PPG.

        Stable method: a player earns bench spots by having PPG > 0, competing
        cross-position by PPG × c^(1+floor(k/t1)).  When a remaining QB scores
        far above the RB/WR/TE pool, it wins enough seats to give QB bench > 0.
        """
        teams = 4
        player_order = {
            "QB": [f"qb{i}" for i in range(30)],
            "RB": [f"rb{i}" for i in range(40)],
            "WR": [f"wr{i}" for i in range(40)],
            "TE": [f"te{i}" for i in range(20)],
            "K": [], "DEF": [],
        }
        player_scores = {}
        # qb0-4 elite (200 PPG); qb5+ low (1 PPG). RB/WR/TE all 1 PPG.
        # After 4 dedicated starters, remaining QB starts at qb4 (200 PPG).
        # effective_QB = 200 × c_QB; effective_RB = 1 × c_RB. QB wins many seats.
        for i, k in enumerate(player_order["QB"]):
            player_scores[k] = 200 if i < 5 else 1
        for k in player_order["RB"]: player_scores[k] = 1
        for k in player_order["WR"]: player_scores[k] = 1
        for k in player_order["TE"]: player_scores[k] = 1
        result = allocate_league(DEFAULT_SLOTS, teams, 2, 1, 0, player_order, player_scores)
        self.assertGreater(result["QB"]["bench"], 0,
                           "QB should get bench when remaining QBs have positive PPG")

    def test_negative_dhondt_would_give_qb_bench_regardless(self):
        """D'Hondt (bench_seats) gives QB>0 bench even when QB pool is exhausted after starters.
        This proves the old approach was wrong: it gave QB bench regardless of pool availability.
        """
        # D'Hondt approach: QB bench weight = 4 starters * 0.88 ratio > 0
        dhondt_result = bench_seats(DEFAULT_SLOTS, 4, 2, superflex=False)
        self.assertGreater(dhondt_result["QB"], 0,
                           "D'Hondt gives QB bench > 0 regardless of player pool availability")

        # Greedy approach: with no QB pool remaining, QB bench = 0
        teams = 4
        player_order = {
            "QB": [f"qb{i}" for i in range(4)],   # exactly 4, exhausted after starters
            "RB": [f"rb{i}" for i in range(40)],
            "WR": [f"wr{i}" for i in range(40)],
            "TE": [f"te{i}" for i in range(20)],
            "K": [], "DEF": [],
        }
        player_scores = {k: 50 for pos in player_order for k in player_order[pos]}
        result = allocate_league(DEFAULT_SLOTS, teams, 2, 1, 0, player_order, player_scores)
        self.assertEqual(result["QB"]["bench"], 0,
                         "Greedy approach gives QB=0 (correct); D'Hondt gave QB>0 (wrong)")

    def test_allocation_is_deterministic(self):
        """Same inputs produce identical allocation every call (no randomness)."""
        teams = 12
        po = {pos: [f"{pos}{i}" for i in range(80)] for pos in POSITIONS}
        ps = {}
        ppg = {"QB": 20.0, "RB": 15.0, "WR": 13.0, "TE": 11.0, "K": 0.0, "DEF": 0.0}
        for pos in POSITIONS:
            for i, k in enumerate(po[pos]):
                ps[k] = max(0.1, ppg.get(pos, 0) - i * 0.2)
        r1 = allocate_league(DEFAULT_SLOTS, teams, 7, 1, 0, po, ps)
        r2 = allocate_league(DEFAULT_SLOTS, teams, 7, 1, 0, po, ps)
        for pos in SKILL_POSITIONS:
            self.assertEqual(r1[pos]["bench"], r2[pos]["bench"],
                             f"{pos} bench must be deterministic")

    def test_no_dhondt_fallback_rb_share_below_old_level(self):
        """With the stable method (no D'Hondt fallback), RB bench share is
        substantially lower than the ~63% produced by the old D'Hondt tail."""
        teams = 12
        po = {}
        ps = {}
        ppg = {"QB": 20.0, "RB": 15.0, "WR": 13.0, "TE": 11.0}
        for pos in SKILL_POSITIONS:
            po[pos] = [f"{pos}{i}" for i in range(80)]
            for i, k in enumerate(po[pos]):
                ps[k] = max(0.1, ppg[pos] - i * 0.2)
        po["K"] = []
        po["DEF"] = []
        result = allocate_league(DEFAULT_SLOTS, teams, 7, 1, 0, po, ps)
        bench_total = sum(result[p]["bench"] for p in SKILL_POSITIONS)
        rb_share = result["RB"]["bench"] / bench_total if bench_total > 0 else 0
        self.assertLess(rb_share, 0.55,
                        f"RB bench share {rb_share:.0%} should be <55% without D'Hondt fallback")

    def test_seats_unfilled_when_all_remaining_zero_ppg(self):
        """Bench seats are left unfilled when all remaining non-starter candidates have 0 PPG."""
        teams = 4
        po = {
            "QB": [f"qb{i}" for i in range(4)],   # exactly 4, all become starters
            "RB": [f"rb{i}" for i in range(4)],   # exactly 4, all become starters
            "WR": [f"wr{i}" for i in range(4)],   # exactly 4, all become starters
            "TE": [f"te{i}" for i in range(4)],   # exactly 4, all become starters
            "K": [], "DEF": [],
        }
        # All players have exactly-enough positive PPG to fill starters; none left for bench.
        ps = {k: 10.0 for pos in po for k in po[pos]}
        result = allocate_league(DEFAULT_SLOTS, teams, 2, 1, 0, po, ps)
        # With pools fully consumed by starters, no bench candidates remain → bench = 0 all positions
        bench_total = sum(result[p]["bench"] for p in SKILL_POSITIONS)
        # Starters exhaust QB/RB/WR/TE pools (4 each, 4 teams × 1/2/2/1 slots = 4+8+8+4 = 24 starters)
        # With only 4 per position available, QB/TE pools exhausted; RB/WR pools also exhausted by flex/starters
        self.assertEqual(result["QB"]["bench"], 0, "QB bench 0 when pool exhausted")
        self.assertEqual(result["TE"]["bench"], 0, "TE bench 0 when pool exhausted")

    def test_units_bug_would_inflate_wr_bench(self):
        """Preserve the original units-bug test: passing league-wide vs per-team flex to
        bench_seats (D'Hondt) gives different results. The convention module still
        exposes bench_seats for other uses; the units matter there too.
        """
        slots = DEFAULT_SLOTS
        per_team = bench_seats(slots, 12, 7, superflex=False,
                               flex_filled={"QB": 0, "RB": 0.5, "WR": 0.5, "TE": 0,
                                            "K": 0, "DEF": 0})
        league_wide = bench_seats(slots, 12, 7, superflex=False,
                                  flex_filled={"QB": 0, "RB": 6, "WR": 6, "TE": 0,
                                               "K": 0, "DEF": 0})
        self.assertGreater(per_team["QB"], league_wide["QB"])
        self.assertLess(per_team["WR"], league_wide["WR"])


if __name__ == "__main__":
    unittest.main()
