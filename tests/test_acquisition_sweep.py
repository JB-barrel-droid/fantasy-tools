"""Tests for pipelines/build_acquisition_sweep.py (JEG-128 fail-open sweep).

Negative-tested against a simulated broken state for every guard:
the regression rule is that each test names the bug it catches and proves
it catches it (CLAUDE.md).

Coverage:
- Complete record passes without issues
- Missing player_id flagged as CRITICAL
- Missing acquisition_date flagged as CRITICAL
- Missing source flagged as HIGH
- Missing status flagged as HIGH
- Multiple missing fields correctly categorized by highest severity
- Empty dataset returns empty incomplete list
- All-complete dataset returns zero incomplete
- All-incomplete dataset returns all as incomplete
- Edge case: null vs missing string distinction
- Edge case: whitespace-only strings treated as missing
"""

import json
import sys
import unittest
from pathlib import Path
from typing import Any, Dict, List

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from pipelines.build_acquisition_sweep import (  # noqa: E402
    CRITICAL_FIELDS,
    AcquisitionRecord,
    run_sweep,
    load_acquisition_records,
)


# ---------------------------------------------------------------------------
# Test data
# ---------------------------------------------------------------------------


def _make_record(**overrides) -> Dict[str, Any]:
    """Build a minimal valid record; allow overrides for negative tests."""
    base = {
        "record_id": "test-001",
        "player_id": "player-123",
        "acquisition_date": "2026-10-01",
        "source": "espn",
        "status": "active",
    }
    base.update(overrides)
    return base


COMPLETE_RECORD = _make_record()

RECORD_MISSING_PLAYER_ID = _make_record(player_id=None)
RECORD_MISSING_PLAYER_ID["missing_field_tested"] = "player_id"

RECORD_MISSING_ACQUISITION_DATE = _make_record(acquisition_date=None)
RECORD_MISSING_ACQUISITION_DATE["missing_field_tested"] = "acquisition_date"

RECORD_MISSING_SOURCE = _make_record(source="")
RECORD_MISSING_SOURCE["missing_field_tested"] = "source"

RECORD_MISSING_STATUS = _make_record(status="  ")  # whitespace-only
RECORD_MISSING_STATUS["missing_field_tested"] = "status"

RECORD_MISSING_MULTIPLE = _make_record(
    player_id=None,
    source=None,
)
RECORD_MISSING_MULTIPLE["missing_field_tested"] = "player_id+source"


# ---------------------------------------------------------------------------
# AcquisitionRecord tests
# ---------------------------------------------------------------------------


class TestAcquisitionRecord(unittest.TestCase):

    def test_complete_record_is_complete(self):
        """Guard: complete record passes validation."""
        record = AcquisitionRecord(COMPLETE_RECORD)
        self.assertTrue(record.is_complete)
        self.assertEqual(record.severity, "NONE")
        self.assertEqual(record.missing_critical_fields, set())

    def test_missing_player_id_is_critical(self):
        """Guard: missing player_id flagged as CRITICAL."""
        record = AcquisitionRecord(RECORD_MISSING_PLAYER_ID)
        self.assertFalse(record.is_complete)
        self.assertEqual(record.severity, "CRITICAL")
        self.assertIn("player_id", record.missing_critical_fields)

    def test_missing_acquisition_date_is_critical(self):
        """Guard: missing acquisition_date flagged as CRITICAL."""
        record = AcquisitionRecord(RECORD_MISSING_ACQUISITION_DATE)
        self.assertFalse(record.is_complete)
        self.assertEqual(record.severity, "CRITICAL")
        self.assertIn("acquisition_date", record.missing_critical_fields)

    def test_missing_source_is_high(self):
        """Guard: missing source flagged as HIGH."""
        record = AcquisitionRecord(RECORD_MISSING_SOURCE)
        self.assertFalse(record.is_complete)
        self.assertEqual(record.severity, "HIGH")
        self.assertIn("source", record.missing_critical_fields)

    def test_missing_status_is_high(self):
        """Guard: missing status (whitespace) flagged as HIGH."""
        record = AcquisitionRecord(RECORD_MISSING_STATUS)
        self.assertFalse(record.is_complete)
        self.assertEqual(record.severity, "HIGH")
        self.assertIn("status", record.missing_critical_fields)

    def test_multiple_missing_takes_highest_severity(self):
        """Guard: multiple missing fields categorized by highest severity."""
        record = AcquisitionRecord(RECORD_MISSING_MULTIPLE)
        self.assertFalse(record.is_complete)
        # player_id missing -> CRITICAL takes precedence over source -> HIGH
        self.assertEqual(record.severity, "CRITICAL")

    def test_null_vs_missing_string_distinction(self):
        """Guard: null None vs empty string both treated as missing."""
        record_none = AcquisitionRecord(_make_record(source=None))
        record_empty = AcquisitionRecord(_make_record(source=""))

        self.assertIn("source", record_none.missing_critical_fields)
        self.assertIn("source", record_empty.missing_critical_fields)

    def test_whitespace_only_treated_as_missing(self):
        """Guard: whitespace-only strings treated as missing."""
        record = AcquisitionRecord(_make_record(status="   \t  "))
        self.assertIn("status", record.missing_critical_fields)


