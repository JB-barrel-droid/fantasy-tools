"""GAP-KDST-GAMES-FIXED: kickers and defenses count games remaining the same
way skill players do (pipelines/lib/games_remaining.py), not a fixed 16 (K)
or 15 (DST) left over from the weeks 3-18 window.

Only espn_ros / blend_ros (and games_remaining) depend on the count; K/DST
chart values price from the per-game rate, which is unchanged.

Discrimination (2026-10-08, docs/claude-log/2026-10-08-value-small.md):
origin/main's players.json (K 16, DST 15 while ESPN's window 5-18 is 13
games for every team) fails test_games_follow_the_window. test_ros_is_rate_times_games
only pins that the ROS total is built from the published count.
"""
import csv
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines" / "lib"))

import games_remaining as gr  # noqa: E402

PLAYERS_JSON = ROOT / "data" / "fixtures" / "current" / "players.json"
ESPN_CSV = ROOT / "data" / "inputs" / "espn_projections.csv"


class KdstGamesRemaining(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.players = [p for p in json.loads(PLAYERS_JSON.read_text(encoding="utf-8"))["players"]
                       if p["pos"] in ("K", "DST")]
        with ESPN_CSV.open(newline="", encoding="utf-8") as f:
            cls.window = gr.window_from_rows(list(csv.DictReader(f)))
        cls.byes, _ = gr.load_byes()

    def test_games_follow_the_window(self):
        window_len = self.window[1] - self.window[0] + 1
        possible = {gr.games_in_window(t, self.window, self.byes) for t in self.byes}
        bad = []
        for p in self.players:
            if p["pos"] == "DST":
                want = gr.games_in_window(p["team"], self.window, self.byes)
                if p["games_remaining"] != want:
                    bad.append((p["name"], p["games_remaining"], want))
            elif p["games_remaining"] not in possible | {window_len}:
                bad.append((p["name"], p["games_remaining"], sorted(possible | {window_len})))
        self.assertGreater(len(self.players), 60)
        self.assertEqual(bad[:5], [], f"{len(bad)} K/DST rows with a stale games count")

    def test_ros_is_rate_times_games(self):
        bad = []
        for p in self.players:
            for s in ("standard", "half_ppr", "ppr"):
                want = round(p["espn_ppg"][s] * p["games_remaining"], 2)
                if abs(p["espn_ros"][s] - want) > 0.011 or p["blend_ros"][s] != p["espn_ros"][s]:
                    bad.append((p["name"], s, p["espn_ros"][s], want))
        self.assertEqual(bad[:5], [], f"{len(bad)} K/DST ROS totals off")


if __name__ == "__main__":
    unittest.main()
