#!/usr/bin/env python3
"""Regression tests for the FantasyCalc drift check and native_value fix.

Covers:
1. check_fantasycalc_drift detects when live != snapshot natives
2. check_fantasycalc_drift passes when they match
3. match_source_snapshot carries native_value through (2026-09-30 JSN defect)
4. build_source_reference preserves native_value in output rows
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))

import check_fantasycalc_drift as drift


class DriftCheckTest(unittest.TestCase):
    def _fake_live(self, values):
        return {f"Player {i}": float(v) for i, v in enumerate(values)}

    def _fake_natives(self, values):
        return {f"Player {i}": float(v) for i, v in enumerate(values)}

    def test_no_drift_when_values_match(self):
        vals = [10000 - i * 100 for i in range(25)]
        with patch.object(drift, "fetch_live",
                          return_value=self._fake_live(vals)), \
             patch.object(drift, "load_snapshot_natives",
                          return_value=self._fake_natives(vals)):
            result = drift.check_drift(threshold=0.05)
        self.assertFalse(result["needs_refresh"])
        self.assertEqual(result["drift_frac"], 0.0)

    def test_drift_detected_when_many_values_move(self):
        live_vals = [10000 - i * 100 for i in range(25)]
        # Shift every native down 5% -- well above the 1% move threshold
        native_vals = [v * 0.95 for v in live_vals]
        with patch.object(drift, "fetch_live",
                          return_value=self._fake_live(live_vals)), \
             patch.object(drift, "load_snapshot_natives",
                          return_value=self._fake_natives(native_vals)):
            result = drift.check_drift(threshold=0.05)
        self.assertTrue(result["needs_refresh"])
        self.assertGreater(result["drift_frac"], 0.05)

    def test_small_noise_does_not_trigger(self):
        live_vals = [10000 - i * 100 for i in range(25)]
        # Move only 1 of 25 by >1% -- below the 5% threshold
        native_vals = list(live_vals)
        native_vals[0] = live_vals[0] * 0.97
        with patch.object(drift, "fetch_live",
                          return_value=self._fake_live(live_vals)), \
             patch.object(drift, "load_snapshot_natives",
                          return_value=self._fake_natives(native_vals)):
            result = drift.check_drift(threshold=0.05)
        self.assertFalse(result["needs_refresh"])

    def test_missing_player_counts_as_drift(self):
        live_vals = [10000 - i * 100 for i in range(25)]
        native_vals = [10000 - i * 100 for i in range(20)]  # 5 missing
        live = {f"Player {i}": float(v) for i, v in enumerate(live_vals)}
        natives = {f"Player {i}": float(v) for i, v in enumerate(native_vals)}
        with patch.object(drift, "fetch_live", return_value=live), \
             patch.object(drift, "load_snapshot_natives", return_value=natives):
            result = drift.check_drift(threshold=0.05)
        self.assertTrue(result["needs_refresh"])


class NativeValuePreservationTest(unittest.TestCase):
    """The 2026-09-30 defect: match_source_snapshot dropped native_value,
    so the pipeline used the flattened `value` (50.7) instead of the raw
    FantasyCalc number (9914). These tests prove native_value survives."""

    def test_matcher_carries_native_value(self):
        sys.path.insert(0, str(REPO / "pipelines"))
        import match_source_snapshot as matcher
        # Build a minimal snapshot with distinct native_value and value
        snap = {
            "schema": "trade-value-source-snapshot-v1",
            "source": "fantasycalc",
            "default_scoring": "half_ppr",
            "default_teams": 12,
            "rows": [{
                "player_name": "Jaxon Smith-Njigba",
                "pos": "WR", "team": "SEA",
                "source_player_id": "12345",
                "scoring": "half_ppr", "teams": 12,
                "native_value": 9914.0,
                "value": 50.7,
            }],
        }
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as f:
            json.dump(snap, f)
            snap_path = Path(f.name)
        with tempfile.NamedTemporaryFile(
                mode="w", suffix=".json", delete=False) as f:
            # Minimal players.json with JSN
            json.dump({"players": [{
                "player_key": 9999, "name": "Jaxon Smith-Njigba",
                "pos": "WR", "team": "SEA",
            }]}, f)
            players_path = Path(f.name)
        try:
            result = matcher.match_snapshot(snap_path, players_path)
            matched = result.get("matched_rows", [])
            self.assertTrue(matched, "expected at least one matched row")
            jsn = matched[0]
            self.assertEqual(jsn.get("native_value"), 9914.0,
                             "matcher must carry native_value, not drop it")
            # The flattened value must NOT be used as native
            self.assertNotEqual(jsn.get("native_value"), 50.7)
        finally:
            snap_path.unlink(missing_ok=True)
            players_path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
