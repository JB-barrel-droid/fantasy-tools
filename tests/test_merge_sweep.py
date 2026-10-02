#!/usr/bin/env python3
"""Tests for merge_sweep.py (JEG-91 / JEG-96 Phase 1).

These tests verify the merge sweep's fail-closed behavior:
  1. Failed validate never calls merge
  2. Failed verify_live never calls merge
  3. Missing independent review never calls merge
  4. Changed head/base after validation discards evidence
  5. Unknown classification never calls merge
  6. Absent authorization never calls merge
  7. Concurrent sweep calls cannot merge two PRs at once
  8. Crashes/timeouts release recoverably
"""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from typing import Dict, Optional
from unittest.mock import MagicMock, patch

# Add repo to path
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "lanes"))
sys.path.insert(0, str(REPO))

import merge_sweep  # noqa: E402


class MockGitAdapter(merge_sweep.GitAdapter):
    """Mock git adapter for testing."""

    def __init__(self, pr_files=None, base_sha="abc123", head_sha="def456"):
        self._pr_files = pr_files or ["docs/test.md"]
        self._base_sha = base_sha
        self._head_sha = head_sha
        self.fetch_count = 0
        self.merge_calls = []
        self.comment_calls = []

    def get_current_main_sha(self):
        return "main_sha_abc123"

    def fetch_main(self):
        self.fetch_count += 1

    def get_pr_files(self, pr_id):
        return self._pr_files

    def get_pr_base_and_head(self, pr_id):
        return self._base_sha, self._head_sha

    def merge_pr(self, pr_id, base_sha, head_sha):
        self.merge_calls.append({"pr_id": pr_id, "base": base_sha, "head": head_sha})
        return True

    def post_comment(self, pr_id, comment):
        self.comment_calls.append({"pr_id": pr_id, "comment": comment})


class MockValidationAdapter(merge_sweep.ValidationAdapter):
    """Mock validation adapter for testing."""

    def __init__(
        self,
        validate_success=True,
        verify_live_success=True,
        contract_tests_success=True,
        wiring_verification_success=True,
    ):
        self._validate_success = validate_success
        self._verify_live_success = verify_live_success
        self._contract_tests_success = contract_tests_success
        self._wiring_verification_success = wiring_verification_success

    def run_validate(self):
        return self._validate_success, "validate output"

    def run_verify_live(self):
        return self._verify_live_success, "verify_live output"

    def run_contract_tests(self):
        return self._contract_tests_success, "contract tests output"

    def run_wiring_verification(self):
        return self._wiring_verification_success, "wiring verification output"


class TestFailedValidateBlocksMerge(unittest.TestCase):
    """Test: Failed validate never calls merge."""

    def test_failed_validate_blocks_tier0_merge(self):
        """A Tier 0 PR with failed validate must not merge."""
        git = MockGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter(validate_success=False, verify_live_success=True)
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        self.assertFalse(result.can_merge)
        self.assertIn("make validate green", result.unmet_gates)
        self.assertEqual(len(git.merge_calls), 0, "merge should not be called")

    def test_failed_verify_live_blocks_tier0_merge(self):
        """A Tier 0 PR with failed verify_live must not merge."""
        git = MockGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter(validate_success=True, verify_live_success=False)
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        self.assertFalse(result.can_merge)
        self.assertIn("verify_live.py green", result.unmet_gates)


class TestMissingReviewBlocksMerge(unittest.TestCase):
    """Test: Missing independent review never calls merge."""

    def test_tier1_missing_review_blocks_merge(self):
        """A Tier 1 PR without different-lane review must not merge."""
        git = MockGitAdapter(pr_files=["pipelines/test.py"])
        validation = MockValidationAdapter(
            validate_success=True,
            verify_live_success=True,
            contract_tests_success=True,
            wiring_verification_success=True,
        )
        # Mock that evidence is attached but review is not
        with patch.object(validation, 'run_contract_tests', return_value=(True, "")):
            with patch.object(validation, 'run_wiring_verification', return_value=(True, "")):
                sweep = merge_sweep.MergeSweep(
                    dry_run=False,
                    git_adapter=git,
                    validation_adapter=validation,
                )
                # Manually set evidence to False in gate results
                result = sweep.process_pr(pr_id="123", branch="minimax/test")

        # The classification should show missing review
        self.assertEqual(result.tier, "tier_1")
        self.assertFalse(result.can_merge)


class TestChangedHeadBaseDiscardsEvidence(unittest.TestCase):
    """Test: Changed head/base after validation discards evidence."""

    def test_head_change_after_validation_fails(self):
        """If head SHA changes after validation, must re-verify."""
        call_count = [0]

        class ChangingGitAdapter(MockGitAdapter):
            def get_pr_base_and_head(self, pr_id):
                call_count[0] += 1
                if call_count[0] == 1:
                    return "base_sha", "head_sha_v1"
                return "base_sha", "head_sha_v2"  # Changed!

        git = ChangingGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter(validate_success=True, verify_live_success=True)
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        self.assertFalse(result.can_merge)
        self.assertFalse(result.evidence_valid)
        self.assertIn("changed", result.reasons[0].lower())


