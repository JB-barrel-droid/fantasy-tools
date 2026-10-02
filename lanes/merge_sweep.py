#!/usr/bin/env python3
"""Merge sweep runtime adapter (JEG-91 / JEG-96 Phase 1).

Provides the runtime implementation for the merge charter:
  - classify_pr against actual diff/content and current plan
  - Approval/evidence gates with dry-run default
  - Serial runtime locking (cross-process)
  - Operator pilot runbook for Tier 0/2 pilots

Usage:
    from lanes.merge_sweep import MergeSweep, SweepResult

    sweep = MergeSweep(dry_run=True)  # default is dry-run
    result = sweep.process_pr(pr_id="123", branch="minimax/jeg-NN-...")
    if result.can_merge:
        sweep.merge_pr(pr_id=result.pr_id, base_sha=result.base_sha)

The sweep is fail-closed: absent approval, stale evidence, unknown classification,
or failed gates all block merge.
"""
from __future__ import annotations

import fcntl
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# Add lanes to path for imports
REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "lanes"))

import merge_charter  # noqa: E402


# Lock file for serial merge queue
LOCK_FILE = REPO / ".merge_queue.lock"

# Authorization record path
AUTHORIZATION_FILE = REPO / ".merge_authorization.json"


@dataclass
class SweepResult:
    """Result of processing a PR through the sweep."""

    pr_id: str
    branch: str
    tier: str
    can_merge: bool
    base_sha: str = ""
    head_sha: str = ""
    reasons: List[str] = field(default_factory=list)
    unmet_gates: List[str] = field(default_factory=list)
    evidence_valid: bool = True
    classification_method: str = ""
    merge_executed: bool = False
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "pr_id": self.pr_id,
            "branch": self.branch,
            "tier": self.tier,
            "can_merge": self.can_merge,
            "base_sha": self.base_sha,
            "head_sha": self.head_sha,
            "reasons": self.reasons,
            "unmet_gates": self.unmet_gates,
            "evidence_valid": self.evidence_valid,
            "classification_method": self.classification_method,
            "merge_executed": self.merge_executed,
            "error": self.error,
        }


