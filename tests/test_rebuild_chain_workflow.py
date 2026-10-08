"""Behaviour tests for .github/workflows/rebuild-chain.yml (JEG-8).

Before JEG-8 a red chain (a fail-closed review hold) stopped the job at the chain
step, so nothing was copied or pushed: the served monitor kept a stale fixture and
a stale chain status, and a red chain was invisible. The workflow now:

  - lets the chain step fail without stopping the job (continue-on-error),
  - on success: syncs the rebuilt fixture into dist and commits it,
  - on failure: publishes ONLY the chain status and never stages the fixture (the
    fixture on disk may hold promotions from sources that passed while others were
    held, with fit and adjusted sections skipped), then fails the job explicitly.

These tests do not just read the YAML: they extract the real `run:` scripts and
execute them against throwaway git repos with a local bare remote, then inspect
what was actually pushed. Every rule is negative-tested against a mutated copy of
the real workflow. Parsing is plain text (PyYAML is not on the CI unit-test step).
"""
import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/rebuild-chain.yml").read_text(encoding="utf-8")

CHAIN = "Rebuild comparison chain (if fixture stale)"
SYNC_OK = "Sync rebuilt fixture into dist (chain succeeded)"
PUBLISH_RED = "Publish chain status only (chain failed)"
COMMIT = "Commit and push if changed"
FAIL = "Fail the job if the chain failed"
REFRESH = "Refresh GitHub Actions status (JEG-109)"

FIXTURE = "data/fixtures/current/comparison-sources-data.json"
MONITOR_FIXTURE = "dist/modules/comparison-sources-data.json"
MONITOR_STATUS = "dist/modules/comparison-chain-status.json"
OUT_STATUS = "output/comparison-chain-status.json"
HEALTH = "dist/modules/source-import-health.json"
OUT_HEALTH = "output/source-import-health.json"
ADJ_DIST = "dist/assets/adjustment-inputs.json"
ADJ_APP = "app/trade-value-chart/assets/adjustment-inputs.json"
GH_ACTIONS = "dist/modules/github-actions.json"
BASELINE = {FIXTURE: "OLD", MONITOR_FIXTURE: "OLD", MONITOR_STATUS: "OLD-STATUS",
            OUT_STATUS: "OLD-STATUS", HEALTH: "OLD-HEALTH", OUT_HEALTH: "OLD-HEALTH",
            ADJ_DIST: "OLD-ADJ", ADJ_APP: "OLD-ADJ", GH_ACTIONS: "OLD-GH"}


def step_blocks(text):
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


def find_step(text, name):
    for block in step_blocks(text):
        if re.search(rf"^\s*(- )?name:\s*{re.escape(name)}\s*$", block, re.M):
            return block
    return None


def script_of(block):
    """The step's `run: |` block, dedented."""
    lines = block.splitlines()
    for i, line in enumerate(lines):
        m = re.match(r"^(\s+)run:\s*\|\s*$", line)
        if m:
            indent = len(m.group(1)) + 2
            body = []
            for nxt in lines[i + 1:]:
                if nxt.strip() and len(nxt) - len(nxt.lstrip()) < indent:
                    break
                body.append(nxt[indent:] if len(nxt) >= indent else "")
            return "\n".join(body).rstrip() + "\n"
    return None


def git(cwd, *args):
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True,
                          text=True).stdout.strip()


def write(root, rel, content):
    p = Path(root) / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content)


def run_script(text, step_name, cwd, env_extra=None):
    block = find_step(text, step_name)
    assert block is not None, f"step {step_name!r} missing"
    script = script_of(block)
    assert script, f"step {step_name!r} has no run block"
    env = {"PATH": "/usr/bin:/bin:/usr/local/bin", "HOME": str(cwd), **(env_extra or {})}
    return subprocess.run(["bash", "-e", "-c", script], cwd=cwd, env=env,
                          capture_output=True, text=True)


