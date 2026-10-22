"""`make test-unit` runs every module even when one fails (2026-10-08).

Preview CI's full suite stopped at a playwright timeout in
tests.test_espn_zero_badge_render, so test_rebuild_chain_workflow,
test_rebuild_chain_conflict_handoff and every module after them never ran on
Linux. test-unit now runs its module list through tests/run_suite.py, which
keeps going past a failing line and fails at the end listing it.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "run_suite.py"
PY = 'python3 -c "import sys; sys.exit({rc})"'


def run_runner(makefile_text: str, target: str):
    with tempfile.TemporaryDirectory() as tmp:
        makefile = Path(tmp) / "Makefile"
        makefile.write_text(makefile_text, encoding="utf-8")
        proc = subprocess.run([sys.executable, str(RUNNER), "--makefile", str(makefile), target],
                              capture_output=True, text=True, timeout=120)
        return proc, (Path(tmp) / "marker").exists()


class RunSuiteTest(unittest.TestCase):
    def test_continues_past_a_failing_line_and_fails_at_the_end(self):
        text = ("other:\n\tpython3 -c \"raise SystemExit(3)\"\n\n"
                "suite:\n\t# a comment line is not a command\n"
                f"\t{PY.format(rc=1)}\n"
                "\tpython3 -c \"open('marker', 'w').write('ran')\"\n"
                "\nafter:\n\tpython3 -c \"raise SystemExit(4)\"\n")
        proc, marker = run_runner(text, "suite")
        self.assertTrue(marker, "the line after the failing one did not run")
        self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
        self.assertIn("1/2 passed", proc.stdout)
        self.assertIn(f"failed: {PY.format(rc=1)}", proc.stdout)

    def test_all_pass_exits_zero(self):
        proc, _ = run_runner(f"suite:\n\t{PY.format(rc=0)}\n\t@{PY.format(rc=0)}\n", "suite")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertIn("2/2 passed", proc.stdout)

    def test_expands_make_variables_before_running(self):
        text = ("OUT = marker\nLATE = $(shell echo late)\n\nsuite:\n"
                "\tpython3 -c \"open('$(OUT)', 'w').write('$(LATE)')\"\n")
        proc, marker = run_runner(text, "suite")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertTrue(marker, "the $(OUT) line was not expanded and run")
        self.assertIn("1/1 passed", proc.stdout)

    def test_real_makefile_test_unit_modules_expands_node_chromium(self):
        sys.path.insert(0, str(RUNNER.parent))
        try:
            import run_suite
        finally:
            sys.path.remove(str(RUNNER.parent))
        env_path = "/opt/fake-chromium"
        old = os.environ.get("CHROMIUM_PATH")
        os.environ["CHROMIUM_PATH"] = env_path
        try:
            modules = run_suite.recipe_lines(ROOT / "Makefile", "test-unit-modules")
        finally:
            if old is None:
                del os.environ["CHROMIUM_PATH"]
            else:
                os.environ["CHROMIUM_PATH"] = old
        node = [m for m in modules if "freshness-hero.mjs" in m]
        self.assertEqual(node, [f'CHROMIUM_PATH="{env_path}" node tests/rendered_gate/freshness-hero.mjs dist'])
        self.assertFalse([m for m in modules if "$(" in m])

    def test_make_test_unit_uses_the_runner_over_the_full_module_list(self):
        sys.path.insert(0, str(RUNNER.parent))
        try:
            import run_suite
        finally:
            sys.path.remove(str(RUNNER.parent))
        self.assertEqual(run_suite.recipe_lines(ROOT / "Makefile", "test-unit"),
                         ["python3 tests/run_suite.py test-unit-modules"])
        modules = run_suite.recipe_lines(ROOT / "Makefile", "test-unit-modules")
        for module in ("tests.test_espn_zero_badge_render", "tests.test_rebuild_chain_workflow",
                       "tests.test_rebuild_chain_conflict_handoff", "tests.test_run_suite"):
            self.assertIn(f"python3 -m unittest {module}", modules)
        self.assertGreater(len(modules), 100)


if __name__ == "__main__":
    unittest.main()