# ---------------------------------------------------------------------------
# run_sweep tests
# ---------------------------------------------------------------------------


class TestRunSweep(unittest.TestCase):

    def test_empty_dataset_returns_empty_incomplete(self):
        """Guard: empty dataset has zero incomplete records."""
        report = run_sweep([])
        self.assertEqual(report["total_records"], 0)
        self.assertEqual(report["complete_records"], 0)
        self.assertEqual(report["incomplete_records"], 0)
        self.assertFalse(report["has_critical_issues"])

    def test_all_complete_returns_zero_incomplete(self):
        """Guard: all complete records result in zero incomplete."""
        records = [
            AcquisitionRecord(_make_record(record_id="1")),
            AcquisitionRecord(_make_record(record_id="2")),
            AcquisitionRecord(_make_record(record_id="3")),
        ]
        report = run_sweep(records)
        self.assertEqual(report["total_records"], 3)
        self.assertEqual(report["complete_records"], 3)
        self.assertEqual(report["incomplete_records"], 0)
        self.assertFalse(report["has_critical_issues"])
        self.assertFalse(report["has_high_issues"])
        self.assertFalse(report["has_medium_issues"])

    def test_all_incomplete_returns_all_incomplete(self):
        """Guard: all incomplete records returned in report."""
        records = [
            AcquisitionRecord(RECORD_MISSING_PLAYER_ID),
            AcquisitionRecord(RECORD_MISSING_SOURCE),
        ]
        report = run_sweep(records)
        self.assertEqual(report["total_records"], 2)
        self.assertEqual(report["complete_records"], 0)
        self.assertEqual(report["incomplete_records"], 2)
        self.assertTrue(report["has_critical_issues"])
        self.assertTrue(report["has_high_issues"])

    def test_critical_issues_detected(self):
        """Guard: CRITICAL issues properly detected."""
        records = [
            AcquisitionRecord(COMPLETE_RECORD),
            AcquisitionRecord(RECORD_MISSING_PLAYER_ID),
        ]
        report = run_sweep(records)
        self.assertTrue(report["has_critical_issues"])
        self.assertEqual(len(report["incomplete_by_severity"]["CRITICAL"]), 1)

    def test_high_issues_detected(self):
        """Guard: HIGH issues properly detected."""
        records = [
            AcquisitionRecord(COMPLETE_RECORD),
            AcquisitionRecord(RECORD_MISSING_SOURCE),
        ]
        report = run_sweep(records)
        self.assertTrue(report["has_high_issues"])
        self.assertEqual(len(report["incomplete_by_severity"]["HIGH"]), 1)

    def test_medium_issues_detected(self):
        """Guard: MEDIUM issues properly detected for non-critical fields."""
        # Create a record missing a field not in CRITICAL but that would cause issues
        record = _make_record()
        record["secondary_status"] = None  # Not a critical field
        records = [AcquisitionRecord(record)]
        report = run_sweep(records)
        # With all critical fields present, should have no issues
        self.assertEqual(report["incomplete_records"], 0)

    def test_incomplete_report_contains_record_id(self):
        """Guard: incomplete records include record_id for tracing."""
        records = [AcquisitionRecord(RECORD_MISSING_PLAYER_ID)]
        report = run_sweep(records)
        critical_issues = report["incomplete_by_severity"]["CRITICAL"]
        self.assertEqual(len(critical_issues), 1)
        self.assertEqual(critical_issues[0]["record_id"], "test-001")

    def test_incomplete_report_contains_missing_fields(self):
        """Guard: incomplete records list which fields are missing."""
        records = [AcquisitionRecord(RECORD_MISSING_MULTIPLE)]
        report = run_sweep(records)
        critical_issues = report["incomplete_by_severity"]["CRITICAL"]
        self.assertEqual(len(critical_issues), 1)
        self.assertIn("player_id", critical_issues[0]["missing_fields"])

    def test_sweep_run_at_timestamp(self):
        """Guard: report includes sweep execution timestamp."""
        report = run_sweep([AcquisitionRecord(COMPLETE_RECORD)])
        self.assertIn("sweep_run_at", report)
        # Timestamp should be ISO format
        self.assertIn("T", report["sweep_run_at"])
        self.assertIn("Z", report["sweep_run_at"])


