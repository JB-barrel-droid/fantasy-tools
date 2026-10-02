#!/usr/bin/env python3
"""Merge charter tier rules (JEG-91 / JEG-96 Phase 1).

Encodes the three pre-authorized auto-merge tiers + merge queue as checkable
rules, not prose. Lane PRs are classified by file paths + forbidden-content
patterns; the result includes the human in the loop, the gates, and the
queue behavior.

The single source of truth is lanes/plan.json's `tier_definitions` and
`merge_queue` blocks. This module loads that, applies glob matching to a
list of changed files, and returns the tier plus a list of unmet gates.

Usage:
    from lanes.merge_charter import classify_pr, MergeQueue

    result = classify_pr(changed_files=["docs/PLAN.md"], review_posted=True)
    result.tier  # "tier_0"
    result.auto_merge  # True
    result.unmet_gates # []

    q = MergeQueue.from_plan()
    decision = q.next_action(current_main_sha="abc1234", pending=["pr1","pr2"])
    decision.serialize  # True
    decision.rebase_and_reverify  # True
"""
from __future__ import annotations

import fnmatch
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

PLAN_JSON = Path(__file__).parent / "plan.json"

TIER_ORDER = ("tier_0", "tier_1", "tier_2")


def _load_plan() -> dict:
    with PLAN_JSON.open() as f:
        return json.load(f)


def _matches_any(path: str, patterns: List[str]) -> bool:
    """Glob-match a path against a list of patterns. Patterns are POSIX
    globs; 'docs/**' matches {docs/x, docs/sub/x}, 'docs/*.md' matches
    {docs/x.md} but not {docs/sub/x.md}. We treat '**' as recursive."""
    # Normalize leading './'
    p = path.lstrip("./")
    for pat in patterns:
        # fnmatch doesn't understand '**' recursion; emulate it.
        if _glob_match(p, pat):
            return True
    return False


def _glob_match(path: str, pattern: str) -> bool:
    """Recursive glob match. Supports ** for any depth."""
    if "**" not in pattern:
        return fnmatch.fnmatch(path, pattern)
    # Translate '**' to a regex equivalent for fnmatch.
    # fnmatch uses * for any sequence (no /). We need ** to also cross '/'.
    import re
    parts = pattern.split("/")
    regex_parts = []
    for part in parts:
        if part == "**":
            regex_parts.append(r".*")
        else:
            # fnmatch.translate escapes regex metachars except * and ?.
            # We use fnmatch to handle single-segment *, then re-join.
            regex_parts.append(fnmatch.translate(part).replace(r"\Z", "").replace(r"(?s:", ""))
    regex = "/".join(regex_parts) + r"\Z"
    return re.match(regex, path) is not None


@dataclass
class TierResult:
    tier: str
    auto_merge: bool
    human_in_loop: str  # "none" | "roman" | "jeremy"
    gates: List[str]
    unmet_gates: List[str] = field(default_factory=list)
    reasons: List[str] = field(default_factory=list)
    tier_decision_method: str = "path_match"  # or "tier_2_override" for content-triggered

    @property
    def ok(self) -> bool:
        return not self.unmet_gates


def _path_tier(changed_files: List[str], tiers: dict) -> Optional[str]:
    """Return the most-restrictive tier matched by file paths alone, or None.

    Tier 0 is the most permissive (auto-merge), Tier 2 is the most restrictive
    (Jeremy's tap). A PR that touches only Tier-0 globs AND no Tier-1+
    forbidden paths qualifies for tier_0. Tier 1 globs are a superset of
    Tier 0: anything that touches the Tier 1 file space but no Tier 2
    content goes to Tier 1. Anything touching Tier 2 forbidden paths or
    content patterns is Tier 2.
    """
    # Collect tier "matches" per tier. A tier matches if every changed file
    # is within one of its globs AND none of its forbidden_paths is touched.
    matches: Dict[str, bool] = {}
    for tier_id in TIER_ORDER:
        spec = tiers[tier_id]
        in_globs = all(_matches_any(f, spec["file_globs"]) for f in changed_files)
        in_forbidden = any(_matches_any(f, spec["forbidden_paths"]) for f in changed_files)
        matches[tier_id] = in_globs and not in_forbidden
    # If Tier 0 matches, it's a Tier 0 candidate. Otherwise if Tier 1 matches,
    # it's Tier 1. Otherwise Tier 2.
    if matches.get("tier_0"):
        return "tier_0"
    if matches.get("tier_1"):
        return "tier_1"
    return "tier_2"


