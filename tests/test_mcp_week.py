"""JEG-1179: get-values and the MCP tools price the site's default week, or the week asked for.

* tests/node/get_values_week_check.mjs runs the deployed get-values handler (index.ts) on the built
  dist/: the default week and its missing_sources, an explicit week, the error for a week with no
  published sources, the JEG-1157 gap (the calendar a week ahead of every chart), synthetic week
  transitions (no carry-forward), and values equal to the parity runner's for the same week.
* tests/node/mcp_week_check.mjs checks the MCP side with a stub get-values: every pricing tool takes
  `week`, read_state honours `wk=` from a site link, results carry week / sources_included /
  missing_sources, and get-values' week error reaches the caller.

Page parity for the same week is tests/test_endpoint_parity.py (test_week_parity, needs Chromium).
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ["node", "--experimental-strip-types", "--no-warnings"]


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class WeekTests(unittest.TestCase):
    def test_mcp_tools_week(self):
        out = subprocess.run(NODE + [str(ROOT / "tests/node/mcp_week_check.mjs")],
                             capture_output=True, text=True, timeout=120, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_get_values_week(self):
        from tests import _render_env
        _render_env.ensure_built()
        out = subprocess.run(NODE + [str(ROOT / "tests/node/get_values_week_check.mjs"), str(ROOT / "dist")],
                             capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
