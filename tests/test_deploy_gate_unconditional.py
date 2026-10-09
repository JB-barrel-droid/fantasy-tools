"""Guard: pages.yml runs validate and rendered gate unconditionally (JEG-133).

A deploy gate that no unrelated commit can bypass must run on EVERY push to main,
regardless of which files the last commit touched. This test verifies:
  (a) the validate step has no `if:` clause
  (b) the rendered-gate step exists and has no `if:` clause
  (c) no step reintroduces `paths-ignore` or `steps.*.outputs.*` gating

This test FAILS on the base commit (5df093c9b199) where path-dependent gating
was still present and the rendered gate was missing, and PASSES after the fix.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGES = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")


def steps(text):
    """Split the job's steps; each step is the text of one '      - ' block."""
    blocks, current = [], None
    for line in text.splitlines():
        if re.match(r"^      - ", line):
            if current is not None:
                blocks.append("\n".join(current))
            current = [line]
        elif current is not None and (line.startswith("        ") or not line.strip()):
            current.append(line)
        elif current is not None:
            blocks.append("\n".join(current))
            current = None
    if current is not None:
        blocks.append("\n".join(current))
    return blocks


def get_step(step_blocks, keyword):
    """Find a step block containing the keyword."""
    for block in step_blocks:
        if keyword in block:
            return block
    return None


def has_if_clause(step_block):
    """Check if a step block has an `if:` clause at step level (not inside run:)."""
    # Look for `      - if:` at step level (not indented further)
    for line in step_block.splitlines():
        if re.match(r"^      - if:", line):
            return True
    return False


class DeployGateUnconditionalTest(unittest.TestCase):
    """Verify deploy gates run unconditionally on every push to main."""

    def test_validate_step_has_no_if_clause(self):
        """(a) the validate step has no `if:` clause."""
        step = get_step(steps(PAGES), "make validate")
        self.assertIsNotNone(step, "pages.yml must have a 'make validate' step")
        self.assertFalse(
            has_if_clause(step),
            "make validate must run unconditionally (no `if:` clause)")

    def test_rendered_gate_step_exists_and_has_no_if_clause(self):
        """(b) the rendered-gate step exists and has no `if:` clause."""
        gate = get_step(steps(PAGES), "tests/rendered_gate/gate.mjs")
        self.assertIsNotNone(
            gate,
            "pages.yml must run the rendered gate (tests/rendered_gate/gate.mjs)")
        self.assertFalse(
            has_if_clause(gate),
            "rendered gate must run unconditionally (no `if:` clause)")

    def test_no_paths_ignore_gating(self):
        """(c) no step reintroduces paths-ignore gating."""
        self.assertNotIn(
            "paths-ignore", PAGES,
            "pages.yml must not use paths-ignore to skip validation")
        self.assertNotIn(
            "paths:", PAGES,
            "pages.yml must not use paths to conditionally run steps")

    def test_no_step_output_gating(self):
        """(c) no step uses steps.*.outputs.* to gate validate or rendered gate."""
        # Check for any conditional that references step outputs
        output_gating_patterns = [
            r"if:.*steps\.[a-z]+\.outputs\.",
            r"if:.*needs\.",
        ]
        for pattern in output_gating_patterns:
            matches = re.findall(pattern, PAGES)
            self.assertEqual(
                [], matches,
                f"pages.yml must not gate on step outputs (found: {matches})")

    def test_validate_step_is_not_continue_on_error(self):
        """make validate must be blocking (not continue-on-error)."""
        step = get_step(steps(PAGES), "make validate")
        self.assertIsNotNone(step, "pages.yml must have a 'make validate' step")
        self.assertNotIn(
            "continue-on-error: true", step,
            "make validate must block the deploy (not continue-on-error)")

    def test_rendered_gate_is_not_continue_on_error(self):
        """rendered gate must be blocking (not continue-on-error)."""
        gate = get_step(steps(PAGES), "tests/rendered_gate/gate.mjs")
        self.assertIsNotNone(
            gate,
            "pages.yml must run the rendered gate (tests/rendered_gate/gate.mjs)")
        self.assertNotIn(
            "continue-on-error: true", gate,
            "rendered gate must block the deploy (not continue-on-error)")



class DeployNeverStarves(unittest.TestCase):
    """2026-10-09: with cancel-in-progress: true, commits landing faster than a
    deploy cancelled every run and nothing went live for hours. A running deploy
    must finish; the newest pending run deploys next."""

    def test_running_deploy_is_not_cancelled(self):
        block = re.search(r"^concurrency:\n((?:  .*\n?)+)", PAGES, re.M)
        self.assertIsNotNone(block, "pages.yml has no concurrency block")
        self.assertRegex(block.group(1), r"cancel-in-progress:\s*false")

if __name__ == "__main__":
    unittest.main()
