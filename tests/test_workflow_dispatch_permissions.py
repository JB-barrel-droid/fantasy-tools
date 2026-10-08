"""Workflow dispatch-permission guard (JEG-300).

On 2026-10-03 the rebuild chain's "Trigger Pages deploy after chain push"
(JEG-274) step failed in production with:

    could not create workflow dispatch event: HTTP 403: Resource not accessible
    by integration (POST .../actions/workflows/363753372/dispatches)

The step runs `gh workflow run pages.yml`, which calls the workflow-dispatches
API. That endpoint requires the `actions: write` permission, but
rebuild-chain.yml declared only `permissions: contents: write`, so the
GITHUB_TOKEN was rejected and every pushing chain rebuild failed its run and
never deployed.

This test scans every workflow for steps that dispatch another workflow via
`gh workflow run` and requires the file to grant `actions: write`. Parsing is
plain text (PyYAML is not on the CI unit-test step).
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def declared_permissions(text):
    """Top-level `permissions:` block as {name: value}; {} when absent.

    A workflow without an explicit block inherits the repo default, which may
    be restrictive — only an explicit `actions: write` satisfies this guard.
    """
    lines = text.splitlines()
    perms = {}
    in_block = False
    for line in lines:
        if re.match(r"^permissions:\s*$", line):
            in_block = True
            continue
        if in_block:
            m = re.match(r"^  ([a-z-]+):\s*([a-z-]+)", line)
            if m:
                perms[m.group(1)] = m.group(2)
                continue
            if line.strip() and not line.startswith(" "):
                break
    return perms


def dispatch_steps(text):
    """Names of steps whose run: body calls `gh workflow run`."""
    names = []
    current_name = None
    in_run = False
    for line in text.splitlines():
        m = re.match(r"^      - name:\s*(.+)$", line)
        if m:
            current_name = m.group(1).strip()
            in_run = False
            continue
        if re.match(r"^        run:\s*\|", line):
            in_run = True
            continue
        if in_run:
            if "gh workflow run" in line:
                names.append(current_name)
            if line.strip() and not line.startswith(" "):
                in_run = False
    return names


def check(text, path="<text>"):
    """Return error strings for dispatch steps lacking actions: write."""
    errors = []
    for step in dispatch_steps(text):
        if declared_permissions(text).get("actions") != "write":
            errors.append(
                f"{path}: step '{step}' runs `gh workflow run` but the "
                "workflow does not declare `actions: write` (the dispatches "
                "API returns HTTP 403 without it — JEG-300)"
            )
    return errors


class DispatchPermissionTest(unittest.TestCase):
    def test_all_workflows_grant_actions_write_for_dispatch_steps(self):
        failures = []
        for path in sorted(WORKFLOWS.glob("*.yml")):
            failures.extend(check(path.read_text(encoding="utf-8"), str(path.name)))
        self.assertEqual(failures, [], "\n".join(failures))

    def test_discrimination_removed_permission_is_caught(self):
        # The exact JEG-300 defect: `gh workflow run pages.yml` present but
        # `actions: write` missing from permissions.
        mutated = (
            "permissions:\n"
            "  contents: write\n"
            "jobs:\n"
            "  x:\n"
            "    steps:\n"
            "      - name: Trigger Pages deploy\n"
            "        run: |\n"
            "          gh workflow run pages.yml\n"
        )
        self.assertTrue(check(mutated))

    def test_granted_permission_passes(self):
        ok = (
            "permissions:\n"
            "  contents: write\n"
            "  actions: write\n"
            "jobs:\n"
            "  x:\n"
            "    steps:\n"
            "      - name: Trigger Pages deploy\n"
            "        run: |\n"
            "          gh workflow run pages.yml\n"
        )
        self.assertEqual(check(ok), [])


if __name__ == "__main__":
    unittest.main()
