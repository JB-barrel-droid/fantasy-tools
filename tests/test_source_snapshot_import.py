import csv
import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class SourceSnapshotImportTest(unittest.TestCase):
    def test_imports_csv_scrape_to_standard_raw_snapshot(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "fantasycalc.csv"
            output = Path(tmp) / "snapshot.json"
            with source.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=["Player", "Team", "Pos", "Value"])
                writer.writeheader()
                writer.writerow({"Player": "Josh Allen", "Team": "BUF", "Pos": "QB", "Value": "24"})
                writer.writerow({"Player": "Kyle Juszczyk", "Team": "SF", "Pos": "RB", "Value": "--"})
                writer.writerow({"Player": "Bijan Robinson", "Team": "ATL", "Pos": "RB", "Value": "67.5"})

            subprocess.run(
                [
                    "python3",
                    "pipelines/import_source_snapshot.py",
                    "--input",
                    str(source),
                    "--source",
                    "fantasycalc",
                    "--scoring",
                    "full_ppr",
                    "--teams",
                    "12",
                    "--fetched-at",
                    "2026-09-21T12:00:00Z",
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-source-snapshot-v1", snapshot["schema"])
            self.assertEqual("fantasycalc", snapshot["source"])
            self.assertEqual("ppr", snapshot["default_scoring"])
            self.assertEqual(12, snapshot["default_teams"])
            self.assertEqual(2, snapshot["row_count"])
            self.assertEqual(
                {"player_name": "Josh Allen", "value": 24.0, "pos": "QB", "team": "BUF", "scoring": "ppr", "teams": 12, "source_player_id": None},
                snapshot["rows"][0],
            )

    def test_imports_json_values_map(self):
        with TemporaryDirectory() as tmp:
            source = Path(tmp) / "cbs.json"
            output = Path(tmp) / "snapshot.json"
            source.write_text(
                json.dumps(
                    {
                        "source": "cbs",
                        "scoring": "half",
                        "teams": 10,
                        "fetched_at": "2026-09-21T13:00:00Z",
                        "values": {"Josh Allen": 20.1, "Bijan Robinson": 54.2},
                    }
                ),
                encoding="utf-8",
            )

            subprocess.run(
                [
                    "python3",
                    "pipelines/import_source_snapshot.py",
                    "--input",
                    str(source),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            snapshot = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("cbs", snapshot["source"])
            self.assertEqual("half_ppr", snapshot["default_scoring"])
            self.assertEqual(10, snapshot["default_teams"])
            self.assertEqual(["Josh Allen", "Bijan Robinson"], [row["player_name"] for row in snapshot["rows"]])


if __name__ == "__main__":
    unittest.main()
