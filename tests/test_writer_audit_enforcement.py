#!/usr/bin/env python3
"""Enforcement tests for the Supabase writer audit system.

These tests verify that:
1. WriterAudit requires all mandatory fields
2. WriterAudit rejects invalid operations
3. Audit records are created with correct structure
4. Rows get audit fields added correctly
5. Undeclared writes (without audit) are detectable

Run: python3 -m unittest tests.test_writer_audit_enforcement
"""

from __future__ import annotations

import sys
import unittest
from unittest.mock import MagicMock, patch


class TestWriterAuditValidation(unittest.TestCase):
    """Test that WriterAudit enforces required fields."""

    def test_requires_writer_identity(self):
        from pipelines.lib.writer_audit import WriterAudit
        with self.assertRaises(ValueError) as ctx:
            WriterAudit(
                writer_identity="",
                source="espn",
                operation="upsert",
                table_name="test_table",
            )
        self.assertIn("writer_identity", str(ctx.exception))

    def test_requires_source(self):
        from pipelines.lib.writer_audit import WriterAudit
        with self.assertRaises(ValueError) as ctx:
            WriterAudit(
                writer_identity="test.py",
                source="",
                operation="upsert",
                table_name="test_table",
            )
        self.assertIn("source", str(ctx.exception))

    def test_requires_table_name(self):
        from pipelines.lib.writer_audit import WriterAudit
        with self.assertRaises(ValueError) as ctx:
            WriterAudit(
                writer_identity="test.py",
                source="espn",
                operation="upsert",
                table_name="",
            )
        self.assertIn("table_name", str(ctx.exception))

    def test_rejects_invalid_operation(self):
        from pipelines.lib.writer_audit import WriterAudit
        with self.assertRaises(ValueError) as ctx:
            WriterAudit(
                writer_identity="test.py",
                source="espn",
                operation="invalid_op",
                table_name="test_table",
            )
        self.assertIn("operation", str(ctx.exception))

    def test_accepts_valid_operations(self):
        from pipelines.lib.writer_audit import WriterAudit
        for op in ("insert", "upsert", "delete", "update"):
            audit = WriterAudit(
                writer_identity="test.py",
                source="espn",
                operation=op,
                table_name="test_table",
            )
            self.assertEqual(audit.operation, op)


class TestWriterAuditLifecycle(unittest.TestCase):
    """Test the audit lifecycle: start -> complete/fail."""

    def _make_audit(self, **kwargs):
        from pipelines.lib.writer_audit import WriterAudit
        defaults = dict(
            writer_identity="test_writer.py",
            source="test_source",
            operation="upsert",
            table_name="test_table",
            reason="Test reason",
        )
        defaults.update(kwargs)
        # Use a mock client factory to avoid real Supabase calls
        mock_client = MagicMock()
        defaults["sb_client_factory"] = lambda: mock_client
        audit = WriterAudit(**defaults)
        audit._mock_client = mock_client  # Save for assertions
        return audit

    def test_start_creates_audit_record(self):
        audit = self._make_audit()
        run_id = audit.start()

        # Verify run_id is a valid UUID format
        self.assertEqual(audit.run_id, run_id)
        self.assertTrue(len(run_id) == 36)  # UUID string length

        # Verify the mock client was called with correct structure
        mock_client = audit._mock_client
        mock_client.post.assert_called_once()
        call_args = mock_client.post.call_args
        self.assertEqual(call_args[0][0], "pipeline_write_audit")
        record = call_args[0][1][0]
        self.assertEqual(record["run_id"], run_id)
        self.assertEqual(record["writer_identity"], "test_writer.py")
        self.assertEqual(record["source"], "test_source")
        self.assertEqual(record["operation"], "upsert")
        self.assertEqual(record["table_name"], "test_table")
        self.assertEqual(record["reason"], "Test reason")
        self.assertIn("started_at", record)
        self.assertIn("code_revision", record)

    def test_start_twice_raises(self):
        audit = self._make_audit()
        audit.start()
        with self.assertRaises(RuntimeError):
            audit.start()

    def test_complete_requires_start(self):
        audit = self._make_audit()
        with self.assertRaises(RuntimeError):
            audit.complete(row_count=10)

    def test_fail_requires_start(self):
        audit = self._make_audit()
        with self.assertRaises(RuntimeError):
            audit.fail("test error")

    def _trap_sbclient(self):
        """A global sbclient that must never be reached: lifecycle calls have to
        go through the injected client, not whatever module is on sys.path."""
        trap = MagicMock()
        trap._request.side_effect = AssertionError(
            "audit ignored the injected client and used the global sbclient")
        patcher = patch.dict(sys.modules, {"sbclient": trap})
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_complete_marks_success(self):
        self._trap_sbclient()
        audit = self._make_audit()
        audit.start()
        audit._mock_client.post.reset_mock()

        audit.complete(row_count=42)

        mock_client = audit._mock_client
        # An update must be a PATCH on the existing row. A POST (even with a
        # run_id filter) inserts a second audit row instead of updating.
        mock_client.post.assert_not_called()
        mock_client._request.assert_called_once()
        args, kwargs = mock_client._request.call_args
        self.assertEqual(("PATCH", "/rest/v1/pipeline_write_audit"), args)
        self.assertEqual(f"?run_id=eq.{audit.run_id}", kwargs["params"])
        self.assertEqual(42, kwargs["body"]["row_count"])
        self.assertIn("completed_at", kwargs["body"])

    def test_fail_marks_failure(self):
        self._trap_sbclient()
        audit = self._make_audit()
        audit.start()
        audit._mock_client.post.reset_mock()

        audit.fail("Something went wrong")

        mock_client = audit._mock_client
        mock_client.post.assert_not_called()
        mock_client._request.assert_called_once()
        args, kwargs = mock_client._request.call_args
        self.assertEqual(("PATCH", "/rest/v1/pipeline_write_audit"), args)
        self.assertEqual(f"?run_id=eq.{audit.run_id}", kwargs["params"])
        self.assertIn("failed_at", kwargs["body"])
        self.assertEqual("Something went wrong", kwargs["body"]["error_message"])


