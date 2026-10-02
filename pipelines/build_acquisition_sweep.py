#!/usr/bin/env python3
"""Fail-open sweep for player acquisition records.

This sweep catches cases where player acquisition records may be incomplete.
It verifies that all acquisition records have complete metadata and flags
any records that are missing critical fields.

Critical fields that must be present:
- player_id: unique player identifier
- acquisition_date: when the player was acquired
- source: where the data came from (espn, cbs, fantasypros, etc.)
- status: current status of the acquisition (active, pending, failed, etc.)

Fail-open case: a record that passes validation but has null/missing critical
fields would silently continue through the system, potentially causing issues
later. This sweep catches those cases.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

# Add parent to path for imports
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Critical fields that must be present in every acquisition record
CRITICAL_FIELDS = frozenset([
    "player_id",
    "acquisition_date",
    "source",
    "status",
])

# Fields that are required but may have safe defaults
OPTIONAL_WITH_DEFAULT = frozenset([
    "player_key",
    "week",
    "season",
])


class AcquisitionRecord:
    """Represents a single player acquisition record."""

    def __init__(self, data: Dict[str, Any]):
        self.data = data
        self.record_id = data.get("record_id") or data.get("id")
        self.player_id = data.get("player_id")
        self.acquisition_date = data.get("acquisition_date")
        self.source = data.get("source")
        self.status = data.get("status")

    @property
    def missing_critical_fields(self) -> Set[str]:
        """Return set of critical fields that are missing or null."""
        missing = set()
        for field in CRITICAL_FIELDS:
            value = self.data.get(field)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing.add(field)
        return missing

    @property
    def is_complete(self) -> bool:
        """Check if record has all critical fields populated."""
        return len(self.missing_critical_fields) == 0

    @property
    def severity(self) -> str:
        """Determine severity of incompleteness.

        - CRITICAL: player_id or acquisition_date missing (can't identify record)
        - HIGH: source or status missing (can't verify provenance)
        - MEDIUM: other critical fields missing
        """
        missing = self.missing_critical_fields
        if "player_id" in missing or "acquisition_date" in missing:
            return "CRITICAL"
        if "source" in missing or "status" in missing:
            return "HIGH"
        if missing:
            return "MEDIUM"
        return "NONE"


def load_acquisition_records(data_source: Any) -> List[AcquisitionRecord]:
    """Load acquisition records from a data source.

    Args:
        data_source: Either a list of dicts (mock/test data) or a path to JSON file

    Returns:
        List of AcquisitionRecord objects
    """
    if isinstance(data_source, list):
        return [AcquisitionRecord(record) for record in data_source]

    # Assume it's a path to JSON file
    path = Path(data_source)
    if path.exists():
        with open(path) as f:
            data = json.load(f)
            return [AcquisitionRecord(record) for record in data]

    raise ValueError(f"Cannot load data from: {data_source}")


def run_sweep(records: List[AcquisitionRecord]) -> Dict[str, Any]:
    """Run the fail-open sweep on acquisition records.

    Args:
        records: List of acquisition records to check

    Returns:
        Sweep report with findings grouped by severity
    """
    incomplete_by_severity: Dict[str, List[Dict[str, Any]]] = {
        "CRITICAL": [],
        "HIGH": [],
        "MEDIUM": [],
    }

    complete_count = 0
    total_count = len(records)

    for record in records:
        if record.is_complete:
            complete_count += 1
        else:
            severity = record.severity
            incomplete_by_severity[severity].append({
                "record_id": record.record_id,
                "missing_fields": sorted(record.missing_critical_fields),
                "severity": severity,
                "data_preview": _preview_record(record.data),
            })

    # Sort each severity group by record_id for deterministic output
    for severity in incomplete_by_severity:
        incomplete_by_severity[severity].sort(key=lambda x: str(x.get("record_id", "")))

    return {
        "sweep_run_at": datetime.now(timezone.utc).isoformat(),
        "total_records": total_count,
        "complete_records": complete_count,
        "incomplete_records": total_count - complete_count,
        "incomplete_by_severity": incomplete_by_severity,
        "has_critical_issues": len(incomplete_by_severity["CRITICAL"]) > 0,
        "has_high_issues": len(incomplete_by_severity["HIGH"]) > 0,
        "has_medium_issues": len(incomplete_by_severity["MEDIUM"]) > 0,
    }


def _preview_record(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create a safe preview of record data, excluding sensitive fields."""
    preview = {}
    for key, value in data.items():
        if key in ("password", "token", "secret", "api_key"):
            preview[key] = "[REDACTED]"
        elif isinstance(value, str) and len(value) > 100:
            preview[key] = value[:100] + "..."
        else:
            preview[key] = value
    return preview


def main(argv: Optional[List[str]] = None) -> int:
    """Main entry point for the sweep."""
    parser = argparse.ArgumentParser(
        description="Fail-open sweep for player acquisition records"
    )
    parser.add_argument(
        "--input",
        "-i",
        help="Path to JSON file containing acquisition records",
    )
    parser.add_argument(
        "--output",
        "-o",
        help="Path to write sweep report (default: stdout)",
    )
    parser.add_argument(
        "--fail-on-critical",
        action="store_true",
        help="Exit with error code if CRITICAL issues found",
    )
    args = parser.parse_args(argv)

    # If no input file, use mock data for testing
    if args.input:
        records = load_acquisition_records(args.input)
    else:
        # Empty sweep when no data provided
        records = []

    report = run_sweep(records)

    # Output report
    output_json = json.dumps(report, indent=2, sort_keys=True)

    if args.output:
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(output_json)
        print(f"Sweep report written to: {args.output}")
    else:
        print(output_json)

    # Exit code based on findings
    if args.fail_on_critical and report["has_critical_issues"]:
        print(f"ERROR: Found {len(report['incomplete_by_severity']['CRITICAL'])} CRITICAL issues")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
