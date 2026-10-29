"""session:cma is retired (JEG-1173, JEG-1269). Static checks only: no script
here is executed. Every managed-agents script must hit the retired exit guard
in lib.sh before it can reach `ant` or Keychain, and the README must not treat
a missing run comment as proof the deployments are paused."""
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
MA = ROOT / "managed-agents"
SCRIPTS = MA / "scripts"
SOURCE_LIB = 'source "$(dirname "$0")/lib.sh"'


def code_lines(path):
    return [ln for ln in path.read_text().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]


class ManagedAgentsRetiredTests(unittest.TestCase):
    def test_lib_guard_exits_before_any_helper(self):
        lines = code_lines(SCRIPTS / "lib.sh")
        guard = next((i for i, ln in enumerate(lines) if "CMA_ALLOW_RETIRED" in ln), None)
        self.assertIsNotNone(guard, "lib.sh has no retired exit guard")
        self.assertIn("exit 1", "\n".join(lines[guard:guard + 4]))
        first_fn = next(i for i, ln in enumerate(lines) if re.match(r"^\w+\(\)\s*\{", ln))
        self.assertLess(guard, first_fn)

    def test_every_script_sources_lib_before_reaching_out(self):
        scripts = sorted(p for p in SCRIPTS.glob("*.sh") if p.name != "lib.sh")
        self.assertTrue(scripts)
        for path in scripts:
            with self.subTest(script=path.name):
                lines = code_lines(path)
                # Sourcing lib.sh is the first command, so its guard runs before ant or Keychain.
                self.assertEqual(lines[0], SOURCE_LIB)

    def test_readme_states_receipt_and_silence_corroboration_only(self):
        text = (MA / "README.md").read_text()
        self.assertIn("Operational state:", text)
        self.assertIn("corroboration only", text)
        for dep in ("depl_0194kATtQ6xdicZiw7wnkzmT", "depl_01PE9v6akCH9muDEUwxdioSs"):
            self.assertIn(dep, text)
        self.assertNotIn("Proof of stop", text)


if __name__ == "__main__":
    unittest.main()
