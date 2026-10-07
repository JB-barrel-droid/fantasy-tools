"""JEG-414 follow-up: health-artifacts.yml must NOT commit to main.

After the JEG-414 follow-up, health artifacts go to Supabase
(public.ops_artifacts) instead of being committed to dist/modules on main.

Rules this pins, each negative-tested against a mutated workflow:
  - no git commit or git push step in health-artifacts.yml (the commit-to-main
    path caused 48+ bot commits/day and Pages-deploy cancellations);
  - the store step runs only when the producer succeeded (a broken build
    never replaces the stored artifacts; the watch then reports them aging);
  - the workflow has no GitHub `schedule:` -- Supabase pg_cron
    `health-artifacts-live` is the single scheduler owner (ops-ownership-001);
  - permissions.contents is `read` (not `write`), confirming no push intent.
"""
import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/health-artifacts.yml").read_text()
STORE_STEP = "Store health artifacts in Supabase (JEG-414 follow-up)"
REQUIRED_STORE_IF = "if: steps.build.outcome == 'success'"
DISALLOWED_COMMIT = re.compile(r"\bgit\s+commit\b")
DISALLOWED_PUSH = re.compile(r"\bgit\s+push\b")
DISALLOWED_PAGES_DISPATCH = re.compile(r"pages\.yml/dispatches")


def _non_comment_text(text: str) -> str:
    """Strip pure-comment lines so the regex doesn't match them."""
    return "\n".join(
        line for line in text.splitlines()
        if not line.lstrip().startswith("#")
    )


def find_step(text, name):
    """Return the text of the named step block, or None."""
    pattern = re.compile(
        r"- name:\s+" + re.escape(name) + r"\n([\s\S]*?)(?=\n\s{6}- name:|\Z)", re.M
    )
    m = pattern.search(text)
    return m.group(0) if m else None


def static_problems(text):
    nc = _non_comment_text(text)
    problems = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        problems.append("GitHub schedule present: pg_cron must be the only scheduler owner")
    if DISALLOWED_COMMIT.search(nc):
        problems.append("git commit found: health artifacts must NOT be committed to main")
    if DISALLOWED_PUSH.search(nc):
        problems.append("git push found: health artifacts must NOT be pushed to main")
    if DISALLOWED_PAGES_DISPATCH.search(nc):
        problems.append("pages.yml dispatch found: no Pages deploy needed for monitoring artifacts")
    # Permissions check (non-comment only)
    if "contents: write" in nc:
        problems.append("permissions.contents is write: must be read (no push intent)")
    # Store step required
    block = find_step(text, STORE_STEP)
    if block is None:
        problems.append(f"store step '{STORE_STEP}' missing")
        return problems
    if REQUIRED_STORE_IF not in block:
        problems.append("store step must run only after a successful build")
    return problems


class HealthArtifactsPublishTest(unittest.TestCase):
    def test_real_workflow_has_no_git_commit(self):
        """The live workflow must pass all static checks (no commit, no push, etc.)."""
        problems = static_problems(WORKFLOW)
        self.assertEqual([], problems, f"Static problems: {problems}")

    def _has_problem(self, problems, key):
        return any(key in p for p in problems)

    def test_adding_git_commit_is_caught(self):
        """Negative: a git commit step triggers the guard."""
        mutated = WORKFLOW + "\n      - name: bad\n        run: git commit -m test\n"
        self.assertTrue(self._has_problem(static_problems(mutated), "git commit found"))

    def test_adding_git_push_is_caught(self):
        """Negative: a git push step triggers the guard."""
        mutated = WORKFLOW + "\n      - name: bad\n        run: git push origin main\n"
        self.assertTrue(self._has_problem(static_problems(mutated), "git push found"))

    def test_pages_dispatch_is_caught(self):
        """Negative: dispatching pages.yml triggers the guard."""
        mutated = WORKFLOW + "\n      - run: curl pages.yml/dispatches\n"
        self.assertTrue(self._has_problem(static_problems(mutated), "pages.yml dispatch found"))

    def test_a_github_schedule_is_caught(self):
        """Negative: a GitHub schedule triggers the guard."""
        mutated = WORKFLOW.replace(
            "on:\n  workflow_dispatch:",
            'on:\n  schedule:\n    - cron: "11,41 * * * *"\n  workflow_dispatch:', 1
        )
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertTrue(any("schedule" in p for p in static_problems(mutated)))

    def test_contents_write_permission_is_caught(self):
        """Negative: contents: write permission triggers the guard."""
        mutated = WORKFLOW.replace("contents: read", "contents: write", 1)
        self.assertTrue(self._has_problem(static_problems(mutated), "permissions.contents is write"))

    def test_store_step_must_be_conditional_on_build_success(self):
        """Negative: store step with always() condition triggers the guard."""
        mutated = WORKFLOW.replace(
            REQUIRED_STORE_IF,
            "if: always()", 1
        )
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertTrue(
            self._has_problem(static_problems(mutated), "store step must run only after a successful build")
        )


if __name__ == "__main__":
    unittest.main()
