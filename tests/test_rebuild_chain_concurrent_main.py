"""A validated rebuild survives main moving under it (JEG-1206).

Run 40689076971 passed `make validate`, then its commit step's rebase onto
origin/main conflicted on dist/modules/source-import-health.json: the
health-artifacts job had pushed a newer import-health report while the chain
built. The rebuild was dropped, and the handoff dispatch was skipped because
another run was already waiting, so the fixture and its week-history index
never reached main.

The commit step now publishes this run's output as one normal commit on top of
current main (no rebase, no merge, never a force-push):

  - a monitor report main updated meanwhile is kept as main has it, and the
    rest of the rebuild still publishes (the 40689076971 case);
  - a code or doc change on main is kept and the rebuild publishes on top;
  - a rebuild input or output changed on main (fixture, week history, legs,
    projection inputs, config/, fidelity holds) means this run's numbers are
    not the newest: nothing is published and a fresh run regenerates;
  - main moving again between fetch and push re-sorts from the new tip;
  - a push whose reply was lost is confirmed on main, not pushed twice.

The real `run:` script runs against throwaway repos with a local bare remote
(harness from test_rebuild_chain_workflow). The race is real: a `git` shim
lands a competing commit on the remote at the moment this run pushes.
"""
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from tests.test_rebuild_chain_workflow import (
    BASELINE, COMMIT, FIXTURE, HEALTH, MONITOR_FIXTURE, MONITOR_STATUS, SYNC_OK,
    WORKFLOW, find_step, git, run_script, script_of, write)

HISTORY_INDEX = "data/history/index.json"
CODE_EDIT = "pipelines/some_stage.py"
REAL_GIT = shutil.which("git")

PROBE_STUB = (
    "import sys, pathlib\n"
    "pathlib.Path('dispatch.log').write_text(' '.join(sys.argv[1:]))\n"
    "print('rebuild-chain (stub): dispatched')\n")

# Wraps git for the commit step. On this run's first `git push` it either lands
# a competing commit on the remote first (race), or lets the push through and
# then reports failure (lost reply).
SHIM = """#!/bin/bash
if [ "$1" = "push" ] && [ ! -e "$SHIM_STATE/fired" ]; then
  touch "$SHIM_STATE/fired"
  case "$SHIM_MODE" in
    race)
      ( cd "$SHIM_OTHER" && {real} pull -q origin main && printf 'RACE' > dist/modules/ops-status.json \\
        && {real} add -A && {real} -c user.name=t -c user.email=t@t commit -qm 'ops status (race)' \\
        && {real} push -q origin HEAD:main ) >/dev/null 2>&1
      ;;
    lost)
      {real} "$@" >/dev/null 2>&1
      echo "fatal: the remote end hung up unexpectedly" >&2
      exit 128
      ;;
  esac
fi
exec {real} "$@"
"""


