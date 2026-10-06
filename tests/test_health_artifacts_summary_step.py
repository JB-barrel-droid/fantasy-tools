#!/usr/bin/env python3
"""Health-artifacts Summary step must not fail the workflow on its own.

Regression guard (2026-10-06 overnight QA): the Summary step in
.github/workflows/health-artifacts.yml runs under `bash -e` (GitHub's
default `bash -e {0}`). It reads /tmp/build.rc, /tmp/build.log, and
/tmp/watch.log, but /tmp/build.rc only exists when the producer step
recorded an error. A bare `cat` on the missing file exits 1, and `bash -e`
fails the entire workflow run even though the producer and the watcher
both succeeded -- every scheduled run went red for this reason.

The test extracts the Summary step's `run:` script from the workflow YAML
and executes it under `bash -e` exactly as GitHub would, with the /tmp
scratch files absent. It must exit 0. Against the pre-fix script (bare
`cat`/`tail`), the same harness exits 1 -- verified by running the old
script text through the harness during development.
"""

import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "health-artifacts.yml"


def _summary_run_script():
    """Extract the Summary step's `run:` script from the workflow YAML."""
    doc = yaml.safe_load(WORKFLOW.read_text())
    for step in doc["jobs"]["produce-and-watch"]["steps"]:
        if step.get("name") == "Summary":
            return step["run"]
    raise AssertionError("Summary step not found in health-artifacts.yml")


def _run_summary_script(script, scratch_dir):
    """Run the Summary script under `bash -e` with a clean scratch dir.

    Returns (returncode, summary_text). The script's /tmp/ reads are
    redirected into an empty temp dir so missing files are genuinely
    missing; GITHUB_STEP_SUMMARY points at a temp file.
    """
    script = script.replace("${{ steps.build.outcome }}", "success")
    script = script.replace("/tmp/", scratch_dir + "/")
    summary_file = os.path.join(scratch_dir, "step-summary.md")
    env = dict(os.environ, GITHUB_STEP_SUMMARY=summary_file)
    proc = subprocess.run(
        ["bash", "-e", "-c", script],
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    text = ""
    if os.path.exists(summary_file):
        text = Path(summary_file).read_text()
    return proc.returncode, text, proc.stderr


class TestHealthArtifactsSummaryStep(unittest.TestCase):
    def test_summary_succeeds_when_scratch_files_missing(self):
        """Producer success leaves no /tmp/build.rc; the Summary must still exit 0."""
        scratch = tempfile.mkdtemp(prefix="qa-summary-")
        try:
            script = _summary_run_script()
            rc, text, stderr = _run_summary_script(script, scratch)
            self.assertEqual(
                rc, 0,
                f"Summary step failed with missing scratch files (rc={rc}): {stderr[-500:]}",
            )
            self.assertIn("## Health artifacts", text)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_summary_still_reports_producer_errors(self):
        """The `|| true` guards must not swallow real producer output."""
        scratch = tempfile.mkdtemp(prefix="qa-summary-")
        try:
            Path(scratch, "build.rc").write_text("build_pipeline_checkpoints exit 2\n")
            script = _summary_run_script()
            rc, text, _ = _run_summary_script(script, scratch)
            self.assertEqual(rc, 0)
            self.assertIn("build_pipeline_checkpoints exit 2", text)
        finally:
            shutil.rmtree(scratch, ignore_errors=True)

    def test_file_reads_are_guarded(self):
        """Static backstop: every scratch-file read in the Summary step is guarded."""
        script = _summary_run_script()
        # A read is guarded when its `;`-delimited command segment contains
        # `|| true` (or `|| :`) -- redirections like `2>/dev/null` may sit
        # between the path and the guard.
        unguarded = []
        for segment in script.split(";"):
            if re.search(r"(cat|tail)\b[^;]*?/tmp/\S+", segment):
                if not re.search(r"\|\|\s*(true|:)\b", segment):
                    unguarded.append(segment.strip())
        self.assertEqual(
            unguarded, [],
            f"Unguarded scratch-file reads in Summary step (fail under bash -e): {unguarded}",
        )


if __name__ == "__main__":
    unittest.main()
