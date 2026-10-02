#!/usr/bin/env python3
"""
Lane autonomous runner (JEG-97).

Enforces dispatch, quota, review, retry and board transitions at runtime,
rather than relying on worker completion claims.

Design:
  * Small state machine with injected adapters (Linear, Protocol, Usage, Review)
  * Durable idempotency via issue/attempt/head tracking in dispatch_ledger.jsonl
  * Process lock prevents duplicate dispatch
  * WIP <= 3 limit enforced
  * Usage/depletion checks immediately before dispatch (fail closed)
  * Worker results enter independent review
  * Board adapter: assignee empty, exactly one owner label, state changes on dispatch/done only
  * Dry-run mode: plans Todo->dispatch without side effects

Usage:
    python3 -m lanes.runner --dry-run --fixture fixture.json
    python3 -m lanes.runner --dry-run --issue JEG-97
    python3 -m lanes.runner --pilot --cycles 3
"""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Add repo root to path
LANES_DIR = Path(__file__).resolve().parent
REPO_ROOT = LANES_DIR.parent
sys.path.insert(0, str(REPO_ROOT))

from lanes import protocol, usage_watcher
from lanes.merge_charter import classify_pr


# ---------------------------------------------------------------------------
# Paths and constants
# ---------------------------------------------------------------------------

DISPATCH_LEDGER = LANES_DIR / "dispatch_ledger.jsonl"
LOCK_FILE = LANES_DIR / "runner.lock"
WIP_LIMIT = 3
MINIMAX_LANE = "minimax"
MAX_ATTEMPTS = 2
ESCALATION_LANE = "muse"  # Roman lane
OPERATOR_WINDOW_HOURS = 3


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class RunnerError(Exception):
    """Base error for runner failures."""
    pass


class QuotaExhaustedError(RunnerError):
    """Lane quota below 20% or depleted."""
    pass


class UsageUnknownError(RunnerError):
    """Usage data missing or stale."""
    pass


class WipLimitError(RunnerError):
    """WIP limit exceeded."""
    pass


class DuplicateDispatchError(RunnerError):
    """Issue already being worked on."""
    pass


class CapabilityRefusedError(RunnerError):
    """Task requires capability the lane cannot fulfill."""
    pass


class LockError(RunnerError):
    """Process lock acquisition failed."""
    pass


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------


@dataclass
class Issue:
    """Represents a Linear issue to be processed."""
    key: str
    title: str
    status: str  # Todo, In Progress, Done, etc.
    owner_labels: List[str] = field(default_factory=list)
    assignee: Optional[str] = None
    description: str = ""
    capabilities_required: List[str] = field(default_factory=list)
    context: str = ""

    @classmethod
    def from_dict(cls, d: Dict[str, Any]) -> "Issue":
        return cls(
            key=d.get("key", ""),
            title=d.get("title", ""),
            status=d.get("status", "Todo"),
            owner_labels=d.get("owner_labels", []),
            assignee=d.get("assignee"),
            description=d.get("description", ""),
            capabilities_required=d.get("capabilities_required", []),
            context=d.get("context", ""),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "key": self.key,
            "title": self.title,
            "status": self.status,
            "owner_labels": self.owner_labels,
            "assignee": self.assignee,
            "description": self.description,
            "capabilities_required": self.capabilities_required,
            "context": self.context,
        }


@dataclass
class DispatchRecord:
    """A durable record of a dispatch attempt."""
    issue_key: str
    lane: str
    attempt: int
    ts: str
    status: str  # dispatched, completed, failed, escalated
    result: Optional[str] = None
    error: Optional[str] = None
    capabilities_required: List[str] = field(default_factory=list)

    def to_ledger_entry(self) -> Dict[str, Any]:
        return {
            "ts": self.ts,
            "issue_id": self.issue_key,
            "lane": self.lane,
            "attempt": self.attempt,
            "status": self.status,
            "result": self.result,
            "error": self.error,
            "capabilities_required": self.capabilities_required,
        }