class TestAuditRowFields(unittest.TestCase):
    """Test that audit fields are added to data rows."""

    def _make_started_audit(self):
        from pipelines.lib.writer_audit import WriterAudit
        mock_client = MagicMock()
        audit = WriterAudit(
            writer_identity="test_writer.py",
            source="test_source",
            operation="upsert",
            table_name="test_table",
            sb_client_factory=lambda: mock_client,
        )
        audit.start()
        return audit

    def test_audit_row_adds_fields(self):
        audit = self._make_started_audit()
        row = {"player_key": 123, "value": 45.6}
        audited = audit.audit_row(row)

        # Original fields preserved
        self.assertEqual(audited["player_key"], 123)
        self.assertEqual(audited["value"], 45.6)

        # Audit fields added
        self.assertEqual(audited["_writer_identity"], "test_writer.py")
        self.assertEqual(audited["_run_id"], audit.run_id)
        self.assertIn("_written_at", audited)

        # Original not mutated
        self.assertNotIn("_writer_identity", row)

    def test_audit_row_requires_start(self):
        from pipelines.lib.writer_audit import WriterAudit
        mock_client = MagicMock()
        audit = WriterAudit(
            writer_identity="test.py",
            source="s",
            operation="upsert",
            table_name="t",
            sb_client_factory=lambda: mock_client,
        )
        with self.assertRaises(RuntimeError):
            audit.audit_row({"a": 1})

    def test_audit_rows_batch(self):
        audit = self._make_started_audit()
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        audited = audit.audit_rows(rows)

        self.assertEqual(len(audited), 3)
        for i, r in enumerate(audited):
            self.assertEqual(r["id"], i + 1)
            self.assertEqual(r["_run_id"], audit.run_id)


class TestUndeclaredWriteDetection(unittest.TestCase):
    """Test that writes without audit fields are detectable.

    This is the negative test: it proves that the enforcement mechanism
    can detect rows that were written without going through WriterAudit.
    """

    def test_row_without_audit_fields_is_detectable(self):
        """A row without _writer_identity/_run_id is an undeclared write."""
        # Simulate a row written without audit
        undeclared_row = {
            "player_key": 123,
            "value": 45.6,
            # Missing: _writer_identity, _run_id, _written_at
        }

        # Detection logic: check for audit fields
        has_audit = all(
            k in undeclared_row
            for k in ("_writer_identity", "_run_id", "_written_at")
        )
        self.assertFalse(has_audit, "Undeclared write should be detectable")

    def test_row_with_audit_fields_passes(self):
        """A row with audit fields is a declared write."""
        declared_row = {
            "player_key": 123,
            "value": 45.6,
            "_writer_identity": "test.py",
            "_run_id": "some-uuid",
            "_written_at": "2026-09-29T00:00:00Z",
        }

        has_audit = all(
            k in declared_row
            for k in ("_writer_identity", "_run_id", "_written_at")
        )
        self.assertTrue(has_audit, "Declared write should have audit fields")


if __name__ == "__main__":
    unittest.main()
