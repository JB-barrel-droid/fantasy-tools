#!/usr/bin/env python3
"""Writer audit helper for Supabase pipeline writes.

Every pipeline that writes to Supabase must use this helper to create
an audit record. This provides data provenance, debugging capability,
and compliance audit trail.

Usage:
    from pipelines.lib.writer_audit import WriterAudit

    audit = WriterAudit(
        writer_identity="save_espn_cbs_references.py",
        source="espn",
        operation="upsert",
        reason="Weekly ESPN projection import",
        table_name="espn_season_projections",
    )
    audit.start()  # Creates audit record, returns run_id

    try:
        # ... do the write ...
        audit.complete(row_count=150)
    except Exception as e:
        audit.fail(str(e))
        raise

The helper automatically captures:
- run_id: UUID generated at start
- code_revision: Git commit SHA of the repo (or "unknown")
- started_at: Timestamp when start() is called
- completed_at / failed_at: Timestamps when operation finishes
"""

from __future__ import annotations

import os
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


# Type for the Supabase client factory (injected for testing)
SbClientFactory = Callable[[], Any]


def _get_code_revision() -> str:
    """Get the current git commit SHA, or 'unknown' if not available."""
    try:
        # Find the repo root (where .git lives)
        current = Path(__file__).resolve()
        for parent in [current] + list(current.parents):
            if (parent / ".git").exists():
                result = subprocess.run(
                    ["git", "rev-parse", "HEAD"],
                    cwd=parent,
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if result.returncode == 0:
                    return result.stdout.strip()[:40]
                break
    except Exception:
        pass
    return "unknown"


def _utc_now_iso() -> str:
    """Current UTC time as ISO string."""
    return datetime.now(timezone.utc).isoformat()


class WriterAudit:
    """Audit helper for Supabase pipeline writes.

    Creates an audit record at start, updates it on completion or failure.
    """

    VALID_OPERATIONS = ("insert", "upsert", "delete", "update")

    def __init__(
        self,
        writer_identity: str,
        source: str,
        operation: str,
        table_name: str,
        reason: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
        sb_client_factory: Optional[SbClientFactory] = None,
    ):
        """Initialize the audit helper.

        Args:
            writer_identity: Name of the writing script/module (e.g., 'save_espn_cbs_references.py')
            source: Data source (e.g., 'espn', 'cbs', 'usatoday')
            operation: One of 'insert', 'upsert', 'delete', 'update'
            table_name: Target Supabase table name
            reason: Human-readable reason for the write
            metadata: Additional context as dict (stored as JSONB)
            sb_client_factory: Factory for Supabase client (for testing)
        """
        if operation not in self.VALID_OPERATIONS:
            raise ValueError(
                f"operation must be one of {self.VALID_OPERATIONS}, got '{operation}'"
            )
        if not writer_identity:
            raise ValueError("writer_identity is required")
        if not source:
            raise ValueError("source is required")
        if not table_name:
            raise ValueError("table_name is required")

        self.writer_identity = writer_identity
        self.source = source
        self.operation = operation
        self.table_name = table_name
        self.reason = reason
        self.metadata = metadata or {}

        self.run_id = str(uuid.uuid4())
        self.code_revision = _get_code_revision()
        self._started = False
        self._sb_client_factory = sb_client_factory

    def _get_sb_client(self):
        """Get Supabase client via factory or default import."""
        if self._sb_client_factory:
            return self._sb_client_factory()
        # Default: import the sbclient module (has module-level post/get functions)
        import sys
        sys.path.insert(0, os.path.expanduser("~/workspace/skills/supabase-football-signal/bin"))
        import sbclient
        return sbclient

    def start(self) -> str:
        """Create the audit record. Returns the run_id.

        Must be called before the write operation.
        """
        if self._started:
            raise RuntimeError("audit already started")

        record = {
            "run_id": self.run_id,
            "writer_identity": self.writer_identity,
            "code_revision": self.code_revision,
            "source": self.source,
            "operation": self.operation,
            "reason": self.reason,
            "table_name": self.table_name,
            "started_at": _utc_now_iso(),
            "metadata": self.metadata,
        }

        sb = self._get_sb_client()
        # Use PostgREST insert
        sb.post("pipeline_write_audit", [record])

        self._started = True
        return self.run_id

    def complete(self, row_count: int) -> None:
        """Mark the operation as completed successfully.

        Args:
            row_count: Number of rows written
        """
        if not self._started:
            raise RuntimeError("audit not started; call start() first")

        # Update the existing audit record (created by start())
        import urllib.parse
        from sbclient import _request
        params = f"?run_id=eq.{urllib.parse.quote(self.run_id)}"
        _request(
            "PATCH",
            "/rest/v1/pipeline_write_audit",
            body={"row_count": row_count, "completed_at": _utc_now_iso()},
            params=params,
        )

    def fail(self, error_message: str) -> None:
        """Mark the operation as failed.

        Args:
            error_message: Description of the failure
        """
        if not self._started:
            raise RuntimeError("audit not started; call start() first")

        sb = self._get_sb_client()
        # Update the existing audit record (created by start()) to mark as failed
        import urllib.parse
        params = f"?run_id=eq.{urllib.parse.quote(self.run_id)}"
        # Use PATCH via _request directly since sbclient may not expose patch
        from sbclient import _request
        _request(
            "PATCH",
            "/rest/v1/pipeline_write_audit",
            body={
                "failed_at": _utc_now_iso(),
                "error_message": error_message[:2000],  # Truncate long errors
            },
            params=params,
        )

    def audit_row(self, row: dict[str, Any]) -> dict[str, Any]:
        """Add audit fields to a data row before writing.

        Returns a copy of the row with _writer_identity, _run_id,
        and _written_at fields added.

        Args:
            row: The data row dict

        Returns:
            Copy of row with audit fields
        """
        if not self._started:
            raise RuntimeError("audit not started; call start() first")

        audited = dict(row)
        audited["_writer_identity"] = self.writer_identity
        audited["_run_id"] = self.run_id
        audited["_written_at"] = _utc_now_iso()
        return audited

    def audit_rows(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Add audit fields to multiple data rows.

        Args:
            rows: List of data row dicts

        Returns:
            List of rows with audit fields
        """
        return [self.audit_row(r) for r in rows]