def scenario(text, main_moves, *, chain="success", mode=None, run_writes=None):
    """Build a baseline, push `main_moves` ({path: content}) to main while this
    run builds, then run this run's sync and commit steps."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work, other = td / "remote.git", td / "work", td / "other"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        baseline = {**BASELINE, HISTORY_INDEX: "OLD-INDEX", CODE_EDIT: "OLD-CODE",
                    "dist/modules/ops-status.json": "OLD-OPS"}
        for rel, content in baseline.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")

        git(td, "clone", "-q", str(remote), str(other))
        if main_moves:
            for rel, content in main_moves.items():
                write(other, rel, content)
            git(other, "add", "-A")
            git(other, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "main moved")
            git(other, "push", "-q", "origin", "main")
        moved_head = git(other, "rev-parse", "HEAD")

        # This run's rebuild (what the chain and import-health steps leave).
        writes = run_writes or {}
        if chain == "success":
            writes = {FIXTURE: "NEW", "output/comparison-chain-status.json": "GREEN",
                      HEALTH: "RUN-HEALTH", HISTORY_INDEX: "NEW-INDEX", **writes}
        else:
            writes = {FIXTURE: "PARTIAL", "output/comparison-chain-status.json": "RED",
                      MONITOR_STATUS: "RED", HEALTH: "RUN-HEALTH", **writes}
        for rel, content in writes.items():
            write(work, rel, content)
        write(work, "pipelines/source_probe.py", PROBE_STUB)

        shim_dir, state = td / "shim", td / "state"
        shim_dir.mkdir()
        state.mkdir()
        (shim_dir / "git").write_text(SHIM.format(real=REAL_GIT))
        (shim_dir / "git").chmod(0o755)
        out, summary = td / "gh_out.txt", td / "summary.md"
        env = {"PATH": f"{shim_dir}:{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/local/bin",
               "GITHUB_OUTPUT": str(out), "GITHUB_STEP_SUMMARY": str(summary),
               "CHAIN_OUTCOME": chain, "CHAIN_ATTEMPT": "1", "MAX_CHAIN_ATTEMPTS": "3",
               "BAKE_PLAYERS": "false", "SHIM_MODE": mode or "", "SHIM_STATE": str(state),
               "SHIM_OTHER": str(other)}
        if chain == "success":
            sync = run_script(text, SYNC_OK, work, env)
            assert sync.returncode == 0, sync.stdout + sync.stderr
        r = run_script(text, COMMIT, work, env)

        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))

        snapshot = {str(p.relative_to(verify)): p.read_text(encoding="utf-8")
                    for p in verify.rglob("*") if p.is_file() and ".git" not in p.parts}
        log = git(verify, "log", "--format=%s", f"{base}..HEAD").splitlines()
        dispatch = work / "dispatch.log"
        return {
            "rc": r.returncode,
            "log": r.stdout + r.stderr,
            "file": snapshot.get,
            "commits_since_base": log,
            "head_is_moved": git(verify, "rev-parse", "HEAD") == moved_head,
            "moved_is_ancestor": subprocess_ok(verify, "merge-base", "--is-ancestor", moved_head, "HEAD"),
            "dispatch": dispatch.read_text(encoding="utf-8") if dispatch.exists() else None,
            "outputs": out.read_text(encoding="utf-8") if out.exists() else "",
            "local_fixture": (work / FIXTURE).read_text(encoding="utf-8"),
        }


def subprocess_ok(cwd, *args):
    import subprocess
    return subprocess.run(["git", *args], cwd=cwd, capture_output=True).returncode == 0


PUBLICATION = "Automated comparison rebuild (GitHub Actions)"


class ConcurrentMainTest(unittest.TestCase):
    def assertPublishedOnTop(self, r):
        self.assertEqual(0, r["rc"], r["log"])
        self.assertIn("pushed=true", r["outputs"])
        self.assertTrue(r["moved_is_ancestor"], "main's newer commits must stay in history (no force-push)")
        self.assertEqual(1, r["commits_since_base"].count(PUBLICATION), r["commits_since_base"])
        self.assertIsNone(r["dispatch"])

    def test_monitor_report_on_main_no_longer_drops_the_rebuild(self):
        # Run 40689076971: health-artifacts pushed import health meanwhile.
        r = scenario(WORKFLOW, {HEALTH: "MAIN-HEALTH"})
        self.assertPublishedOnTop(r)
        self.assertEqual("NEW", r["file"](FIXTURE))
        self.assertEqual("NEW", r["file"](MONITOR_FIXTURE))
        self.assertEqual("NEW-INDEX", r["file"](HISTORY_INDEX), "the week-history index must publish")
        self.assertEqual("MAIN-HEALTH", r["file"](HEALTH), "main's newer monitor report is kept")

    def test_source_edit_on_main_is_kept_and_rebuild_publishes(self):
        r = scenario(WORKFLOW, {CODE_EDIT: "MAIN-CODE", HEALTH: "MAIN-HEALTH"})
        self.assertPublishedOnTop(r)
        self.assertEqual("MAIN-CODE", r["file"](CODE_EDIT))
        self.assertEqual("NEW", r["file"](FIXTURE))

    def test_rebuild_input_on_main_regenerates_instead_of_publishing(self):
        for path in (HISTORY_INDEX, "config/lineup_parameters.json",
                     "data/ddf-two-tier/leg/ddf_leg_espn.json",
                     "data/inputs/espn_projections.csv", "dist/modules/fidelity-pulse.json"):
            with self.subTest(path=path):
                r = scenario(WORKFLOW, {path: "MAIN-INPUT"})
                self.assertEqual(0, r["rc"], r["log"])
                self.assertTrue(r["head_is_moved"], "nothing may publish over a newer input")
                self.assertEqual("OLD", r["file"](FIXTURE))
                self.assertIn("pushed=false", r["outputs"])
                self.assertIn("handoff=true", r["outputs"])
                self.assertIn("attempt=2", r["dispatch"] or "")

    def test_main_moving_again_at_push_time_retries_from_the_new_tip(self):
        r = scenario(WORKFLOW, {HEALTH: "MAIN-HEALTH"}, mode="race")
        self.assertPublishedOnTop(r)
        self.assertEqual("RACE", r["file"]("dist/modules/ops-status.json"), "the racing commit is kept")
        self.assertEqual("NEW", r["file"](FIXTURE))

    def test_lost_push_reply_is_confirmed_not_pushed_twice(self):
        r = scenario(WORKFLOW, {HEALTH: "MAIN-HEALTH"}, mode="lost")
        self.assertPublishedOnTop(r)
        self.assertEqual("NEW", r["file"](FIXTURE))

    def test_failed_chain_publishes_status_only_beside_a_newer_monitor(self):
        r = scenario(WORKFLOW, {HEALTH: "MAIN-HEALTH"}, chain="failure")
        self.assertEqual(0, r["rc"], r["log"])
        self.assertIn("pushed=true", r["outputs"])
        self.assertEqual("OLD", r["file"](FIXTURE), "a red chain never promotes the fixture")
        self.assertEqual("RED", r["file"](MONITOR_STATUS))
        self.assertEqual("MAIN-HEALTH", r["file"](HEALTH))
        self.assertEqual("PARTIAL", r["local_fixture"], "the checkout's partial fixture is left alone")

    def test_failed_chain_status_publishes_when_a_rebuild_input_moves(self):
        # JEG-1308: a red run stages only status and health, so a newer input
        # on main says nothing about whether that status is current. It must
        # reach the monitor, not hand off to a fresh run.
        for path in ("dist/modules/fidelity-pulse.json", "data/inputs/espn_projections.csv",
                     HISTORY_INDEX, "config/lineup_parameters.json"):
            with self.subTest(path=path):
                r = scenario(WORKFLOW, {path: "MAIN-INPUT", HEALTH: "MAIN-HEALTH"}, chain="failure")
                self.assertEqual(0, r["rc"], r["log"])
                self.assertIn("pushed=true", r["outputs"])
                self.assertIsNone(r["dispatch"], "a red status is published, not regenerated")
                self.assertTrue(r["moved_is_ancestor"])
                self.assertEqual("RED", r["file"](MONITOR_STATUS))
                self.assertEqual("MAIN-INPUT", r["file"](path), "main's newer input is kept")
                self.assertEqual("MAIN-HEALTH", r["file"](HEALTH))
                self.assertEqual("OLD", r["file"](FIXTURE))

    def test_commit_step_never_rewrites_or_merges_main(self):
        script = script_of(find_step(WORKFLOW, COMMIT))
        code = "\n".join(l for l in script.splitlines() if not l.strip().startswith("#"))
        for banned in (r"git push[^\n]*(--force|\s-f\b|\s\+)", r"\bgit rebase\b", r"\bgit merge\s",
                       r"\bgit pull\b", r"\bgit reset\b"):
            self.assertNotRegex(code, banned, f"commit step must not run {banned!r}")


if __name__ == "__main__":
    unittest.main()
