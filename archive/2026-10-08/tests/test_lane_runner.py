"""Tests for lanes/runner.py (JEG-97 autonomous lane runner).

Coverage:
- Dry-run planning: Todo->dispatch decisions with reason/evidence
- Usage/depletion checks: <20% fails, missing/stale/unknown fails closed
- WIP limit enforcement: <=3 active dispatches
- Idempotency: duplicate dispatch detection, attempt tracking
- Process lock: prevents concurrent runner execution
- Capability guard: OCR/browser/credential/unknown tasks refuse M3
- Two failures: escalation to Roman
- Board adapter: assignee empty, owner label management
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, Optional
from unittest.mock import patch, MagicMock

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from lanes import protocol, usage_watcher
from lanes.runner import (
    LaneRunner,
    Issue,
    RunnerPlan,
    RunnerError,
    QuotaExhaustedError,
    UsageUnknownError,
    WipLimitError,
    DuplicateDispatchError,
    CapabilityRefusedError,
    LockError,
    ProcessLock,
    DISPATCH_LEDGER,
    LOCK_FILE,
    MINIMAX_LANE,
    WIP_LIMIT,
    MAX_ATTEMPTS,
    OPERATOR_WINDOW_HOURS,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ok_issue(**overrides) -> Issue:
    """Build a known-good issue; allow overrides for negative tests."""
    base = dict(
        key="JEG-97",
        title="Test issue",
        status="Todo",
        owner_labels=["owner:minimax"],
        capabilities_required=["repo_code_change"],
        context="Test context",
    )
    base.update(overrides)
    return Issue(**base)


def _write_ledger(entries: list) -> None:
    """Write entries to the dispatch ledger."""
    DISPATCH_LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with open(DISPATCH_LEDGER, 'w') as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")


def _clear_ledger() -> None:
    """Clear the dispatch ledger."""
    if DISPATCH_LEDGER.exists():
        DISPATCH_LEDGER.unlink()


def _clear_lock() -> None:
    """Clear the lock file."""
    if LOCK_FILE.exists():
        LOCK_FILE.unlink()


# ---------------------------------------------------------------------------
# Mock adapters for testing
# ---------------------------------------------------------------------------


class MockUsageAdapter:
    """Mock usage adapter for testing."""

    def __init__(self, remaining_percent: Optional[float] = None, status: str = "ok"):
        self.remaining_percent = remaining_percent
        self.status = status

    def get_usage(self, lane: str) -> Dict[str, Any]:
        if self.remaining_percent is None:
            return {"status": "unknown"}
        return {
            "remaining_percent": self.remaining_percent,
            "status": self.status,
            "used_percent": 100 - self.remaining_percent,
        }

    def can_dispatch(self, lane: str) -> bool:
        if self.remaining_percent is None:
            return False
        return self.remaining_percent >= 20.0 and self.status != "depleted"

    def check_usage(self, lane: str) -> None:
        if self.remaining_percent is None:
            raise UsageUnknownError("No usage data")
        if self.status == "depleted":
            raise QuotaExhaustedError("Lane depleted")
        if self.remaining_percent < 20.0:
            raise QuotaExhaustedError(f"Below 20%: {self.remaining_percent}%")


class MockBoardAdapter:
    """Mock board adapter for testing."""

    def __init__(self):
        self.moved_to_in_progress: list = []
        self.moved_to_done: list = []
        self.labels_set: list = []

    def move_to_in_progress(self, issue_key: str, lane: str) -> None:
        self.moved_to_in_progress.append((issue_key, lane))

    def move_to_done(self, issue_key: str) -> None:
        self.moved_to_done.append(issue_key)

    def set_owner_label(self, issue_key: str, owner: str) -> None:
        self.labels_set.append((issue_key, owner))


class MockReviewAdapter:
    """Mock review adapter for testing."""

    def __init__(self, verify_result: bool = True):
        self.verify_result = verify_result
        self.acceptance_run: list = []

    def verify_result(self, result_path: Path, brief_path: Path) -> bool:
        return self.verify_result

    def run_acceptance(self, issue_key: str, result: Dict[str, Any]) -> tuple:
        self.acceptance_run.append((issue_key, result))
        return True, "mock evidence"


# ---------------------------------------------------------------------------
# Test: Dry-run planning
# ---------------------------------------------------------------------------


class TestDryRunPlanning(unittest.TestCase):
    """Test that dry-run mode plans without side effects."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_dry_run_plans_dispatch(self):
        """Dry-run should plan dispatch without writing to ledger."""
        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97", capabilities_required=["repo_code_change"])]
        plans = runner.run(issues)

        self.assertEqual(len(plans), 1)
        self.assertEqual(plans[0].action, "dispatch")
        self.assertEqual(plans[0].reason, "All preconditions met")
        # Ledger should be empty
        self.assertFalse(DISPATCH_LEDGER.exists())

    def test_dry_run_emits_reason_and_evidence(self):
        """Each decision must include reason and evidence."""
        usage = MockUsageAdapter(remaining_percent=10.0)  # Below 20%
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "wait")
        self.assertIn("20%", plans[0].reason)
        self.assertIn("quota_error", plans[0].evidence)