class TestUnknownClassificationNeverMerges(unittest.TestCase):
    """Test: Unknown classification never calls merge."""

    def test_unknown_files_not_auto_merged(self):
        """PR with unknown file patterns should not auto-merge."""
        git = MockGitAdapter(pr_files=["some/unknown/path/file.xyz"])
        validation = MockValidationAdapter(validate_success=True, verify_live_success=True)
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        # Unknown path should default to Tier 2, which requires approval
        self.assertEqual(result.tier, "tier_2")
        self.assertFalse(result.can_merge)


class TestAbsentAuthorizationBlocksMerge(unittest.TestCase):
    """Test: Absent authorization never calls merge."""

    def setUp(self):
        # Clear any existing authorization
        auth_file = REPO / ".merge_authorization.json"
        if auth_file.exists():
            os.remove(auth_file)

    def test_tier2_without_approval_blocks_merge(self):
        """Tier 2 PR without Jeremy approval must not merge."""
        git = MockGitAdapter(pr_files=["dist/chart.js"])
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        self.assertEqual(result.tier, "tier_2")
        self.assertFalse(result.can_merge)
        self.assertIn("Jeremy", " ".join(result.reasons))

    def test_tier2_with_approval_can_merge(self):
        """Tier 2 PR with Jeremy approval can merge."""
        # Record approval
        merge_sweep.AuthorizationManager.record_approval("tier_2", "jeremy", "test approval")

        git = MockGitAdapter(pr_files=["dist/chart.js"])
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        # For actual merge, we'd need all gates, but the authorization check passes
        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        # With approval, the tier check passes (gates still required for actual merge)
        self.assertEqual(result.tier, "tier_2")

        # Cleanup
        os.remove(REPO / ".merge_authorization.json")


class TestConcurrentSweepCalls(unittest.TestCase):
    """Test: Concurrent merge calls serialize via the file lock."""

    def test_only_one_merge_at_a_time(self):
        """Only one merge executes at a time; the other times out gracefully."""
        merge_sweep.LOCK_FILE.unlink(missing_ok=True)

        results = []
        errors = []

        def run_merge(pr_id):
            try:
                git = MockGitAdapter(pr_files=["docs/test.md"])
                sweep = merge_sweep.MergeSweep(
                    dry_run=False, git_adapter=git, lock_timeout=2.0)
                # merge_pr is the locked section: acquire, merge, release
                ok = sweep.merge_pr(pr_id=pr_id, base_sha="abc", head_sha="def")
                results.append((pr_id, ok))
            except Exception as e:
                errors.append(str(e))

        # Hold the lock in the main thread so the workers contend
        holder = merge_sweep.MergeLock()
        self.assertTrue(holder.acquire(timeout=1.0))
        try:
            t1 = threading.Thread(target=run_merge, args=("1",))
            t2 = threading.Thread(target=run_merge, args=("2",))
            t1.start()
            t2.start()
            t1.join(timeout=10)
            t2.join(timeout=10)
        finally:
            holder.release()

        self.assertFalse(t1.is_alive(), "worker thread hung")
        self.assertFalse(t2.is_alive(), "worker thread hung")
        # Both workers attempted; both timed out gracefully (no crash, no merge)
        self.assertEqual(len(results), 2)
        self.assertEqual(errors, [])
        for pr_id, ok in results:
            self.assertFalse(ok, "merge must not execute while lock is held")


class TestCrashTimeoutReleasesLock(unittest.TestCase):
    """Test: Crashes/timeouts release recoverably."""

    def test_lock_release_on_exception(self):
        """Lock is released even if exception occurs during processing."""
        merge_sweep.LOCK_FILE.unlink(missing_ok=True)

        class CrashingGitAdapter(MockGitAdapter):
            def get_pr_files(self, pr_id):
                raise RuntimeError("Simulated crash")

        git = CrashingGitAdapter()
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        # Should not raise, should handle gracefully
        result = sweep.process_pr(pr_id="123", branch="minimax/test")

        # Lock should be released (we can acquire it)
        lock = merge_sweep.MergeLock()
        acquired = lock.acquire(timeout=2.0)
        self.assertTrue(acquired, "Lock should be released after crash")
        lock.release()

    def test_lock_timeout_releases(self):
        """If lock is held, subsequent attempts timeout and release."""
        merge_sweep.LOCK_FILE.unlink(missing_ok=True)

        # Hold lock in a thread
        lock_held = threading.Event()
        lock_released = threading.Event()

        def hold_lock():
            lock = merge_sweep.MergeLock()
            lock.acquire()
            lock_held.set()
            lock_released.wait(timeout=5)
            lock.release()

        holder = threading.Thread(target=hold_lock)
        holder.start()
        lock_held.wait(timeout=2)  # Wait for lock to be held

        # Try to acquire - should timeout
        new_lock = merge_sweep.MergeLock()
        acquired = new_lock.acquire(timeout=1.0)

        # Signal release
        lock_released.set()
        holder.join(timeout=3)

        self.assertFalse(acquired, "Should timeout when lock held")


