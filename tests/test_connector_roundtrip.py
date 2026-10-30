"""JEG-1030: state -> connector tool -> get-values -> site link round trips (node, no network).

Input and state round-trip coverage (what each tool prices and what its link opens), not pricing
parity: the page side of parity is tests/test_endpoint_parity.py.

The checks, the leagues (3-WR / 6-bench, three scorings, shares, bench override, injury history,
confidence, season weeks), the explicit-override cases with their engine inputs written out, and the
deliberately broken variants are in tests/node/connector_roundtrip_check.mjs.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / "tests" / "node" / "connector_roundtrip_check.mjs"


def run(*flags):
    return subprocess.run(["node", "--experimental-strip-types", "--no-warnings", str(CHECK), *flags],
                          capture_output=True, text=True, timeout=120)


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class ConnectorRoundTripTests(unittest.TestCase):
    def test_round_trips(self):
        out = run()
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))
        self.assertRegex(out.stdout, r"round trips: \d+ tools x \d+ leagues, \d+ override cases, 0 failures")

    def test_known_gaps_still_fail_strict(self):
        # Each known gap is a real defect: --strict fails while any remains (the fix's PR removes it).
        out = run("--strict")
        if "0 known gaps" in out.stdout:
            self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        else:
            self.assertEqual(out.returncode, 1, out.stdout + out.stderr)


if __name__ == "__main__":
    unittest.main()
