"""Regression tests for the ECR bake intake (JEG-46).

Cause 1: fp_season_latest_norm has no `id` column, so get_all()'s default
`order=id` 400s. The intake must order explicitly on player_key.
Cause 2: the norm table went stale (writer not run since 2026-09-22) and the
bake silently produced zero ECR rows. The intake must fail closed when the
norm table has no rows at the current ECR snapshot date.

Discrimination: each test is written against the fixed fetch_ecr_intake();
the pre-fix behavior (no explicit order, silent empty intake) fails them.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import bake_players


def _row(key, date="2026-10-01"):
    return {"player_key": key, "player_norm": f"player {key}",
            "position": "WR", "team": "KC", "passing_yards": 0,
            "passing_tds": 0, "rushing_yards": 0, "rushing_tds": 0,
            "receptions": 5, "receiving_yards": 60, "receiving_tds": 0.5}


class FakeQueryAll:
    """Captures (table, params); serves canned snapshot + norm rows."""

    def __init__(self, snapshot_date="2026-10-01", norm_rows=None):
        self.calls = []
        self.snapshot_date = snapshot_date
        self.norm_rows = norm_rows if norm_rows is not None else [_row(1)]

    def __call__(self, table, params):
        self.calls.append((table, params))
        if table == "fp_season_projections":
            return [{"snapshot_date": self.snapshot_date}]
        return list(self.norm_rows)


class TestEcrIntake(unittest.TestCase):
    def test_explicit_order_on_norm_table(self):
        """The norm-table query must carry an explicit order= — never rely on
        get_all()'s order=id default (the table has no id column)."""
        fake = FakeQueryAll(norm_rows=[_row(2), _row(1)])
        bake_players.fetch_ecr_intake(fake)
        norm_calls = [c for c in fake.calls if c[0] == "fp_season_latest_norm"]
        self.assertEqual(len(norm_calls), 1)
        params = norm_calls[0][1]
        self.assertIn("order=player_key", params)
        self.assertNotIn("order=id", params)

    def test_empty_norm_table_fails_closed(self):
        """Zero rows at the current ECR snapshot date must abort the bake,
        not silently bake a chart with no expert intake."""
        fake = FakeQueryAll(norm_rows=[])
        with self.assertRaises(SystemExit) as cm:
            bake_players.fetch_ecr_intake(fake)
        self.assertIn("FAIL-CLOSED", str(cm.exception))
        self.assertIn("2026-10-01", str(cm.exception))

    def test_empty_projections_fails_closed(self):
        fake = FakeQueryAll()
        fake.snapshot_date = None

        def _empty(table, params):
            fake.calls.append((table, params))
            return []

        with self.assertRaises(SystemExit) as cm:
            bake_players.fetch_ecr_intake(_empty)
        self.assertIn("FAIL-CLOSED", str(cm.exception))

    def test_happy_path_returns_date_and_rows(self):
        rows = [_row(7), _row(3)]
        fake = FakeQueryAll(norm_rows=rows)
        date, got = bake_players.fetch_ecr_intake(fake)
        self.assertEqual(date, "2026-10-01")
        self.assertEqual(got, rows)
        # intake pins the norm table to the projections snapshot date
        norm_params = [c[1] for c in fake.calls
                       if c[0] == "fp_season_latest_norm"][0]
        self.assertIn("snapshot_date=eq.2026-10-01", norm_params)


if __name__ == "__main__":
    unittest.main()
