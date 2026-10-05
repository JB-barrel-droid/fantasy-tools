#!/usr/bin/env python3
"""JEG-389 bake-identity cleanup: loader must resolve bakes against the LIVE
public.bakes columns (bake_id uuid, ingested_at) — not the nonexistent
bake_uuid / created_at columns.

All tests are hermetic (no DB, no network).
"""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import load_ddf_leg_to_supabase as loader  # noqa: E402


class _FakeSb:
    """Records get() calls and returns a scripted bake row."""

    def __init__(self, rows):
        self.rows = rows
        self.get_params = []

    def get(self, table, params=""):
        self.get_params.append((table, params))
        return self.rows


class TestResolveBakeUuidLiveColumns(unittest.TestCase):
    """resolve_bake_uuid must query public.bakes.bake_id ordered by
    ingested_at — the live columns (JEG-389)."""

    def test_uses_bake_id_and_ingested_at(self):
        sb = _FakeSb([{"bake_id": "d8697da5-0b16-4756-b6e7-3bc7167b22c8"}])
        got = loader.resolve_bake_uuid(sb, "skill", "espn", None)
        self.assertEqual(got, "d8697da5-0b16-4756-b6e7-3bc7167b22c8")
        self.assertEqual(len(sb.get_params), 1)
        table, params = sb.get_params[0]
        self.assertEqual(table, "bakes")
        self.assertIn("select=bake_id", params)
        self.assertIn("order=ingested_at.desc", params)
        # Must NOT reference the nonexistent columns.
        self.assertNotIn("bake_uuid", params)
        self.assertNotIn("created_at", params)

    def test_cli_uuid_short_circuits_without_query(self):
        sb = _FakeSb([])
        got = loader.resolve_bake_uuid(sb, "skill", "espn", "cli-uuid-123")
        self.assertEqual(got, "cli-uuid-123")
        self.assertEqual(sb.get_params, [])

    def test_missing_bake_fails_closed(self):
        sb = _FakeSb([])
        with self.assertRaises(loader.LoadError):
            loader.resolve_bake_uuid(sb, "skill", "nosuchsource", None)


class TestLatestBakeUuidsSqlLiveColumns(unittest.TestCase):
    """PublishGate._SQL_LATEST_BAKE_UUIDS must reference bakes.bake_id /
    ingested_at — the live columns (JEG-389)."""

    def test_sql_uses_live_columns(self):
        from pipelines.publish_gate import PublishGate

        sql = PublishGate._SQL_LATEST_BAKE_UUIDS
        self.assertIn("bake_id::text AS bake_uuid", sql)
        self.assertIn("ingested_at DESC", sql)
        self.assertNotIn("bake_uuid::text", sql)
        self.assertNotIn("created_at", sql)


if __name__ == "__main__":
    unittest.main()
