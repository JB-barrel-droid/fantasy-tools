"""JEG-414: health-artifacts.yml is the monitor's health writer.

Rules this pins, each negative-tested against a mutated workflow:
  - the publish step runs only when the producer succeeded and only on main,
    so a broken build never replaces the served artifacts;
  - it pushes exactly the two health files (never the fixture or anything else);
  - the workflow has no GitHub `schedule:` -- Supabase pg_cron
    `health-artifacts-live` is the single scheduler owner (ops-ownership-001;
    GitHub's own schedule fired only twice on 2026-10-06 instead of every 30 min).

The publish script is executed for real against a throwaway repo with a local
bare remote (same harness as test_rebuild_chain_workflow).
"""
import re
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import find_step, git, run_script, write  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/health-artifacts.yml").read_text(encoding="utf-8")
PUBLISH = "Publish to the monitor (JEG-414)"
HEALTH = "dist/modules/source-import-health.json"
CHECKPOINTS = "dist/modules/pipeline-checkpoints.json"
FIXTURE = "data/fixtures/current/comparison-sources-data.json"
REQUIRED_IF = "if: steps.build.outcome == 'success' && github.ref == 'refs/heads/main'"


def static_problems(text):
    problems = []
    if re.search(r"^\s*schedule:\s*$", text, re.M):
        problems.append("GitHub schedule present: pg_cron must be the only scheduler owner")
    block = find_step(text, PUBLISH)
    if block is None:
        return problems + ["publish step missing"]
    if REQUIRED_IF not in block:
        problems.append("publish must run only after a successful build, on main")
    return problems


def publish_run(text):
    """Run the real publish script; return the set of files changed on the remote."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel in (HEALTH, CHECKPOINTS, FIXTURE):
            write(work, rel, "OLD")
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "base")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")
        write(work, "output/source-import-health.json", "NEW-HEALTH")
        write(work, "output/pipeline-checkpoints.json", "NEW-CP")
        write(work, FIXTURE, "PARTIAL")  # must never be published by this job
        r = run_script(text, PUBLISH, work, {"GITHUB_OUTPUT": str(td / "out.txt")})
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        changed = set(git(verify, "diff", "--name-only", base, "HEAD").split())
        return r.returncode, changed, (verify / HEALTH).read_text(encoding="utf-8")


class HealthArtifactsPublishTest(unittest.TestCase):
    def test_real_workflow(self):
        self.assertEqual([], static_problems(WORKFLOW))
        rc, changed, health = publish_run(WORKFLOW)
        self.assertEqual(0, rc)
        self.assertEqual({HEALTH, CHECKPOINTS}, changed)
        self.assertEqual("NEW-HEALTH", health)

    def test_publishing_after_a_failed_build_is_caught(self):
        mutated = WORKFLOW.replace(REQUIRED_IF, "if: always()", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertIn("publish must run only after a successful build, on main", static_problems(mutated))

    def test_a_github_schedule_is_caught(self):
        mutated = WORKFLOW.replace("on:\n  workflow_dispatch:", 'on:\n  schedule:\n    - cron: "11,41 * * * *"\n  workflow_dispatch:', 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertTrue(any("schedule" in p for p in static_problems(mutated)))

    def test_staging_the_fixture_is_caught(self):
        mutated = WORKFLOW.replace(
            "git add dist/modules/source-import-health.json dist/modules/pipeline-checkpoints.json",
            "git add dist/modules/source-import-health.json dist/modules/pipeline-checkpoints.json "
            "data/fixtures/current/comparison-sources-data.json", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        _, changed, _ = publish_run(mutated)
        self.assertIn(FIXTURE, changed)


if __name__ == "__main__":
    unittest.main()
