#!/usr/bin/env python3
"""JEG-90: bake-aware read pattern for pipelines/verify_import_health.py.

The four as_published readers (fantasycalc / usatoday / fantasypros / cbs)
now SELECT bake_id alongside player_key/source_content_date/week/created_at,
and latest_vintage_rows scopes the newest-vintage slice to a single bake via
the canonical _select_latest_bake (import_supabase_references). Without
bake-scoping, multiple immutable bakes in the same week would be blended --
that was the September 2026 defect class JEG-90 was opened for.

Each test names a defect and asserts the negative case fails closed (or the
positive case selects the latest bake exactly). These run offline: the
importable verify_import_health module exposes latest_vintage_rows directly,
and the _select_latest_bake call inside it is the canonical pattern.

Two required acceptance scenarios (run by reviewer):
  - two bakes in the same week -> exactly the latest bake selected
  - rows with no created_at -> fail closed
"""

from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PIPELINES = ROOT / "pipelines"

spec = importlib.util.spec_from_file_location(
    "verify_import_health", PIPELINES / "verify_import_health.py"
)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def _row(player_id: int, *, week: int, bake_id: str, created_at: str,
         source_content_date: str = "2026-09-22") -> dict:
    """One source_trade_values row at the JEG-90 9-column grain."""
    return {
        "player_key": f"p_{player_id}",
        "source_content_date": source_content_date,
        "week": week,
        "created_at": created_at,
        "bake_id": bake_id,
    }


class LatestVintageRowsBakeSelectionTest(unittest.TestCase):
    """latest_vintage_rows must scope the newest-vintage slice to one bake."""

    def test_two_bakes_same_week_picks_latest_created_at(self):
        """Two immutable bakes in Week 3 -- the later one wins, exclusively.

        Defect guarded: a bake-blind read (just latest week) would return
        rows from both bakes and blend content vintages inside one snapshot.
        """
        rows = [
            _row(1, week=3, bake_id="bake_2026_09_22T08_00Z",
                 created_at="2026-09-22T08:00:00Z"),
            _row(2, week=3, bake_id="bake_2026_09_22T08_00Z",
                 created_at="2026-09-22T08:00:00Z"),
            # Older bake: latest row at 07:00.
            _row(3, week=3, bake_id="bake_2026_09_22T07_00Z",
                 created_at="2026-09-22T07:00:00Z"),
            _row(4, week=3, bake_id="bake_2026_09_22T07_00Z",
                 created_at="2026-09-22T07:00:00Z"),
        ]
        vintage, latest = mod.latest_vintage_rows(rows)
        # All rows share a date -> the date path is taken (not the week path).
        self.assertEqual(vintage, "2026-09-22")
        self.assertEqual(
            sorted(r["player_key"] for r in latest),
            ["p_1", "p_2"],
            "must select only the later bake's rows -- never blend bakes",
        )
        # Sanity: the older bake's player_key is absent.
        self.assertNotIn("p_3", [r["player_key"] for r in latest])
        self.assertNotIn("p_4", [r["player_key"] for r in latest])

    def test_two_bakes_same_week_picks_latest_by_bake_id_tiebreak(self):
        """Tie on max(created_at) -> greatest bake_id wins (deterministic)."""
        # Both bakes have a row with identical created_at; tiebreak by bake_id.
        same_ts = "2026-09-22T08:00:00Z"
        rows = [
            _row(10, week=3, bake_id="bake_A", created_at=same_ts),
            _row(11, week=3, bake_id="bake_B", created_at=same_ts),
        ]
        vintage, latest = mod.latest_vintage_rows(rows)
        self.assertEqual(vintage, "2026-09-22")
        self.assertEqual(
            [r["player_key"] for r in latest], ["p_11"],
            "max bake_id tiebreak must select bake_B exclusively",
        )

    def test_no_created_at_with_multiple_bakes_fails_closed(self):
        """Multiple bakes, no created_at anywhere -> SystemExit (fail closed).

        The canonical _select_latest_bake raises SystemExit when recency would
        be a guess. latest_vintage_rows re-raises it; the caller
        (verify_source) catches SystemExit and converts to TABLE_DRIFT.
        Negative-tested here so the no-blend guard stays in place.
        """
        rows = [
            # bake_id present (the column is in the select set), but no
            # created_at on any row -- the no-blend guard must fire.
            {"player_key": "p_1", "source_content_date": "2026-09-22",
             "week": 3, "created_at": None, "bake_id": "bake_X"},
            {"player_key": "p_2", "source_content_date": "2026-09-22",
             "week": 3, "created_at": None, "bake_id": "bake_Y"},
        ]
        with self.assertRaises(SystemExit) as cm:
            mod.latest_vintage_rows(rows)
        # The canonical message names the defect class explicitly.
        self.assertIn("Fail closed", str(cm.exception))
        self.assertIn("multiple bakes", str(cm.exception).lower())

    def test_single_bake_passes_through(self):
        """One bake in the window -> no scope filter, every row kept."""
        rows = [
            _row(20, week=3, bake_id="bake_only", created_at="2026-09-22T09:00:00Z"),
            _row(21, week=3, bake_id="bake_only", created_at="2026-09-22T09:00:00Z"),
        ]
        vintage, latest = mod.latest_vintage_rows(rows)
        self.assertEqual(vintage, "2026-09-22")
        self.assertEqual(len(latest), 2)

    def test_week_path_also_scopes_to_latest_bake(self):
        """Date path exercised by the as_published tests above. This test
        confirms the WEEK path (no source_content_date on any row) also
        scopes to the latest bake -- the JEG-90 defect class applies to
        both branches."""
        rows = [
            {"player_key": "p_30", "week": 3, "created_at": "2026-09-22T07:00:00Z",
             "bake_id": "bake_old"},
            {"player_key": "p_31", "week": 3, "created_at": "2026-09-22T08:00:00Z",
             "bake_id": "bake_new"},
            {"player_key": "p_32", "week": 2, "created_at": "2026-09-15T08:00:00Z",
             "bake_id": "bake_lastweek"},
        ]
        vintage, latest = mod.latest_vintage_rows(rows)
        self.assertEqual(vintage, "Week 3")
        self.assertEqual(
            [r["player_key"] for r in latest], ["p_31"],
            "week path must also scope to the latest bake within the week",
        )


