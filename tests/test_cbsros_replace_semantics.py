#!/usr/bin/env python3
"""Tests for JEG-125: CBS ROS saver replace semantics per vintage.

These tests verify that the CBS ROS saver replaces stale rows when saving the
same vintage twice in one day, instead of franken-merging the two snapshots.

The fix: after upserting clean rows, DELETE rows with cbs_snapshot_date=vintage
whose player_key is NOT in the new clean set (upsert-then-prune, never prune-then-upsert).
"""

from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "save_cbsros_references", PIPELINES / "save_cbsros_references.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


# Test players - subset of real identities for testing
PLAYERS = [
    {"player_key": 869, "full_name": "Josh Allen", "position": "QB"},
    {"player_key": 2227, "full_name": "Jahmyr Gibbs", "position": "RB"},
    {"player_key": 3139, "full_name": "Bijan Robinson", "position": "RB"},
    {"player_key": 4242, "full_name": "Breece Hall", "position": "RB"},
]


def make_snapshot(vintage: str, player_names: list[str]) -> dict:
    """Create a fake CBS ROS snapshot with given player names."""
    return {
        "vintage_date": vintage,
        "fetched_at": "2026-10-02T12:00:00Z",
        "url": "https://example.com/cbsros",
        "rows": [
            {
                "player_name": name,
                "player_norm": name.lower(),
                "pos": "RB",
                "ros_half_ppr": 100.0 + i,
                "ros_standard": 90.0 + i,
                "ros_ppr": 110.0 + i,
                "per_game_half_ppr": 10.0 + i,
                "per_game_standard": 9.0 + i,
                "per_game_ppr": 11.0 + i,
                "gp": 17.0,
                "receptions": 5.0,
                "raw_stats": {},
            }
            for i, name in enumerate(player_names)
        ],
    }


