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

    def test_nulls_are_not_silently_zero_filled(self):
        by_name = {player["name"]: player for player in self.players["players"]}
        self.assertIsNone(by_name["Kyle Juszczyk"].get("pm_ros"))
        self.assertNotEqual(0, by_name["Kyle Juszczyk"].get("pm_ros"))
        text = (APP / "assets" / "curve-widget.js").read_text(encoding="utf-8")
        self.assertIn("return null", text)
        self.assertRegex(text, r"drawing\s*=\s*false")


if __name__ == "__main__":
    unittest.main()
