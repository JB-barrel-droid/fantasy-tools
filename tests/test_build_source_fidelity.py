#!/usr/bin/env python3
"""Tests for pipelines/build_source_fidelity.py native-field selection.

The fidelity builder compares each source's fixture natives against the raw
snapshot. For "reindexed-as-given" sources the published value IS the native,
so the builder must read the snapshot's `native_value` field -- not the
transformed `value` field -- for sources whose fixture was baked from published
values.

Regression (2026-10-04): the usatoday fixture section was corrected to genuine
published native_value ("were transformed value" per the fixture promotion
notes; 227/227 fixture natives match the snapshot's native_value, only 3/227
match `value`), but NATIVE_FIELD still mapped usatoday -> `value`, so a healthy
fixture false-redded 46/46. The tests below fail on the old mapping and pass
on the fixed one.

All tests use synthetic snapshots in a tmp dir. No network, no repo I/O.
"""
from __future__ import annotations

import json
import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "pipelines"))
import build_source_fidelity as bsf  # noqa: E402


def _write_snapshot(root, src, dated, rows):
    d = os.path.join(root, "data", "raw", "sources", src, dated)
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, "snapshot.json"), "w", encoding="utf-8") as f:
        json.dump({"rows": rows}, f)
    return d


class NativeFieldSelectionTest(unittest.TestCase):
    def setUp(self):
        # tmp tree standing in for the repo; patch the module's RAW_DIR so
        # find_latest_snapshot / load_snapshot_natives read synthetic data.
        import tempfile
        from pathlib import Path

        self._tmp = tempfile.TemporaryDirectory()
        self._old_raw_dir = bsf.RAW_DIR
        bsf.RAW_DIR = Path(self._tmp.name) / "data" / "raw" / "sources"

    def tearDown(self):
        bsf.RAW_DIR = self._old_raw_dir
        self._tmp.cleanup()

    def _rows(self):
        # native_value (published) and value (transformed) deliberately differ.
        return [
            {"player_name": "Jahmyr Gibbs", "scoring": "ppr",
             "native_value": 77.0, "value": 68.095},
            {"player_name": "Bijan Robinson", "scoring": "ppr",
             "native_value": 71.0, "value": 49.515},
        ]

    def test_usatoday_reads_published_native_value(self):
        """usatoday fixture natives are published values; the builder must
        compare against native_value. Fails on the old `value` mapping."""
        _write_snapshot(self._tmp.name, "usatoday", "2026-09-29", self._rows())
        natives, vintage = bsf.load_snapshot_natives("usatoday")
        self.assertEqual(vintage, "2026-09-29")
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 77.0)
        self.assertEqual(natives[("bijan robinson", "ppr")], 71.0)
        # Guard against silently reading the transformed field instead.
        self.assertNotEqual(natives[("jahmyr gibbs", "ppr")], 68.095)

    def test_fantasypros_still_reads_native_value(self):
        """Locks the existing fantasypros mapping (flattening fix, 2026-09-30)."""
        _write_snapshot(self._tmp.name, "fantasypros", "2026-09-29", self._rows())
        natives, _ = bsf.load_snapshot_natives("fantasypros")
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 77.0)

    def test_native_value_missing_falls_back_to_value(self):
        """A row with no native_value still compares against value (no data loss)."""
        rows = [{"player_name": "Jahmyr Gibbs", "scoring": "ppr", "value": 68.095}]
        _write_snapshot(self._tmp.name, "usatoday", "2026-09-29", rows)
        natives, _ = bsf.load_snapshot_natives("usatoday")
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 68.095)

    def test_cbs_still_reads_value(self):
        """cbs was not part of the native_value correction; mapping unchanged."""
        _write_snapshot(self._tmp.name, "cbs", "week-4", self._rows())
        natives, _ = bsf.load_snapshot_natives("cbs")
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 68.095)


if __name__ == "__main__":
    unittest.main()
