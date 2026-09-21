import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class SourceReferenceBuildTest(unittest.TestCase):
    def write_match(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema": "trade-value-source-matches-v1",
                    "source": "fantasycalc",
                    "fetched_at": "2026-09-21T12:00:00Z",
                    "default_scoring": "ppr",
                    "default_teams": 12,
                    "summary": {"input_row_count": 5, "matched_count": 4, "review_count": 1},
                    "matched_rows": [
                        {"player_key": 869, "canonical_name": "Josh Allen", "source_player_name": "Josh Allen", "source": "fantasycalc", "value": 24.0, "scoring": "ppr", "teams": 12, "pos": "QB", "team": "BUF", "source_player_id": None},
                        {"player_key": 101, "canonical_name": "Bijan Robinson", "source_player_name": "Bijan Robinson", "source": "fantasycalc", "value": 67.5, "scoring": "ppr", "teams": 12, "pos": "RB", "team": "ATL", "source_player_id": None},
                        {"player_key": 202, "canonical_name": "Duplicate One", "source_player_name": "Duplicate One A", "source": "fantasycalc", "value": 10.0, "scoring": "ppr", "teams": 12, "pos": "WR", "team": "NO", "source_player_id": None},
                        {"player_key": 202, "canonical_name": "Duplicate One", "source_player_name": "Duplicate One B", "source": "fantasycalc", "value": 11.0, "scoring": "ppr", "teams": 12, "pos": "WR", "team": "NO", "source_player_id": None},
                    ],
                    "review_rows": [
                        {"reason": "no_match", "source_player_name": "Unknown Player", "value": 1.0}
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_builds_reference_rows_and_keeps_duplicate_conflicts_for_review(self):
        with TemporaryDirectory() as tmp:
            match = Path(tmp) / "matched.json"
            output = Path(tmp) / "reference.json"
            self.write_match(match)

            subprocess.run(
                [
                    "python3",
                    "pipelines/build_source_reference.py",
                    "--input",
                    str(match),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-source-reference-v1", payload["schema"])
            self.assertEqual("ppr_12", payload["combo_key"])
            self.assertEqual(
                {
                    "matched_input_count": 4,
                    "reference_row_count": 2,
                    "inherited_review_count": 1,
                    "duplicate_review_count": 1,
                },
                payload["summary"],
            )
            self.assertEqual([101, 869], [row["player_key"] for row in payload["rows"]])
            self.assertEqual({"101": 67.5, "869": 24.0}, payload["values_by_player_key"])
            self.assertEqual(["no_match", "duplicate_player_key"], [row["reason"] for row in payload["review_rows"]])


if __name__ == "__main__":
    unittest.main()
