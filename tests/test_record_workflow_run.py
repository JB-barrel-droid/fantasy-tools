#!/usr/bin/env python3
"""JEG-1159: unit tests for pipelines/lib/record_workflow_run.py.

The module records a workflow run's ``started_at`` and ``cron_at`` into the
``workflow_runs`` section of comparison-chain-status.json (JEG-137, R10). Two
behaviours matter and neither is covered today:

  - ``compute_cron_at``: the most recent cron fire at or before ``started_at``,
    including the rollover to the previous day when the run starts before the
    scheduled time; and ``None`` for anything it cannot read honestly
    (empty/dispatch, malformed, non-numeric, wrong field count).
  - ``main``: idempotent merge into the JSON store -- creates a missing file,
    overwrites the same workflow's entry instead of duplicating, preserves
    other workflows' entries, and records ``cron_at`` null for dispatch.

All datetimes are fixed; no test reads the real clock.

Run via ``python -m unittest tests.test_record_workflow_run``.
"""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest import mock

from pipelines.lib.record_workflow_run import compute_cron_at, main

# 2026-03-10 is a Tuesday; 2026-03-09 the preceding Monday.
BEFORE_FIRE = datetime(2026, 3, 10, 10, 0, 0, tzinfo=timezone.utc)
AFTER_FIRE = datetime(2026, 3, 10, 12, 0, 0, tzinfo=timezone.utc)


class TestComputeCronAt(unittest.TestCase):
    def test_empty_cron_returns_none(self):
        # workflow_dispatch passes "" and must record no cron_at (JEG-137).
        self.assertIsNone(compute_cron_at("", AFTER_FIRE))

    def test_wrong_field_count_returns_none(self):
        self.assertIsNone(compute_cron_at("30 11 * *", AFTER_FIRE))
        self.assertIsNone(compute_cron_at("30 11 * * * *", AFTER_FIRE))

    def test_malformed_returns_none(self):
        # Non-numeric minute/hour, and a non-"*" day-of-month, must not guess.
        self.assertIsNone(compute_cron_at("xx 11 * * *", AFTER_FIRE))
        self.assertIsNone(compute_cron_at("30 yy * * *", AFTER_FIRE))
        self.assertIsNone(compute_cron_at("30 11 5 * *", AFTER_FIRE))

    def test_daily_after_fire_uses_same_day(self):
        got = compute_cron_at("30 11 * * *", AFTER_FIRE)
        self.assertEqual(got, "2026-03-10T11:30:00+00:00")

    def test_daily_before_fire_rolls_back_one_day(self):
        # started_at 10:00 is before the 11:30 fire, so the most recent fire is
        # the previous day's -- the rollover the ticket calls out.
        got = compute_cron_at("30 11 * * *", BEFORE_FIRE)
        self.assertEqual(got, "2026-03-09T11:30:00+00:00")


class TestMainMerge(unittest.TestCase):
    def _run(self, output: Path, workflow: str, started_at: str,
             cron: str = "", run_id: str = "1") -> int:
        argv = [
            "record_workflow_run.py",
            "--workflow", workflow,
            "--started-at", started_at,
            "--cron", cron,
            "--run-id", run_id,
            "--status", "success",
            "--output", str(output),
        ]
        with mock.patch.object(sys, "argv", argv):
            return main()

    def test_missing_file_is_created(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "nested" / "comparison-chain-status.json"
            self.assertFalse(output.exists())
            self.assertEqual(
                self._run(output, "Rebuild comparison chain",
                          "2026-03-10T12:00:00Z", "30 11 * * *"), 0)
            self.assertTrue(output.exists())
            data = json.loads(output.read_text())
            self.assertIn("Rebuild comparison chain", data["workflow_runs"])

    def test_rerun_overwrites_same_workflow_no_duplicate(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "comparison-chain-status.json"
            self._run(output, "Rebuild comparison chain",
                      "2026-03-10T12:00:00Z", "30 11 * * *", run_id="1")
            self._run(output, "Rebuild comparison chain",
                      "2026-03-11T12:00:00Z", "30 11 * * *", run_id="2")
            data = json.loads(output.read_text())
            runs = data["workflow_runs"]
            # One key per workflow: the second run replaced, not appended.
            self.assertEqual(list(runs), ["Rebuild comparison chain"])
            self.assertEqual(runs["Rebuild comparison chain"]["run_id"], 2)
            self.assertEqual(runs["Rebuild comparison chain"]["started_at"],
                             "2026-03-11T12:00:00+00:00")

    def test_other_workflows_preserved(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "comparison-chain-status.json"
            self._run(output, "Alpha workflow", "2026-03-10T12:00:00Z")
            self._run(output, "Bravo workflow", "2026-03-10T13:00:00Z")
            data = json.loads(output.read_text())
            self.assertEqual(sorted(data["workflow_runs"]),
                             ["Alpha workflow", "Bravo workflow"])

    def test_dispatch_records_cron_at_null(self):
        with tempfile.TemporaryDirectory() as td:
            output = Path(td) / "comparison-chain-status.json"
            self._run(output, "Alpha workflow", "2026-03-10T12:00:00Z",
                      cron="")
            data = json.loads(output.read_text())
            entry = data["workflow_runs"]["Alpha workflow"]
            self.assertIsNone(entry["cron_at"])
            self.assertIsNone(entry["cron"])
            self.assertIsNone(entry["slip_minutes"])


if __name__ == "__main__":
    unittest.main()
