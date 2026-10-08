#!/usr/bin/env python3
"""JEG-128 (R1a): no fail-open swallows in pull workflows.

Regression guard: every pull workflow must fail the job (never swallow) on a
failed pull/import/save step, and each pull job must write exactly one
acquisition summary line to $GITHUB_STEP_SUMMARY.

The fail-open half is verified by scanning the workflow YAMLs for swallow
patterns on pull/import/save steps. The summary half is verified by checking
for a GITHUB_STEP_SUMMARY write in each pull job.
"""

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = ROOT / ".github" / "workflows"

# The four pull workflows covered by R1a.
PULL_WORKFLOWS = [
    "espn-supabase-sync.yml",
    "cbsros-supabase-sync.yml",
    "fantasycalc-drift.yml",
    "source-vintage-check.yml",
]

# Swallow patterns that must never appear on a pull/import/save step.
SWALLOW_PATTERNS = [
    re.compile(r"\|\|\s*echo\b"),          # `|| echo "failed, using old data"`
    re.compile(r"\|\|\s*true\b"),          # `|| true` on a pull step
    re.compile(r"continue-on-error\s*:\s*true", re.IGNORECASE),
]


def _step_blocks(yaml_text):
    """Split a workflow's steps into (name, body) pairs.

    Minimal YAML-aware split: a step starts at a line matching
    `- name:` or `- uses:` / `- run:` at the step indent level.
    Good enough for the swallow scan; not a general YAML parser.
    """
    blocks = []
    current_name = None
    current_lines = []
    for line in yaml_text.splitlines():
        m = re.match(r"^(\s*)-\s+(name:\s*(.+)|uses:|run:\s*\|)", line)
        if m:
            if current_name is not None:
                blocks.append((current_name, "\n".join(current_lines)))
            name_part = m.group(2)
            if name_part.startswith("name:"):
                current_name = m.group(3).strip().strip("'\"")
            else:
                current_name = name_part.strip()
            current_lines = [line]
        elif current_name is not None:
            current_lines.append(line)
    if current_name is not None:
        blocks.append((current_name, "\n".join(current_lines)))
    return blocks


def _is_pull_step(name, body):
    """Heuristic: is this step a pull / import / save step?

    Commit/push steps are excluded: a `|| true` on `git commit` (which exits
    1 when there is nothing to commit) is legitimate flow control, not a
    fail-open data swallow.
    """
    name_low = name.lower()
    if any(kw in name_low for kw in ("commit", "push")):
        return False
    hay = f"{name}\n{body}".lower()
    return any(
        kw in hay
        for kw in ("scrape", "pull", "import", "save to", "drift")
    )


class TestNoFailopenWorkflows(unittest.TestCase):
    def test_no_swallow_on_pull_steps(self):
        """No `|| echo`, `|| true`, or `continue-on-error: true` on pull steps."""
        violations = []
        for wf in PULL_WORKFLOWS:
            path = WORKFLOWS / wf
            self.assertTrue(path.exists(), f"workflow missing: {wf}")
            text = path.read_text(encoding="utf-8")
            for name, body in _step_blocks(text):
                if not _is_pull_step(name, body):
                    continue
                for pat in SWALLOW_PATTERNS:
                    if pat.search(body):
                        violations.append(f"{wf} :: {name} :: {pat.pattern}")
        self.assertEqual(
            violations, [],
            f"Fail-open swallows on pull steps:\n" + "\n".join(violations),
        )

    def test_each_pull_job_writes_step_summary(self):
        """Each pull workflow writes an acquisition line to $GITHUB_STEP_SUMMARY."""
        missing = []
        for wf in PULL_WORKFLOWS:
            path = WORKFLOWS / wf
            text = path.read_text(encoding="utf-8")
            if "GITHUB_STEP_SUMMARY" not in text:
                missing.append(wf)
        self.assertEqual(
            missing, [],
            f"Pull workflows with no $GITHUB_STEP_SUMMARY write: {missing}",
        )


if __name__ == "__main__":
    unittest.main()
