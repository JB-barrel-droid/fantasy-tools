"""rebuild-chain.yml must never fail on generated-file conflicts, and never
publish a stale merge (2026-10-08).

Run 37802134747 failed in "Commit and push if changed": its rebase onto
origin/main conflicted on generated files (fixture, dist/modules/*.json, week
history) that run 37802033901 had pushed while it waited. The concurrency group
did serialize the two (the second job started 4 s after the first ended); the
second rebuilt on a stale tree because actions/checkout used the dispatch-time
SHA. Two fixes are pinned here:

  - the checkout takes the branch tip at job start (`ref: ${{ github.ref }}`);
  - when main still moves under a run and the rebase conflicts, the commit step
    keeps main's newer outputs untouched (no merge, no force-push), dispatches a
    fresh chain run that regenerates on top of them (attempt+1), and stays
    green; after MAX_CHAIN_ATTEMPTS it fails loudly. A plain moved-main
    (no overlap) is rebased and pushed as before.

The real `run:` scripts are executed against throwaway repos with a local bare
remote (harness from test_rebuild_chain_workflow).
"""
import os
import re
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import (
    BASELINE, COMMIT, FIXTURE, MONITOR_FIXTURE, SYNC_OK, WORKFLOW, find_step, git, run_script, write)

# Records the dispatch instead of calling GitHub.
PROBE_STUB = (
    "import sys, pathlib\n"
    "pathlib.Path('dispatch.log').write_text(' '.join(sys.argv[1:]))\n")


def scenario(text, other_push, attempt="1"):
    """Run SYNC_OK + COMMIT after another chain run pushed `other_push`
    ({path: content}) to main while this run built a NEW fixture."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work, other = td / "remote.git", td / "work", td / "other"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel, content in BASELINE.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        # The run ahead of us publishes while we build.
        git(td, "clone", "-q", str(remote), str(other))
        for rel, content in other_push.items():
            write(other, rel, content)
        git(other, "add", "-A")
        git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "other run")
        git(other, "push", "-q", "origin", "main")
        other_head = git(other, "rev-parse", "HEAD")
        # This run's rebuild.
        write(work, FIXTURE, "NEW")
        write(work, "output/comparison-chain-status.json", "GREEN")
        write(work, "pipelines/source_probe.py", PROBE_STUB)
        out, summary = td / "gh_out.txt", td / "summary.md"
        env = {"PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/local/bin",
               "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary),
               "CHAIN_OUTCOME": "success", "CHAIN_ATTEMPT": attempt,
               "MAX_CHAIN_ATTEMPTS": "3", "BAKE_PLAYERS": "true"}
        run_script(text, SYNC_OK, work, env)
        r = run_script(text, COMMIT, work, env)
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        dispatch = work / "dispatch.log"
        return {
            "rc": r.returncode,
            "log": r.stdout + r.stderr,
            "remote_fixture": (verify / FIXTURE).read_text(encoding="utf-8"),
            "remote_monitor": (verify / MONITOR_FIXTURE).read_text(encoding="utf-8"),
            "remote_head_is_other": git(verify, "rev-parse", "HEAD") == other_head,
            "dispatch": dispatch.read_text(encoding="utf-8") if dispatch.exists() else None,
            "outputs": out.read_text(encoding="utf-8") if out.exists() else "",
            "summary": summary.read_text(encoding="utf-8") if summary.exists() else "",
        }


CONFLICTING = {FIXTURE: "OTHER-RUN", MONITOR_FIXTURE: "OTHER-RUN"}


class ConflictHandoffTest(unittest.TestCase):
    def test_conflict_hands_off_instead_of_failing(self):
        r = scenario(WORKFLOW, CONFLICTING)
        self.assertEqual(0, r["rc"], f"a generated-file conflict must not fail the run:\n{r['log']}")
        # main keeps the other run's outputs exactly: no stale merge, no force-push.
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual("OTHER-RUN", r["remote_fixture"])
        self.assertEqual("OTHER-RUN", r["remote_monitor"])
        # A fresh run regenerates on top of it, carrying the bake request.
        self.assertIsNotNone(r["dispatch"], "no fresh chain run was dispatched")
        self.assertIn("dispatch-chain", r["dispatch"])
        self.assertIn("attempt=2", r["dispatch"])
        self.assertIn("bake_players=true", r["dispatch"])
        self.assertIn("pushed=false", r["outputs"])
        self.assertIn("handoff=true", r["outputs"])
        self.assertIn("handoff", r["summary"].lower())

    def test_handoff_is_bounded(self):
        r = scenario(WORKFLOW, CONFLICTING, attempt="3")
        self.assertNotEqual(0, r["rc"], "the last attempt must fail loudly, not loop forever")
        self.assertIsNone(r["dispatch"])
        self.assertEqual("OTHER-RUN", r["remote_fixture"])

    def test_moved_main_without_overlap_still_pushes(self):
        r = scenario(WORKFLOW, {"dist/modules/ops-status.json": "OPS"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual("NEW", r["remote_fixture"])
        self.assertEqual("NEW", r["remote_monitor"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=true", r["outputs"])

    def test_checkout_takes_the_branch_tip_not_the_dispatch_sha(self):
        block = find_step(WORKFLOW, "actions/checkout@v4") or WORKFLOW[WORKFLOW.index("uses: actions/checkout@v4"):]
        head = block[:block.index("- name:")] if "- name:" in block else block
        self.assertRegex(head, r"ref:\s*\$\{\{\s*github\.ref\s*\}\}",
                         "a queued run must build on main as of its start, not as of its dispatch")

    def test_attempt_is_a_declared_dispatch_input(self):
        # The dispatches API rejects undeclared inputs (HTTP 422, JEG-269).
        on_block = WORKFLOW[WORKFLOW.index("workflow_dispatch:"):WORKFLOW.index("\nconcurrency:")]
        self.assertRegex(on_block, r"\n      attempt:\n")
        self.assertRegex(on_block, r"\n      bake_players:\n")


if __name__ == "__main__":
    unittest.main()