class SourceConfigBakeIdPresentTest(unittest.TestCase):
    """The four as_published SOURCE_CONFIGS must select bake_id.

    Defect guarded: a re-read that omits bake_id collapses every row into
    one implicit bake, and the no-blend guarantee degrades to whatever the
    table contract provides. The bake_id column must be in the params so
    _select_latest_bake actually has a key to group on.
    """

    def test_as_published_configs_select_bake_id(self):
        for source in ("fantasycalc", "usatoday", "fantasypros", "cbs"):
            with self.subTest(source=source):
                params = mod.SOURCE_CONFIGS[source]["params"]
                self.assertIn("bake_id", params,
                              f"{source} SOURCE_CONFIGS.params must select bake_id")

    def test_non_as_published_configs_unaffected(self):
        """espn / cbsros / razzball use different tables; bake_id selection
        is the source_trade_values as_published readers' concern (per the
        JEG-90 DDL). Adding it to those params is a no-op -- don't."""
        for source in ("espn",):
            with self.subTest(source=source):
                params = mod.SOURCE_CONFIGS[source]["params"]
                self.assertNotIn("bake_id", params,
                                 f"{source} SOURCE_CONFIGS.params must NOT select bake_id")


class VerifySourceFailClosedOnBakeBlindnessTest(unittest.TestCase):
    """End-to-end: a fixture with no created_at across bakes -> TABLE_DRIFT.

    verify_source catches SystemExit from latest_vintage_rows and converts
    to TABLE_DRIFT (the gate never raises for a named source). This is the
    full path the health-check caller observes.
    """

    def test_verify_source_returns_table_drift_when_no_created_at(self):
        # Inject a fixture whose as_published rows have no created_at.
        no_ts = {
            "player_key": "p_1", "source_content_date": "2026-09-22",
            "week": 3, "created_at": None, "bake_id": "bake_X",
        }
        no_ts2 = dict(no_ts, player_key="p_2", bake_id="bake_Y")

        def fake_fetch(table, params):
            if "source=eq.fantasycalc" in params:
                return [no_ts, no_ts2]
            return []

        mod.fetch_table_summary = fake_fetch
        try:
            # Stamp a manifest so the gate reaches the table query.
            import hashlib
            import json
            import tempfile
            from datetime import date as _date

            tmp = tempfile.TemporaryDirectory()
            root = Path(tmp.name) / "sources"
            snap_dir = root / "fantasycalc" / "week-3"
            snap_dir.mkdir(parents=True, exist_ok=True)
            snap_bytes = json.dumps(
                {"schema": "trade-value-source-snapshot-v1",
                 "source": "fantasycalc", "row_count": 2, "rows": [],
                 "review_count": 0, "review_rows": []},
                indent=2, sort_keys=True,
            ).encode("utf-8") + b"\n"
            (snap_dir / "snapshot.json").write_bytes(snap_bytes)
            (snap_dir / "snapshot-manifest.json").write_text(json.dumps(
                {"schema": "trade-value-source-manifest-v1",
                 "source": "fantasycalc",
                 "snapshot_path": str(snap_dir / "snapshot.json"),
                 "snapshot_sha256": hashlib.sha256(snap_bytes).hexdigest(),
                 "filter": "python backstop dropped 0 ECR-flavored row(s)",
                 "content_vintage": "Week 3", "week_designated": 3,
                 "pulled_at": "2026-09-21T12:00:00Z",
                 "row_count": 2, "review_count": 0,
                 "supabase_table": "public.source_trade_values"},
                indent=2, sort_keys=True,
            ) + "\n", encoding="utf-8")

            entry, _ = mod.verify_source(
                "fantasycalc", sources_root=root, nfl_week=3,
                check_date=_date(2026, 9, 21), prev_entry=None,
                checked_at="2026-09-21T00:00:00Z",
            )
            self.assertEqual(entry["status"], "failed")
            self.assertTrue(entry["failure_reason"].startswith("TABLE_DRIFT"))
            self.assertIn("bake scoping failed", entry["failure_reason"])
        finally:
            mod.fetch_table_summary = lambda table, params: []


if __name__ == "__main__":
    unittest.main()