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

    def write_snapshot_with_qb_slots(self, path: Path) -> None:
        """Snapshot with qb_slots field (local FantasyCalc format)."""
        path.write_text(
            json.dumps(
                {
                    "schema": "trade-value-source-snapshot-v1",
                    "source": "fantasycalc",
                    "fetched_at": "2026-09-29T12:00:00Z",
                    "row_count": 2,
                    "rows": [
                        {
                            "player_name": "Josh Allen",
                            "value": 5000.0,
                            "native_value": 5000.0,
                            "team": "BUF",
                            "pos": "QB",
                            "scoring": "ppr",
                            "teams": 12,
                            "qb_slots": 1,
                        },
                        {
                            "player_name": "Bijan Robinson Jr.",
                            "value": 8000.0,
                            "native_value": 8000.0,
                            "team": "ATL",
                            "pos": "RB",
                            "scoring": "ppr",
                            "teams": 12,
                            "qb_slots": 2,
                        },
                    ],
                }
            ),
            encoding="utf-8",
        )

    def test_qb_slots_carried_through_match(self):
        """qb_slots from snapshot rows is propagated as qb in matched output.

        Without this, combo_key_for(qb=None) produces bare keys like 'full_12'
        instead of 'full_12_qb1', causing combos_match failure for any source
        that carries explicit qb_slots (e.g. FantasyCalc Week 4 local pull).
        """
        with TemporaryDirectory() as tmp:
            players = Path(tmp) / "players.json"
            snapshot = Path(tmp) / "snapshot.json"
            output = Path(tmp) / "matched.json"
            self.write_players(players)
            self.write_snapshot_with_qb_slots(snapshot)

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
            matched = {r["player_key"]: r for r in payload["matched_rows"]}

            # Josh Allen (qb_slots=1): qb must be 1 in matched row
            self.assertIn(869, matched, "Josh Allen must resolve")
            self.assertEqual(
                1,
                matched[869]["qb"],
                "qb_slots=1 must propagate as qb=1 through match stage",
            )

            # Bijan Robinson (qb_slots=2): qb must be 2 in matched row
            self.assertIn(101, matched, "Bijan Robinson must resolve")
            self.assertEqual(
                2,
                matched[101]["qb"],
                "qb_slots=2 must propagate as qb=2 through match stage",
            )

    def test_qb_field_on_row_takes_precedence_over_qb_slots(self):
        """If a row has both qb and qb_slots, qb wins (not qb_slots).

        This guards against future changes where a Supabase import path that
        already mapped qb_slots -> qb could be double-mapped.
        """
        with TemporaryDirectory() as tmp:
            players = Path(tmp) / "players.json"
            snapshot = Path(tmp) / "snapshot_qb_field.json"
            output = Path(tmp) / "matched.json"
            self.write_players(players)
            snapshot.write_text(
                json.dumps(
                    {
                        "schema": "trade-value-source-snapshot-v1",
                        "source": "fantasycalc",
                        "fetched_at": "2026-09-29T12:00:00Z",
                        "row_count": 1,
                        "rows": [
                            {
                                "player_name": "Josh Allen",
                                "value": 5000.0,
                                "team": "BUF",
                                "pos": "QB",
                                "scoring": "ppr",
                                "teams": 12,
                                "qb": 2,
                                "qb_slots": 1,  # qb field should win
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

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
            matched = {r["player_key"]: r for r in payload["matched_rows"]}
            self.assertEqual(
                2,
                matched[869]["qb"],
                "explicit qb=2 must not be overridden by qb_slots=1",
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
            self.assertIn("source_provenance", payload)
            self.assertIsNone(payload["source_provenance"]["content_vintage"])
            self.assertEqual("unknown", payload["source_provenance"]["vintage_kind"])
            self.assertEqual({"input_row_count": 5, "matched_count": 3, "review_count": 2}, payload["summary"])
            self.assertEqual([869, 101, 201], [row["player_key"] for row in payload["matched_rows"]])
            reasons = [row["reason"] for row in payload["review_rows"]]
            self.assertEqual(["ambiguous", "no_match"], reasons)
            self.assertEqual([201, 202], payload["review_rows"][0]["candidate_player_keys"])


if __name__ == "__main__":
    unittest.main()
