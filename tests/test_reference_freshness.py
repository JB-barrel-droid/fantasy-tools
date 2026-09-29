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
                        "ecr_content_date": value_date,
                        "espn_snapshot": value_date,
                        "pm_snapshot": value_date,
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
        (root / "player-news.json").write_text(
            json.dumps(
                {
                    "meta": {
                        "generated_at": f"{value_date}T12:00:00Z",
                        "trade_values_published_at": f"{value_date}T12:00:00Z",
                    },
                    "news_by_player_key": {},
                }
            ),
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
            self.assertEqual(8, payload["summary"]["expired_count"])
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
            self.assertEqual(7, payload["summary"]["expired_count"])
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


if __name__ == "__main__":
    unittest.main()
