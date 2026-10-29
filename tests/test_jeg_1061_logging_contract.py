"""JEG-1258 (part of JEG-1061): get-values logging contract, offline (node, no network, no credentials).

The harness is tests/node/jeg_1061_logging_contract.mjs; the spec, the recorded before-hook failures and
the hook proposal are in tests/fixtures/jeg_1061_logging/. Until the get-values owner adds the logging
hook, the contract is held in strict expected-failure mode: the run passes only while the violations
are exactly the recorded list and every status (the 11th-compute and 31st-request 429s included) is
unchanged. When the hook lands, set expected_failures_before_hook.json to [] and the same test then
requires a full pass.
"""
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "tests/node/jeg_1061_logging_contract.mjs"
EXPECTED = ROOT / "tests/fixtures/jeg_1061_logging/expected_failures_before_hook.json"


def _run(*args):
    return subprocess.run(
        ["node", "--experimental-strip-types", "--no-warnings", str(HARNESS), *args],
        capture_output=True, text=True, timeout=300, cwd=str(ROOT),
    )


@unittest.skipIf(shutil.which("node") is None, "node not installed")
class Jeg1061LoggingContractTests(unittest.TestCase):
    def test_checker_catches_missing_and_misclassified_events(self):
        out = _run("--self-test")
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))

    def test_handler_matches_recorded_contract_state(self):
        from tests import _render_env
        _render_env.ensure_built()
        out = _run(str(ROOT / "dist"), "--expect-failures", str(EXPECTED))
        self.assertEqual(out.returncode, 0, out.stdout + out.stderr)
        self.assertTrue(out.stdout.strip().endswith("ok"))


if __name__ == "__main__":
    unittest.main()