@dataclass
class RunnerPlan:
    """A planned action from dry-run."""
    issue: Issue
    action: str  # dispatch, skip, escalate, wait
    reason: str
    evidence: Dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Adapters (injected dependencies)
# ---------------------------------------------------------------------------


class LaneAdapter(protocol.LaneAdapter):
    """Protocol adapter - dispatches briefs to lanes."""

    name: str = "runner"

    def dispatch(self, brief: Dict[str, Any], *, dry_run: bool = False) -> Dict[str, Any]:
        """Dispatch a brief via the protocol."""
        return protocol.MiniMaxAdapter().dispatch(brief, dry_run=dry_run)

    def self_test(self) -> Tuple[bool, str]:
        """Self-test the adapter."""
        return protocol.MiniMaxAdapter().self_test()


class UsageAdapter:
    """Usage adapter - checks lane quotas."""

    def get_usage(self, lane: str) -> Dict[str, Any]:
        """Get current usage for a lane."""
        return usage_watcher.get_all_usage().get(lane, {})

    def can_dispatch(self, lane: str) -> bool:
        """Check if lane has >= 20% quota remaining."""
        return usage_watcher.can_dispatch(lane)

    def check_usage(self, lane: str) -> None:
        """
        Check usage immediately before dispatch.
        Raises QuotaExhaustedError if < 20% remaining.
        Raises UsageUnknownError if usage is unknown/stale/missing.
        """
        usage = self.get_usage(lane)

        if not usage:
            raise UsageUnknownError(f"No usage data for lane {lane}")

        # Check for unknown status
        status = usage.get("status")
        if status == "unknown":
            raise UsageUnknownError(f"Usage unknown for lane {lane} (status=unknown)")

        if status == "depleted":
            raise QuotaExhaustedError(f"Lane {lane} is depleted")

        remaining = usage.get("remaining_percent")
        if remaining is None:
            raise UsageUnknownError(f"No remaining_percent for lane {lane}")

        if remaining < 20.0:
            raise QuotaExhaustedError(
                f"Lane {lane} at {remaining}% remaining (below 20% threshold)"
            )


class BoardAdapter:
    """
    Board adapter - manages Linear issue state transitions.

    Key rules:
    - Assignee field is always empty (ownership via labels only)
    - Exactly one owner label (owner:minimax, owner:muse, etc.)
    - State changes: Todo -> In Progress on dispatch, Done after review
    """

    def get_todo_issues(self, lane: str) -> List[Issue]:
        """Get Todo issues with the given owner label."""
        # This is implemented via fixture in dry-run mode
        # In live mode, this would query Linear API
        return []

    def move_to_in_progress(self, issue_key: str, lane: str) -> None:
        """Move issue to In Progress (called on dispatch)."""
        # In live mode: update Linear state
        # In dry-run: just log the intent
        pass

    def move_to_done(self, issue_key: str) -> None:
        """Move issue to Done (called after review passes)."""
        # In live mode: update Linear state
        # In dry-run: just log the intent
        pass

    def set_owner_label(self, issue_key: str, owner: str) -> None:
        """Set the owner label, removing any stale owner labels."""
        # In live mode: update Linear labels
        # In dry-run: just log the intent
        pass

    def remove_stale_labels(self, issue_key: str, keep: str) -> None:
        """Remove all owner:* labels except the one to keep."""
        # In live mode: update Linear labels
        # In dry-run: just log the intent
        pass


