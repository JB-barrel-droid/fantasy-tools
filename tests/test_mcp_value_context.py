"""JEG-1343 (JEG-1225 slice 4c): the MCP tools honor a pasted link's own value basis and player overrides.

tests/node/mcp_value_context_check.mjs runs the tools against a stub get-values (the link's text is sent, the
answer names the basis and overrides, the link back keeps valuecontext=, basis= and ov=, refusals give no
numbers) and against the real get-values handler on the built dist/ (an override prices at its value)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ["node", "--experimental-strip-types", "--no-warnings"]


class McpValueContextTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_tools_price_the_links_value_context(self):
        if not (ROOT / "dist" / "index.html").exists():
            self.skipTest("dist/ not built")
        out = subprocess.run(NODE + [str(ROOT / "tests/node/mcp_value_context_check.mjs"), str(ROOT / "dist")],
                             capture_output=True, text=True, timeout=600, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout[-4000:] + out.stderr[-4000:])
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
