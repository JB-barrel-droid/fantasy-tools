"""JEG-1225 (slice 4b): get-values prices under a share link's value basis and player overrides.

tests/node/get_values_value_context_check.mjs runs the deployed handler (index.ts) on the built dist/ with the
site's link reader and compares it with the parity runner, checks errors, the cache key, the site writer to
get-values round trip, and that the basis reaches the engine in the site engine's own form (curve-widget.js
canonicalBasis). Page parity is tests/test_endpoint_parity.py test_value_context_parity (needs Chromium)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NODE = ["node", "--experimental-strip-types", "--no-warnings"]


class GetValuesValueContextTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_handler_prices_the_value_context(self):
        if not (ROOT / "dist" / "index.html").exists():
            self.skipTest("dist/ not built")
        out = subprocess.run(NODE + [str(ROOT / "tests/node/get_values_value_context_check.mjs"), str(ROOT / "dist")],
                             capture_output=True, text=True, timeout=600, cwd=ROOT)
        self.assertEqual(out.returncode, 0, out.stdout[-4000:] + out.stderr[-4000:])
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
