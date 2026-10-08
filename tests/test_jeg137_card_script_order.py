#!/usr/bin/env python3
"""Regression tests for the JEG-137 slip/grace card wiring (R10 review).

Guards the defects found in independent review of the JEG-137 worker branch.

Removed 2026-10-08: the TDZ helper-order checks (slipBySource/graceLabel/
slipCard) and the deadline-checker fetch check. They read
app/trade-value-chart/index.html, and the per-source dataset-health cards they
guarded were deleted from that page in 0ca6ab4 (JEG-211, 2026-10-03), so they
failed on a page that no longer has the code.

1. Workflow start-time capture: each scheduled workflow must capture
   WORKFLOW_STARTED_AT in an early step (job start) rather than timestamping
   the recording step at job end -- otherwise scheduler slip is inflated by
   the job's own duration.

2. Sync wiring: sync_dashboard_artifacts.py must copy
   output/deadline-checker.json -> app assets when the checker has produced
   it (the card falls back to the 6h default when the asset is absent).
"""

import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SYNC_SCRIPT = REPO_ROOT / "pipelines" / "sync_dashboard_artifacts.py"


class TestWorkflowStartCapture(unittest.TestCase):
    WORKFLOWS = (
        "rebuild-chain.yml",
        "espn-supabase-sync.yml",
        "cbsros-supabase-sync.yml",
        "fantasycalc-drift.yml",
    )

    def test_start_captured_before_record_step(self):
        """WORKFLOW_STARTED_AT must be set in an early step and read later."""
        for name in self.WORKFLOWS:
            path = REPO_ROOT / ".github" / "workflows" / name
            text = path.read_text(encoding="utf-8")
            with self.subTest(workflow=name):
                set_pos = text.find("WORKFLOW_STARTED_AT=$(date")
                read_pos = text.find("${WORKFLOW_STARTED_AT")
                self.assertGreater(set_pos, -1, "start-capture step missing")
                self.assertGreater(read_pos, -1, "record step does not read it")
                self.assertLess(set_pos, read_pos, "capture must precede record")


class TestSyncWiring(unittest.TestCase):
    def test_sync_copies_deadline_checker_when_present(self):
        """sync must stage output/deadline-checker.json into app assets."""
        text = SYNC_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("deadline-checker.json", text)
        # Guarded copy: absent file must not break the sync.
        self.assertIn("deadline_checker.exists()", text)


if __name__ == "__main__":
    unittest.main()
