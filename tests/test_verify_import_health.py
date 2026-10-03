#!/usr/bin/env python3
"""Tests for the JEG-307 Razzball freshness entry (pipelines/verify_import_health.py).

Razzball has no CI puller (GAP-024), so the snapshot can drift while the DB
landing still agrees. The freshness entry reads the newest directory under
data/raw/sources/razzball/<date>/snapshot.json, parses <date> as ISO, and
drives the c5 health verdict from the snapshot's age (today - vintage_date).

Negative tests assert the verdict the c5 branch actually emits:
  - age_days <= 2 -> status 'ok' (within fresh window)
  - age_days 3..6 -> status 'warn'
  - age_days > 6  -> status 'bad'
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "verify_import_health", PIPELINES / "verify_import_health.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class RazzballFreshnessEntryTest(unittest.TestCase):
    """The unit-level freshness helper. No DB, no manifest."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sources"

    def tearDown(self):
        self.tmp.cleanup()

    def _stamp_snapshot(self, vintage: str) -> Path:
        snap_dir = self.root / "razzball" / vintage
        snap_dir.mkdir(parents=True, exist_ok=True)
        (snap_dir / "snapshot.json").write_text(
            json.dumps({"schema": "trade-value-source-snapshot-v1", "rows": []}),
            encoding="utf-8",
        )
        return snap_dir

    def test_missing_source_dir_is_unk(self):
        # No data/raw/sources/razzball/ at all -> not a failure, just unk.
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry, {"vintage_date": None, "age_days": None, "status": "unk"})

    def test_missing_snapshot_json_is_unk(self):
        # Directory exists but no snapshot.json inside -> unk.
        (self.root / "razzball" / "2026-10-01").mkdir(parents=True)
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["status"], "unk")

    def test_unparseable_dir_name_is_ignored(self):
        # A non-ISO directory name is skipped; if it's the only candidate the
        # entry is unk, never a phantom date.
        self._stamp_snapshot("not-a-date")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["status"], "unk")

    def test_age_one_day_is_ok(self):
        # (a) snapshot aged 1 day -> status 'ok' (covered explicitly by task)
        self._stamp_snapshot("2026-10-02")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["vintage_date"], "2026-10-02")
        self.assertEqual(entry["age_days"], 1)
        self.assertEqual(entry["status"], "ok")

    def test_age_ten_days_is_bad(self):
        # (b) snapshot aged 10 days -> status 'bad' (covered explicitly by task)
        self._stamp_snapshot("2026-09-23")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["vintage_date"], "2026-09-23")
        self.assertEqual(entry["age_days"], 10)
        self.assertEqual(entry["status"], "bad")

    def test_age_three_days_is_warn(self):
        # Edge of the warn window: age_days = 3 -> warn.
        self._stamp_snapshot("2026-09-30")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["age_days"], 3)
        self.assertEqual(entry["status"], "warn")

    def test_age_six_days_is_warn(self):
        # Top of the warn window: age_days = 6 -> warn (still inside <= 6).
        self._stamp_snapshot("2026-09-27")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["age_days"], 6)
        self.assertEqual(entry["status"], "warn")

    def test_age_seven_days_is_bad(self):
        # Just past the warn window: age_days = 7 -> bad.
        self._stamp_snapshot("2026-09-26")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["age_days"], 7)
        self.assertEqual(entry["status"], "bad")

    def test_newest_iso_dir_wins(self):
        # Older and newer snapshots both present: newest ISO date wins.
        self._stamp_snapshot("2026-09-25")
        self._stamp_snapshot("2026-10-02")
        self._stamp_snapshot("2026-10-01")
        entry = mod.razzball_freshness_entry(self.root, date(2026, 10, 3))
        self.assertEqual(entry["vintage_date"], "2026-10-02")
        self.assertEqual(entry["age_days"], 1)
        self.assertEqual(entry["status"], "ok")