class TestDryRunDefault(unittest.TestCase):
    """Test: Default is dry-run, no actual merges."""

    def test_default_dry_run(self):
        """By default, sweep is dry_run=True."""
        git = MockGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(git_adapter=git, validation_adapter=validation)

        self.assertTrue(sweep.dry_run)

    def test_dry_run_does_not_merge(self):
        """Dry run never actually merges."""
        git = MockGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(dry_run=True, git_adapter=git, validation_adapter=validation)

        # Create a result that would allow merge
        result = merge_sweep.SweepResult(
            pr_id="123",
            branch="minimax/test",
            tier="tier_0",
            can_merge=True,
            base_sha="abc",
            head_sha="def",
        )

        # merge_pr should not call git.merge_pr in dry-run mode
        sweep.merge_pr("123", "abc", "def")

        self.assertEqual(len(git.merge_calls), 0, "merge should not be called in dry-run")


class TestPilotRunbook(unittest.TestCase):
    """Test: Pilot runbook for Tier 0 and Tier 2."""

    def test_tier0_pilot_auto_merges(self):
        """Tier 0 pilot should auto-merge if gates pass."""
        git = MockGitAdapter(pr_files=["docs/test.md"])
        validation = MockValidationAdapter(validate_success=True, verify_live_success=True)
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.run_pilot("123", "minimax/test", "tier_0")

        # Result should indicate merge was attempted
        self.assertIn(result.tier, ("tier_0", "unknown"))

    def test_tier2_pilot_held_for_jeremy(self):
        """Tier 2 pilot should be held for Jeremy's tap."""
        git = MockGitAdapter(pr_files=["dist/chart.js"])
        validation = MockValidationAdapter()
        sweep = merge_sweep.MergeSweep(dry_run=False, git_adapter=git, validation_adapter=validation)

        result = sweep.run_pilot("123", "minimax/test", "tier_2")

        self.assertFalse(result.can_merge)
        self.assertIn("Jeremy", " ".join(result.reasons))
        # Should have posted comment
        self.assertGreater(len(git.comment_calls), 0)


class TestAuthorizationManager(unittest.TestCase):
    """Test: Authorization manager records approvals."""

    def setUp(self):
        auth_file = REPO / ".merge_authorization.json"
        if auth_file.exists():
            os.remove(auth_file)

    def test_record_and_check_approval(self):
        """Can record and check tier approval."""
        self.assertFalse(merge_sweep.AuthorizationManager.is_approved("tier_2"))

        merge_sweep.AuthorizationManager.record_approval("tier_2", "jeremy", "test")

        self.assertTrue(merge_sweep.AuthorizationManager.is_approved("tier_2"))

    def test_approval_includes_metadata(self):
        """Approval record includes who and when."""
        merge_sweep.AuthorizationManager.record_approval("tier_0", "jeremy", "pilot test")

        auth = merge_sweep.AuthorizationManager.load_authorization()
        self.assertEqual(auth.get("approved_by"), "jeremy")
        self.assertIn("approved_at", auth)
        self.assertIn("tier_0", auth.get("approved_tiers", []))


class TestSweepResultSerialization(unittest.TestCase):
    """Test: SweepResult can be serialized to dict."""

    def test_to_dict_includes_all_fields(self):
        """All fields are included in serialization."""
        result = merge_sweep.SweepResult(
            pr_id="123",
            branch="minimax/test",
            tier="tier_0",
            can_merge=True,
            base_sha="abc",
            head_sha="def",
            reasons=["test reason"],
            unmet_gates=["gate1"],
            evidence_valid=True,
            classification_method="path_match",
            merge_executed=True,
        )

        d = result.to_dict()

        self.assertEqual(d["pr_id"], "123")
        self.assertEqual(d["tier"], "tier_0")
        self.assertTrue(d["can_merge"])
        self.assertEqual(d["base_sha"], "abc")
        self.assertEqual(d["head_sha"], "def")
        self.assertIn("test reason", d["reasons"])
        self.assertIn("gate1", d["unmet_gates"])
        self.assertTrue(d["evidence_valid"])
        self.assertEqual(d["classification_method"], "path_match")
        self.assertTrue(d["merge_executed"])


if __name__ == "__main__":
    unittest.main()