def classify_pr(
    changed_files: List[str],
    *,
    touches_methodology: bool = False,
    touches_values: bool = False,
    touches_copy: bool = False,
    touches_publish: bool = False,
    touches_ddl: bool = False,
    touches_pricing_math: bool = False,
    touches_fixed_pie: bool = False,
    validate_green: bool = False,
    verify_live_green: bool = False,
    contract_tests_green: bool = False,
    wiring_verification_green: bool = False,
    evidence_bundle_attached: bool = False,
    different_lane_review_posted: bool = False,
    jeremy_tap_recorded: bool = False,
) -> TierResult:
    """Classify a lane PR under the merge charter.

    Path-based classification sets the tier ceiling; any content-pattern
    trigger upgrades to Tier 2. Gates are then evaluated against the tier's
    spec.
    """
    plan = _load_plan()
    tiers = plan["tier_definitions"]

    content_triggers = {
        "methodology": touches_methodology,
        "values": touches_values,
        "user-facing copy": touches_copy,
        "publish": touches_publish,
        "DDL": touches_ddl,
        "pricing math": touches_pricing_math,
        "fixed-pie": touches_fixed_pie,
        "indexation": touches_fixed_pie,
    }
    triggered = [name for name, hit in content_triggers.items() if hit]

    ceiling = _path_tier(changed_files, tiers)
    tier_id = "tier_2" if triggered or ceiling is None else ceiling

    spec = tiers[tier_id]
    auto_merge = bool(spec.get("auto_merge"))
    human = "none" if tier_id == "tier_0" else ("jeremy" if tier_id == "tier_2" else "roman")
    gates = list(spec.get("gates", []))

    unmet: List[str] = []
    reasons: List[str] = []

    if tier_id == "tier_0":
        if not validate_green:
            unmet.append("make validate green")
        if not verify_live_green:
            unmet.append("verify_live.py green")
    elif tier_id == "tier_1":
        if not contract_tests_green:
            unmet.append("contract tests green")
        if not wiring_verification_green:
            unmet.append("wiring verification green")
        if not evidence_bundle_attached:
            unmet.append("evidence bundle attached")
        if not different_lane_review_posted:
            unmet.append("different-lane review posted")
    else:  # tier_2
        if not jeremy_tap_recorded:
            unmet.append("Jeremy explicitly approves the tap")

    if triggered:
        reasons.append(f"content trigger: {', '.join(triggered)} -> Tier 2")
    if ceiling is None and not triggered:
        reasons.append("path-based classification: no tier matches -> Tier 2 default")

    return TierResult(
        tier=tier_id,
        auto_merge=auto_merge and not unmet,
        human_in_loop=human,
        gates=gates,
        unmet_gates=unmet,
        reasons=reasons,
        tier_decision_method="tier_2_override" if triggered else "path_match",
    )


@dataclass
class QueueDecision:
    serialize: bool
    max_concurrent: int
    actions_per_item: List[str]
    rationale: str
    enqueue: List[str]
    wait: List[str]


@dataclass
class MergeQueue:
    spec: dict

    @classmethod
    def from_plan(cls) -> "MergeQueue":
        plan = _load_plan()
        return cls(spec=plan["merge_queue"])

    def next_action(
        self,
        current_main_sha: str,
        pending: List[str],
        *,
        in_flight: Optional[List[str]] = None,
    ) -> QueueDecision:
        """Return the queue's next action.

        The queue is strictly serial: at most one PR merges at a time, and
        each item re-runs the gate before it lands. Items currently in flight
        stay in flight; the rest wait their turn.
        """
        in_flight = in_flight or []
        serialize = bool(self.spec.get("serialize", True))
        max_concurrent = int(self.spec.get("max_concurrent", 1))
        actions = list(self.spec.get("per_item", []))
        rationale = self.spec.get("rationale", "")

        if not serialize:
            return QueueDecision(
                serialize=False,
                max_concurrent=max_concurrent,
                actions_per_item=actions,
                rationale=rationale,
                enqueue=pending,
                wait=[],
            )

        wait = []
        enqueue = []
        slot_open = max(0, max_concurrent - len(in_flight))
        for pr in pending:
            if slot_open > 0:
                enqueue.append(pr)
                slot_open -= 1
            else:
                wait.append(pr)
        return QueueDecision(
            serialize=True,
            max_concurrent=max_concurrent,
            actions_per_item=actions,
            rationale=rationale,
            enqueue=enqueue,
            wait=wait,
        )


def main() -> int:
    """CLI: classify a PR from changed-files on argv. Demo only; production
    sweep cron reads the PR's actual diff."""
    import sys
    changed = sys.argv[1:] or ["docs/PLAN.md"]
    result = classify_pr(
        changed,
        validate_green=True,
        verify_live_green=True,
    )
    print(json.dumps({
        "tier": result.tier,
        "auto_merge": result.auto_merge,
        "human_in_loop": result.human_in_loop,
        "gates": result.gates,
        "unmet_gates": result.unmet_gates,
        "reasons": result.reasons,
        "method": result.tier_decision_method,
    }, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())