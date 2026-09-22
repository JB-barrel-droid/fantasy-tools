import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def players_payload(rows):
    return {"meta": {}, "players": rows}


def player_row(key, name, pos="QB", team="BUF"):
    return {"player_key": key, "name": name, "full_name": name, "pos": pos, "team": team}


class NamingDriftTest(unittest.TestCase):
    def run(self, script, *args):
        return subprocess.run(
            ["python3", f"pipelines/{script}", *args],
            cwd=ROOT, capture_output=True, text=True,
        )

    def pin(self, players_path: Path, manifest_path: Path, label="supabase:players"):
        result = self.run("pin_naming_manifest.py",
                          "--players", str(players_path), "--manifest", str(manifest_path),
                          "--source-label", label)
        self.assertEqual(0, result.returncode, msg=f"pin failed:\n{result.stderr}")

    def test_matching_pin_passes(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            players = tmp / "players.json"
            manifest = tmp / "players.naming-manifest.json"
            write_json(players, players_payload([player_row(869, "Josh Allen"), player_row(101, "Bijan Robinson", "RB", "ATL")]))
            self.pin(players, manifest)

            result = self.run("check_naming_drift.py", "--players", str(players), "--manifest", str(manifest))
            self.assertEqual(0, result.returncode, msg=f"check failed:\n{result.stderr}")
            self.assertIn("Naming manifest OK", result.stdout)

    def test_renamed_player_fails_closed(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            players = tmp / "players.json"
            manifest = tmp / "players.naming-manifest.json"
            write_json(players, players_payload([player_row(869, "Josh Allen")]))
            self.pin(players, manifest)

            # Simulate a hand-edit or out-of-band regeneration.
            write_json(players, players_payload([player_row(869, "Joshua Allen")]))
            result = self.run("check_naming_drift.py", "--players", str(players), "--manifest", str(manifest))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("NAMING DRIFT DETECTED", result.stderr)

    def test_added_player_fails_closed(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            players = tmp / "players.json"
            manifest = tmp / "players.naming-manifest.json"
            write_json(players, players_payload([player_row(869, "Josh Allen")]))
            self.pin(players, manifest)

            write_json(players, players_payload([player_row(869, "Josh Allen"), player_row(101, "Bijan Robinson", "RB", "ATL")]))
            result = self.run("check_naming_drift.py", "--players", str(players), "--manifest", str(manifest))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("NAMING DRIFT DETECTED", result.stderr)

    def test_missing_manifest_fails_closed(self):
        with TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            players = tmp / "players.json"
            write_json(players, players_payload([player_row(869, "Josh Allen")]))

            result = self.run("check_naming_drift.py",
                              "--players", str(players),
                              "--manifest", str(tmp / "nope.json"))
            self.assertNotEqual(0, result.returncode)
            self.assertIn("Missing naming manifest", result.stderr)


if __name__ == "__main__":
    unittest.main()
