"""JEG-1225 (slice 4a): the shared value-context link format, app/v2/ddf-value-link.js (node, no network).

The site's Overrides tab, get-values and the MCP function read basis= and ov= through this one module."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DdfValueLinkTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_link_format(self):
        out = subprocess.run(
            ["node", str(ROOT / "tests/node/ddf_value_link_check.cjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_build_publishes_the_module_before_overrides(self):
        # get-values loads <site>/v2/ddf-value-link.js, and overrides.js needs it loaded first on the page.
        build = (ROOT / "pipelines/build_v2_page.py").read_text()
        self.assertIn('"ddf-value-link.js"', build)
        self.assertLess(build.index('v2/ddf-value-link.js" defer'), build.index('v2/overrides.js" defer'))


if __name__ == "__main__":
    unittest.main()
