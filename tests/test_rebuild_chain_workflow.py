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
import re
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORKFLOW = (ROOT / ".github/workflows/rebuild-chain.yml").read_text()

CHAIN = "Rebuild comparison chain (if fixture stale)"
SYNC_OK = "Sync rebuilt fixture into dist (chain succeeded)"
PUBLISH_RED = "Publish chain status only (chain failed)"
COMMIT = "Commit and push if changed"
FAIL = "Fail the job if the chain failed"

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
            return p.read_text() if p.exists() else None
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
        mutated = WORKFLOW.replace("        continue-on-error: true\n", "", 1)
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


if __name__ == "__main__":
    unittest.main()
