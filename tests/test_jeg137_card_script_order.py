#!/usr/bin/env python3
"""Regression tests for the JEG-137 slip/grace card wiring (R10 review).

Guards the defects found in independent review of the JEG-137 worker branch:

1. TDZ crash: the worker defined the slip/grace helpers
   (slipBySource/graceLabel/slipCard) as `const` arrow functions AFTER the
   card-building map that calls them. `const` is in the temporal dead zone
   until its declaration executes, so the whole dataset-health section would
   have thrown ReferenceError on page load. The guard asserts every helper
   is *defined* before its first *use* in the page source.

2. Workflow start-time capture: each scheduled workflow must capture
   WORKFLOW_STARTED_AT in an early step (job start) rather than timestamping
   the recording step at job end -- otherwise scheduler slip is inflated by
   the job's own duration.

3. Sync wiring: sync_dashboard_artifacts.py must copy
   output/deadline-checker.json -> app assets when the checker has produced
   it (the card falls back to the 6h default when the asset is absent).
"""

import re
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
INDEX_HTML = REPO_ROOT / "app" / "trade-value-chart" / "index.html"
SYNC_SCRIPT = REPO_ROOT / "pipelines" / "sync_dashboard_artifacts.py"

# Helpers the card template calls inside the per-source map.
HELPERS = ("slipBySource", "graceLabel", "slipCard")


def check_helper_order(html: str) -> list[str]:
    """Return helper names whose definition does NOT precede their first use."""
    bad = []
    for name in HELPERS:
        def_match = re.search(rf"const {name}\s*=", html)
        # First use: a call site like graceLabel( or slipCard( (slipBySource is
        # used as a value; its first textual occurrence after the Promise.all
        # fetch block is the call site region).
        use_match = re.search(rf"{name}\s*\(", html)
        if use_match is None:
            use_match = re.search(rf"{name}\b", html)
        if def_match is None or use_match is None:
            bad.append(name)
        elif def_match.start() > use_match.start():
            bad.append(name)
    return bad


class TestCardScriptOrder(unittest.TestCase):
    def test_helpers_defined_before_use_in_live_page(self):
        """The real index.html must define each helper before its first use."""
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertEqual(check_helper_order(html), [])

    def test_guard_catches_tdz_order(self):
        """Discrimination: helpers defined AFTER use must be flagged."""
        buggy = (
            "const cards = live.map(k => `<div>${graceLabel(k)}${slipCard(k)}</div>`);\n"
            "const slipBySource = {};\n"
            "const graceLabel = (s) => s;\n"
            "const slipCard = (s) => s;\n"
        )
        bad = check_helper_order(buggy)
        self.assertIn("graceLabel", bad)
        self.assertIn("slipCard", bad)

    def test_guard_accepts_correct_order(self):
        """Discrimination: helpers defined BEFORE use must pass."""
        fixed = (
            "const slipBySource = {};\n"
            "const graceLabel = (s) => s;\n"
            "const slipCard = (s) => s;\n"
            "const cards = live.map(k => `<div>${graceLabel(k)}${slipCard(k)}</div>`);\n"
        )
        self.assertEqual(check_helper_order(fixed), [])

    def test_card_fetch_is_fail_safe(self):
        """The deadline-checker fetch must tolerate a missing asset."""
        html = INDEX_HTML.read_text(encoding="utf-8")
        self.assertIn('fetch("assets/deadline-checker.json").catch(()=>null)', html)


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
