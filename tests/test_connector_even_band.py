"""JEG-1412: default connector verdict and guidance agree with the site's even band."""
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ConnectorEvenBandTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_compare_and_guidance_match_site(self):
        result = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/connector_even_band_check.mjs")],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertTrue(result.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_guard_rejects_premature_sum_rounding(self):
        """The boundary sentinels must distinguish classification from display rounding."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(ROOT / "supabase/functions/mcp", root / "supabase/functions/mcp")
            for path in ("app/v2/trade.js", "tests/node/connector_even_band_check.mjs",
                         "tests/fixtures/connector_even_band.json"):
                target = root / path
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(ROOT / path, target)
            tools = root / "supabase/functions/mcp/tools.ts"
            source = tools.read_text()
            original = "const sum = (rows: PlayerValue[]) => rows.reduce((t, p) => t + p.value, 0);"
            self.assertIn(original, source)
            tools.write_text(source.replace(original,
                "const sum = (rows: PlayerValue[]) => round1(rows.reduce((t, p) => t + p.value, 0));", 1))
            result = subprocess.run(
                ["node", "--experimental-strip-types", "--no-warnings",
                 str(root / "tests/node/connector_even_band_check.mjs")],
                capture_output=True, text=True, timeout=30,
            )
            self.assertNotEqual(result.returncode, 0, "premature rounding escaped the regression")
            self.assertIn("outside before sum rounding, inside after", result.stderr)


if __name__ == "__main__":
    unittest.main()
