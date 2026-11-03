"""JEG-1321 isolated adapter: legacy defaults and active guardrails on frozen USO rosters."""
from __future__ import annotations

import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from tests import test_league_levels_real as real
from tests.test_league_levels_trades import league_input

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests/node/jeg1321_league_discovery_options.cjs"


class LeagueDiscoveryOptionsTest(unittest.TestCase):
    def test_shared_options_and_uso_default_parity(self):
        doc = real.load("uso")
        levels = {level: real.run_js(doc, real.level_extra(doc, level))["rows"] for level in ("ddf", "market")}
        inp = league_input(doc, levels, "page")
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "uso-pairings.json"
            fixture.write_text(json.dumps(inp))
            result = subprocess.run(["node", str(RUNNER), str(fixture)], cwd=ROOT,
                                    capture_output=True, text=True, timeout=120, check=False)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn("7 passed, 0 failed", result.stdout)
        self.assertIn("11 opponents", result.stdout)


if __name__ == "__main__":
    unittest.main()
