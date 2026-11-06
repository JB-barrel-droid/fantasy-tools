"""JEG-1508: real 1.0 reader/board consumers and roster-grain regressions."""
import importlib.util
import json
import sys

from tests import test_build_weekly_inputs as producer

import build_waiver_board as board
import waiver_board


class ConsumerCompatibility(producer.ProducerCase):
    stub_contract = False

    def test_default_artifact_builds_the_existing_board(self):
        weekly = self.build()
        values = json.loads((producer.ROOT / "tests/fixtures/waiver_board/values_half_ppr_12.json").read_text())
        result = board.build_board(weekly, values, values["setting"], "2026-10-30T12:00:00Z")
        self.assertEqual(waiver_board.validate(result), [])
        self.assertEqual(next(r for r in result["players"] if r["player_key"] == 102)["this_week"]["points"], 0.0)

    def test_default_artifact_validates_with_the_actual_base_1_0_reader(self):
        # Byte-for-byte copy of ad0cfc3a's real reader, not a permissive stand-in.
        path = producer.ROOT / "tests/fixtures/weekly_inputs/base_1_0_reader.py"
        spec = importlib.util.spec_from_file_location("weekly_inputs_base_1_0", path)
        reader = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = reader
        self.addCleanup(sys.modules.pop, spec.name, None)
        spec.loader.exec_module(reader)
        self.assertEqual(reader.SCHEMA_VERSION, "1.0.0")
        issues = reader.validate(self.build())
        self.assertEqual(reader.errors(issues), [], "\n".join(map(str, issues)))


class RosterGrain(producer.ProducerCase):
    stub_contract = False
    games = [{"home_team": "AAA", "away_team": "CCC", "kickoff_at": "2026-11-01T17:00:00Z"},
             {"home_team": "BBB", "away_team": "DDD", "kickoff_at": "2026-11-01T21:25:00Z"}]

    def roster(self, rows, **grain):
        return self.write("roster.json", json.dumps({"season": 2026, "week": 8,
                          "captured_at": "2026-10-28T12:00:00Z", "rows": rows, **grain}))

    def test_equal_values_with_conflicting_teams_cannot_choose_a_kickoff(self):
        rows = [{"player_key": 101, "team": team, "rostered_pct": 0.0, "adds_trend": 0.0}
                for team in ("AAA", "BBB", "AAA")]
        slate = self.write("slate.json", json.dumps({"season": 2026, "week": 8,
                           "captured_at": "2026-10-28T12:00:00Z", "games": self.games}))
        actual = []
        for ordered in (rows, list(reversed(rows)), rows[1:] + rows[:1]):
            doc = self.build(espn_weekly=None, status=None, byes=None,
                             espn_roster=self.roster(ordered), slate=slate)
            row = self.row(doc, 101)
            self.assertEqual(doc["input_report"]["roster"]["conflict"], 1)
            self.assertIsNone(row["team"])
            self.assertIsNone(row["legs"]["slate"]["values"]["kickoff_at"])
            self.assertEqual(row["legs"]["slate"]["missing_reason"], {"kickoff_at": "no team"})
            self.assertEqual(row["legs"]["roster"]["values"], {"rostered_pct": 0.0, "adds_trend": 0.0})
            self.assertEqual(producer.bwi.validate(doc), [])
            actual.append(doc["players"])
        self.assertEqual(actual[0], actual[1])
        self.assertEqual(actual[0], actual[2])

    def test_missing_file_grain_cannot_publish_stale_row_grain_as_current(self):
        row = {"player_key": 101, "team": "AAA", "season": 2025, "week": 7,
               "rostered_pct": 50.0, "adds_trend": 1.0}
        for field in ("season", "week"):
            with self.subTest(missing=field):
                path = self.roster([row])
                raw = json.loads(path.read_text())
                raw.pop(field)
                path.write_text(json.dumps(raw))
                doc = self.build(espn_roster=path)
                self.assertEqual(doc["legs"]["roster"]["availability"], "unavailable")
                self.assertEqual(doc["input_report"]["roster"]["bad_row"], 1)
                self.assertIsNone(self.row(doc, 101)["legs"]["roster"]["values"]["rostered_pct"])

    def test_explicit_row_grain_must_agree_with_file_grain(self):
        for field, wrong, counter in (("season", 2025, "wrong_season"), ("week", 7, "wrong_week")):
            with self.subTest(field=field):
                bad = {"player_key": 101, "team": "AAA", "rostered_pct": 50.0, "adds_trend": 1.0,
                       field: wrong}
                zero = {"player_key": 102, "team": "BBB", "rostered_pct": 0.0, "adds_trend": 0.0}
                doc = self.build(espn_roster=self.roster([bad, zero]))
                self.assertEqual(doc["input_report"]["roster"][counter], 1)
                self.assertIsNone(self.row(doc, 101)["legs"]["roster"]["values"]["rostered_pct"])
                self.assertEqual(self.row(doc, 102)["legs"]["roster"]["values"]["rostered_pct"], 0.0)

    def test_bare_row_list_cannot_invent_a_file_grain(self):
        path = self.write("roster.json", json.dumps([{"player_key": 101, "team": "AAA",
                          "season": 2025, "week": 7, "rostered_pct": 50.0, "adds_trend": 1.0}]))
        doc = self.build(espn_roster=path)
        self.assertEqual(doc["legs"]["roster"]["availability"], "unavailable")
        self.assertEqual(doc["input_report"]["roster"]["bad_row"], 1)

    def test_only_explicitly_supplied_optional_leg_is_declared(self):
        doc = self.build(espn_roster=self.roster([]))
        self.assertIn("roster", doc["legs"])
        self.assertNotIn("slate", doc["legs"])
        self.assertEqual(doc["legs"]["roster"]["availability"], "unavailable")
        for row in doc["players"]:
            self.assertEqual(row["legs"]["roster"], {"provenance": "missing", "values": {
                "rostered_pct": None, "adds_trend": None}})
            self.assertNotIn("slate", row["legs"])

    def test_normalized_duplicate_team_keeps_real_zero(self):
        rows = [{"player_key": 101, "team": team, "rostered_pct": 0.0, "adds_trend": 0.0}
                for team in (" aaa ", "AAA")]
        doc = self.build(espn_roster=self.roster(rows))
        self.assertEqual(doc["input_report"]["roster"]["conflict"], 0)
        self.assertEqual(doc["input_report"]["roster"]["duplicate"], 1)
        row = self.row(doc, 101)
        self.assertEqual(row["legs"]["roster"]["values"], {"rostered_pct": 0.0, "adds_trend": 0.0})

    def test_invalid_and_missing_roster_values_keep_their_reasons(self):
        rows = [{"player_key": 101, "team": "AAA", "rostered_pct": -1, "adds_trend": None},
                {"player_key": 102, "team": "BBB", "rostered_pct": 0.0, "adds_trend": 0.0}]
        doc = self.build(espn_roster=self.roster(rows))
        cell = self.row(doc, 101)["legs"]["roster"]
        self.assertEqual(cell["values"], {"rostered_pct": None, "adds_trend": None})
        self.assertEqual(cell["missing_reason"], {"rostered_pct": "invalid in the ESPN roster file",
                                               "adds_trend": "not set in the ESPN roster file"})
        self.assertEqual(doc["input_report"]["roster"]["bad_row"], 1)
        self.assertEqual(self.row(doc, 102)["legs"]["roster"]["values"]["rostered_pct"], 0.0)
