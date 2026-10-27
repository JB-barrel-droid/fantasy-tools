"""JEG-1031: the league -> engine-input mapping used by get-values (node, no network)."""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class LeagueMappingTests(unittest.TestCase):
    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_mapping_and_clamps(self):
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/league_mapping_check.mjs")],
            capture_output=True, text=True, timeout=60,
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_handler_runs_and_matches_runner(self):
        """index.ts itself: parses, wires league through, rate limits (a merge once left `\\n\\1` in it)."""
        from tests import _render_env
        _render_env.ensure_built()
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/get_values_handler_check.mjs"), str(ROOT / "dist")],
            capture_output=True, text=True, timeout=300, cwd=str(ROOT),
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    @unittest.skipIf(shutil.which("node") is None, "node not installed")
    def test_compute_rate_limit_pinned(self):
        """JEG-1061: on one instance, the 11th fresh compute in a minute from one key is a 429."""
        from tests import _render_env
        _render_env.ensure_built()
        out = subprocess.run(
            ["node", "--experimental-strip-types", "--no-warnings",
             str(ROOT / "tests/node/get_values_rate_limit_check.mjs"), str(ROOT / "dist")],
            capture_output=True, text=True, timeout=300, cwd=str(ROOT),
        )
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