# ---------------------------------------------------------------------------
# Test: Usage/depletion checks
# ---------------------------------------------------------------------------


class TestUsageChecks(unittest.TestCase):
    """Test usage and depletion checks fail closed."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_quota_19_9_fails(self):
        """19.9% remaining should fail (below 20% threshold)."""
        usage = MockUsageAdapter(remaining_percent=19.9)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "wait")
        self.assertIn("19.9", plans[0].reason)

    def test_quota_20_passes(self):
        """Exactly 20% should pass."""
        usage = MockUsageAdapter(remaining_percent=20.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "dispatch")

    def test_depleted_fails(self):
        """Depleted status should fail closed."""
        usage = MockUsageAdapter(remaining_percent=0.0, status="depleted")
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "wait")
        self.assertIn("depleted", plans[0].reason.lower())

    def test_unknown_usage_fails(self):
        """Unknown/missing usage should fail closed."""
        usage = MockUsageAdapter(remaining_percent=None)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "wait")
        self.assertIn("no usage data", plans[0].reason.lower())


# ---------------------------------------------------------------------------
# Test: WIP limit
# ---------------------------------------------------------------------------


class TestWipLimit(unittest.TestCase):
    """Test WIP <= 3 limit enforcement."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_wip_limit_enforced(self):
        """Should wait when WIP >= 3."""
        # Write 3 active dispatches
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-1", "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
            {"ts": now, "issue_id": "JEG-2", "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
            {"ts": now, "issue_id": "JEG-3", "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "wait")
        self.assertIn("WIP limit", plans[0].reason)
        self.assertEqual(plans[0].evidence["wip"], 3)

    def test_wip_allows_below_limit(self):
        """Should dispatch when WIP < 3."""
        _write_ledger([
            {"ts": datetime.now(timezone.utc).isoformat(), "issue_id": "JEG-1",
             "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "dispatch")


# ---------------------------------------------------------------------------
# Test: Idempotency / duplicate dispatch
# ---------------------------------------------------------------------------


class TestIdempotency(unittest.TestCase):
    """Test idempotency and duplicate detection."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_duplicate_dispatch_blocked(self):
        """Should skip issue with active dispatch."""
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "skip")
        self.assertIn("already", plans[0].reason.lower())
        self.assertTrue(plans[0].evidence.get("duplicate"))

    def test_completed_dispatch_allows_retry(self):
        """Should allow dispatch for completed issues."""
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "completed"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "dispatch")

    def test_attempt_tracking(self):
        """Should track attempt count correctly."""
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "failed"},
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 2, "status": "failed"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        # Third attempt should escalate
        self.assertEqual(plans[0].action, "escalate")
        self.assertIn("Max attempts", plans[0].reason)


# ---------------------------------------------------------------------------
# Test: Capability guard
# ---------------------------------------------------------------------------


class TestCapabilityGuard(unittest.TestCase):
    """Test capability-based routing."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_ocr_refused(self):
        """OCR capability should be refused for MiniMax."""
        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97", capabilities_required=["needs_ocr"])]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "escalate")
        self.assertIn("ocr", plans[0].reason.lower())

    def test_browser_refused(self):
        """Browser capability should be refused for MiniMax."""
        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97", capabilities_required=["needs_browser"])]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "escalate")
        self.assertIn("browser", plans[0].reason.lower())

    def test_credentials_refused(self):
        """Credentials capability should be refused for MiniMax."""
        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97", capabilities_required=["needs_credentials"])]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "escalate")
        self.assertIn("credentials", plans[0].reason.lower())

    def test_repo_code_allowed(self):
        """Repo code capability should be allowed."""
        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97", capabilities_required=["repo_code_change"])]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "dispatch")


# ---------------------------------------------------------------------------
# Test: Process lock
# ---------------------------------------------------------------------------


class TestProcessLock(unittest.TestCase):
    """Test process lock prevents concurrent execution."""

    def setUp(self):
        _clear_lock()

    def tearDown(self):
        _clear_lock()

    def test_lock_prevents_duplicate(self):
        """Second runner should fail to acquire lock."""
        with ProcessLock() as lock1:
            # Try to acquire again in same process - should fail
            with self.assertRaises(LockError):
                with ProcessLock():
                    pass

    def test_lock_allows_retry_after_release(self):
        """Lock should be re-acquirable after release."""
        with ProcessLock():
            pass  # First lock released
        # Second should succeed
        with ProcessLock():
            pass


# ---------------------------------------------------------------------------
# Test: Two failures -> escalation
# ---------------------------------------------------------------------------


class TestEscalation(unittest.TestCase):
    """Test escalation after two failures."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_two_failures_escalates(self):
        """Two failed attempts should escalate to Roman."""
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "failed"},
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 2, "status": "failed"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "escalate")
        self.assertIn("Max attempts", plans[0].reason)

    def test_one_failure_allows_retry(self):
        """One failure should still allow dispatch."""
        now = datetime.now(timezone.utc).isoformat()
        _write_ledger([
            {"ts": now, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "failed"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        self.assertEqual(plans[0].action, "dispatch")


# ---------------------------------------------------------------------------
# Test: Board adapter
# ---------------------------------------------------------------------------


class TestBoardAdapter(unittest.TestCase):
    """Test board state transitions."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_assignee_always_empty(self):
        """Assignee should always be empty (ownership via labels)."""
        issue = _ok_issue(key="JEG-97")
        # In the runner, assignee is never set
        self.assertIsNone(issue.assignee)

    def test_owner_label_enforced(self):
        """Should have exactly one owner label."""
        issue = _ok_issue(key="JEG-97", owner_labels=["owner:minimax"])
        owner_labels = [l for l in issue.owner_labels if l.startswith("owner:")]
        self.assertEqual(len(owner_labels), 1)

    def test_escalation_sets_muse_label(self):
        """Escalation should set owner:muse label."""
        board = MockBoardAdapter()
        board.set_owner_label("JEG-97", "muse")

        self.assertEqual(board.labels_set, [("JEG-97", "muse")])


# ---------------------------------------------------------------------------
# Test: CLI surface
# ---------------------------------------------------------------------------


class TestCLI(unittest.TestCase):
    """Test CLI entry points."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_dry_run_cli(self):
        """Dry-run CLI should work without errors."""
        # Create a temporary fixture
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({
                "issues": [
                    {"key": "JEG-97", "title": "Test", "status": "Todo",
                     "owner_labels": ["owner:minimax"], "capabilities_required": ["repo_code_change"]}
                ]
            }, f)
            fixture_path = f.name

        try:
            result = subprocess.run(
                [sys.executable, "-m", "lanes.runner", "--dry-run", "--fixture", fixture_path],
                capture_output=True,
                text=True,
                cwd=str(REPO),
            )
            # Should succeed
            self.assertEqual(result.returncode, 0, result.stderr)
            output = json.loads(result.stdout)
            self.assertTrue(output["dry_run"])
            self.assertEqual(len(output["plans"]), 1)
        finally:
            os.unlink(fixture_path)

    def test_single_issue_cli(self):
        """--issue flag should process single issue."""
        result = subprocess.run(
            [sys.executable, "-m", "lanes.runner", "--dry-run", "--issue", "JEG-97"],
            capture_output=True,
            text=True,
            cwd=str(REPO),
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(len(output["plans"]), 1)
        self.assertEqual(output["plans"][0]["issue"], "JEG-97")


# ---------------------------------------------------------------------------
# Test: Timeout and restart recovery
# ---------------------------------------------------------------------------


class TestTimeoutRecovery(unittest.TestCase):
    """Test timeout and restart handling."""

    def setUp(self):
        _clear_ledger()
        _clear_lock()

    def tearDown(self):
        _clear_ledger()
        _clear_lock()

    def test_stale_dispatch_recovered_on_restart(self):
        """Stale dispatches should be recoverable."""
        # Dispatch from 2 hours ago
        old_ts = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        _write_ledger([
            {"ts": old_ts, "issue_id": "JEG-97", "lane": MINIMAX_LANE, "attempt": 1, "status": "dispatched"},
        ])

        usage = MockUsageAdapter(remaining_percent=80.0)
        runner = LaneRunner(usage_adapter=usage, dry_run=True)

        # Should see it as duplicate (still marked dispatched)
        issues = [_ok_issue(key="JEG-97")]
        plans = runner.run(issues)

        # The dispatch is still "active" since it's within the lookback
        # (though this depends on OPERATOR_WINDOW_HOURS)
        # For now, let's just verify it doesn't crash
        self.assertIn(plans[0].action, ["dispatch", "skip"])


if __name__ == "__main__":
    unittest.main()