def run_scenario(text, outcome):
    """Simulate one workflow run after the chain step, with the real scripts.

    Returns what ended up on the remote and the exit code of the fail step.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel, content in BASELINE.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")

        results = {}
        if outcome == "failure":
            # What a held chain leaves behind: a PARTIAL fixture, and a red status.
            write(work, FIXTURE, "PARTIAL")
            write(work, OUT_STATUS, "RED")
            steps = [PUBLISH_RED, COMMIT, FAIL]
        else:
            write(work, FIXTURE, "NEW")
            write(work, OUT_STATUS, "GREEN")
            write(work, ADJ_APP, "NEW-ADJ")
            steps = [SYNC_OK, COMMIT]
        for step in steps:
            if find_step(text, step) is None:
                results[step] = None
                continue
            r = run_script(text, step, work, {"CHAIN_OUTCOME": outcome})
            results[step] = r
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        changed = set(git(verify, "diff", "--name-only", base, "HEAD").splitlines())

        def remote_file(rel):
            p = verify / rel
            return p.read_text(encoding="utf-8") if p.exists() else None
        return {
            "changed": changed,
            "fixture": remote_file(FIXTURE),
            "monitor_fixture": remote_file(MONITOR_FIXTURE),
            "monitor_status": remote_file(MONITOR_STATUS),
            "fail_rc": None if results.get(FAIL) is None else results[FAIL].returncode,
            "commit_rc": None if results.get(COMMIT) is None else results[COMMIT].returncode,
        }


def static_problems(text):
    problems = []
    chain = find_step(text, CHAIN)
    if chain is None:
        return ["chain step missing"]
    if "id: chain" not in chain:
        problems.append("chain step must have id: chain")
    if "continue-on-error: true" not in chain:
        problems.append("chain step must continue-on-error so the status can be published")
    for name, cond in ((SYNC_OK, "steps.chain.outcome == 'success'"),
                       (PUBLISH_RED, "steps.chain.outcome == 'failure'"),
                       (FAIL, "steps.chain.outcome == 'failure'")):
        block = find_step(text, name)
        if block is None:
            problems.append(f"step {name!r} missing")
        elif f"if: {cond}" not in block:
            problems.append(f"step {name!r} must run only when {cond}")
    commit = find_step(text, COMMIT)
    if commit is None:
        problems.append(f"step {COMMIT!r} missing")
    elif "if: always()" not in commit:
        problems.append(
            f"step {COMMIT!r} must publish even when an earlier step failed "
            "(if: always()) -- otherwise a failed import-health check strands "
            "the refreshed workflow-health file in the runner")
    order = [text.find(f"name: {n}") for n in (CHAIN, SYNC_OK, PUBLISH_RED, COMMIT, FAIL)]
    if order != sorted(order) or -1 in order:
        problems.append("steps are not in the order chain, sync, publish, commit, fail")
    return problems


def behaviour_problems(text):
    problems = []
    red = run_scenario(text, "failure")
    if FIXTURE in red["changed"] or red["fixture"] != "OLD":
        problems.append("a failed chain pushed the partial fixture")
    for rel in (ADJ_DIST, ADJ_APP, MONITOR_FIXTURE):
        if rel in red["changed"]:
            problems.append(f"a failed chain pushed {rel}")
    if red["monitor_status"] != "RED":
        problems.append("a failed chain did not publish its status to the monitor")
    if red["fail_rc"] in (None, 0):
        problems.append("the job does not fail after a failed chain")
    green = run_scenario(text, "success")
    if green["fixture"] != "NEW" or green["monitor_fixture"] != "NEW":
        problems.append("a green chain did not push the rebuilt fixture and its monitor copy")
    if green["monitor_status"] != "GREEN":
        problems.append("a green chain did not publish its status")
    return problems


def health_failure_problems(text):
    """Simulate the job state when the import-health step fails the run.

    Regression (2026-10-06 overnight QA): the "Run import health check" step
    fails the job before the chain runs. The Refresh step carries
    `if: always()` so it still rewrote dist/modules/github-actions.json, and
    verify_import_health wrote its red artifact to output/ before exiting 1.
    The chain step is skipped (outcome "skipped"). The commit step must still
    run and publish the refreshed workflow-health file plus the red health
    artifact -- without it the monitor's workflow-health card goes stale
    while the gate is red (observed: false failing-streak badge on the
    health-artifacts workflow, served bytes older than main). The fixture
    must NOT be pushed.
    """
    problems = []
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel, content in BASELINE.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")
        # Post-health-failure on-disk state: refreshed workflow-health file,
        # red health artifact in output/. The chain never ran.
        write(work, GH_ACTIONS, "NEW-GH")
        write(work, OUT_HEALTH, "RED-HEALTH")
        # GitHub sets GITHUB_OUTPUT for every step; the commit script writes
        # its pushed= flag there (an unset GITHUB_OUTPUT would fail the
        # `>>` redirect under bash -e, a harness artifact, not a workflow bug).
        r = run_script(text, COMMIT, work,
                       {"CHAIN_OUTCOME": "skipped",
                        "GITHUB_OUTPUT": str(work / "gh_out.txt")})
        if r.returncode != 0:
            problems.append("commit step failed after a failed health check")
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        gh = verify / GH_ACTIONS
        if not gh.exists() or gh.read_text(encoding="utf-8") != "NEW-GH":
            problems.append("a failed health check did not publish the refreshed workflow-health file")
        oh = verify / OUT_HEALTH
        if not oh.exists() or oh.read_text(encoding="utf-8") != "RED-HEALTH":
            problems.append("a failed health check did not publish the red health artifact")
        if (verify / FIXTURE).read_text(encoding="utf-8") != "OLD":
            problems.append("a failed health check pushed the fixture")
    return problems


def refresh_fallback_problems(text):
    """The Refresh step's `||` fallback must restore the last committed
    workflow-health artifact, never write an empty one.

    Regression (2026-10-06 overnight QA): the 11:00 UTC chain run hit the
    GitHub API 403 rate limit, the old fallback wrote workflows: [] +
    'refresh failed', and the Commit step (if: always()) pushed it to main.
    From then on every Pages deploy failed `make validate` at
    tests.test_published_surfaces ('github-actions: workflows=0 < 1'),
    blocking all production updates until the artifact was repaired. A
    failed refresh must leave the stale-but-valid artifact in place so the
    deploy gate stays green.
    """
    problems = []
    block = find_step(text, REFRESH)
    if block is None:
        return ["refresh step missing"]
    # Check the executable script only: the explanatory comment above the
    # run block legitimately names the old failure mode.
    script = "\n".join(
        ln for ln in script_of(block).splitlines()
        if not ln.strip().startswith("#"))
    # The broken fallback wrote an empty workflow-health artifact
    # (workflows: [] + 'refresh failed'). Match the artifact payload, not
    # the bare words, so a warning echo in the new fallback does not trip.
    if "'workflows': []" in script or '"workflows": []' in script:
        problems.append(
            "the Refresh step fallback writes an empty workflow-health artifact "
            "('refresh failed'): a failed refresh must restore the last committed "
            "artifact so the deploy gate stays green")
    if "git checkout --" not in script:
        problems.append(
            "the Refresh step does not restore the last committed workflow-health "
            "artifact when the refresh fails")
    return problems


def failed_refresh_preserves_artifact(text):
    """Simulate a 403 rate-limit refresh failure: the builder script exits
    nonzero; after the Refresh step runs, the committed artifact must still
    hold its old valid bytes (byte-identical), not an empty error-flagged
    payload."""
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        old = '{"generated_at": "X", "workflows": ["w1"], "summary": {"total_workflows": 1}}'
        write(work, GH_ACTIONS, old)
        # A rate-limited builder: fails before writing anything.
        write(work, "pipelines/build_github_actions_status.py",
              "#!/usr/bin/env python3\nimport sys\nsys.exit(1)\n")
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        r = run_script(text, REFRESH, work)
        return {"rc": r.returncode, "artifact": (work / GH_ACTIONS).read_text(encoding="utf-8")}


HEALTH_STEP = "Run import health check"


def red_health_step(text):
    """Run the real health step with a stub checker that writes a RED artifact
    and exits 1 (what verify_import_health.py does on a red gate). output/ is
    gitignored, so the step itself must copy the artifact into dist/modules/
    for the commit step to publish it; the step must still fail."""
    with tempfile.TemporaryDirectory() as td:
        work = Path(td)
        write(work, HEALTH, "OLD-HEALTH")
        write(work, "pipelines/verify_import_health.py",
              "import pathlib, sys\n"
              "p = pathlib.Path('output/source-import-health.json')\n"
              "p.parent.mkdir(parents=True, exist_ok=True)\n"
              "p.write_text('RED-HEALTH')\n"
              "sys.exit(1)\n")
        script_text = text.replace("${{ steps.week.outputs.nfl_week }}", "5")
        r = run_script(script_text, HEALTH_STEP, work)
        return {"rc": r.returncode, "monitor": (work / HEALTH).read_text(encoding="utf-8")}


PIN_FAILURE_LOG = (
    "FAIL: test_known_full_ppr_12_team_source_values "
    "(tests.test_static_export.StaticExportTest.test_known_full_ppr_12_team_source_values)\n"
    "AssertionError: 25.5 != 25.3 : pinned value for "
    "('fantasycalc_adjusted', 'full_12_qb1') (josh allen)\n"
    "make: *** [test-unit] Error 1\n")


def run_post_rebuild_scenario(text, validate_ok):
    """GAP-MAIN-STATIC-PIN: run the REAL chain step with a stub chain that
    rebuilds the fixture (NEW) and a stub `make validate` that fails the way
    main did on 2026-10-07 (or passes), then the real downstream steps the
    workflow would run for that outcome. Returns what reached the remote.
    """
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        remote, work = td / "remote.git", td / "work"
        git(td, "init", "-q", "--bare", "-b", "main", str(remote))
        git(td, "clone", "-q", str(remote), str(work))
        git(work, "checkout", "-q", "-b", "main")
        for rel, content in BASELINE.items():
            write(work, rel, content)
        git(work, "add", "-A")
        git(work, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-qm", "baseline")
        git(work, "push", "-q", "-u", "origin", "main")
        base = git(work, "rev-parse", "HEAD")
        # Stubs: the chain promotes a NEW fixture and writes a green status;
        # validate replays the 0b0ddee failure (or passes). The recorder is
        # the real script.
        write(work, "pipelines/rebuild_comparison_chain.py",
              "import json, pathlib\n"
              f"pathlib.Path({FIXTURE!r}).write_text('NEW')\n"
              f"pathlib.Path({OUT_STATUS!r}).write_text(json.dumps({{'success': True, 'failed': []}}))\n")
        write(work, "validate.out", PIN_FAILURE_LOG if not validate_ok else "OK\n")
        write(work, "Makefile", "validate:\n\t@cat validate.out; exit %d\n" % (0 if validate_ok else 1))
        recorder = ROOT / "pipelines/record_post_rebuild_validation.py"
        write(work, "pipelines/record_post_rebuild_validation.py", recorder.read_text(encoding="utf-8"))
        env = {"PATH": f"{os.path.dirname(sys.executable)}:/usr/bin:/bin:/usr/local/bin",
               "GITHUB_OUTPUT": str(td / "gh_out.txt")}
        chain_text = text.replace("${{ steps.week.outputs.nfl_week }}", "5")
        chain = run_script(chain_text, CHAIN, work, env)
        outcome = "success" if chain.returncode == 0 else "failure"
        steps = [SYNC_OK, COMMIT] if outcome == "success" else [PUBLISH_RED, COMMIT, FAIL]
        rcs = {}
        for step in steps:
            rcs[step] = run_script(text, step, work, {**env, "CHAIN_OUTCOME": outcome}).returncode
        verify = td / "verify"
        git(td, "clone", "-q", str(remote), str(verify))
        changed = set(git(verify, "diff", "--name-only", base, "HEAD").splitlines())
        status_path = verify / MONITOR_STATUS
        return {"outcome": outcome, "changed": changed,
                "fixture": (verify / FIXTURE).read_text(encoding="utf-8"),
                "monitor_status": status_path.read_text(encoding="utf-8") if status_path.exists() else None,
                "fail_rc": rcs.get(FAIL), "chain_log": chain.stdout + chain.stderr}


def post_rebuild_validation_problems(text):
    problems = []
    red = run_post_rebuild_scenario(text, validate_ok=False)
    if red["outcome"] != "failure":
        problems.append("a red post-rebuild validate did not fail the chain step")
    if FIXTURE in red["changed"] or red["fixture"] != "OLD" or MONITOR_FIXTURE in red["changed"]:
        problems.append("a fixture that fails make validate was pushed")
    try:
        status = json.loads(red["monitor_status"] or "")
    except json.JSONDecodeError:
        status = {}
    if status.get("success") is not False or "post_rebuild_validation" not in (status.get("failed") or []):
        problems.append("the chain status was not published as failed after a red validate")
    elif "fantasycalc_adjusted" not in json.dumps(status.get("post_rebuild_validation")):
        problems.append("the published failure does not name the failing pin")
    if red["fail_rc"] in (None, 0):
        problems.append("the job does not fail after a red post-rebuild validate")
    green = run_post_rebuild_scenario(text, validate_ok=True)
    if green["outcome"] != "success" or green["fixture"] != "NEW":
        problems.append("a fixture that passes make validate was not pushed")
    return problems


class RebuildChainWorkflowTest(unittest.TestCase):
    def assertCaught(self, mutated, fragment):
        self.assertNotEqual(WORKFLOW, mutated, "mutation did not change the workflow")
        problems = static_problems(mutated) + (
            [] if static_problems(mutated) else behaviour_problems(mutated))
        self.assertTrue(any(fragment in p for p in problems),
                        msg=f"expected a problem containing {fragment!r}, got {problems}")

    def test_real_workflow_is_clean(self):
        self.assertEqual([], static_problems(WORKFLOW))
        self.assertEqual([], behaviour_problems(WORKFLOW))
        self.assertEqual([], health_failure_problems(WORKFLOW))
        self.assertEqual([], refresh_fallback_problems(WORKFLOW))
        sim = failed_refresh_preserves_artifact(WORKFLOW)
        self.assertEqual(0, sim["rc"])
        self.assertIn('"total_workflows": 1', sim["artifact"])

    def test_empty_refresh_fallback_is_caught(self):
        # Reintroduce the 2026-10-06 deploy blocker: on refresh failure the
        # fallback writes the empty error-flagged artifact instead of
        # restoring the committed one.
        mutated = WORKFLOW.replace(
            '|| { echo "WARNING: GitHub Actions status refresh failed (likely API rate limit); keeping the last committed artifact." >&2; git checkout -- dist/modules/github-actions.json; }',
            '|| python3 -c "import json; json.dump({\'workflows\': [], \'error\': \'refresh failed\'}, '
            'open(\'dist/modules/github-actions.json\',\'w\'))"', 1)
        self.assertNotEqual(WORKFLOW, mutated, "mutation did not change the workflow")
        problems = refresh_fallback_problems(mutated)
        self.assertTrue(any("must restore the last committed" in p for p in problems),
                        msg=f"expected a restore-the-artifact problem, got {problems}")
        sim = failed_refresh_preserves_artifact(mutated)
        self.assertNotIn('"total_workflows": 1', sim["artifact"],
                         "sim should catch the empty artifact replacing the valid one")

    def test_red_chain_pushes_only_status_and_health_files(self):
        red = run_scenario(WORKFLOW, "failure")
        self.assertEqual({MONITOR_STATUS, OUT_STATUS}, red["changed"])
        self.assertEqual("OLD", red["fixture"])
        self.assertNotEqual(0, red["fail_rc"])

    def test_green_chain_pushes_fixture_and_monitor_copy(self):
        green = run_scenario(WORKFLOW, "success")
        for rel in (FIXTURE, MONITOR_FIXTURE, MONITOR_STATUS, OUT_STATUS, ADJ_APP):
            self.assertIn(rel, green["changed"])

    def test_staging_the_fixture_on_failure_is_caught(self):
        mutated = WORKFLOW.replace(
            "            git add dist/modules/source-import-health.json \\\n",
            "            git add data/fixtures/current/comparison-sources-data.json \\\n"
            "                    dist/modules/source-import-health.json \\\n", 1)
        self.assertCaught(mutated, "partial fixture")

    def test_not_publishing_status_on_failure_is_caught(self):
        mutated = WORKFLOW.replace(
            "          cp output/comparison-chain-status.json dist/modules/comparison-chain-status.json 2>/dev/null \\\n"
            "            || echo \"No chain status was written; nothing to publish.\"\n",
            "          echo skipped\n", 1)
        self.assertCaught(mutated, "did not publish its status")

    def test_losing_continue_on_error_is_caught(self):
        # Target the chain step itself: other steps (the ESPN anchor bake)
        # carry continue-on-error too, so a bare first-match replace would
        # mutate the wrong step.
        chain = find_step(WORKFLOW, CHAIN)
        mutated = WORKFLOW.replace(
            chain, chain.replace("        continue-on-error: true\n", "", 1), 1)
        self.assertNotEqual(mutated, WORKFLOW)
        self.assertCaught(mutated, "continue-on-error")

    def test_a_job_that_stays_green_after_a_failed_chain_is_caught(self):
        mutated = WORKFLOW.replace("          exit 1\n", "          exit 0\n")
        self.assertCaught(mutated, "does not fail")

    def test_dropping_the_fail_step_condition_is_caught(self):
        mutated = WORKFLOW.replace(
            "        if: steps.chain.outcome == 'failure'\n        run: |\n          echo \"Comparison chain failed",
            "        run: |\n          echo \"Comparison chain failed", 1)
        self.assertCaught(mutated, "must run only when")

    def test_green_path_not_syncing_the_monitor_copy_is_caught(self):
        mutated = WORKFLOW.replace(
            "          cp data/fixtures/current/comparison-sources-data.json dist/modules/comparison-sources-data.json\n",
            "", 1)
        self.assertCaught(mutated, "did not push the rebuilt fixture")

    def test_dropping_commit_always_after_failed_health_check_is_caught(self):
        # Without `if: always()` the Commit step is skipped when the
        # import-health step fails the job: the refreshed workflow-health
        # file never reaches the monitor. This is the exact 2026-10-06
        # failure mode (stale card, false failing-streak badge).
        mutated = WORKFLOW.replace(
            "        if: always()\n        env:\n          CHAIN_OUTCOME: ${{ steps.chain.outcome }}",
            "        env:\n          CHAIN_OUTCOME: ${{ steps.chain.outcome }}", 1)
        self.assertCaught(mutated, "must publish even when an earlier step failed")

    def test_red_health_reaches_the_monitor_copy(self):
        r = red_health_step(WORKFLOW)
        # Go-live (2026-10-07): a red import-health gate warns; it no longer
        # stops the rebuild.
        self.assertEqual(0, r["rc"], "a red import-health gate must not stop the rebuild")
        self.assertEqual("RED-HEALTH", r["monitor"],
                         "red health must be copied to dist/modules (output/ is gitignored)")

    def test_copy_only_on_green_is_caught(self):
        # The pre-2026-10-06 step: `cp` after the checker, so bash -e skips it on RED.
        mutated = WORKFLOW.replace(
            "          set +e\n"
            "          python3 pipelines/verify_import_health.py --nfl-week ${{ steps.week.outputs.nfl_week }}\n"
            "          rc=$?\n"
            "          set -e\n"
            "          cp output/source-import-health.json dist/modules/source-import-health.json \\\n"
            "            || echo \"::warning::verify_import_health wrote no artifact; nothing to publish\"\n",
            "          python3 pipelines/verify_import_health.py --nfl-week ${{ steps.week.outputs.nfl_week }}\n"
            "          cp output/source-import-health.json dist/modules/source-import-health.json\n", 1)
        self.assertNotEqual(WORKFLOW, mutated, "mutation did not change the workflow")
        self.assertEqual("OLD-HEALTH", red_health_step(mutated)["monitor"])

    def test_post_rebuild_validation_blocks_the_push(self):
        self.assertEqual([], post_rebuild_validation_problems(WORKFLOW))
        red = run_post_rebuild_scenario(WORKFLOW, validate_ok=False)
        self.assertEqual({MONITOR_STATUS, OUT_STATUS}, red["changed"])
        self.assertIn("('fantasycalc_adjusted', 'full_12_qb1')", red["monitor_status"])

    def test_dropping_post_rebuild_validation_is_caught(self):
        # The pre-fix chain step (0b0ddee, 2026-10-07): rebuild then publish,
        # with no validate in between.
        start = WORKFLOW.index("          mkdir -p output\n")
        end = WORKFLOW.index("            exit 1\n          fi\n", start) + len("            exit 1\n          fi\n")
        mutated = WORKFLOW[:start] + WORKFLOW[end:]
        self.assertNotEqual(WORKFLOW, mutated)
        problems = post_rebuild_validation_problems(mutated)
        self.assertIn("a fixture that fails make validate was pushed", problems)

    def test_swallowing_the_validate_exit_code_is_caught(self):
        mutated = WORKFLOW.replace(
            '          if [ "$rc" -ne 0 ]; then\n'
            "            python3 pipelines/record_post_rebuild_validation.py --log output/post-rebuild-validate.log\n"
            "            exit 1\n",
            '          if [ "$rc" -ne 0 ]; then\n'
            "            python3 pipelines/record_post_rebuild_validation.py --log output/post-rebuild-validate.log\n", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertIn("a fixture that fails make validate was pushed",
                      post_rebuild_validation_problems(mutated))

    def test_unrecorded_validation_failure_is_caught(self):
        mutated = WORKFLOW.replace(
            "            python3 pipelines/record_post_rebuild_validation.py --log output/post-rebuild-validate.log\n",
            "", 1)
        self.assertNotEqual(WORKFLOW, mutated)
        self.assertIn("the chain status was not published as failed after a red validate",
                      post_rebuild_validation_problems(mutated))


if __name__ == "__main__":
    unittest.main()
