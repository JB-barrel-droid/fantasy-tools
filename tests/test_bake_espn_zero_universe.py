"""JEG-392: the board carries ESPN-zeroed and comparison-keyed skill players.

JEG-ECR-EXIT narrowed players.json to ESPN's eligible skill players (425
total), orphaning 185 identities the comparison artifact still keys. That
broke `make validate` (reference orphans, pie totals, bench mix, CBS ROS
coverage) and made the source chain's coverage review hold every source.

espn_zero_universe() returns the skill players the bake must carry at an
ESPN value of zero. Each test names the regression it catches; the negative
cases prove the guard discriminates (it must not admit unresolvable names,
non-skill keys, or double-count ESPN-priced players).
"""
import csv
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import bake_players  # noqa: E402

COLS = ["player", "pos", "team", "eligible", "espn_snapshot_date"]


def _csv(rows):
    fd, p = tempfile.mkstemp(suffix=".csv", text=True)
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in COLS})
    return p


def _fixture(player_keys):
    fd, p = tempfile.mkstemp(suffix=".json", text=True)
    with os.fdopen(fd, "w") as f:
        json.dump({"player_keys": player_keys}, f)
    return p


def _reg():
    return bake_players.load_registry(rows=[
        {"player_key": 1, "full_name": "Priced Star", "position": "WR", "active": True},
        {"player_key": 2, "full_name": "Ir Back", "position": "RB", "active": True},
        {"player_key": 3, "full_name": "Deep Bench", "position": "TE", "active": True},
        {"player_key": 4, "full_name": "Some Kicker", "position": "K", "active": True},
    ])


class EspnZeroUniverseTest(unittest.TestCase):
    def test_ineligible_and_absent_players_are_carried(self):
        espn_csv = _csv([
            {"player": "Priced Star", "pos": "WR", "team": "BUF", "eligible": "True"},
            {"player": "Ir Back", "pos": "RB", "team": "MIA", "eligible": "False"},
        ])
        fixture = _fixture({"priced star": 1, "ir back": 2, "deep bench": 3})
        espn_med = {1: {"comps": {"rec": 1.0}, "pos": "WR", "team": "BUF"}}
        out = bake_players.espn_zero_universe(espn_csv, fixture, espn_med, _reg())
        # Regression caught: the JEG-ECR-EXIT universe dropped both of these.
        self.assertEqual({2, 3}, set(out))
        self.assertEqual("ineligible", out[2]["espn_status"])
        self.assertEqual("RB", out[2]["pos"])
        self.assertEqual("absent", out[3]["espn_status"])
        self.assertEqual("TE", out[3]["pos"])

    def test_espn_priced_players_are_never_duplicated(self):
        # Negative: a priced player listed again as ineligible (or keyed by
        # the fixture) must not get a second, zero row.
        espn_csv = _csv([{"player": "Priced Star", "pos": "WR", "eligible": "False"}])
        fixture = _fixture({"priced star": 1})
        espn_med = {1: {"comps": {"rec": 1.0}, "pos": "WR", "team": "BUF"}}
        out = bake_players.espn_zero_universe(espn_csv, fixture, espn_med, _reg())
        self.assertNotIn(1, out)

    def test_unresolvable_and_non_skill_identities_are_excluded(self):
        # Negative: unknown names never get guessed keys; K/DST keys in the
        # fixture are not skill rows (they are baked from ESPN K/DST files).
        espn_csv = _csv([{"player": "Nobody Known", "pos": "WR", "eligible": "False"}])
        fixture = _fixture({"some kicker": 4, "ghost": 999})
        out = bake_players.espn_zero_universe(espn_csv, fixture, {}, _reg())
        self.assertEqual({}, out)

    def test_missing_fixture_falls_back_to_csv_only(self):
        espn_csv = _csv([{"player": "Ir Back", "pos": "RB", "eligible": "False"}])
        out = bake_players.espn_zero_universe(espn_csv, "/nonexistent.json", {}, _reg())
        self.assertEqual({2}, set(out))


if __name__ == "__main__":
    unittest.main()
