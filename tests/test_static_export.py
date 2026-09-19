import json
import re
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "app" / "trade-value-chart"
FIXTURES = ROOT / "data" / "fixtures" / "current"


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


class StaticExportTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.index = (APP / "index.html").read_text(encoding="utf-8")
        cls.players = load_json(FIXTURES / "players.json")
        cls.comparison = load_json(FIXTURES / "comparison-sources-data.json")

    def test_inline_players_match_fixture(self):
        match = re.search(
            r"<script[^>]*id=[\"']players-data[\"'][^>]*>(.*?)</script>",
            self.index,
            re.S,
        )
        self.assertIsNotNone(match, "index.html must contain players-data")
        self.assertEqual(json.loads(match.group(1)), self.players)

    def test_expected_player_universe_and_identity(self):
        players = self.players["players"]
        self.assertEqual(596, len(players))
        by_name = {player["name"]: player for player in players}
        self.assertEqual(869, by_name["Josh Allen"]["player_key"])
        self.assertEqual("QB", by_name["Josh Allen"]["pos"])
        self.assertEqual("BUF", by_name["Josh Allen"]["team"])
        self.assertEqual(1, by_name["Josh Allen"]["preseason_ecr_rank"])
        self.assertEqual("experts_only", by_name["Josh Allen"]["pricing"])
        self.assertEqual(1.0, by_name["Josh Allen"]["ecr_share"]["ppr"])

    def test_known_player_values_are_preserved(self):
        by_name = {player["name"]: player for player in self.players["players"]}
        self.assertEqual(351.48, by_name["Josh Allen"]["ecr_ros"]["ppr"])
        self.assertEqual(351.48, by_name["Josh Allen"]["blend_ros"]["ppr"])
        self.assertEqual(386.51, by_name["Josh Allen"]["espn_ros"]["ppr"])
        self.assertEqual(325.87, by_name["Bijan Robinson"]["ecr_ros"]["ppr"])
        self.assertIsNone(by_name["Kyle Juszczyk"].get("pm_ros"))

    def test_comparison_sources_contract(self):
        expected_sources = {
            "usatoday",
            "fantasycalc",
            "fantasypros",
            "cbs",
            "espn",
            "fantasycalc_adjusted",
            "usatoday_adjusted",
            "fantasypros_adjusted",
        }
        self.assertEqual(expected_sources, set(self.comparison["sources"]))
        for source in expected_sources:
            self.assertEqual("live", self.comparison["source_validation"][source])
        self.assertEqual("stale", self.comparison["source_validation"]["ecr"])
        self.assertEqual("pending", self.comparison["source_validation"]["razzball"])

    def test_known_full_ppr_12_team_source_values(self):
        sources = self.comparison["sources"]

        def value(source, combo):
            combo_data = sources[source]["combos"][combo]
            values = combo_data.get("values") or combo_data.get("reindexed")
            return values["josh allen"]

        expected = {
            ("usatoday", "full_12"): 22.3,
            ("fantasycalc", "full_12_qb1"): 24.0,
            ("fantasypros", "full_12"): 26.0,
            ("cbs", "full_12"): 22.1,
            ("espn", "full_12"): 17.2,
            ("fantasycalc_adjusted", "full_12_qb1"): 19.0,
            ("usatoday_adjusted", "full_12"): 21.2,
            ("fantasypros_adjusted", "full_12"): 18.1,
        }
        for key, expected_value in expected.items():
            self.assertEqual(expected_value, value(*key))

    def test_fixed_pie_totals_match_source_metadata(self):
        players = load_json(FIXTURES / "players.json")["players"]
        position_by_key = {player["player_key"]: player["pos"] for player in players}

        def combo_key(source, scoring):
            if source in {"fantasycalc", "fantasycalc_adjusted"}:
                return f"{scoring}_12_qb1"
            return f"{scoring}_12"

        combos = {
            "full": "full",
            "half": "half",
            "standard": "std",
        }
        tolerance = 2.0
        for source, source_data in self.comparison["sources"].items():
            for scoring, adjusted_scoring in combos.items():
                key = combo_key(source, adjusted_scoring if source.endswith("_adjusted") else scoring)
                combo = source_data["combos"].get(key)
                if combo is None:
                    continue
                values = combo.get("values") or combo.get("reindexed") or {}
                for pos, target_data in combo.get("index_total", {}).items():
                    target = target_data["target_total"]
                    total = 0
                    for source_id, value in values.items():
                        player_key = self.comparison["player_keys"].get(source_id)
                        if position_by_key.get(player_key) == pos and isinstance(value, (int, float)):
                            total += value
                    self.assertLessEqual(
                        abs(total - target),
                        tolerance,
                        f"{source} {key} {pos} total {total:.1f} should match fixed-pie target {target}",
                    )

    def test_nulls_are_not_silently_zero_filled(self):
        by_name = {player["name"]: player for player in self.players["players"]}
        self.assertIsNone(by_name["Kyle Juszczyk"].get("pm_ros"))
        self.assertNotEqual(0, by_name["Kyle Juszczyk"].get("pm_ros"))
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("return null", text)
        self.assertRegex(text, r"drawing\s*=\s*false")

    def test_roster_lines_are_two_transitions(self):
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("Starter → Bench", text)
        self.assertIn("Bench → Waiver", text)
        self.assertIn("fixed-pie indexed values", text)
        self.assertIn("window.TradeValueCurveDiagnostics", text)

    def test_default_qb_waiver_transition_is_zero_value_boundary(self):
        players = load_json(FIXTURES / "players.json")["players"]
        by_key = {
            player["player_key"]: player
            for player in players
            if player.get("pos") in {"QB", "RB", "WR", "TE"}
        }
        sources = self.comparison["sources"]
        source_keys = [
            "usatoday",
            "fantasycalc",
            "fantasypros",
            "cbs",
            "espn",
            "fantasycalc_adjusted",
            "usatoday_adjusted",
            "fantasypros_adjusted",
        ]

        def combo_key(source):
            return "full_12_qb1" if source in {"fantasycalc", "fantasycalc_adjusted"} else "full_12"

        source_maps = {}
        for source in source_keys:
            combo = sources[source]["combos"][combo_key(source)]
            values = combo.get("values") or combo.get("reindexed") or {}
            native = combo.get("native") or {}
            source_maps[source] = {}
            for source_id, value in values.items():
                if source in {"fantasypros", "fantasypros_adjusted"} and source_id not in native:
                    continue
                player_key = self.comparison["player_keys"].get(source_id)
                if player_key in by_key and isinstance(value, (int, float)):
                    source_maps[source][player_key] = max(0, value)

        all_keys = set().union(*[set(values) for values in source_maps.values()])
        rows = []
        for player_key in all_keys:
            player = by_key[player_key]
            if player["pos"] != "QB":
                continue
            rank = player.get("preseason_ecr_rank")
            row_values = {source: source_maps[source].get(player_key) for source in source_keys}
            rows.append((rank if isinstance(rank, int) else 9999, player["name"], row_values))
        rows.sort(key=lambda item: (item[0], item[1]))

        last_positive = 0
        for index, (_, _, values) in enumerate(rows, 1):
            max_value = max([value for value in values.values() if isinstance(value, (int, float))], default=0)
            if max_value > 0:
                last_positive = index

        self.assertEqual(33, last_positive)
        self.assertEqual(34, last_positive + 1)


if __name__ == "__main__":
    unittest.main()
