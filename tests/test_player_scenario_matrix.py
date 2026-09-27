"""End-to-end player scenario tests over the shipped trade-value fixtures.

These tests deliberately pick *current* players from the fixture at run time.
They are not trying to remember that a specific player was WR39 in one week.
They answer football-product questions:

- Do we have live-current representatives for core starters, bench players,
  waiver players, and both roster cut lines?
- Do starter/bench/waiver boundaries remain ordered when read through the same
  source maps the dashboard uses?
- Do multi-player trade packages sum canonical player values, across positions,
  without depending on stale names or silently filling missing source values?
"""
import json
import math
import unittest
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "data" / "fixtures" / "current"
POSITIONS = ("QB", "RB", "WR", "TE")
DEFAULT_SHAPE = {"QB": 1, "RB": 2, "WR": 3, "TE": 1, "FLEX": 1, "BENCH": 6}
TEAMS = 12


@dataclass(frozen=True)
class ScenarioPlayer:
    player_key: int
    name: str
    pos: str
    team: str
    value: float
    role: str


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def stable_key(row):
    return (-row.value, row.name, row.player_key)


def combo_key_for(source_key, source_data):
    combos = source_data.get("combos") or {}
    for key in ("full_12", "full_12_qb1"):
        if key in combos:
            return key
    raise AssertionError(f"{source_key} has no full-PPR 12-team combo")


class PlayerScenarioMatrixTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.players = load_json(FIXTURES / "players.json")["players"]
        cls.by_key = {int(player["player_key"]): player for player in cls.players}
        cls.comparison = load_json(FIXTURES / "comparison-sources-data.json")
        cls.key_by_slug = {
            str(slug): int(player_key)
            for slug, player_key in cls.comparison["player_keys"].items()
        }
        cls.espn_values = cls.source_values("espn")
        cls.espn_rows = cls.rows_for_values(cls.espn_values)
        cls.roles = {row.player_key: row.role for row in cls.espn_rows}

    @classmethod
    def source_values(cls, source_key):
        source = cls.comparison["sources"][source_key]
        combo = source["combos"][combo_key_for(source_key, source)]
        raw = combo.get("values") or combo.get("reindexed") or {}
        values = {}
        for slug, value in raw.items():
            player_key = cls.key_by_slug.get(slug)
            if player_key is None or not isinstance(value, (int, float)):
                continue
            values[player_key] = float(value)
        return values

    @classmethod
    def rows_for_values(cls, values):
        roles = cls.role_map(values)
        rows = []
        for player_key, value in values.items():
            player = cls.by_key.get(player_key)
            if not player or player.get("pos") not in POSITIONS:
                continue
            if not math.isfinite(value) or value < 0:
                continue
            rows.append(
                ScenarioPlayer(
                    player_key=player_key,
                    name=player["name"],
                    pos=player["pos"],
                    team=player.get("team") or "",
                    value=value,
                    role=roles.get(player_key, "waiver"),
                )
            )
        return sorted(rows, key=stable_key)

    @classmethod
    def role_map(cls, values):
        """Port of ValueModel.roleMap for the default 12-team chart state."""
        rows = []
        for player_key, value in values.items():
            player = cls.by_key.get(player_key)
            if not player or player.get("pos") not in POSITIONS:
                continue
            numeric = float(value)
            if not math.isfinite(numeric) or numeric <= 0:
                continue
            rows.append((player_key, numeric, player))
        rows.sort(key=lambda row: (-row[1], row[2]["name"], row[0]))

        roles = {}
        for pos in POSITIONS:
            pos_rows = [row for row in rows if row[2]["pos"] == pos]
            for player_key, _, _ in pos_rows[: TEAMS * DEFAULT_SHAPE[pos]]:
                roles[player_key] = "starter"

        flex_rows = [
            row
            for row in rows
            if row[2]["pos"] in {"RB", "WR", "TE"} and row[0] not in roles
        ]
        for player_key, _, _ in flex_rows[: TEAMS * DEFAULT_SHAPE["FLEX"]]:
            roles[player_key] = "starter"

        bench_rows = [row for row in rows if row[0] not in roles]
        for player_key, _, _ in bench_rows[: TEAMS * DEFAULT_SHAPE["BENCH"]]:
            roles[player_key] = "bench"

        return roles

    def rows(self, *, pos=None, role=None):
        rows = self.espn_rows
        if pos:
            rows = [row for row in rows if row.pos == pos]
        if role:
            rows = [row for row in rows if row.role == role]
        return rows

    def boundary_pair(self, pos, better_role, worse_role):
        better = self.rows(pos=pos, role=better_role)
        worse = self.rows(pos=pos, role=worse_role)
        if not better or not worse:
            return None
        return min(better, key=lambda row: row.value), max(worse, key=lambda row: row.value)

    def trade_total(self, players, values=None):
        values = values or self.espn_values
        total = 0.0
        for player in players:
            self.assertIn(
                player.player_key,
                values,
                f"{player.name} is missing from the source being summed",
            )
            total += values[player.player_key]
        return total

    def source_coverage(self, player):
        source_maps = {
            source_key: self.source_values(source_key)
            for source_key in self.comparison["sources"]
        }
        return [
            source_key
            for source_key, values in source_maps.items()
            if isinstance(values.get(player.player_key), float)
            and math.isfinite(values[player.player_key])
        ]

    def covered_row(self, *, pos, role, minimum_sources=3):
        for row in self.rows(pos=pos, role=role):
            if len(self.source_coverage(row)) >= minimum_sources:
                return row
        return None

    def test_dynamic_archetypes_cover_starters_bench_waivers_and_margins(self):
        """Concept: every weekly run must find live players for the board questions."""
        core_starters = {pos: self.rows(pos=pos, role="starter")[0] for pos in POSITIONS}
        square_bench = {
            pos: self.rows(pos=pos, role="bench")[len(self.rows(pos=pos, role="bench")) // 2]
            for pos in POSITIONS
            if self.rows(pos=pos, role="bench")
        }
        square_waiver = {
            pos: self.rows(pos=pos, role="waiver")[len(self.rows(pos=pos, role="waiver")) // 2]
            for pos in POSITIONS
            if self.rows(pos=pos, role="waiver")
        }
        starter_bench = {
            pos: pair
            for pos in POSITIONS
            if (pair := self.boundary_pair(pos, "starter", "bench"))
        }
        bench_waiver = {
            pos: pair
            for pos in POSITIONS
            if (pair := self.boundary_pair(pos, "bench", "waiver"))
        }

        self.assertEqual(set(POSITIONS), set(core_starters))
        self.assertGreaterEqual(len(square_bench), 3, "need bench examples across most positions")
        self.assertGreaterEqual(len(square_waiver), 2, "need waiver examples across multiple positions")
        self.assertEqual(set(POSITIONS), set(starter_bench))
        self.assertGreaterEqual(len(bench_waiver), 2, "need bench/waiver boundary examples")

        for player in list(core_starters.values()) + list(square_bench.values()) + list(square_waiver.values()):
            self.assertGreaterEqual(player.value, 0, f"{player.name} has an invalid source value")
            self.assertEqual(player.role, self.roles[player.player_key])

    def test_boundary_scenarios_preserve_role_ordering(self):
        """Concept: margin players should expose where starter, bench, and waiver split."""
        checked = 0
        for pos in POSITIONS:
            starter_bench = self.boundary_pair(pos, "starter", "bench")
            if starter_bench:
                starter, bench = starter_bench
                self.assertGreaterEqual(
                    starter.value,
                    bench.value,
                    f"{pos} starter fringe {starter.name} fell below bench fringe {bench.name}",
                )
                checked += 1

            bench_waiver = self.boundary_pair(pos, "bench", "waiver")
            if bench_waiver:
                bench, waiver = bench_waiver
                self.assertGreaterEqual(
                    bench.value,
                    waiver.value,
                    f"{pos} bench fringe {bench.name} fell below waiver fringe {waiver.name}",
                )
                checked += 1

        self.assertGreaterEqual(checked, 6, "not enough boundary scenarios were available")

    def test_two_for_one_trade_package_uses_current_bench_and_starter_values(self):
        """Concept: a multi-player consolidation test should sum people, not names."""
        bench = sorted(self.rows(role="bench"), key=stable_key)
        starters = sorted(self.rows(role="starter"), key=lambda row: row.value)
        self.assertGreaterEqual(len(bench), 2)
        self.assertGreaterEqual(len(starters), 1)

        package = bench[:2]
        package_total = self.trade_total(package)
        target = min(starters, key=lambda row: abs(row.value - package_total))
        target_total = self.trade_total([target])

        self.assertTrue(all(player.role == "bench" for player in package))
        self.assertEqual("starter", target.role)
        self.assertAlmostEqual(package_total, sum(player.value for player in package), places=9)
        self.assertAlmostEqual(target_total, target.value, places=9)
        self.assertNotEqual({player.player_key for player in package}, {target.player_key})

    def test_cross_position_trade_package_keeps_positional_context(self):
        """Concept: cross-position packages must keep each player's own source value."""
        starter_by_pos = {pos: self.rows(pos=pos, role="starter")[0] for pos in POSITIONS}
        bench_by_pos = {
            pos: self.rows(pos=pos, role="bench")[0]
            for pos in POSITIONS
            if self.rows(pos=pos, role="bench")
        }
        self.assertIn("QB", starter_by_pos)
        self.assertIn("RB", starter_by_pos)
        self.assertIn("WR", bench_by_pos)

        side_a = [starter_by_pos["QB"], bench_by_pos["WR"]]
        side_b = [starter_by_pos["RB"]]
        total_a = self.trade_total(side_a)
        total_b = self.trade_total(side_b)

        self.assertGreater(total_a, 0)
        self.assertGreater(total_b, 0)
        self.assertEqual({player.pos for player in side_a}, {"QB", "WR"})
        self.assertEqual({player.pos for player in side_b}, {"RB"})

    def test_waiver_throw_in_is_low_value_and_never_missing_value_fill(self):
        """Concept: a waiver add-on should be explicit value, not a hidden zero-fill."""
        bench_waiver_pairs = [
            pair for pos in POSITIONS if (pair := self.boundary_pair(pos, "bench", "waiver"))
        ]
        self.assertTrue(bench_waiver_pairs)
        bench, waiver = min(bench_waiver_pairs, key=lambda pair: pair[1].value)

        base = self.trade_total([bench])
        with_throw_in = self.trade_total([bench, waiver])

        self.assertEqual("bench", bench.role)
        self.assertEqual("waiver", waiver.role)
        self.assertIn(waiver.player_key, self.espn_values)
        self.assertGreaterEqual(with_throw_in, base)
        self.assertAlmostEqual(with_throw_in - base, waiver.value, places=9)
        self.assertLessEqual(waiver.value, bench.value)

    def test_selected_scenario_players_are_priced_by_multiple_sources(self):
        """Concept: end-to-end scenarios should exercise source coverage, not one column."""
        candidates = []
        for pos in POSITIONS:
            starter = self.covered_row(pos=pos, role="starter")
            bench = self.covered_row(pos=pos, role="bench")
            waiver = self.covered_row(pos=pos, role="waiver")
            self.assertIsNotNone(starter, f"{pos} has no multi-source starter scenario")
            candidates.append(starter)
            if bench:
                candidates.append(bench)
            if waiver:
                candidates.append(waiver)

        self.assertGreaterEqual(
            len([player for player in candidates if player.role == "bench"]),
            3,
            "need multi-source bench scenarios across most positions",
        )
        self.assertGreaterEqual(
            len([player for player in candidates if player.role == "waiver"]),
            2,
            "need multi-source waiver scenarios across multiple positions",
        )
        for player in candidates:
            priced_by = self.source_coverage(player)
            self.assertIn("espn", priced_by, f"{player.name} lost the ESPN anchor value")
            self.assertGreaterEqual(
                len(priced_by),
                3,
                f"{player.name} is too thinly sourced for a scenario player: {priced_by}",
            )


if __name__ == "__main__":
    unittest.main()
