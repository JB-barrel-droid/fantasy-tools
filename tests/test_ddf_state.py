"""JEG-1025: the DDF state codec shared by the site and the MCP endpoint (node, no network)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class DdfStateTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_codec(self):
        out = subprocess.run(
            ["node", str(ROOT / "tests/node/ddf_state_check.cjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_build_publishes_the_codec(self):
        # The remote MCP function loads <site>/v2/ddf-state.js at cold start (JEG-1027); if the build
        # stops copying it, chat tools silently lose the shared state reader.
        build = (ROOT / "pipelines/build_v2_page.py").read_text()
        self.assertIn('"ddf-state.js"', build)
        self.assertTrue((ROOT / "app/v2/ddf-state.js").exists())


if __name__ == "__main__":
    unittest.main()
