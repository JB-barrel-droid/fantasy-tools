"""Rebuild publication survives independent monitoring writes (JEG-1206).

Run 37802134747 failed in "Commit and push if changed": its rebase onto
origin/main conflicted on generated files (fixture, dist/modules/*.json, week
history) that run 37802033901 had pushed while it waited. The concurrency group
did serialize the two (the second job started 4 s after the first ended); the
second rebuilt on a stale tree because actions/checkout used the dispatch-time
SHA. Two fixes are pinned here:

  - the checkout takes the branch tip at job start (`ref: ${{ github.ref }}`);
  - independent monitoring writes on main must not drop a validated rebuild;
    its fixture and week index publish together, keeping main's newer monitor;
  - source/data changes require a fresh chain run on current main, bounded by
    MAX_CHAIN_ATTEMPTS, even when Git could merge them without text conflicts.

The real `run:` scripts are executed against throwaway repos with a local bare
remote (harness from test_rebuild_chain_workflow).
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import (
    BASELINE, COMMIT, FIXTURE, HEALTH, MONITOR_FIXTURE, MONITOR_STATUS,
    OUT_STATUS, PUBLISH_RED, SYNC_OK, WORKFLOW, find_step, git, run_script, write)

# Records the dispatch instead of calling GitHub.
PROBE_STUB = (
    "import sys, pathlib\n"
    "pathlib.Path('dispatch.log').write_text(' '.join(sys.argv[1:]))\n")

HISTORY = "data/history/index.json"
SOURCE = "pipelines/example.py"
DIRTY = "app/unpublished.txt"


def scenario(text, other_push, attempt="1", *, local_changes=None,
             outcome="success", race=False, race_source=False, reject_pushes=False,
             lost_ack=False, confirmation_fetch_fails=False):
    """Run SYNC_OK + COMMIT after another chain run pushed `other_push`
    ({path: content}) to main while this run built a NEW fixture."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work, other = td / "remote.git", td / "work", td / "other"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        baseline = {**BASELINE, HISTORY: "OLD-HISTORY", SOURCE: "OLD-SOURCE",
                    DIRTY: "COMMITTED"}
        for rel, content in baseline.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        # The run ahead of us publishes while we build.
        git(td, "clone", "-q", str(remote), str(other))
        if other_push:
            for rel, content in other_push.items():
                write(other, rel, content)
            git(other, "add", "-A")
            git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "other run")
            git(other, "push", "-q", "origin", "main")
        other_head = git(other, "rev-parse", "HEAD")
        # This run's rebuild.
        changes = {FIXTURE: "NEW" if outcome == "success" else "PARTIAL",
                   OUT_STATUS: "GREEN" if outcome == "success" else "RED",
                   HISTORY: "NEW-HISTORY", DIRTY: "LOCAL UNFINISHED WORK"}
        changes.update(local_changes or {})
        for rel, content in changes.items():
            write(work, rel, content)
        write(work, "pipelines/source_probe.py", PROBE_STUB)
        out, summary = td / "gh_out.txt", td / "summary.md"
        # A client hook races one real competing push after the workflow has
        # fetched main. It also counts rejected pushes without mocking Git.
        hook = work / ".git/hooks/pre-push"
        hook.write_text(
            "#!/bin/sh\n"
            "count=$(cat \"$TEST_PUSH_COUNT\" 2>/dev/null || echo 0)\n"
            "echo $((count + 1)) > \"$TEST_PUSH_COUNT\"\n"
            "if [ \"$TEST_RACE\" = true ] && [ \"$count\" = 0 ]; then\n"
            "  unset $(git rev-parse --local-env-vars)\n"
            "  printf '%s' \"$TEST_RACE_CONTENT\" > \"$TEST_OTHER/$TEST_RACE_PATH\"\n"
            "  git -C \"$TEST_OTHER\" add \"$TEST_RACE_PATH\"\n"
            "  git -C \"$TEST_OTHER\" -c user.name=t -c user.email=t@t commit -qm racing-monitor\n"
            "  git -C \"$TEST_OTHER\" push -q origin main || exit 1\n"
            "fi\n"
            "[ \"$TEST_REJECT\" != true ]\n", encoding="utf-8")
        hook.chmod(0o755)
        sleep = td / "bin/sleep"
        write(td, "bin/sleep", "#!/bin/sh\nexit 0\n")
        sleep.chmod(0o755)
        if lost_ack:
            # The server accepts the first push, but the client loses its
            # acknowledgement. Recovery must detect acceptance before retrying.
            wrapper = td / "bin/git"
            wrapper.write_text(
                f"#!{sys.executable}\n"
                "import os, pathlib, subprocess, sys\n"
                "marker = pathlib.Path(os.environ['TEST_ACK_LOST'])\n"
                "if 'fetch' in sys.argv[1:] and os.environ['TEST_FAIL_CONFIRMATION'] == 'true' "
                "and marker.exists() and marker.read_text() == 'accepted':\n"
                "    marker.write_text('confirmation failed')\n"
                "    sys.exit(1)\n"
                f"result = subprocess.run([{shutil.which('git')!r}, *sys.argv[1:]])\n"
                "if result.returncode == 0 and 'push' in sys.argv[1:] and not marker.exists():\n"
                "    marker.write_text('accepted')\n"
                "    sys.exit(1)\n"
                "sys.exit(result.returncode)\n", encoding="utf-8")
            wrapper.chmod(0o755)
        count_file = td / "push-count"
        env = {"PATH": f"{td / 'bin'}:{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/local/bin",
               "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary),
               "CHAIN_OUTCOME": outcome, "CHAIN_ATTEMPT": attempt,
               "MAX_CHAIN_ATTEMPTS": "3", "BAKE_PLAYERS": "true",
               "TEST_PUSH_COUNT": str(count_file), "TEST_OTHER": str(other),
               "TEST_RACE": str(race or race_source).lower(),
               "TEST_RACE_PATH": SOURCE if race_source else HEALTH,
               "TEST_RACE_CONTENT": "RACING-SOURCE" if race_source else "LATEST-HEALTH",
               "TEST_ACK_LOST": str(td / "ack-lost"),
               "TEST_FAIL_CONFIRMATION": str(confirmation_fetch_fails).lower(),
               "TEST_REJECT": str(reject_pushes).lower()}
        run_script(text, SYNC_OK if outcome == "success" else PUBLISH_RED, work, env)
        r = run_script(text, COMMIT, work, env)
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        dispatch = work / "dispatch.log"
        return {
            "rc": r.returncode,
            "log": r.stdout + r.stderr,
            "remote_fixture": (verify / FIXTURE).read_text(encoding="utf-8"),
            "remote_monitor": (verify / MONITOR_FIXTURE).read_text(encoding="utf-8"),
            "remote_health": (verify / HEALTH).read_text(encoding="utf-8"),
            "remote_status": (verify / MONITOR_STATUS).read_text(encoding="utf-8"),
            "remote_history": (verify / HISTORY).read_text(encoding="utf-8"),
            "remote_source": (verify / SOURCE).read_text(encoding="utf-8"),
            "remote_dirty": (verify / DIRTY).read_text(encoding="utf-8"),
            "local_dirty": (work / DIRTY).read_text(encoding="utf-8"),
            "push_count": int(count_file.read_text()) if count_file.exists() else 0,
            "patch_saved": (work / "output/rebuild-publication.patch").exists(),
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

    def test_health_conflict_keeps_validated_fixture_and_week_history(self):
        # Run 40689076971: only a shared health report conflicted after the
        # chain had already validated the new week's complete data.
        r = scenario(WORKFLOW, {HEALTH: "NEWER-MAIN-HEALTH"},
                     local_changes={HEALTH: "RUN-HEALTH"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual("NEW", r["remote_fixture"])
        self.assertEqual("NEW", r["remote_monitor"])
        self.assertEqual("NEW-HISTORY", r["remote_history"])
        self.assertEqual("GREEN", r["remote_status"])
        self.assertEqual("NEWER-MAIN-HEALTH", r["remote_health"])
        self.assertEqual("COMMITTED", r["remote_dirty"])
        self.assertEqual("LOCAL UNFINISHED WORK", r["local_dirty"])
        self.assertEqual(1, r["push_count"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=true", r["outputs"])

    def test_source_change_requires_regeneration_even_without_text_conflict(self):
        r = scenario(WORKFLOW, {SOURCE: "NEW-SOURCE"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual("NEW-SOURCE", r["remote_source"])
        self.assertEqual("OLD", r["remote_fixture"])
        self.assertEqual(0, r["push_count"])
        self.assertIn("attempt=2", r["dispatch"] or "")
        self.assertIn("pushed=false", r["outputs"])
        self.assertTrue(r["patch_saved"], "the validated candidate must remain recoverable")

    def test_history_change_requires_regeneration(self):
        r = scenario(WORKFLOW, {HISTORY: "MAIN-HISTORY"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual("MAIN-HISTORY", r["remote_history"])
        self.assertEqual("OLD", r["remote_fixture"])
        self.assertIn("attempt=2", r["dispatch"] or "")

    def test_failed_chain_publishes_only_status_after_monitor_conflict(self):
        r = scenario(WORKFLOW, {HEALTH: "NEWER-MAIN-HEALTH"}, outcome="failure",
                     local_changes={HEALTH: "RUN-HEALTH"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual("OLD", r["remote_fixture"])
        self.assertEqual("OLD", r["remote_monitor"])
        self.assertEqual("OLD-HISTORY", r["remote_history"])
        self.assertEqual("RED", r["remote_status"])
        self.assertEqual("NEWER-MAIN-HEALTH", r["remote_health"])
        self.assertEqual("LOCAL UNFINISHED WORK", r["local_dirty"])
        self.assertIn("pushed=true", r["outputs"])

    def test_monitor_push_after_fetch_retries_against_latest_main(self):
        r = scenario(WORKFLOW, {HEALTH: "OTHER-HEALTH"}, race=True)
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual(2, r["push_count"])
        self.assertEqual("LATEST-HEALTH", r["remote_health"])
        self.assertEqual("NEW", r["remote_fixture"])
        self.assertEqual("NEW-HISTORY", r["remote_history"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=true", r["outputs"])

    def test_rejected_pushes_stop_after_three_attempts_and_preserve_candidate(self):
        r = scenario(WORKFLOW, {}, reject_pushes=True)
        self.assertNotEqual(0, r["rc"], "repeated push rejection must fail loudly")
        self.assertEqual(3, r["push_count"], r["log"])
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual("OLD", r["remote_fixture"])
        self.assertIsNone(r["dispatch"])
        self.assertNotIn("pushed=true", r["outputs"])
        self.assertTrue(r["patch_saved"])

    def test_source_push_after_fetch_requires_regeneration(self):
        r = scenario(WORKFLOW, {HEALTH: "OTHER-HEALTH"}, race_source=True)
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual(1, r["push_count"])
        self.assertEqual("RACING-SOURCE", r["remote_source"])
        self.assertEqual("OLD", r["remote_fixture"])
        self.assertEqual("OLD-HISTORY", r["remote_history"])
        self.assertIn("attempt=2", r["dispatch"] or "")
        self.assertIn("pushed=false", r["outputs"])

    def test_accepted_push_with_lost_acknowledgement_still_deploys(self):
        r = scenario(WORKFLOW, {}, lost_ack=True)
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual(1, r["push_count"], "an accepted push must not be published twice")
        self.assertEqual("NEW", r["remote_fixture"])
        self.assertEqual("NEW-HISTORY", r["remote_history"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=true", r["outputs"], "Pages must run for the accepted commit")

    def test_lost_acknowledgement_is_confirmed_after_transient_fetch_failure(self):
        r = scenario(WORKFLOW, {}, lost_ack=True, confirmation_fetch_fails=True)
        self.assertEqual(0, r["rc"], r["log"])
        self.assertEqual(1, r["push_count"])
        self.assertEqual("NEW", r["remote_fixture"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=true", r["outputs"], "later confirmation must still trigger Pages")

    def test_no_candidate_changes_do_not_push(self):
        r = scenario(WORKFLOW, {}, local_changes={FIXTURE: "OLD", HISTORY: "OLD-HISTORY",
                                                 OUT_STATUS: "OLD-STATUS"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual(0, r["push_count"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=false", r["outputs"])

    def test_monitor_only_candidate_superseded_on_main_does_not_push(self):
        r = scenario(WORKFLOW, {HEALTH: "NEWER-MAIN-HEALTH"}, local_changes={
            FIXTURE: "OLD", HISTORY: "OLD-HISTORY", OUT_STATUS: "OLD-STATUS",
            HEALTH: "RUN-HEALTH"})
        self.assertEqual(0, r["rc"], r["log"])
        self.assertTrue(r["remote_head_is_other"])
        self.assertEqual("NEWER-MAIN-HEALTH", r["remote_health"])
        self.assertEqual(0, r["push_count"])
        self.assertIsNone(r["dispatch"])
        self.assertIn("pushed=false", r["outputs"])

    def test_commit_handler_never_rewrites_history(self):
        block = find_step(WORKFLOW, COMMIT)
        self.assertNotRegex(block, r"git (?:pull[^\n]*--rebase|rebase|reset --hard)")
        self.assertNotRegex(block, r"git [^\n]*push[^\n]*(?:--force|-f\b)")

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
