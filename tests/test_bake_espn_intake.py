"""Regression tests for the ESPN bake intake (JEG-ECR-EXIT, 2026-10-05).

The ESPN intake is the PRIMARY leg of the bake (replaces full-season ECR
as of JEG-ECR-EXIT). ESPN is already rest-of-season, so no snapshot_date /
content-vintage gate applies. These tests verify:

  1. The intake reads the CSV row by row, captures priced components into
     a {player_key: {comp: value}} comps dict, and stores pos/team so the
     main loop can iterate without re-querying.
  2. Components missing from the CSV default to 0.0 in espn_ros_comps —
     never KeyError (fantasy_points() treats missing keys as 0).
  3. espn_snapshot_date is taken as the MAX espn_snapshot_date across rows
     (never the wall-clock — the CSV carries its own date).
  4. Zero-priced skill players (no eligible rows, all components blank) fail
     closed with "FAIL-CLOSED" — the bake never silently publishes a chart
     with no primary-leg input.
  5. Unresolvable player names (canonical_players returns None) are
     skipped silently with an unresolved counter — never guessed.

Discrimination: each test is written against fetch_espn_intake()'s contract;
a regression (e.g. reverting to fp_season_latest_norm, dropping the
fail-closed gate) trips one of these.
"""
import csv
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import bake_players


def _row(player, pos, team, **comps):
    """Build one ESPN CSV row, blank-rendering zero values for comps."""
    cols = {
        "player": player, "pos": pos, "team": team,
        "eligible": "True",
        "espn_snapshot_date": "2026-10-03",
    }
    cols.update({
        "r_pass_yds": "", "r_pass_tds": "", "r_rush_yds": "",
        "r_rush_tds": "", "r_receptions": "", "r_rec_yds": "",
        "r_rec_tds": "",
    })
    for csv_col, val in comps.items():
        cols[csv_col] = str(val)
    return cols


def _write_csv(rows):
    """Write a temp ESPN CSV with the rows; return the path."""
    cols = ["player", "pos", "team", "eligible", "espn_snapshot_date",
            "r_pass_yds", "r_pass_tds", "r_rush_yds", "r_rush_tds",
            "r_receptions", "r_rec_yds", "r_rec_tds"]
    fd, p = tempfile.mkstemp(suffix=".csv", text=True)
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, "") for c in cols})
    return p


def _reg():
    """Return a registry that resolves 'Test Player' -> 777 skill.

    Test Player is registered as QB so position-conflict resolution accepts
    a QB row in the CSV. Other Player is an RB so the position conflict
    path can be exercised if a test needs it.
    """
    return bake_players.load_registry(rows=[
        {"player_key": 777, "id": "u1", "full_name": "Test Player",
         "position": "QB", "active": True, "team_id": 1},
        {"player_key": 888, "id": "u2", "full_name": "Other Player",
         "position": "RB", "active": True, "team_id": 2},
    ])


class TestEspnIntake(unittest.TestCase):
    def test_loads_components(self):
        path = _write_csv([_row(
            "Test Player", "QB", "KC",
            r_pass_yds=250, r_pass_tds=2, r_rush_yds=20)])
        med, snap = bake_players.fetch_espn_intake(path, _reg())
        self.assertEqual(snap, "2026-10-03")
        self.assertIn(777, med)
        self.assertEqual(med[777]["comps"]["passing_yards"], 250.0)
        self.assertEqual(med[777]["comps"]["passing_tds"], 2.0)
        self.assertEqual(med[777]["comps"]["rushing_yards"], 20.0)
        self.assertEqual(med[777]["pos"], "QB")
        self.assertEqual(med[777]["team"], "KC")

    def test_missing_components_default_to_zero(self):
        """A QB row with only pass_yds/rates has no rushing/receiving
        comps in the CSV. fetch_espn_intake() must still emit an entry;
        the main loop builds espn_ros_comps with .get(c, 0.0) for the
        rest. fantasy_points() also defaults to 0 via stats.get(k, 0.0)."""
        path = _write_csv([_row(
            "Test Player", "QB", "BUF",
            r_pass_yds=3163.3, r_pass_tds=20.7)])
        med, _ = bake_players.fetch_espn_intake(path, _reg())
        self.assertIn(777, med)
        self.assertEqual(med[777]["comps"]["passing_yards"], 3163.3)
        self.assertEqual(med[777]["comps"]["passing_tds"], 20.7)
        # No rushing/receiving comps at all -> missing components default
        # to 0.0 in the main loop, never KeyError.
        self.assertNotIn("rushing_yards", med[777]["comps"])

    def test_snapshot_date_is_max(self):
        """A heterogeneous CSV (mixed dates) must report the MAX date,
        not the wall-clock or the first-row date."""
        rows = [_row("Test Player", "QB", "BUF",
                     r_pass_yds=100, r_pass_tds=1,
                     espn_snapshot_date="2026-09-30"),
                _row("Other Player", "RB", "DET",
                     r_rush_yds=200, r_rush_tds=2,
                     espn_snapshot_date="2026-10-03")]
        path = _write_csv(rows)
        _, snap = bake_players.fetch_espn_intake(path, _reg())
        self.assertEqual(snap, "2026-10-03")

    def test_empty_intake_fails_closed(self):
        """Zero eligible rows must abort, not bake a chart with no
        primary-leg input. JEG-ECR-EXIT: the prior ECR intake failed
        closed on stale fp_season_latest_norm rows; ESPN fails closed
        on a priced-zero intake (no NPC projections to set the blend)."""
        path = _write_csv([])  # header only
        with self.assertRaises(SystemExit) as cm:
            bake_players.fetch_espn_intake(path, _reg())
        self.assertIn("FAIL-CLOSED", str(cm.exception))

    def test_unresolvable_name_skipped_not_guessed(self):
        """Names the canonical registry can't place (wrong spelling,
        unlisted) are skipped with an unresolved counter — never guessed
        to a key. Fail-closed on missing primary input still holds: zero
        priced players after the unresolved skip aborts the bake."""
        path = _write_csv([_row(
            "Not In Registry", "WR", "KC",
            r_rec_yds=60, r_rec_tds=0.5, r_receptions=5)])
        with self.assertRaises(SystemExit) as cm:
            bake_players.fetch_espn_intake(path, _reg())
        self.assertIn("FAIL-CLOSED", str(cm.exception))

    def test_unpriced_row_skipped_not_guessed(self):
        """A row with eligible=True but every comp blank is dropped
        (n_unpriced counter); never priced to zero across all 7 components."""
        path = _write_csv([
            _row("Test Player", "WR", "KC"),  # eligible=True, all comps blank
        ])
        with self.assertRaises(SystemExit) as cm:
            bake_players.fetch_espn_intake(path, _reg())
        self.assertIn("FAIL-CLOSED", str(cm.exception))


if __name__ == "__main__":
    unittest.main()