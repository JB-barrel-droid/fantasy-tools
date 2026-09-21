import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


class SourceSnapshotMatchTest(unittest.TestCase):
    def write_players(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "players": [
                        {"player_key": 869, "name": "Josh Allen", "team": "BUF", "pos": "QB"},
                        {"player_key": 101, "name": "Bijan Robinson", "team": "ATL", "pos": "RB"},
                        {"player_key": 201, "name": "Michael Wilson", "team": "ARI", "pos": "WR"},
                        {"player_key": 202, "name": "Michael Wilson", "team": "NO", "pos": "WR"},
                    ]
                }
            ),
            encoding="utf-8",
        )

    def write_snapshot(self, path: Path) -> None:
        path.write_text(
            json.dumps(
                {
                    "schema": "trade-value-source-snapshot-v1",
                    "source": "fantasycalc",
                    "fetched_at": "2026-09-21T12:00:00Z",
                    "default_scoring": "ppr",
                    "default_teams": 12,
                    "row_count": 5,
                    "rows": [
                        {"player_name": "Josh Allen", "value": 24.0, "team": "BUF", "pos": "QB", "scoring": "ppr", "teams": 12},
                        {"player_name": "Bijan Robinson Jr.", "value": 67.5, "team": "ATL", "pos": "RB", "scoring": "ppr", "teams": 12},
                        {"player_name": "Michael Wilson", "value": 3.0, "team": "ARI", "pos": "WR", "scoring": "ppr", "teams": 12},
                        {"player_name": "Michael Wilson", "value": 2.0, "pos": "WR", "scoring": "ppr", "teams": 12},
                        {"player_name": "Unknown Player", "value": 1.0, "team": "FA", "pos": "RB", "scoring": "ppr", "teams": 12},
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_matches_snapshot_rows_fail_closed(self):
        with TemporaryDirectory() as tmp:
            players = Path(tmp) / "players.json"
            snapshot = Path(tmp) / "snapshot.json"
            output = Path(tmp) / "matched.json"
            self.write_players(players)
            self.write_snapshot(snapshot)

            subprocess.run(
                [
                    "python3",
                    "pipelines/match_source_snapshot.py",
                    "--input",
                    str(snapshot),
                    "--players",
                    str(players),
                    "--output",
                    str(output),
                ],
                cwd=ROOT,
                check=True,
                capture_output=True,
                text=True,
            )

            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual("trade-value-source-matches-v1", payload["schema"])
            self.assertEqual({"input_row_count": 5, "matched_count": 3, "review_count": 2}, payload["summary"])
            self.assertEqual([869, 101, 201], [row["player_key"] for row in payload["matched_rows"]])
            reasons = [row["reason"] for row in payload["review_rows"]]
            self.assertEqual(["ambiguous", "no_match"], reasons)
            self.assertEqual([201, 202], payload["review_rows"][0]["candidate_player_keys"])


if __name__ == "__main__":
    unittest.main()