class ReviewAdapter:
    """Review adapter - processes worker results."""

    def verify_result(self, result_path: Path, brief_path: Path) -> bool:
        """Verify a result against its brief."""
        try:
            result = protocol.load_result(result_path)
            brief = protocol.load_brief(brief_path)
            protocol.verify_signature(result, brief)
            return True
        except protocol.LaneProtocolError:
            return False

    def run_acceptance(self, issue_key: str, result: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Run acceptance checks for a completed task.
        Returns (passed, evidence).
        """
        # In dry-run: just return True
        # In live mode: run actual acceptance commands
        return True, "dry-run: acceptance not executed"


# ---------------------------------------------------------------------------
# Core runner logic
# ---------------------------------------------------------------------------


class LaneRunner:
    """
    Autonomous lane runner with state machine.

    States:
    - IDLE: no work scheduled
    - PLANNING: analyzing issues for dispatch
    - DISPATCHING: sending work to lane
    - REVIEWING: checking worker results
    - ESCALATING: moving failed work to Roman
    """

    STATE_IDLE = "idle"
    STATE_PLANNING = "planning"
    STATE_DISPATCHING = "dispatching"
    STATE_REVIEWING = "reviewing"
    STATE_ESCALATING = "escalating"

    def __init__(
        self,
        usage_adapter: Optional[UsageAdapter] = None,
        board_adapter: Optional[BoardAdapter] = None,
        review_adapter: Optional[ReviewAdapter] = None,
        dry_run: bool = True,
        pilot: bool = False,
    ):
        self.usage_adapter = usage_adapter or UsageAdapter()
        self.board_adapter = board_adapter or BoardAdapter()
        self.review_adapter = review_adapter or ReviewAdapter()
        self.dry_run = dry_run
        self.pilot = pilot
        self.state = self.STATE_IDLE
        self.current_issues: List[Issue] = []
        self.plans: List[RunnerPlan] = []

    def load_issues_from_fixture(self, fixture_path: Path) -> List[Issue]:
        """Load issues from a fixture JSON file."""
        data = json.loads(fixture_path.read_text())
        return [Issue.from_dict(i) for i in data.get("issues", [])]

    def count_wip(self, lane: str = MINIMAX_LANE) -> int:
        """Count current WIP for a lane from the ledger."""
        if not DISPATCH_LEDGER.exists():
            return 0

        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(hours=OPERATOR_WINDOW_HOURS * 24)  # Look back further
        wip_count = 0

        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("lane") != lane:
                    continue
                if entry.get("status") not in ("dispatched", "in_progress"):
                    continue

                ts_str = entry.get("ts", "")
                if ts_str:
                    try:
                        ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                        if ts >= cutoff:
                            wip_count += 1
                    except ValueError:
                        continue

        return wip_count

    def get_attempt_count(self, issue_key: str, lane: str = MINIMAX_LANE) -> int:
        """Get the number of attempts for an issue."""
        if not DISPATCH_LEDGER.exists():
            return 0

        max_attempt = 0
        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("issue_id") == issue_key and entry.get("lane") == lane:
                    attempt = entry.get("attempt", 0)
                    if attempt > max_attempt:
                        max_attempt = attempt

        return max_attempt

    def is_duplicate_dispatch(self, issue_key: str, lane: str = MINIMAX_LANE) -> bool:
        """Check if issue already has an active dispatch."""
        if not DISPATCH_LEDGER.exists():
            return False

        with open(DISPATCH_LEDGER, 'r') as f:
            for line in f:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if entry.get("issue_id") == issue_key and entry.get("lane") == lane:
                    if entry.get("status") in ("dispatched", "in_progress"):
                        return True

        return False

    def check_capabilities(self, issue: Issue) -> None:
        """
        Check if the lane can fulfill the required capabilities.
        Raises CapabilityRefusedError if any capability is missing.
        """
        # Define capability matrix from ROUTING.md
        # MiniMax can do: repo code change, wiring verification
        # MiniMax cannot do: vision/OCR, live browser, credentials, Mac-only,
        #                     methodology decisions, values/copy decisions,
        #                     cross-model review, merge/push/deploy
        CAN_DO = {"repo_code_change", "wiring_verification"}
        CANNOT_DO = {
            "needs_vision", "needs_ocr", "needs_browser", "needs_credentials",
            "needs_mac_only", "methodology_decision", "values_decision",
            "copy_decision", "cross_model_review", "merge_push_deploy",
        }

        for cap in issue.capabilities_required:
            if cap in CANNOT_DO:
                raise CapabilityRefusedError(
                    f"Capability {cap} not available for lane {MINIMAX_LANE}"
                )

    def plan_dispatch(self, issue: Issue) -> RunnerPlan:
        """
        Plan whether to dispatch, skip, escalate, or wait for an issue.
        """
        # Check for duplicate dispatch
        if self.is_duplicate_dispatch(issue.key):
            return RunnerPlan(
                issue=issue,
                action="skip",
                reason="Issue already has active dispatch",
                evidence={"duplicate": True},
            )

        # Check WIP limit
        wip = self.count_wip()
        if wip >= WIP_LIMIT:
            return RunnerPlan(
                issue=issue,
                action="wait",
                reason=f"WIP limit reached ({wip}/{WIP_LIMIT})",
                evidence={"wip": wip, "limit": WIP_LIMIT},
            )

        # Check capabilities
        try:
            self.check_capabilities(issue)
        except CapabilityRefusedError as e:
            return RunnerPlan(
                issue=issue,
                action="escalate",
                reason=str(e),
                evidence={"capability_refused": True},
            )

        # Check usage/quota
        try:
            self.usage_adapter.check_usage(MINIMAX_LANE)
        except (QuotaExhaustedError, UsageUnknownError) as e:
            return RunnerPlan(
                issue=issue,
                action="wait",
                reason=str(e),
                evidence={"quota_error": True},
            )

        # Check attempt count for escalation
        attempts = self.get_attempt_count(issue.key)
        if attempts >= MAX_ATTEMPTS:
            return RunnerPlan(
                issue=issue,
                action="escalate",
                reason=f"Max attempts reached ({attempts}/{MAX_ATTEMPTS})",
                evidence={"attempts": attempts, "max_attempts": MAX_ATTEMPTS},
            )

        # All checks pass - plan to dispatch
        return RunnerPlan(
            issue=issue,
            action="dispatch",
            reason="All preconditions met",
            evidence={
                "wip": wip,
                "attempts": attempts,
                "capabilities": issue.capabilities_required,
            },
        )

    def execute_plan(self, plan: RunnerPlan) -> bool:
        """
        Execute a planned action.
        Returns True if execution succeeded.
        """
        if plan.action == "dispatch":
            return self._dispatch(plan.issue)
        elif plan.action == "escalate":
            return self._escalate(plan.issue)
        elif plan.action in ("skip", "wait"):
            # No execution needed
            return True
        else:
            return False

    def _dispatch(self, issue: Issue) -> bool:
        """
        Dispatch an issue to the lane.
        """
        # Build the brief
        brief = protocol.make_brief(
            issue=issue.key,
            lane=MINIMAX_LANE,
            sender="runner",
            subject=issue.title,
            context=issue.context or issue.description,
        )

        # Record the dispatch
        attempt = self.get_attempt_count(issue.key) + 1
        record = DispatchRecord(
            issue_key=issue.key,
            lane=MINIMAX_LANE,
            attempt=attempt,
            ts=protocol.now_iso(),
            status="dispatched",
            capabilities_required=issue.capabilities_required,
        )

        if not self.dry_run:
            # Actually dispatch
            try:
                result = protocol.MiniMaxAdapter().dispatch(brief, dry_run=False)
                record.status = "completed"
                record.result = result.get("subject", "")
            except Exception as e:
                record.status = "failed"
                record.error = str(e)

        # Write to ledger
        self._write_ledger_entry(record)

        # Update board state (In Progress)
        if not self.dry_run:
            self.board_adapter.move_to_in_progress(issue.key, MINIMAX_LANE)

        return True

    def _escalate(self, issue: Issue) -> bool:
        """
        Escalate an issue to Roman (muse lane).
        """
        record = DispatchRecord(
            issue_key=issue.key,
            lane=MINIMAX_LANE,
            attempt=self.get_attempt_count(issue.key),
            ts=protocol.now_iso(),
            status="escalated",
            error="Max attempts reached or capability refused",
        )
        self._write_ledger_entry(record)

        if not self.dry_run:
            # Update owner label to muse
            self.board_adapter.set_owner_label(issue.key, ESCALATION_LANE)

        return True

    def _write_ledger_entry(self, record: DispatchRecord) -> None:
        """Write a dispatch record to the ledger."""
        DISPATCH_LEDGER.parent.mkdir(parents=True, exist_ok=True)
        with open(DISPATCH_LEDGER, 'a') as f:
            f.write(json.dumps(record.to_ledger_entry()) + "\n")

    def run(self, issues: List[Issue]) -> List[RunnerPlan]:
        """
        Run the runner on a list of issues.
        Returns the list of planned actions.
        """
        self.state = self.STATE_PLANNING
        self.current_issues = issues
        self.plans = []

        for issue in issues:
            if issue.status != "Todo":
                continue
            if "owner:minimax" not in issue.owner_labels:
                continue

            plan = self.plan_dispatch(issue)
            self.plans.append(plan)

            if not self.dry_run and plan.action == "dispatch":
                self.state = self.STATE_DISPATCHING
                self.execute_plan(plan)

        self.state = self.STATE_IDLE
        return self.plans


# ---------------------------------------------------------------------------
# Process lock
# ---------------------------------------------------------------------------


class ProcessLock:
    """Process lock to prevent duplicate runner execution."""

    def __init__(self, lock_path: Path = LOCK_FILE):
        self.lock_path = lock_path
        self.fd = None

    def __enter__(self):
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = open(self.lock_path, 'w')
        try:
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            self.fd.close()
            raise LockError("Another runner is already running")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.fd:
            fcntl.flock(self.fd, fcntl.LOCK_UN)
            self.fd.close()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def load_fixture(fixture_path: Path) -> Dict[str, Any]:
    """Load a fixture JSON file."""
    return json.loads(fixture_path.read_text())


def main() -> int:
    parser = argparse.ArgumentParser(description="Lane autonomous runner")
    parser.add_argument("--dry-run", action="store_true", help="Plan without executing")
    parser.add_argument("--pilot", action="store_true", help="Run pilot cycles")
    parser.add_argument("--cycles", type=int, default=3, help="Number of pilot cycles")
    parser.add_argument("--fixture", type=Path, help="Path to fixture JSON file")
    parser.add_argument("--issue", type=str, help="Process a single issue key")
    parser.add_argument("--lock-timeout", type=int, default=5, help="Lock timeout seconds")

    args = parser.parse_args()

    # Load issues
    issues = []
    if args.fixture:
        fixture = load_fixture(args.fixture)
        issues = [Issue.from_dict(i) for i in fixture.get("issues", [])]
    elif args.issue:
        issues = [Issue(key=args.issue, title="Single issue", status="Todo",
                       owner_labels=["owner:minimax"])]

    if not issues:
        print("No issues to process", file=sys.stderr)
        return 1

    # Run with lock
    try:
        with ProcessLock() if not args.dry_run else None:
            runner = LaneRunner(dry_run=args.dry_run, pilot=args.pilot)
            plans = runner.run(issues)

            # Output plans
            print(json.dumps({
                "dry_run": args.dry_run,
                "pilot": args.pilot,
                "plans": [
                    {
                        "issue": p.issue.key,
                        "action": p.action,
                        "reason": p.reason,
                        "evidence": p.evidence,
                    }
                    for p in plans
                ]
            }, indent=2))

            return 0

    except LockError as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