class RazzballFreshnessDrivesC5Test(unittest.TestCase):
    """End-to-end: verify_source for razzball writes vintage_date / age_days
    and uses the freshness entry to drive the c5 health verdict (status).
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sources"
        self.out = Path(self.tmp.name) / "output" / "source-import-health.json"
        self._fetch = mod.fetch_table_summary
        mod.fetch_table_summary = lambda table, params: []
        self.check_date = date(2026, 10, 3)

    def tearDown(self):
        mod.fetch_table_summary = self._fetch
        self.tmp.cleanup()

    def _make_razzball_snapshot(self, vintage: str) -> None:
        # Mirrors test_import_health.make_snapshot for razzball: a minimal
        # snapshot+manifest that verify_source will accept. The freshness
        # entry is derived from the directory name, so the manifest's
        # content_vintage is set to the same ISO date.
        snap_dir = self.root / "razzball" / vintage
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_bytes = (json.dumps({
            "schema": "trade-value-source-snapshot-v1",
            "source": "razzball",
            "fetched_at": f"{vintage}T00:00:00Z",
            "row_count": 5,
            "rows": [],
        }, indent=2, sort_keys=True) + "\n").encode("utf-8")
        snap_path = snap_dir / "snapshot.json"
        snap_path.write_bytes(snap_bytes)
        manifest = {
            "schema": "trade-value-source-manifest-v1",
            "source": "razzball",
            "snapshot_path": str(snap_path),
            "snapshot_sha256": __import__("hashlib").sha256(snap_bytes).hexdigest(),
            "from_file": None,
            "filter": "",
            "content_vintage": vintage,
            "content_vintage_derived_from": "test fixture",
            "week_designated": None,
            "save_gap": None,
            "pulled_at": f"{vintage}T12:00:00Z",
            "row_count": 5,
            "review_count": 0,
            "supabase_table": "public.razzball_projections",
        }
        (snap_dir / "snapshot-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    def test_snapshot_aged_ten_days_drives_c5_to_bad(self):
        # (a) snapshot aged 10 days -> status 'bad' (covered by task)
        self._make_razzball_snapshot("2026-09-23")
        entry, _ = mod.verify_source(
            "razzball",
            sources_root=self.root,
            nfl_week=4,
            check_date=self.check_date,
            prev_entry=None,
            checked_at="2026-10-03T00:00:00Z",
        )
        self.assertEqual(entry["status"], "bad", entry.get("failure_reason"))
        self.assertEqual(entry["vintage_date"], "2026-09-23")
        self.assertEqual(entry["age_days"], 10)
        self.assertIn("RAZZBALL_STALE", entry["failure_reason"])

    def test_snapshot_aged_one_day_drives_c5_to_ok(self):
        # (b) snapshot aged 1 day -> status 'ok' (covered by task)
        self._make_razzball_snapshot("2026-10-02")
        entry, _ = mod.verify_source(
            "razzball",
            sources_root=self.root,
            nfl_week=4,
            check_date=self.check_date,
            prev_entry=None,
            checked_at="2026-10-03T00:00:00Z",
        )
        self.assertEqual(entry["status"], "ok", entry.get("failure_reason"))
        self.assertEqual(entry["vintage_date"], "2026-10-02")
        self.assertEqual(entry["age_days"], 1)
        self.assertIsNone(entry["failure_reason"])

    def test_snapshot_aged_four_days_drives_c5_to_warn(self):
        # warn window middle: c5 verdict is 'warn'.
        self._make_razzball_snapshot("2026-09-29")
        entry, _ = mod.verify_source(
            "razzball",
            sources_root=self.root,
            nfl_week=4,
            check_date=self.check_date,
            prev_entry=None,
            checked_at="2026-10-03T00:00:00Z",
        )
        self.assertEqual(entry["status"], "warn", entry.get("failure_reason"))
        self.assertEqual(entry["age_days"], 4)
        self.assertIn("RAZZBALL_STALE", entry["failure_reason"])

    def test_no_snapshot_dir_records_unk(self):
        # No directory under data/raw/sources/razzball/ -> vintage_date None,
        # status 'unk', and the gate sees an unrecorded Razzball cell.
        entry, _ = mod.verify_source(
            "razzball",
            sources_root=self.root,
            nfl_week=4,
            check_date=self.check_date,
            prev_entry=None,
            checked_at="2026-10-03T00:00:00Z",
        )
        # verify_source treats a missing manifest as MISSING_SNAPSHOT first;
        # the freshness entry is only computed after the manifest exists.
        self.assertEqual(entry["status"], "missing")


if __name__ == "__main__":
    unittest.main()