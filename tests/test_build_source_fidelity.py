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


class FakeSbclient:
    """Minimal stub of the Supabase client for cbsros DB tests."""

    def __init__(self, dates, rows, fail=False):
        self._dates = dates
        self._rows = rows
        self._fail = fail

    def get_all(self, table, params=""):
        if self._fail:
            raise RuntimeError("network down")
        if "cbs_snapshot_date&order" in params:
            return self._dates
        return self._rows


class CbsrosDbReferenceTest(unittest.TestCase):
    """Regression (2026-10-04): cbsros is DB-backed since 2026-10-01, so the
    fidelity check must compare the fixture against the Supabase table -- not
    the local file. The file held the 20:12 UTC export while the DB/fixture
    had the 21:21 UTC update; comparing against the file false-redded 50/50
    on a healthy fixture. These tests fail if load_snapshot_natives("cbsros")
    reads the file instead of the DB.
    """

    def test_cbsros_prefers_db_over_file(self):
        """DB data wins even when a (stale) file snapshot exists."""
        import tempfile
        from pathlib import Path

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        old_raw = bsf.RAW_DIR
        bsf.RAW_DIR = Path(tmp.name) / "data" / "raw" / "sources"
        self.addCleanup(setattr, bsf, "RAW_DIR", old_raw)
        # Stale file: Gibbs 24.857 (the 20:12 UTC export).
        d = os.path.join(tmp.name, "data", "raw", "sources", "cbsros", "2026-10-02")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "snapshot.json"), "w", encoding="utf-8") as f:
            json.dump({"rows": [
                {"player_norm": "jahmyr gibbs", "per_game_ppr": 24.857,
                 "per_game_half_ppr": 22.607, "per_game_standard": 20.357},
            ]}, f)
        # DB: Gibbs 25.657 (the 21:21 UTC update the fixture was built from).
        fake = FakeSbclient(
            dates=[{"cbs_snapshot_date": "2026-10-02"}],
            rows=[{"player_norm": "jahmyr gibbs", "per_game_ppr": 25.657,
                   "per_game_half_ppr": 23.407, "per_game_standard": 21.0}],
        )
        natives, vintage = bsf.load_cbsros_db_natives(sbclient=fake)
        self.assertEqual(vintage, "2026-10-02")
        # Must be the DB value, not the stale file value.
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 25.657)
        self.assertNotEqual(natives[("jahmyr gibbs", "ppr")], 24.857)

    def test_cbsros_db_failure_warns_instead_of_false_bad(self):
        """DB unreachable -> empty (warn "cannot verify"), never the file.

        Falling back to the file would reintroduce the false-red: a stale
        file reads as a broken fixture.
        """
        fake = FakeSbclient(dates=[], rows=[], fail=True)
        natives, vintage = bsf.load_cbsros_db_natives(sbclient=fake)
        self.assertEqual(natives, {})
        self.assertIsNone(vintage)

    def test_cbsros_db_empty_warns(self):
        """DB returns no rows -> empty (warn), not a fabricated comparison."""
        fake = FakeSbclient(dates=[{"cbs_snapshot_date": "2026-10-02"}], rows=[])
        natives, vintage = bsf.load_cbsros_db_natives(sbclient=fake)
        self.assertEqual(natives, {})
        self.assertIsNone(vintage)

    def test_load_snapshot_natives_routes_cbsros_to_db(self):
        """load_snapshot_natives('cbsros') must use the DB loader, never the
        file. Fails if the branch reads find_latest_snapshot instead."""
        calls = []
        orig = bsf.load_cbsros_db_natives
        def spy(sbclient=None):
            calls.append(True)
            return {("jahmyr gibbs", "ppr"): 25.657}, "2026-10-02"
        bsf.load_cbsros_db_natives = spy
        try:
            natives, vintage = bsf.load_snapshot_natives("cbsros")
        finally:
            bsf.load_cbsros_db_natives = orig
        self.assertTrue(calls, "cbsros branch did not call the DB loader")
        self.assertEqual(natives[("jahmyr gibbs", "ppr")], 25.657)
        self.assertEqual(vintage, "2026-10-02")


if __name__ == "__main__":
    unittest.main()