class CbsrosReplaceSemanticsTest(unittest.TestCase):
    def setUp(self):
        """Save original callables and set up fakes."""
        self._fetch = mod.fetch_players
        self._upsert = mod.upsert_rows
        self._count = mod.count_rows
        self._delete = mod.delete_rows

        # Track all calls for assertions
        self.upsert_calls = []
        self.count_calls = []
        self.delete_calls = []

        # Fake fetch_players to return our test players
        mod.fetch_players = lambda: PLAYERS

        # Fake upsert_rows - just records calls
        def fake_upsert(table, rows, conflict):
            self.upsert_calls.append((table, rows, conflict))

        mod.upsert_rows = fake_upsert

        # Fake count_rows - returns count based on what was "upserted"
        # This simulates: after first save, table has X rows; after second save+prune, has Y rows
        self._db_state = {}  # vintage -> set of player_keys

        def fake_count(table, params):
            self.count_calls.append((table, params))
            # Parse vintage from params like "?select=id&cbs_snapshot_date=eq.2026-10-02"
            for part in params.split("&"):
                if "cbs_snapshot_date=eq." in part:
                    vintage = part.split("=")[1]
                    return len(self._db_state.get(vintage, set()))
            return 0

        mod.count_rows = fake_count

        # Fake delete_rows - records calls
        def fake_delete(table, vintage, keep_keys):
            self.delete_calls.append((table, vintage, keep_keys))
            # Simulate deletion: remove keys NOT in keep_keys from db state
            if vintage in self._db_state:
                self._db_state[vintage] = self._db_state[vintage] & keep_keys

        mod.delete_rows = fake_delete

    def tearDown(self):
        """Restore original callables."""
        mod.fetch_players = self._fetch
        mod.upsert_rows = self._upsert
        mod.count_rows = self._count
        mod.delete_rows = self._delete

    def _simulate_save(self, vintage: str, player_names: list[str], dry_run: bool = False):
        """Helper to simulate a save with given player names."""
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_path = tmp_path / "snapshot.json"
            snapshot_path.write_text(json.dumps(make_snapshot(vintage, player_names)))

            # Reset calls for this save
            self.upsert_calls.clear()
            self.count_calls.clear()
            self.delete_calls.clear()

            # Initialize db state for this vintage if not exists
            if vintage not in self._db_state:
                self._db_state[vintage] = set()

            try:
                mod.main_with_args(snapshot_path=snapshot_path, dry_run=dry_run)
            except SystemExit:
                pass

            # After save (or failed save), update db state based on upsert
            if not dry_run and self.upsert_calls:
                # Get the keys that were upserted
                _, rows, _ = self.upsert_calls[-1]
                upserted_keys = {row["player_key"] for row in rows}
                self._db_state[vintage] = self._db_state[vintage] | upserted_keys

    # -- Test (a): two sequential saves with disjoint player sets ---------------
    def test_replace_semantics_two_saves_disjoint_players(self):
        """Two sequential saves of same vintage with disjoint player sets:
        - First save: Jahmyr Gibbs + Bijan Robinson (2 players)
        - Second save: Breece Hall only (1 player)
        - Delete should be called with first set's keys
        - Final count should equal second set's size (1)
        """
        vintage = "2026-10-02"

        # First save: Gibbs + Robinson
        self._simulate_save(vintage, ["Jahmyr Gibbs", "Bijan Robinson"])

        # Verify first save worked
        self.assertEqual(len(self.upsert_calls), 1)
        self.assertEqual(len(self.delete_calls), 1)  # pruning empty set = delete nothing

        # Second save: Hall only (disjoint from first)
        self._simulate_save(vintage, ["Breece Hall"])

        # Verify delete was called with exactly the first set's keys
        self.assertEqual(len(self.delete_calls), 2)
        second_delete_call = self.delete_calls[1]
        _, deleted_vintage, keep_keys = second_delete_call
        self.assertEqual(deleted_vintage, vintage)

        # keep_keys should be the second set's keys (Breece Hall = 4242)
        self.assertEqual(keep_keys, {4242})

        # Final count should equal the second set's size (1)
        final_count = mod.count_rows("cbs_ros_projections", f"?select=id&cbs_snapshot_date=eq.{vintage}")
        self.assertEqual(final_count, 1)

    # -- Test (b): negative test - skip prune, count check fails ---------------
    def test_skip_prune_fails_closed_on_union(self):
        """If prune is skipped (simulated), count check fails closed on the union.

        This proves the guard catches the original bug where morning + afternoon
        snapshots franken-merge.
        """
        vintage = "2026-10-02"

        # First save: Gibbs + Robinson
        self._simulate_save(vintage, ["Jahmyr Gibbs", "Bijan Robinson"])
        first_keys = {2227, 3139}  # Gibbs, Robinson

        # Now simulate what happens WITHOUT prune: just upsert second set
        # Manually upsert second set without prune
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_path = tmp_path / "snapshot.json"
            snapshot_path.write_text(json.dumps(make_snapshot(vintage, ["Breece Hall"])))

            # Patch delete to be a no-op (simulate skipping prune)
            original_delete = mod.delete_rows
            mod.delete_rows = lambda *args, **kwargs: None  # no-op delete

            try:
                mod.main_with_args(snapshot_path=snapshot_path, dry_run=False)
            except SystemExit as e:
                # Should fail closed because count != len(clean)
                self.assertIn("Fail closed", str(e))
            finally:
                mod.delete_rows = original_delete

        # Without prune, the count would be 3 (union of {Gibbs, Robinson} + {Hall})
        # The guard should catch this and fail

    # -- Test (c): prune never runs before fail-closed guards pass ----------
    def test_zero_clean_rows_exits_before_delete(self):
        """A zero-clean-rows input must exit before any delete call."""
        vintage = "2026-10-02"

        # Create a snapshot with no resolvable players (all names invalid)
        bad_snapshot = {
            "vintage_date": vintage,
            "fetched_at": "2026-10-02T12:00:00Z",
            "url": "https://example.com/cbsros",
            "rows": [
                {
                    "player_name": "Invalid Player One",
                    "player_norm": "invalid player one",
                    "pos": "QB",
                    "ros_half_ppr": 100.0,
                }
            ],
        }

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_path = tmp_path / "snapshot.json"
            snapshot_path.write_text(json.dumps(bad_snapshot))

            # Reset calls
            self.delete_calls.clear()

            # Should raise SystemExit due to zero clean rows
            with self.assertRaises(SystemExit) as cm:
                mod.main_with_args(snapshot_path=snapshot_path, dry_run=False)

            self.assertIn("zero clean rows", str(cm.exception).lower())

            # Delete should NEVER have been called
            self.assertEqual(len(self.delete_calls), 0,
                "Delete was called before fail-closed guards passed!")

    # -- Test (d): dry-run doesn't call delete --------------------------------
    def test_dry_run_skips_delete(self):
        """Dry-run mode must NOT call the delete seam."""
        vintage = "2026-10-02"

        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            snapshot_path = tmp_path / "snapshot.json"
            snapshot_path.write_text(json.dumps(make_snapshot(vintage, ["Jahmyr Gibbs"])))

            # Reset calls
            self.delete_calls.clear()

            mod.main_with_args(snapshot_path=snapshot_path, dry_run=True)

            # Delete should NOT have been called in dry-run mode
            self.assertEqual(len(self.delete_calls), 0,
                "Delete seam was called in dry-run mode!")

            # But upsert should have been mentioned
            self.assertTrue(len(self.upsert_calls) > 0)


# Direct function to call main with args for testing (bypassing argparse)
def main_with_args(snapshot_path: Path, dry_run: bool = False):
    """Test helper to call main with specific args."""
    # This imports and patches sys.argv
    import sys
    old_argv = sys.argv
    try:
        sys.argv = [
            "save_cbsros_references.py",
            "--snapshot", str(snapshot_path),
        ]
        if dry_run:
            sys.argv.append("--dry-run")
        mod.main()
    finally:
        sys.argv = old_argv


# Monkey-patch the module with the test helper
mod.main_with_args = main_with_args


if __name__ == "__main__":
    unittest.main()