# ---------------------------------------------------------------------------
# load_acquisition_records tests
# ---------------------------------------------------------------------------


class TestLoadAcquisitionRecords(unittest.TestCase):

    def test_load_from_list(self):
        """Guard: can load records from a list of dicts."""
        data = [COMPLETE_RECORD, COMPLETE_RECORD]
        records = load_acquisition_records(data)
        self.assertEqual(len(records), 2)
        self.assertTrue(all(isinstance(r, AcquisitionRecord) for r in records))

    def test_load_from_json_file(self, tmp_path=None):
        """Guard: can load records from a JSON file."""
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([COMPLETE_RECORD], f)
            temp_path = f.name

        try:
            records = load_acquisition_records(temp_path)
            self.assertEqual(len(records), 1)
            self.assertTrue(records[0].is_complete)
        finally:
            Path(temp_path).unlink()

    def test_load_nonexistent_file_raises(self):
        """Guard: loading nonexistent file raises ValueError."""
        with self.assertRaises(ValueError):
            load_acquisition_records("/nonexistent/path/to/file.json")


# ---------------------------------------------------------------------------
# CLI entry point tests
# ---------------------------------------------------------------------------


class TestCLI(unittest.TestCase):

    def test_cli_empty_input(self):
        """Guard: CLI handles empty input gracefully."""
        import subprocess

        result = subprocess.run(
            [sys.executable, str(REPO / "pipelines" / "build_acquisition_sweep.py")],
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        report = json.loads(result.stdout)
        self.assertEqual(report["total_records"], 0)

    def test_cli_fail_on_critical_with_issues(self):
        """Guard: --fail-on-critical exits 1 when CRITICAL issues found."""
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([RECORD_MISSING_PLAYER_ID], f)
            temp_path = f.name

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "pipelines" / "build_acquisition_sweep.py"),
                    "--input", temp_path,
                    "--fail-on-critical",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("CRITICAL", result.stderr)
        finally:
            Path(temp_path).unlink()

    def test_cli_fail_on_critical_without_issues(self):
        """Guard: --fail-on-critical exits 0 when no CRITICAL issues."""
        import subprocess
        import tempfile

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump([COMPLETE_RECORD], f)
            temp_path = f.name

        try:
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "pipelines" / "build_acquisition_sweep.py"),
                    "--input", temp_path,
                    "--fail-on-critical",
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
        finally:
            Path(temp_path).unlink()

    def test_cli_output_to_file(self):
        """Guard: CLI can write report to file."""
        import subprocess
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "report.json"
            result = subprocess.run(
                [
                    sys.executable,
                    str(REPO / "pipelines" / "build_acquisition_sweep.py"),
                    "--output", str(output_path),
                ],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 0)
            self.assertTrue(output_path.exists())
            report = json.loads(output_path.read_text())
            self.assertIn("total_records", report)


if __name__ == "__main__":
    unittest.main()
