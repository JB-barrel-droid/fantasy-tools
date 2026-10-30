#!/usr/bin/env python3
"""The health-artifacts watch step: exit 3 warns, exit 1 and 2 fail (JEG-1239).

Jeremy, 2026-10-30, JEG-1239: "A". When the watch cannot verify that this run's
artifacts arrived (exit 3, e.g. the served copy answers 403), the run stays green
and is flagged as unverified. Stale (1) and not arrived (2) still turn it red.

The test extracts the step's `run:` script from health-artifacts.yml and runs it
under `bash -e`, as GitHub does, with the watcher replaced by a stub that exits
with a chosen code. Before the fix the step passed the watcher's code straight
through, so exit 3 failed the step.
"""

import os
import re
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "health-artifacts.yml"
WATCHER = "python3 pipelines/health_artifacts_watch.py"


def _watch_run_script():
    """The `run: |` block of the watch step (stdlib only, parsed literally)."""
    lines = WORKFLOW.read_text(encoding="utf-8").splitlines()
    in_step = False
    for i, line in enumerate(lines):
        if re.match(r"^\s*-\s+name:\s*Watch served artifacts", line):
            in_step = True
            continue
        if not in_step:
            continue
        m = re.match(r"^(\s*)run:\s*\|\s*$", line)
        if not m:
            continue
        raw = []
        for nxt in lines[i + 1:]:
            if nxt.strip() and len(nxt) - len(nxt.lstrip()) <= len(m.group(1)):
                break
            raw.append(nxt)
        return textwrap.dedent("\n".join(raw)).strip("\n")
    raise AssertionError("watch step not found in health-artifacts.yml")


def _run(watch_rc):
    script = _watch_run_script()
    if WATCHER not in script:
        raise AssertionError("the watch step no longer calls the watcher as expected")
    with tempfile.TemporaryDirectory() as tmp:
        stub = os.path.join(tmp, "watch_stub.sh")
        Path(stub).write_text(f"#!/bin/sh\necho 'publication_arrival: stub'\nexit {watch_rc}\n")
        os.chmod(stub, 0o755)
        script = script.replace("/tmp/", tmp + "/").replace(WATCHER, stub)
        script = script.replace("${{ steps.build.outcome }}", "success")
        env = dict(os.environ, PUBLISHED="true")
        proc = subprocess.run(["bash", "-e", "-c", script], env=env, capture_output=True, text=True, timeout=60)
        log = Path(tmp, "watch.log").read_text() if Path(tmp, "watch.log").exists() else ""
    return proc.returncode, proc.stdout + proc.stderr, log


class WatchStepExitPolicyTest(unittest.TestCase):
    def test_unverified_warns_and_stays_green(self):
        rc, out, log = _run(3)
        self.assertEqual(rc, 0, out)
        self.assertIn("::warning", out)
        self.assertIn("unverified", out)
        self.assertIn("publication_arrival: stub", log, "the watch log must still be written for the summary")

    def test_stale_still_fails(self):
        rc, out, _ = _run(1)
        self.assertEqual(rc, 1, out)
        self.assertNotIn("::warning", out)

    def test_not_arrived_still_fails(self):
        rc, out, _ = _run(2)
        self.assertEqual(rc, 2, out)
        self.assertNotIn("::warning", out)

    def test_fresh_and_arrived_is_green(self):
        rc, out, _ = _run(0)
        self.assertEqual(rc, 0, out)
        self.assertNotIn("::warning", out)


if __name__ == "__main__":
    unittest.main()
