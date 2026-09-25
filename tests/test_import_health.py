#!/usr/bin/env python3
"""Tests for pipelines/verify_import_health.py.

Each named defect the gate guards is negative-tested: a missing snapshot,
a stale week-designated vintage, a manifest sha mismatch, Supabase table
drift (row count and vintage), and a vintage-less manifest all produce the
right status + failure code and a non-zero exit. Supabase access is injected
via the module-level fetch_table_summary callable, so these run offline with
recorded fixtures.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import io
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "verify_import_health", PIPELINES / "verify_import_health.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

DB_SOURCES = ("fantasycalc", "usatoday", "fantasypros", "espn", "cbs")

SOURCE_TABLES = {
    "fantasycalc": "public.source_trade_values",
    "usatoday": "public.source_trade_values",
    "fantasypros": "public.source_trade_values",
    "espn": "public.espn_season_projections",
    "cbs": "public.cbs_trade_values",
}

SOURCE_KEYS = {
    "status",
    "last_successful_import",
    "content_vintage",
    "vintage_kind",
    "row_count",
    "supabase_table",
    "supabase_landing",
    "snapshot_path",
    "failure_reason",
}
TOP_KEYS = {"schema", "checked_at", "nfl_week", "sources"}


def make_snapshot(
    root: Path,
    source: str,
    vintage_dir: str,
    *,
    content_vintage: str,
    week_designated,
    row_count: int = 10,
    review_count: int = 0,
    vintage_note: str = "test fixture",
    record_absolute_path: bool = True,
    manifest_overrides: dict | None = None,
) -> Path:
    """Stamp a consistent (snapshot.json, snapshot-manifest.json) pair."""
    snap_dir = root / source / vintage_dir
    snap_dir.mkdir(parents=True, exist_ok=True)
    snapshot = {
        "schema": "trade-value-source-snapshot-v1",
        "source": source,
        "fetched_at": "2026-09-21T00:00:00Z",
        "row_count": row_count,
        "rows": [],
        "review_count": review_count,
        "review_rows": [],
    }
    snap_bytes = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
    snap_path = snap_dir / "snapshot.json"
    snap_path.write_bytes(snap_bytes)
    manifest = {
        "schema": "trade-value-source-manifest-v1",
        "source": source,
        "snapshot_path": str(snap_path) if record_absolute_path else "data/raw/sources/x/y/snapshot.json",
        "snapshot_sha256": hashlib.sha256(snap_bytes).hexdigest(),
        "supabase_table": SOURCE_TABLES[source],
        "from_file": None,
        "filter": (
            "select=*&source=eq.x&variant=eq.as_published (as_published only); "
            "python backstop dropped 0 ECR-flavored row(s)"
        ),
        "content_vintage": content_vintage,
        "content_vintage_derived_from": vintage_note,
        "week_designated": week_designated,
        "save_gap": None,
        "pulled_at": "2026-09-21T12:00:00Z",
        "row_count": row_count,
        "review_count": review_count,
    }
    manifest.update(manifest_overrides or {})
    (snap_dir / "snapshot-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return snap_dir


def db_rows(n: int, *, source_content_date=None, week=None, date_col="source_content_date") -> list[dict]:
    return [
        {"player_key": 1000 + i, date_col: source_content_date, "week": week}
        for i in range(n)
    ]


def table_rows_for(table: str, params: str, *, n: int, week: int | None, date: str | None) -> list[dict]:
    """Recorded table fixture dispatching on the verified per-source config."""
    if table == "espn_season_projections":
        assert "espn_snapshot_date" in params and "source=eq" not in params, params
        return db_rows(n, source_content_date=date, week=week, date_col="espn_snapshot_date")
    assert "source_content_date" in params, params
    return db_rows(n, source_content_date=date, week=week)


class VerifyImportHealthTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "sources"
        self.out = Path(self.tmp.name) / "output" / "source-import-health.json"
        self._fetch = mod.fetch_table_summary
        mod.fetch_table_summary = lambda table, params: []
        self.check_date = date(2026, 9, 21)

    def tearDown(self):
        mod.fetch_table_summary = self._fetch
        self.tmp.cleanup()

    def run_gate(self, nfl_week: int) -> tuple[int, dict, str]:
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code = mod.run_health(
                nfl_week=nfl_week,
                sources_root=self.root,
                output_path=self.out,
                check_date=self.check_date,
            )
        health = json.loads(self.out.read_text(encoding="utf-8"))
        return code, health, err.getvalue()

    def stamp_all_ok(self, nfl_week: int = 3, espn_vintage: str = "2026-09-21"):
        """Stamp fixtures where every source verifies fresh for nfl_week.

        All five sources are DB-backed (stage 1b closed): the table fixtures
        mirror each source's verified params from SOURCE_CONFIGS.
        """
        week_label = f"Week {nfl_week}"
        dated = "2026-09-22"  # an in-season date mapping to nfl_week

        def tables(table, params):
            if table == "espn_season_projections":
                return table_rows_for(table, params, n=10, week=nfl_week, date=espn_vintage)
            if table == "cbs_trade_values":
                return table_rows_for(table, params, n=10, week=nfl_week, date=None)
            if "fantasycalc" in params:
                return table_rows_for(table, params, n=10, week=nfl_week, date=None)
            return table_rows_for(table, params, n=10, week=None, date=dated)

        mod.fetch_table_summary = tables
        make_snapshot(self.root, "fantasycalc", f"week-{nfl_week}",
                      content_vintage=week_label, week_designated=nfl_week)
        for source in ("usatoday", "fantasypros"):
            make_snapshot(self.root, source, dated,
                          content_vintage=dated, week_designated=None)
        make_snapshot(self.root, "cbs", f"week-{nfl_week}",
                      content_vintage=week_label, week_designated=nfl_week)
        make_snapshot(self.root, "espn", espn_vintage,
                      content_vintage=espn_vintage, week_designated=None)

    # -- hard error: unknown / excluded sources --------------------------------
    # defect: a non-dashboard source name sneaking into the gate
    def test_unknown_and_excluded_sources_hard_error(self):
        for bad in ("ecr", "vegas", "razzball", "nflverse", "fantasypros_ecr"):
            with self.assertRaises(SystemExit, msg=bad):
                mod.check_source(bad)
        for good in ("espn", "usatoday", "fantasycalc", "fantasypros", "cbs"):
            self.assertEqual(mod.check_source(good), good)

    # -- defect 1: missing snapshot -> missing + non-zero ------------------------
    def test_missing_snapshot(self):
        code, health, err = self.run_gate(nfl_week=3)
        self.assertNotEqual(code, 0)
        for source in ("espn", "usatoday", "fantasycalc", "fantasypros", "cbs"):
            entry = health["sources"][source]
            self.assertEqual(entry["status"], "missing", source)
            self.assertTrue(entry["failure_reason"].startswith("MISSING_SNAPSHOT"), source)
            self.assertIsNone(entry["last_successful_import"], source)
            self.assertIsNone(entry["snapshot_path"], source)
        self.assertIn("GATE: RED", err)

    # -- defect 2: week-2 chart vintage with NFL_WEEK=3 -> stale + non-zero -----
    def test_week2_vintage_stale_with_nfl_week_3(self):
        mod.fetch_table_summary = lambda table, params: db_rows(10, week=2)
        make_snapshot(self.root, "fantasycalc", "week-2",
                      content_vintage="Week 2", week_designated=2)
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="2026-09-21T00:00:00Z",
        )
        self.assertEqual(entry["status"], "stale")
        self.assertTrue(entry["failure_reason"].startswith("STALE_VINTAGE"))
        self.assertIn("NFL week 3", entry["failure_reason"])
        # bytes still verified: the import landed, the vintage is old
        self.assertEqual(entry["last_successful_import"], "2026-09-21T00:00:00Z")

    def test_iso_date_maps_to_nfl_week_for_freshness(self):
        # 2026-09-15 is editorial Week 2 (verified 2026 schedule: Tue..Mon weeks)
        mod.fetch_table_summary = lambda table, params: db_rows(10, source_content_date="2026-09-15")
        make_snapshot(self.root, "usatoday", "2026-09-15",
                      content_vintage="2026-09-15", week_designated=None)
        ok_entry, _ = mod.verify_source(
            "usatoday", sources_root=self.root, nfl_week=2,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(ok_entry["status"], "ok")
        self.assertEqual(ok_entry["vintage_kind"], "source_content_date")
        stale_entry, _ = mod.verify_source(
            "usatoday", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(stale_entry["status"], "stale")
        self.assertTrue(stale_entry["failure_reason"].startswith("STALE_VINTAGE"))

    # -- defect 3: manifest sha mismatch -> failed + non-zero --------------------
    def test_byte_mismatch(self):
        mod.fetch_table_summary = lambda table, params: db_rows(10, week=3)
        snap_dir = make_snapshot(self.root, "fantasycalc", "week-3",
                                 content_vintage="Week 3", week_designated=3)
        (snap_dir / "snapshot.json").write_bytes(b'{"tampered": true}\n')
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("BYTE_MISMATCH"))

    # -- defect 4: Supabase row-count drift -> failed + non-zero -----------------
    def test_table_row_count_drift(self):
        # manifest expects 10 rows; the table now holds 8 (partial load)
        mod.fetch_table_summary = lambda table, params: db_rows(8, week=3)
        make_snapshot(self.root, "fantasycalc", "week-3",
                      content_vintage="Week 3", week_designated=3)
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
        self.assertIn("8 rows", entry["failure_reason"])

    def test_table_vintage_drift(self):
        # table reverted to Week 2 content while the manifest stamps Week 3
        mod.fetch_table_summary = lambda table, params: db_rows(10, week=2)
        make_snapshot(self.root, "fantasycalc", "week-3",
                      content_vintage="Week 3", week_designated=3)
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
        self.assertIn("Week 2", entry["failure_reason"])

    def test_multi_week_table_verifies_when_scoped_to_manifest_vintage(self):
        # defect: the gate re-queried the whole multi-week table, so a
        # retained older week read as TABLE_DRIFT. The gate now scopes the
        # re-query to the manifest's vintage; the injected fetch simulates
        # PostgREST by honoring the week=eq.N filter.
        def postgrest(table, params):
            if "week=eq.3" in params:
                return db_rows(10, source_content_date="2026-09-23", week=3)
            return (db_rows(10, source_content_date="2026-09-15", week=2)
                    + db_rows(10, source_content_date="2026-09-23", week=3))
        mod.fetch_table_summary = postgrest
        make_snapshot(self.root, "usatoday", "2026-09-23",
                      content_vintage="2026-09-23", week_designated=3)
        entry, _ = mod.verify_source(
            "usatoday", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "ok", entry["failure_reason"])
        self.assertEqual(entry["row_count"], 10)

    def test_multi_week_table_still_catches_drift_within_scoped_week(self):
        # scoping must not blind the gate: rows changed *within* the stamped
        # week still fail as TABLE_DRIFT.
        def postgrest(table, params):
            return db_rows(8, source_content_date="2026-09-23", week=3)
        mod.fetch_table_summary = postgrest
        make_snapshot(self.root, "usatoday", "2026-09-23",
                      content_vintage="2026-09-23", week_designated=3)
        entry, _ = mod.verify_source(
            "usatoday", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))

    def test_table_query_failure_fails_closed(self):
        def boom(table, params):
            raise RuntimeError("connection refused")
        mod.fetch_table_summary = boom
        make_snapshot(self.root, "fantasycalc", "week-3",
                      content_vintage="Week 3", week_designated=3)
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("IMPORT_FAILED"))

    # -- defect 5: vintage-less manifest -> failed + non-zero --------------------
    def test_vintage_less_manifest(self):
        mod.fetch_table_summary = lambda table, params: db_rows(10, week=3)
        make_snapshot(self.root, "fantasycalc", "mystery",
                      content_vintage="sometime last week", week_designated=None)
        entry, _ = mod.verify_source(
            "fantasycalc", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("NO_VINTAGE"))
        self.assertEqual(entry["vintage_kind"], "unknown")

    # -- stage 1b closed: espn/cbs are DB-backed, no gap lines -------------------
    # defect: the old file-backed gap silently surviving the table migration
    def test_all_db_backed_no_gap_lines(self):
        self.stamp_all_ok(nfl_week=3)
        code, health, err = self.run_gate(nfl_week=3)
        self.assertEqual(code, 0, err)
        for source in DB_SOURCES:
            entry = health["sources"][source]
            self.assertEqual(entry["status"], "ok", source)
            self.assertTrue(entry["supabase_landing"], source)
            self.assertEqual(entry["supabase_table"], SOURCE_TABLES[source], source)
        self.assertNotIn("GAP", err)
        self.assertNotIn("stage1b", err)
        self.assertIn("GATE: GREEN", err)

    # -- new-table drift guards (espn/cbs) ----------------------------------------
    # defect: partial/stale rows in the new reference tables treated as complete
    def test_espn_table_row_count_drift(self):
        # manifest expects 10 rows; the table now holds 8 (partial save)
        mod.fetch_table_summary = lambda table, params: table_rows_for(
            table, params, n=8, week=3, date="2026-09-21")
        make_snapshot(self.root, "espn", "2026-09-21",
                      content_vintage="2026-09-21", week_designated=None)
        entry, _ = mod.verify_source(
            "espn", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
        self.assertIn("8 rows", entry["failure_reason"])

    def test_cbs_table_vintage_drift(self):
        # table reverted to Week 2 content while the manifest stamps Week 3
        mod.fetch_table_summary = lambda table, params: table_rows_for(
            table, params, n=10, week=2, date=None)
        make_snapshot(self.root, "cbs", "week-3",
                      content_vintage="Week 3", week_designated=3)
        entry, _ = mod.verify_source(
            "cbs", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
        self.assertIn("Week 2", entry["failure_reason"])

    def test_espn_table_query_uses_espn_params(self):
        # defect: re-querying espn_season_projections with a source/variant
        # filter it does not have (would 400 and fail the gate spuriously)
        seen = {}

        def spy(table, params):
            seen["table"] = table
            seen["params"] = params
            return table_rows_for(table, params, n=10, week=3, date="2026-09-21")

        mod.fetch_table_summary = spy
        make_snapshot(self.root, "espn", "2026-09-21",
                      content_vintage="2026-09-21", week_designated=None)
        entry, _ = mod.verify_source(
            "espn", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(seen["table"], "espn_season_projections")
        self.assertIn("espn_snapshot_date", seen["params"])
        self.assertNotIn("source=eq", seen["params"])
        self.assertNotIn("variant=eq", seen["params"])

    # -- expected-rows reconciliation ---------------------------------------------
    # defect: review rows that never touched the espn/cbs tables being
    # demanded from them (or review rows missing from the big-three tables
    # being ignored)
    def test_espn_review_rows_not_expected_in_table(self):
        mod.fetch_table_summary = lambda table, params: table_rows_for(
            table, params, n=10, week=3, date="2026-09-21")
        make_snapshot(self.root, "espn", "2026-09-21",
                      content_vintage="2026-09-21", week_designated=None,
                      row_count=10, review_count=3)
        entry, _ = mod.verify_source(
            "espn", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "ok", entry["failure_reason"])

    def test_big_three_still_expect_review_rows_in_table(self):
        # usatoday: importer read FROM the table, so table must hold
        # row_count + review_count
        mod.fetch_table_summary = lambda table, params: db_rows(10, source_content_date="2026-09-22")
        make_snapshot(self.root, "usatoday", "2026-09-22",
                      content_vintage="2026-09-22", week_designated=None,
                      row_count=10, review_count=2)
        entry, _ = mod.verify_source(
            "usatoday", sources_root=self.root, nfl_week=3,
            check_date=self.check_date, prev_entry=None, checked_at="t",
        )
        self.assertEqual(entry["status"], "failed")
        self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
    # -- ESPN daily rule ---------------------------------------------------------
    def test_espn_fresh_within_two_days(self):
        self.stamp_all_ok(nfl_week=3, espn_vintage="2026-09-21")
        code, health, err = self.run_gate(nfl_week=3)
        self.assertEqual(code, 0, err)
        entry = health["sources"]["espn"]
        self.assertEqual(entry["status"], "ok")
        self.assertEqual(entry["vintage_kind"], "file_meta")

    def test_espn_stale_after_two_days(self):
        self.stamp_all_ok(nfl_week=3, espn_vintage="2026-09-18")
        code, health, err = self.run_gate(nfl_week=3)
        self.assertNotEqual(code, 0)
        entry = health["sources"]["espn"]
        self.assertEqual(entry["status"], "stale")
        self.assertTrue(entry["failure_reason"].startswith("STALE_VINTAGE"))

    # -- stateful carry-forward ---------------------------------------------------
    def test_last_successful_import_carried_forward_on_failure(self):
        self.stamp_all_ok(nfl_week=3)
        code, health, _ = self.run_gate(nfl_week=3)
        self.assertEqual(code, 0)
        first_seen = health["sources"]["fantasycalc"]["last_successful_import"]
        self.assertIsNotNone(first_seen)
        # now break the fantasycalc snapshot -> missing; the previous good
        # import time must carry forward, not reset to null
        import shutil
        shutil.rmtree(self.root / "fantasycalc")
        code, health, _ = self.run_gate(nfl_week=3)
        self.assertNotEqual(code, 0)
        entry = health["sources"]["fantasycalc"]
        self.assertEqual(entry["status"], "missing")
        self.assertEqual(entry["last_successful_import"], first_seen)

    # -- all-green: exit 0 + exact contract shape ---------------------------------
    def test_all_green_exit_zero_and_shape(self):
        self.stamp_all_ok(nfl_week=3)
        code, health, err = self.run_gate(nfl_week=3)
        self.assertEqual(code, 0, err)
        self.assertEqual(set(health.keys()), TOP_KEYS)
        self.assertEqual(health["schema"], "trade-value-import-health-v1")
        self.assertEqual(health["nfl_week"], 3)
        self.assertEqual(set(health["sources"].keys()),
                         {"espn", "usatoday", "fantasycalc", "fantasypros", "cbs"})
        for source, entry in health["sources"].items():
            with self.subTest(source=source):
                # exact shape: no missing keys, no extra keys
                self.assertEqual(set(entry.keys()), SOURCE_KEYS, source)
                # the four watchdog fields are present and populated
                self.assertEqual(entry["status"], "ok", source)
                self.assertIsNotNone(entry["last_successful_import"], source)
                self.assertIsNotNone(entry["content_vintage"], source)
                self.assertIsNotNone(entry["row_count"], source)
                self.assertIsNone(entry["failure_reason"], source)

    # -- non-zero exit whenever anything is not ok ---------------------------------
    def test_any_non_ok_source_fails_the_gate(self):
        self.stamp_all_ok(nfl_week=3)
        # re-stamp fantasypros with a Week-2-dated manifest whose table rows
        # agree (so bytes+vintage verify) -- freshness alone makes it stale
        import shutil
        shutil.rmtree(self.root / "fantasypros")
        make_snapshot(self.root, "fantasypros", "2026-09-15",
                      content_vintage="2026-09-15", week_designated=None)
        def mixed(table, params):
            if table == "espn_season_projections":
                return table_rows_for(table, params, n=10, week=3, date="2026-09-21")
            if table == "cbs_trade_values":
                return table_rows_for(table, params, n=10, week=3, date=None)
            if "fantasypros" in params:
                return db_rows(10, source_content_date="2026-09-15")
            if "fantasycalc" in params:
                return db_rows(10, week=3)
            return db_rows(10, source_content_date="2026-09-22")
        mod.fetch_table_summary = mixed
        code, health, err = self.run_gate(nfl_week=3)
        self.assertNotEqual(code, 0)
        self.assertEqual(health["sources"]["fantasypros"]["status"], "stale")
        self.assertIn("GATE: RED", err)
        self.assertIn("no fixture update", err)


if __name__ == "__main__":
    unittest.main()
