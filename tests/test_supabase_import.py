#!/usr/bin/env python3
"""Tests for pipelines/import_supabase_references.py.

Each guard is negative-tested against its named defect. Supabase access is
injected via module-level fetch callables, so these run offline with recorded
fixtures.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "import_supabase_references", PIPELINES / "import_supabase_references.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def db_row(**overrides):
    base = {
        "source": "fantasycalc",
        "player_key": 2227,
        "player_norm": "jahmyr gibbs",
        "position": "RB",
        "team": "DET",
        "scoring": "half",
        "league_teams": 12,
        "qb_slots": 1,
        "season": 2026,
        "week": 2,
        "variant": "as_published",
        "value": 82.0,
        "native_value": 10606.0,
        "source_content_date": None,
        "pulled_at": "2026-09-16T00:00:00+00:00",
        "bake_id": "fitwk2_2026-09-17_v3",
    }
    base.update(overrides)
    return base


def dated_row(**overrides):
    overrides.setdefault("source", "usatoday")
    overrides.setdefault("source_content_date", "2026-09-15")
    return db_row(**overrides)


def espn_row(**overrides):
    base = {
        "player_key": 869,
        "player_norm": "josh allen",
        "season": 2026,
        "week": 2,
        "scoring": "half_ppr",
        "r_pass_yds": 3674.1,
        "r_pass_tds": 24.6,
        "r_rush_yds": 517.7,
        "r_rush_tds": 11.5,
        "r_receptions": 0.0,
        "r_rec_yds": 0.0,
        "r_rec_tds": 0.0,
        "ros_half_ppr": 366.13,
        "weeks_covered": "3-18",
        "espn_snapshot_date": "2026-09-21",
        "pulled_at": "2026-09-22T02:00:00+00:00",
    }
    base.update(overrides)
    return base


def cbs_row(**overrides):
    base = db_row(source="cbs", scoring="half_ppr", value=46.0, native_value=46.0)
    base.pop("source_content_date", None)
    base.update(overrides)
    return base


class ImportSupabaseReferencesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.outdir = Path(self.tmp.name) / "sources"
        self._rows = mod.fetch_supabase_rows
        self._names = mod.fetch_player_names
        self._positions = mod.fetch_player_positions
        self._fixture = mod.fixture_pos_team
        mod.fetch_player_names = lambda keys: {2227: "Jahmyr Gibbs", 869: "Josh Allen"}
        mod.fetch_player_positions = lambda keys: {2227: "RB", 869: "QB"}
        mod.fixture_pos_team = lambda: {2227: ("RB", "DET"), 869: ("QB", "BUF")}

    def tearDown(self):
        mod.fetch_supabase_rows = self._rows
        mod.fetch_player_names = self._names
        mod.fetch_player_positions = self._positions
        mod.fixture_pos_team = self._fixture
        self.tmp.cleanup()

    def import_with(self, rows, source="fantasycalc", **kwargs):
        mod.fetch_supabase_rows = lambda table, params: rows
        return mod.import_source(source, output_dir=self.outdir, **kwargs)

    def snapshot_files(self):
        return [p for p in self.outdir.rglob("snapshot.json") if "_superseded" not in p.parts]

    # -- guard 1: unknown source -> fail closed --------------------------------
    # defect: importing a non-dashboard source (ECR/Vegas/Razzball sneaking in)
    def test_unknown_source_fails_closed(self):
        for bad in ("ecr", "vegas", "razzball", "prediction_markets", "fantasypros_ecr", "nflverse"):
            with self.assertRaises(SystemExit, msg=bad):
                mod.import_source(bad, output_dir=self.outdir)
        self.assertEqual(self.snapshot_files(), [])

    # -- guard 2: zero rows -> fail closed, never writes an empty snapshot -----
    # defect: empty snapshot masquerading as a source
    def test_zero_rows_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.import_with([])
        self.assertEqual(self.snapshot_files(), [])

    def test_all_rows_ecr_dropped_is_zero_rows(self):
        with self.assertRaises(SystemExit):
            self.import_with([db_row(source="fantasycalc-ecr")])
        self.assertEqual(self.snapshot_files(), [])

    def test_espn_zero_rows_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.import_with([], source="espn")
        self.assertEqual(self.snapshot_files(), [])

    def test_cbs_zero_rows_fails_closed(self):
        with self.assertRaises(SystemExit):
            self.import_with([], source="cbs")
        self.assertEqual(self.snapshot_files(), [])

    # -- guard 3: vintage undeterminable -> fail closed ------------------------
    # defect: vintage-less snapshot resetting freshness
    def test_vintage_undeterminable_fails_closed(self):
        rows = [db_row(source_content_date=None, week=None)]
        with self.assertRaises(SystemExit):
            self.import_with(rows)
        self.assertEqual(self.snapshot_files(), [])

    def test_mixed_vintage_fails_closed(self):
        rows = [dated_row(), dated_row(source_content_date="2026-09-14")]
        with self.assertRaises(SystemExit):
            self.import_with(rows, source="usatoday")
        self.assertEqual(self.snapshot_files(), [])

    def test_espn_mixed_snapshot_dates_fail_closed(self):
        rows = [espn_row(), espn_row(player_key=2227, espn_snapshot_date="2026-09-20")]
        with self.assertRaises(SystemExit):
            self.import_with(rows, source="espn")
        self.assertEqual(self.snapshot_files(), [])

    def test_cbs_mixed_weeks_fail_closed(self):
        rows = [cbs_row(), cbs_row(player_key=869, week=3)]
        with self.assertRaises(SystemExit):
            self.import_with(rows, source="cbs")
        self.assertEqual(self.snapshot_files(), [])

    # -- guard 4: stamped snapshot with different bytes -> fail closed --------
    # defect: stamped snapshot silently replaced
    def test_overwrite_guard(self):
        first = self.import_with([db_row()])
        original = first["snapshot_path"].read_bytes()
        with self.assertRaises(SystemExit):
            self.import_with([db_row(value=83.0)])
        self.assertEqual(first["snapshot_path"].read_bytes(), original)

    def test_identical_bytes_is_idempotent_noop(self):
        first = self.import_with([db_row()])
        second = self.import_with([db_row()])
        self.assertTrue(second["already_stamped"])
        self.assertEqual(first["snapshot_sha256"], second["snapshot_sha256"])

    def test_espn_overwrite_guard_same_provenance(self):
        first = self.import_with([espn_row()], source="espn")
        original = first["snapshot_path"].read_bytes()
        with self.assertRaises(SystemExit):
            self.import_with([espn_row(ros_half_ppr=400.0)], source="espn")
        self.assertEqual(first["snapshot_path"].read_bytes(), original)

    # -- guard 4b: provenance migration archives, never silently replaces -----
    # defect: the stage-1b file->DB migration silently overwriting a stamped
    # snapshot, or losing the old bytes' audit trail
    def _stamp_file_backed(self, source, vintage_dir, manifest_overrides, snapshot):
        snap_dir = self.outdir / source / vintage_dir
        snap_dir.mkdir(parents=True, exist_ok=True)
        snap_bytes = (json.dumps(snapshot, indent=2, sort_keys=True) + "\n").encode("utf-8")
        snap_path = snap_dir / "snapshot.json"
        snap_path.write_bytes(snap_bytes)
        manifest = {
            "schema": "trade-value-source-manifest-v1",
            "source": source,
            "snapshot_path": str(snap_path),
            "snapshot_sha256": mod.sha256_bytes(snap_bytes),
            "supabase_table": None,
            "from_file": "/tmp/old-cache",
            "save_gap": "no-supabase-table-stage1b",
            "content_vintage": "2026-09-21" if source == "espn" else "Week 2",
            "week_designated": None if source == "espn" else 2,
            "row_count": snapshot["row_count"],
            "review_count": snapshot["review_count"],
        }
        manifest.update(manifest_overrides)
        (snap_dir / "snapshot-manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return snap_dir, snap_path

    def _file_snapshot(self, source):
        return {
            "schema": "trade-value-source-snapshot-v1",
            "source": source,
            "fetched_at": "2026-09-21T00:00:00Z",
            "row_count": 1,
            "rows": [{"player_name": "Josh Allen", "value": 366.13, "source_player_id": None}],
            "review_count": 0,
            "review_rows": [],
        }

    def test_espn_file_snapshot_superseded_by_db_import(self):
        snap_dir, old_path = self._stamp_file_backed("espn", "2026-09-21", {}, self._file_snapshot("espn"))
        old_bytes = old_path.read_bytes()
        result = self.import_with([espn_row()], source="espn")
        self.assertFalse(result["already_stamped"])
        self.assertIsNotNone(result["superseded"])
        # old pair archived under _superseded, bytes intact
        archived = list((snap_dir / "_superseded").rglob("snapshot.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), old_bytes)
        self.assertEqual(
            json.loads((archived[0].parent / "snapshot-manifest.json").read_text())["save_gap"],
            "no-supabase-table-stage1b",
        )
        # new manifest records the migration and the DB provenance
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertIn("supersedes", manifest)
        self.assertEqual(manifest["supersedes"]["sha256"], mod.sha256_bytes(old_bytes))
        self.assertEqual(manifest["supabase_table"], "public.espn_season_projections")
        self.assertIsNone(manifest["save_gap"])
        # idempotent re-run keeps the audit trail
        again = self.import_with([espn_row()], source="espn")
        self.assertTrue(again["already_stamped"])
        manifest2 = json.loads(again["manifest_path"].read_text())
        self.assertIn("supersedes", manifest2)

    def test_cbs_file_snapshot_superseded_by_db_import(self):
        snap_dir, old_path = self._stamp_file_backed("cbs", "week-2", {}, self._file_snapshot("cbs"))
        old_bytes = old_path.read_bytes()
        result = self.import_with([cbs_row()], source="cbs")
        self.assertIsNotNone(result["superseded"])
        archived = list((snap_dir / "_superseded").rglob("snapshot.json"))
        self.assertEqual(len(archived), 1)
        self.assertEqual(archived[0].read_bytes(), old_bytes)
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertEqual(manifest["supabase_table"], "public.cbs_trade_values")
        self.assertIsNone(manifest["save_gap"])

    # -- guard 5: bad rows go to review, never guessed or zero-filled ---------
    # defect: zero-fill / identity guess on import
    def test_bad_rows_go_to_review(self):
        rows = [
            db_row(),  # clean
            db_row(player_key="not-a-key"),  # non-numeric key -> review
            db_row(player_key=None),  # null key -> review
            db_row(player_key=869, value="N/A"),  # non-numeric value -> review
            db_row(player_key=869, value=None),  # null value -> review, never zero-filled
            db_row(player_key=99999),  # unresolvable key -> review, never guessed
        ]
        result = self.import_with(rows)
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(snapshot["row_count"], 1)
        self.assertEqual(snapshot["rows"][0]["player_name"], "Jahmyr Gibbs")
        self.assertEqual(snapshot["review_count"], 5)
        reasons = {r["reason"] for r in snapshot["review_rows"]}
        self.assertEqual(
            reasons,
            {"non_numeric_player_key", "missing_or_non_numeric_value", "unresolved_player_key"},
        )
        # no zero was invented anywhere
        for row in snapshot["rows"]:
            self.assertIsInstance(row["value"], (int, float))

    def test_espn_missing_ros_goes_to_review(self):
        rows = [espn_row(), espn_row(player_key=2227, ros_half_ppr=None)]
        result = self.import_with(rows, source="espn")
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(snapshot["row_count"], 1)
        self.assertEqual(snapshot["review_count"], 1)
        self.assertEqual(snapshot["review_rows"][0]["reason"], "missing_or_non_numeric_value")
        # the clean row kept its real value; nothing was zero-filled
        self.assertEqual(snapshot["rows"][0]["value"], 366.13)

    # -- guard 6: fantasypros excludes ECR rows even with a widened filter ----
    # defect: ECR leaking into the FP trade-value source
    def test_fantasypros_ecr_flavored_rows_excluded(self):
        rows = [
            dated_row(source="fantasypros", player_key=869),
            dated_row(source="fantasypros-ecr", player_key=869, value=99.9),
        ]
        result = self.import_with(rows, source="fantasypros")
        snapshot = json.loads(result["snapshot_path"].read_text())
        values = [r["value"] for r in snapshot["rows"]]
        self.assertNotIn(99.9, values)
        self.assertEqual(snapshot["row_count"], 1)
        # the ECR row is dropped outright -- not in rows, not in review
        review_names = [r.get("player_key") for r in snapshot["review_rows"]]
        self.assertEqual(review_names, [])
        self.assertIn("ECR-flavored", result["manifest"]["filter"])

    # -- vintage derivation ---------------------------------------------------
    def test_fantasycalc_week_is_the_vintage(self):
        result = self.import_with([db_row(), db_row(player_key=869)])
        self.assertEqual(result["content_vintage"], "Week 2")
        self.assertEqual(result["snapshot_path"].parent.name, "week-2")
        self.assertIn("week column", result["manifest"]["content_vintage_derived_from"])
        self.assertIsNone(result["manifest"]["save_gap"])

    def test_dated_source_uses_source_content_date(self):
        result = self.import_with([dated_row()], source="usatoday")
        self.assertEqual(result["content_vintage"], "2026-09-15")
        self.assertEqual(result["snapshot_path"].parent.name, "2026-09-15")

    # -- ESPN DB import --------------------------------------------------------
    # defect: ESPN staying file-backed / ros value misread / pos-team misattributed
    def test_espn_db_import_row_shape_and_manifest(self):
        result = self.import_with([espn_row(), espn_row(player_key=2227, ros_half_ppr=350.70)], source="espn")
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(result["content_vintage"], "2026-09-21")
        self.assertEqual(result["snapshot_path"].parent.name, "2026-09-21")
        self.assertEqual(snapshot["default_scoring"], "half_ppr")
        self.assertEqual(snapshot["row_count"], 2)
        by_name = {r["player_name"]: r for r in snapshot["rows"]}
        allen = by_name["Josh Allen"]
        self.assertEqual(allen["value"], 366.13)  # ros_half_ppr, verbatim
        self.assertEqual(allen["scoring"], "half_ppr")
        self.assertEqual(allen["pos"], "QB")  # canonical players-table position
        self.assertEqual(allen["team"], "BUF")  # fixture map (players carries no team)
        self.assertEqual(allen["source_player_id"], 869)
        self.assertEqual(allen["native_value"], 366.13)
        gibbs = by_name["Jahmyr Gibbs"]
        self.assertEqual(gibbs["team"], "DET")
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertEqual(manifest["supabase_table"], "public.espn_season_projections")
        self.assertIsNone(manifest["from_file"])
        self.assertIsNone(manifest["save_gap"])
        # ESPN vintage is the dated snapshot (daily rule), never a week label
        self.assertIsNone(manifest["week_designated"])
        self.assertIsNone(manifest["table_week"])
        self.assertIn("espn_snapshot_date", manifest["content_vintage_derived_from"])

    # -- CBS DB import ----------------------------------------------------------
    # defect: CBS staying file-backed / implied QB split lost or fabricated
    def test_cbs_db_import_row_shape_and_manifest(self):
        rows = [
            cbs_row(),  # half_ppr skill row
            cbs_row(scoring="standard", value=45.0),
            cbs_row(scoring="ppr", value=47.0),
            cbs_row(player_key=869, position="QB", team="BUF", value=20.0),  # implied QB row
        ]
        result = self.import_with(rows, source="cbs")
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(result["content_vintage"], "Week 2")
        self.assertEqual(snapshot["row_count"], 4)
        by_key_scoring = {(r["source_player_id"], r["scoring"]): r for r in snapshot["rows"]}
        self.assertEqual(by_key_scoring[(2227, "half_ppr")]["value"], 46.0)
        self.assertEqual(by_key_scoring[(869, "half_ppr")]["player_name"], "Josh Allen")
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertEqual(manifest["supabase_table"], "public.cbs_trade_values")
        self.assertIsNone(manifest["save_gap"])
        self.assertEqual(manifest["week_designated"], 2)
        self.assertIn("IMPLIED", manifest["filter"])

    # -- schema / manifest ----------------------------------------------------
    def test_snapshot_uses_v1_schema_and_record_shape(self):
        result = self.import_with([db_row()])
        snapshot = json.loads(result["snapshot_path"].read_text())
        self.assertEqual(snapshot["schema"], "trade-value-source-snapshot-v1")
        row = snapshot["rows"][0]
        for key in ("player_name", "value", "pos", "team", "scoring", "teams", "source_player_id"):
            self.assertIn(key, row)
        # repo scoring vocabulary (full/half/standard -> ppr/half_ppr/standard)
        self.assertEqual(row["scoring"], "half_ppr")
        self.assertEqual(row["source_player_id"], 2227)  # numeric key preserved
        self.assertEqual(row["native_value"], 10606.0)  # scraped native carried
        self.assertEqual(row["value"], 82.0)  # value as-is from the table

    def test_manifest_fields_and_sha(self):
        result = self.import_with([db_row()])
        manifest = json.loads(result["manifest_path"].read_text())
        self.assertEqual(manifest["schema"], "trade-value-source-manifest-v1")
        self.assertEqual(manifest["source"], "fantasycalc")
        self.assertEqual(manifest["supabase_table"], "public.source_trade_values")
        self.assertEqual(manifest["content_vintage"], "Week 2")
        self.assertIn("pulled_at", manifest)
        self.assertIn("not content vintage", manifest["pulled_at_note"].lower())
        self.assertEqual(manifest["row_count"], 1)
        actual = mod.sha256_bytes(result["snapshot_path"].read_bytes())
        self.assertEqual(manifest["snapshot_sha256"], actual)

    def test_repo_scoring_vocabulary(self):
        self.assertEqual(mod.repo_scoring("full"), "ppr")
        self.assertEqual(mod.repo_scoring("half"), "half_ppr")
        self.assertEqual(mod.repo_scoring("std"), "standard")
        self.assertEqual(mod.repo_scoring("half_ppr"), "half_ppr")


if __name__ == "__main__":
    unittest.main()
