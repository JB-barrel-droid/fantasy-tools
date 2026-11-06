"""Pure board swap adapter: native Node cases, existing frozen waiver fixtures."""
import shutil
import subprocess
import unittest
from pathlib import Path


class WaiverBoardSwapsTests(unittest.TestCase):
    def test_node_contract_and_parity(self):
        self.assertIsNotNone(shutil.which("node"), "node is required for Waivers parity")
        root = Path(__file__).resolve().parents[1]
        result = subprocess.run(
            ["node", "--test", "tests/waiver_board_swaps.test.cjs"], cwd=root,
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
