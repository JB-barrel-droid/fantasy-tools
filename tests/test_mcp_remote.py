"""JEG-1012: the remote MCP endpoint's dispatch and tool logic (node, no network)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class RemoteMcpTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_dispatch_and_tools(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/mcp_remote_check.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_explicit_superflex_link(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/mcp_superflex_link_check.mjs")],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_connector_fit_label(self):
        # JEG-1115: the connector's fit label matches the finder's own rule (parity on the
        # 20-team fixture), every returned trade carries fit + fit_reason, and the check
        # fails when the label is stubbed out of find-trades.ts.
        out = subprocess.run(
            ["node", str(ROOT / "tests/node/connector_fit_check.mjs")],
            capture_output=True, text=True, timeout=180,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_batch_trade_discovery(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/batch_trade_check.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertIn("All batch trade tests passed", out.stdout)

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_connector_both_sides_and_league_link(self):
        # JEG-1329: every trade row carries both teams' side of the finder's tradeFit, and the
        # league scan's site link opens the league finder with every team (workspace.js decodeShare).
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/connector_both_sides_check.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_function_is_public_like_get_values(self):
        cfg = (ROOT / "supabase/config.toml").read_text()
        self.assertIn("[functions.mcp]\nverify_jwt = false", cfg)


if __name__ == "__main__":
    unittest.main()
