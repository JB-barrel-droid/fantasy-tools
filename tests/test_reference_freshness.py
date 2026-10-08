import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class ReferenceFreshnessTest(unittest.TestCase):
    def write_fixtures(self, root: Path, value_date: str, comparison_date=None) -> None:
        comparison_date = comparison_date or value_date
        root.mkdir(parents=True)
        (root / "players.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "as_of": value_date,
                        "espn_snapshot": value_date,
                        "kdst_snapshot": value_date,
                    },
                    "players": [],
                }
            ),
            encoding="utf-8",
        )
        (root / "comparison-sources-data.json").write_text(
            json.dumps({"built_at": f"{comparison_date}T12:00:00Z", "source_validation": {}}),
            encoding="utf-8",
        )

    def test_freshness_gate_fails_for_expired_reference_dates(self):
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-20")

            result = subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    "2026-09-27",
                    "--max-age-days",
                    "2",
                    "--enforce",
                ],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )

            self.assertNotEqual(0, result.returncode)
            self.assertIn("Freshness gate failed", result.stdout)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(4, payload["summary"]["expired_count"])  # 2026-10-08: players.pm_snapshot item retired with the prediction-markets leg; news.generated_at + news.trade_values_published_at retired with the player-news artifact (chore/retire-extras)
            self.assertEqual(1, payload["summary"]["enforced_expired_count"])

    def test_freshness_gate_passes_for_current_reference_dates(self):
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-27")

            subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    "2026-09-27",
                    "--max-age-days",
                    "2",
                    "--enforce",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(0, payload["summary"]["expired_count"])
            self.assertEqual(0, payload["summary"]["enforced_expired_count"])

    def test_freshness_gate_reports_legacy_staleness_without_blocking_current_comparison(self):
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-20", comparison_date="2026-09-27")

            subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    "2026-09-27",
                    "--max-age-days",
                    "2",
                    "--enforce",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(3, payload["summary"]["expired_count"])  # 2026-10-08: players.pm_snapshot item retired with the prediction-markets leg; the two news.* items retired with the player-news artifact (chore/retire-extras)
            self.assertEqual(0, payload["summary"]["enforced_expired_count"])

    def test_l1_import_health_is_reported_as_source_freshness(self):
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-27")
            (fixtures / "source-import-health.json").write_text(
                json.dumps(
                    {
                        "schema": "trade-value-import-health-v1",
                        "checked_at": "2026-09-27T12:00:00Z",
                        "nfl_week": 3,
                        "sources": {
                            "fantasycalc": {
                                "status": "stale",
                                "last_successful_import": "2026-09-20T12:00:00Z",
                                "content_vintage": "Week 2",
                                "failure_reason": "STALE_VINTAGE: old",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    "2026-09-27",
                    "--max-age-days",
                    "2",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(1, payload["summary"]["l1_unhealthy_count"])
            item = next(i for i in payload["items"] if i["key"] == "source_import.fantasycalc")
            self.assertEqual("Week 2", item["value"])
            self.assertEqual("stale", item["l1_status"])
            self.assertFalse(item["freshness_ok"])

    def test_jeg_407_no_ecr_content_date_in_players_meta(self):
        """JEG-407: Ensure ecr_content_date is not read from players meta and content_vintage is used instead."""
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-27")
            
            # Add a source-import-health entry with content_vintage
            (fixtures / "source-import-health.json").write_text(
                json.dumps(
                    {
                        "schema": "trade-value-import-health-v1",
                        "checked_at": "2026-09-27T12:00:00Z",
                        "nfl_week": 3,
                        "sources": {
                            "espn": {
                                "status": "ok",
                                "last_successful_import": "2026-09-27T12:00:00Z",
                                "content_vintage": "2026-09-27",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    "2026-09-27",
                    "--max-age-days",
                    "2",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            
            # Check that ecr_content_date is NOT in the items
            ecr_content_date_items = [item for item in payload["items"] if item["key"] == "players.ecr_content_date"]
            self.assertEqual(0, len(ecr_content_date_items), 
                           "ecr_content_date should not be present in freshness items")
            
            # Check that content_vintage from source import IS used
            espn_items = [item for item in payload["items"] if item["key"] == "source_import.espn"]
            self.assertEqual(1, len(espn_items), "source_import.espn item should be present")
            espn_item = espn_items[0]
            self.assertEqual("2026-09-27", espn_item["value"], 
                           "content_vintage from source import should be used")
            self.assertTrue(espn_item["freshness_ok"], 
                          "ESPN content_vintage should be fresh")

    def test_players_as_of_ten_days_old_paints_red_on_chart_input(self):
        """JEG-316 negative test: players.as_of = today - 10d must surface as
        a red chart-input row, with chart_input=true and chart_input_at_risk
        counting it. Confirms the chart-input pipeline flags the kind of
        staleness the dashboard needs to show.
        """
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            today_iso = "2026-10-03"
            self.write_fixtures(fixtures, "2026-09-23")  # today - 10d

            subprocess.run(
                [
                    "python3",
                    "pipelines/check_reference_freshness.py",
                    "--fixtures",
                    str(fixtures),
                    "--output",
                    str(output),
                    "--today",
                    today_iso,
                    "--max-age-days",
                    "2",
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            chart_inputs = payload.get("chart_inputs") or []
            # news.generated_at left with the player-news artifact (retired
            # 2026-10-08, chore/retire-extras).
            self.assertEqual(2, payload["summary"]["chart_input_count"])
            self.assertEqual(
                ["players.as_of", "players.kdst_snapshot"],
                payload["summary"]["chart_input_keys"],
            )
            as_of = next(
                (item for item in chart_inputs if item["key"] == "players.as_of"),
                None,
            )
            self.assertIsNotNone(as_of, "players.as_of missing from chart_inputs")
            self.assertTrue(as_of["chart_input"])
            self.assertEqual(10, as_of["age_days"])
            self.assertEqual("red", as_of["color"], "10-day-stale players.as_of must paint red")
            self.assertFalse(as_of["freshness_ok"])
            # The red row counts toward the at-risk rollup used by the panel.
            self.assertGreaterEqual(payload["summary"]["chart_input_at_risk_count"], 1)

    def test_chart_input_color_classification_covers_yellow_and_unknown(self):
        """JEG-316: assert every age band the dashboard relies on actually
        fires. Negative test for the color helper: a 3-day-old players.as_of
        (warning band) must paint yellow, and a '?' kdst_snapshot must paint
        unknown. Catches a regression where the band thresholds drift or
        unknown is mis-bucketed as red.
        """
        import importlib
        import sys
        if "pipelines" not in sys.path:
            sys.path.insert(0, str(ROOT / "pipelines"))
        if "check_reference_freshness" not in sys.modules:
            importlib.import_module("check_reference_freshness")
        color_for = importlib.import_module("check_reference_freshness").color_for

        # Within the window (max_age_days=2): green
        self.assertEqual("green", color_for(0, 2))
        self.assertEqual("green", color_for(2, 2))
        # Warning band (2*max_age_days = 4): yellow
        self.assertEqual("yellow", color_for(3, 2))
        self.assertEqual("yellow", color_for(4, 2))
        # Past the window: red
        self.assertEqual("red", color_for(5, 2))
        self.assertEqual("red", color_for(10, 2))
        # Missing date: unknown (must NOT be red; otherwise the K/DST gap
        # would look like an emergency).
        self.assertEqual("unknown", color_for(None, 2))
        # Future-dated or negative ages are also unknown.
        self.assertEqual("unknown", color_for(-1, 2))


    def test_retired_news_items_are_not_reported(self):
        # chore/retire-extras (2026-10-08): the player-news artifact has no
        # producer and was retired. Its two rows (news.generated_at,
        # news.trade_values_published_at) sat on the monitor as permanent
        # stale/unknown items. With no player-news.json present the report
        # must carry no news.* row and no player-news hash.
        with TemporaryDirectory() as tmp:
            fixtures = Path(tmp) / "fixtures"
            output = Path(tmp) / "freshness.json"
            self.write_fixtures(fixtures, "2026-09-27")
            subprocess.run(
                ["python3", "pipelines/check_reference_freshness.py", "--fixtures", str(fixtures),
                 "--output", str(output), "--today", "2026-09-27", "--max-age-days", "2"],
                cwd=ROOT, check=True, capture_output=True, text=True,
            )
            payload = json.loads(output.read_text(encoding="utf-8"))
            keys = [item["key"] for item in payload["items"]]
            self.assertEqual([], [k for k in keys if k.startswith("news.")], keys)
            self.assertNotIn("player-news.json", json.dumps(payload))
            self.assertEqual(0, payload["summary"]["unknown_count"], payload["summary"])


if __name__ == "__main__":
    unittest.main()