class AuthorizationManager:
    """Manages one-time Jeremy approval for auto-merge modes."""

    @classmethod
    def load_authorization(cls) -> dict:
        """Load authorization record, or empty dict if none."""
        if not AUTHORIZATION_FILE.exists():
            return {}
        try:
            with open(AUTHORIZATION_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return {}

    @classmethod
    def save_authorization(cls, auth: dict) -> None:
        """Save authorization record."""
        AUTHORIZATION_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(AUTHORIZATION_FILE, "w") as f:
            json.dump(auth, f, indent=2)

    @classmethod
    def is_approved(cls, tier: str) -> bool:
        """Check if a tier is approved for auto-merge."""
        auth = cls.load_authorization()
        approved_tiers = auth.get("approved_tiers", [])
        return tier in approved_tiers

    @classmethod
    def record_approval(cls, tier: str, approved_by: str, note: str = "") -> None:
        """Record approval for a tier."""
        auth = cls.load_authorization()
        if "approved_tiers" not in auth:
            auth["approved_tiers"] = []
        if tier not in auth["approved_tiers"]:
            auth["approved_tiers"].append(tier)
        auth["approved_by"] = approved_by
        auth["approved_at"] = datetime.now().isoformat()
        if note:
            auth["note"] = note
        cls.save_authorization(auth)


class MergeLock:
    """Cross-process lock for serial merge queue."""

    def __init__(self, lock_path: Path = LOCK_FILE):
        self.lock_path = lock_path
        self.lock_fd: Optional[int] = None

    def acquire(self, timeout: float = 30.0) -> bool:
        """Acquire the merge lock. Returns True on success, False on timeout."""
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR)
        try:
            fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Write PID for debugging
            os.write(self.lock_fd, f"{os.getpid()}\n".encode())
            return True
        except (IOError, OSError):
            # Lock held by another process - retry with non-blocking attempts
            if self.lock_fd is not None:
                os.close(self.lock_fd)
                self.lock_fd = None
            start = time.time()
            while time.time() - start < timeout:
                try:
                    self.lock_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR)
                    fcntl.flock(self.lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    os.write(self.lock_fd, f"{os.getpid()}\n".encode())
                    return True
                except (IOError, OSError):
                    if self.lock_fd is not None:
                        os.close(self.lock_fd)
                        self.lock_fd = None
                    time.sleep(0.1)
            return False

    def release(self) -> None:
        """Release the merge lock."""
        if self.lock_fd is not None:
            try:
                fcntl.flock(self.lock_fd, fcntl.LOCK_UN)
                os.close(self.lock_fd)
            except OSError:
                pass
            finally:
                self.lock_fd = None

    def __enter__(self):
        if not self.acquire():
            raise RuntimeError("Could not acquire merge lock")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.release()
        return False


class GitAdapter:
    """Adapter for git operations. Can be mocked for testing."""

    def get_current_main_sha(self) -> str:
        """Get current SHA of main branch."""
        result = subprocess.run(
            ["git", "rev-parse", "main"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not get main SHA: {result.stderr}")
        return result.stdout.strip()

    def fetch_main(self) -> None:
        """Fetch latest main."""
        result = subprocess.run(
            ["git", "fetch", "origin", "main"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(f"Could not fetch main: {result.stderr}")

    def get_pr_files(self, pr_id: str) -> List[str]:
        """Get list of files changed in a PR."""
        # Use GitHub CLI if available, otherwise use git log
        result = subprocess.run(
            ["gh", "pr", "view", pr_id, "--json", "files", "-q", ".files[].path"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Fallback: try to get from branch
            result = subprocess.run(
                ["git", "diff", "--name-only", "main...HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            if result.returncode != 0:
                return []
            return [f.strip() for f in result.stdout.splitlines() if f.strip()]
        try:
            files = json.loads(result.stdout)
            return [f["path"] for f in files]
        except (json.JSONDecodeError, IndexError, KeyError):
            return []

    def get_pr_base_and_head(self, pr_id: str) -> Tuple[str, str]:
        """Get base and head SHAs for a PR."""
        result = subprocess.run(
            ["gh", "pr", "view", pr_id, "--json", "baseRefName,headRefName"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            # Fallback: use git
            base_result = subprocess.run(
                ["git", "rev-parse", "main"],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            head_result = subprocess.run(
                ["git", "rev-parse", "HEAD"],
                cwd=REPO,
                capture_output=True,
                text=True,
            )
            base = base_result.stdout.strip() if base_result.returncode == 0 else ""
            head = head_result.stdout.strip() if head_result.returncode == 0 else ""
            return base, head

        try:
            data = json.loads(result.stdout)
            base = data.get("baseRefName", "")
            head = data.get("headRefName", "")
            # Convert branch names to SHAs
            base_sha = self._get_branch_sha(base) if base else ""
            head_sha = self._get_branch_sha(head) if head else ""
            return base_sha, head_sha
        except (json.JSONDecodeError, KeyError):
            return "", ""

    def _get_branch_sha(self, branch: str) -> str:
        """Get SHA for a branch."""
        result = subprocess.run(
            ["git", "rev-parse", branch],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return result.stdout.strip() if result.returncode == 0 else ""

    def merge_pr(self, pr_id: str, base_sha: str, head_sha: str) -> bool:
        """Merge a PR. Returns True on success."""
        result = subprocess.run(
            ["gh", "pr", "merge", pr_id, "--admin", "--squash"],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0

    def post_comment(self, pr_id: str, comment: str) -> bool:
        """Post a comment to a PR."""
        result = subprocess.run(
            ["gh", "pr", "comment", pr_id, "--body", comment],
            cwd=REPO,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0


class ValidationAdapter:
    """Adapter for validation commands. Can be mocked for testing."""

    def run_validate(self) -> Tuple[bool, str]:
        """Run make validate. Returns (success, output)."""
        result = subprocess.run(
            ["make", "validate"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def run_verify_live(self) -> Tuple[bool, str]:
        """Run verify_live.py. Returns (success, output)."""
        result = subprocess.run(
            [sys.executable, "verify_live.py"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=60,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def run_contract_tests(self) -> Tuple[bool, str]:
        """Run contract tests. Returns (success, output)."""
        result = subprocess.run(
            [sys.executable, "-m", "pytest", "tests/test_contract/", "-v"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=300,
        )
        return result.returncode == 0, result.stdout + result.stderr

    def run_wiring_verification(self) -> Tuple[bool, str]:
        """Run wiring verification. Returns (success, output)."""
        result = subprocess.run(
            [sys.executable, "pipelines/verify_vorp_wiring.py"],
            cwd=REPO,
            capture_output=True,
            text=True,
            timeout=120,
        )
        return result.returncode == 0, result.stdout + result.stderr


class MergeSweep:
    """Main sweep class that orchestrates PR classification and merge."""

    def __init__(
        self,
        dry_run: bool = True,
        git_adapter: Optional[GitAdapter] = None,
        validation_adapter: Optional[ValidationAdapter] = None,
        lock_timeout: float = 30.0,
    ):
        """Initialize the sweep.

        Args:
            dry_run: If True, never actually merge. Default is True (fail-closed).
            git_adapter: Git operations adapter. Defaults to real git commands.
            validation_adapter: Validation adapter. Defaults to real commands.
        """
        self.dry_run = dry_run
        self.git = git_adapter or GitAdapter()
        self.validation = validation_adapter or ValidationAdapter()
        self.lock_timeout = lock_timeout

    def process_pr(
        self,
        pr_id: str,
        branch: str,
        content_flags: Optional[dict] = None,
    ) -> SweepResult:
        """Process a PR through the merge sweep.

        Args:
            pr_id: PR number or identifier
            branch: Branch name (e.g., "minimax/jeg-NN-...")
            content_flags: Optional dict of content triggers:
                - touches_methodology
                - touches_values
                - touches_copy
                - touches_publish
                - touches_ddl
                - touches_pricing_math
                - touches_fixed_pie

        Returns:
            SweepResult with merge decision and details
        """
        content_flags = content_flags or {}

        try:
            # Step 1: Fetch latest main
            self.git.fetch_main()
            current_main_sha = self.git.get_current_main_sha()

            # Step 2: Get PR files and SHAs
            changed_files = self.git.get_pr_files(pr_id)
            if not changed_files:
                return SweepResult(
                    pr_id=pr_id,
                    branch=branch,
                    tier="unknown",
                    can_merge=False,
                    reasons=["could not determine changed files"],
                    evidence_valid=False,
                )

            base_sha, head_sha = self.git.get_pr_base_and_head(pr_id)

            # Step 3: Run gates and classify
            gate_results = self._run_gates(changed_files, content_flags)
            classification = self._classify_pr(
                changed_files, content_flags, gate_results
            )

            # Step 4: Check authorization (Tier 2 requires Jeremy's tap)
            if classification.tier == "tier_2" and not AuthorizationManager.is_approved("tier_2"):
                return SweepResult(
                    pr_id=pr_id,
                    branch=branch,
                    tier=classification.tier,
                    can_merge=False,
                    base_sha=base_sha,
                    head_sha=head_sha,
                    reasons=classification.reasons + ["Jeremy approval not recorded"],
                    unmet_gates=classification.unmet_gates,
                    classification_method=classification.tier_decision_method,
                )

            # Step 5: Check if head/base changed after validation
            new_base_sha, new_head_sha = self.git.get_pr_base_and_head(pr_id)
            if new_base_sha != base_sha or new_head_sha != head_sha:
                return SweepResult(
                    pr_id=pr_id,
                    branch=branch,
                    tier=classification.tier,
                    can_merge=False,
                    base_sha=new_base_sha,
                    head_sha=new_head_sha,
                    reasons=["head/base changed after validation - re-verifying required"],
                    unmet_gates=["re-verify required"],
                    evidence_valid=False,
                    classification_method=classification.tier_decision_method,
                )

            # Step 6: Determine merge eligibility
            can_merge = (
                classification.ok
                and classification.auto_merge
                and gate_results["all_passed"]
                and (classification.tier != "tier_2" or AuthorizationManager.is_approved("tier_2"))
            )

            return SweepResult(
                pr_id=pr_id,
                branch=branch,
                tier=classification.tier,
                can_merge=can_merge,
                base_sha=new_base_sha,
                head_sha=new_head_sha,
                reasons=classification.reasons,
                unmet_gates=classification.unmet_gates,
                evidence_valid=True,
                classification_method=classification.tier_decision_method,
            )

        except Exception as e:
            return SweepResult(
                pr_id=pr_id,
                branch=branch,
                tier="unknown",
                can_merge=False,
                reasons=[f"error during sweep: {str(e)}"],
                error=str(e),
            )

    def _run_gates(
        self, changed_files: List[str], content_flags: dict
    ) -> Dict[str, bool]:
        """Run the appropriate gates based on likely tier.

        Returns dict with gate results and overall pass status.
        """
        # Determine likely tier for gate selection
        plan = merge_charter._load_plan()
        tier = merge_charter._path_tier(changed_files, plan["tier_definitions"])

        # Also check content triggers
        triggered = [
            k for k, v in content_flags.items()
            if v and k.startswith("touches_")
        ]
        if triggered:
            tier = "tier_2"

        results = {
            "validate_passed": False,
            "verify_live_passed": False,
            "contract_tests_passed": False,
            "wiring_verification_passed": False,
            "evidence_bundle_attached": False,
            "different_lane_review_posted": False,
            "all_passed": False,
        }

        # Run Tier 0 gates
        if tier in ("tier_0", "unknown"):
            try:
                results["validate_passed"], _ = self.validation.run_validate()
            except Exception:
                results["validate_passed"] = False

            try:
                results["verify_live_passed"], _ = self.validation.run_verify_live()
            except Exception:
                results["verify_live_passed"] = False

        # Run Tier 1 gates
        if tier in ("tier_1",):
            try:
                results["contract_tests_passed"], _ = self.validation.run_contract_tests()
            except Exception:
                results["contract_tests_passed"] = False

            try:
                results["wiring_verification_passed"], _ = self.validation.run_wiring_verification()
            except Exception:
                results["wiring_verification_passed"] = False

            # Evidence and review are external; check via gh CLI or assume not present
            # These would be checked via PR metadata in production
            results["evidence_bundle_attached"] = False
            results["different_lane_review_posted"] = False

        # Tier 2 gates are approval only (checked elsewhere)
        results["all_passed"] = all([
            results.get("validate_passed", True),
            results.get("verify_live_passed", True),
            results.get("contract_tests_passed", True),
            results.get("wiring_verification_passed", True),
            results.get("evidence_bundle_attached", True),
            results.get("different_lane_review_posted", True),
        ])

        return results

    def _classify_pr(
        self,
        changed_files: List[str],
        content_flags: dict,
        gate_results: Dict[str, bool],
    ) -> merge_charter.TierResult:
        """Classify the PR using merge_charter."""
        return merge_charter.classify_pr(
            changed_files,
            touches_methodology=content_flags.get("touches_methodology", False),
            touches_values=content_flags.get("touches_values", False),
            touches_copy=content_flags.get("touches_copy", False),
            touches_publish=content_flags.get("touches_publish", False),
            touches_ddl=content_flags.get("touches_ddl", False),
            touches_pricing_math=content_flags.get("touches_pricing_math", False),
            touches_fixed_pie=content_flags.get("touches_fixed_pie", False),
            validate_green=gate_results.get("validate_passed", False),
            verify_live_green=gate_results.get("verify_live_passed", False),
            contract_tests_green=gate_results.get("contract_tests_passed", False),
            wiring_verification_green=gate_results.get("wiring_verification_passed", False),
            evidence_bundle_attached=gate_results.get("evidence_bundle_attached", False),
            different_lane_review_posted=gate_results.get("different_lane_review_posted", False),
            jeremy_tap_recorded=AuthorizationManager.is_approved("tier_2"),
        )

    def merge_pr(self, pr_id: str, base_sha: str, head_sha: str) -> bool:
        """Execute the merge. Only call if can_merge is True."""
        if self.dry_run:
            print(f"[DRY-RUN] Would merge PR {pr_id}")
            return True

        # Serial locking: only one merge executes at a time
        lock = MergeLock()
        if not lock.acquire(timeout=self.lock_timeout):
            print(f"[LOCK] Could not acquire merge lock for PR {pr_id}, skipping")
            return False
        try:
            success = self.git.merge_pr(pr_id, base_sha, head_sha)
        finally:
            lock.release()

        # Post tier as comment
        if success:
            result = self.process_pr(pr_id, "")
            self.git.post_comment(
                pr_id,
                f"Auto-merged via merge sweep. Tier: {result.tier}",
            )

        return success

    def run_pilot(
        self,
        pr_id: str,
        branch: str,
        pilot_type: str = "tier_0",
    ) -> SweepResult:
        """Run a pilot merge for a specific tier.

        Args:
            pr_id: PR to pilot
            branch: Branch name
            pilot_type: "tier_0" or "tier_2"

        Returns:
            SweepResult with pilot outcome
        """
        if pilot_type == "tier_0":
            # Tier 0 pilot: auto-merge if all gates pass
            result = self.process_pr(pr_id, branch)
            if result.can_merge:
                self.merge_pr(pr_id, result.base_sha, result.head_sha)
                result.merge_executed = not self.dry_run
            return result
        elif pilot_type == "tier_2":
            # Tier 2 pilot: hold for Jeremy
            result = self.process_pr(pr_id, branch)
            result.can_merge = False
            result.reasons.append("Tier 2 pilot - held for Jeremy's tap")
            self.git.post_comment(
                pr_id,
                "Tier 2 pilot - held for Jeremy's tap. Reason: requires explicit approval.",
            )
            return result
        else:
            return SweepResult(
                pr_id=pr_id,
                branch=branch,
                tier="unknown",
                can_merge=False,
                reasons=[f"unknown pilot type: {pilot_type}"],
            )


def main() -> int:
    """CLI entry point for merge sweep."""
    import argparse

    parser = argparse.ArgumentParser(description="Merge sweep for lane PRs")
    parser.add_argument("--pr", required=True, help="PR number or ID")
    parser.add_argument("--branch", required=True, help="Branch name")
    parser.add_argument("--dry-run", action="store_true", default=True,
                        help="Dry run (default: True)")
    parser.add_argument("--no-dry-run", dest="dry_run", action="store_false",
                        help="Actually merge (requires authorization)")
    parser.add_argument("--pilot", choices=["tier_0", "tier_2", "none"],
                        default="none", help="Run a pilot merge")
    parser.add_argument("--content", nargs="*", default=[],
                        help="Content flags: touches_methodology touches_values ...")

    args = parser.parse_args()

    # Parse content flags
    content_flags = {}
    for flag in args.content:
        if "=" in flag:
            k, v = flag.split("=", 1)
            content_flags[k] = v.lower() in ("true", "1", "yes")
        else:
            content_flags[flag] = True

    sweep = MergeSweep(dry_run=args.dry_run)

    if args.pilot != "none":
        result = sweep.run_pilot(args.pr, args.branch, args.pilot)
    else:
        result = sweep.process_pr(args.pr, args.branch, content_flags)

    print(json.dumps(result.to_dict(), indent=2))
    return 0 if result.can_merge else 1


if __name__ == "__main__":
    sys.exit(main())
