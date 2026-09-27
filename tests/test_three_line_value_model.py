import unittest
from pathlib import Path

from pipelines.three_line_value_model import (
    LeagueShape,
    PlayerRow,
    _validate_flex_raw_ppg,
    build_model,
    load_players,
)


ROOT = Path(__file__).resolve().parents[1]


def p(key, name, pos, ppg):
    return PlayerRow(key=key, name=name, pos=pos, ppg=ppg)


class ThreeLineValueModelTest(unittest.TestCase):
    def test_flex_is_awarded_by_raw_points_after_dedicated_slots(self):
        players = [
            p(1, "RB starter", "RB", 20),
            p(2, "WR starter", "WR", 18),
            p(3, "RB flex", "RB", 10),
            p(4, "WR lower raw", "WR", 9),
            p(5, "RB waiver", "RB", 1),
            p(6, "WR waiver", "WR", 0),
        ]
        shape = LeagueShape(
            teams=1,
            slots={"QB": 0, "RB": 1, "WR": 1, "TE": 0},
            flex=1,
            bench=0,
            flex_eligible=("RB", "WR"),
            bench_positions=("RB", "WR"),
        )

        result = build_model(players, shape)
        roles = {row["name"]: row["role"] for row in result["players"]}

        self.assertEqual("flex_starter", roles["RB flex"])
        self.assertTrue(result["validations"]["flex_raw_ppg_ok"])
        self.assertEqual(10, result["lines"]["flex"])

    def test_flex_guard_fails_against_simulated_vorp_style_misassignment(self):
        players = [
            p(1, "RB starter", "RB", 20),
            p(2, "WR starter", "WR", 18),
            p(3, "RB higher raw", "RB", 10),
            p(4, "WR lower raw", "WR", 9),
        ]
        shape = LeagueShape(
            teams=1,
            slots={"QB": 0, "RB": 1, "WR": 1, "TE": 0},
            flex=1,
            bench=0,
            flex_eligible=("RB", "WR"),
            bench_positions=("RB", "WR"),
        )
        broken_roles = {
            1: "dedicated_starter",
            2: "dedicated_starter",
            3: "waiver",
            4: "flex_starter",
        }

        self.assertFalse(_validate_flex_raw_ppg(players, broken_roles, shape))

    def test_bench_caps_prevent_raw_qb_ppg_from_swamping_one_qb_bench(self):
        players = [
            p(1, "QB starter", "QB", 24),
            p(2, "QB bench one", "QB", 23),
            p(3, "QB bench two", "QB", 22),
            p(4, "RB starter", "RB", 12),
            p(5, "WR starter", "WR", 11),
            p(6, "RB bench", "RB", 8),
            p(7, "WR bench", "WR", 7),
        ]
        shape = LeagueShape(
            teams=1,
            slots={"QB": 1, "RB": 1, "WR": 1, "TE": 0},
            flex=0,
            bench=3,
            flex_eligible=("RB", "WR"),
            bench_positions=("QB", "RB", "WR"),
            bench_starter_slots_per_team=1,
            bench_caps={"QB": 1},
        )

        result = build_model(players, shape)
        qb_bench = result["counts"]["QB"]["bench_starter"] + result["counts"]["QB"]["bench_depth"]

        self.assertEqual(1, qb_bench)
        self.assertTrue(result["validations"]["bench_caps_ok"])

    def test_current_half_ppr_no_te_shape_lands_in_expected_rb_range(self):
        players = load_players(ROOT / "data" / "fixtures" / "current" / "players.json", "half_ppr")
        shape = LeagueShape(
            teams=12,
            slots={"QB": 1, "RB": 2, "WR": 3, "TE": 0},
            flex=1,
            bench=5,
            flex_eligible=("RB", "WR"),
            bench_positions=("QB", "RB", "WR"),
            bench_starter_slots_per_team=2,
            bench_caps={"QB": 6},
        )

        result = build_model(players, shape)
        rb = result["counts"]["RB"]
        wr = result["counts"]["WR"]

        self.assertTrue(all(result["validations"].values()))
        self.assertEqual(24, rb["dedicated_starter"])
        self.assertEqual(10, rb["flex_starter"])
        self.assertEqual(18, rb["bench_starter"] + rb["bench_depth"])
        self.assertEqual(36, wr["dedicated_starter"])
        self.assertEqual(52, sum(rb.values()))

    def test_bench_starter_tier_does_not_change_waiver_math_by_itself(self):
        players = load_players(ROOT / "data" / "fixtures" / "current" / "players.json", "half_ppr")
        common = {
            "teams": 12,
            "slots": {"QB": 1, "RB": 2, "WR": 3, "TE": 1},
            "flex": 1,
            "bench": 5,
            "flex_eligible": ("RB", "WR", "TE"),
            "bench_positions": ("QB", "RB", "WR", "TE"),
            "bench_caps": {"QB": 6},
        }

        shallow_bench_starter = build_model(
            players,
            LeagueShape(**common, bench_starter_slots_per_team=1),
        )
        deeper_bench_starter = build_model(
            players,
            LeagueShape(**common, bench_starter_slots_per_team=3),
        )

        self.assertEqual(shallow_bench_starter["lines"]["position_waiver"], deeper_bench_starter["lines"]["position_waiver"])
        self.assertEqual(
            {pos: sum(counts.values()) for pos, counts in shallow_bench_starter["counts"].items()},
            {pos: sum(counts.values()) for pos, counts in deeper_bench_starter["counts"].items()},
        )
        self.assertNotEqual(shallow_bench_starter["lines"]["bench_starter"], deeper_bench_starter["lines"]["bench_starter"])


if __name__ == "__main__":
    unittest.main()
