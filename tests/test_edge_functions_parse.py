"""Edge function sources must parse. A bad merge once left literal `\\n\\1` in get-values (JEG-1031 + JEG-1037)."""
import re
import shutil
import subprocess
import unittest
from pathlib import Path

FUNCTIONS = Path(__file__).resolve().parent.parent / "supabase" / "functions"
ARTIFACT = re.compile(r"\\n\\\d|^\\\d", re.M)


class EdgeFunctionParseTests(unittest.TestCase):
    def test_no_regex_backreference_artifacts(self):
        for path in FUNCTIONS.rglob("*.ts"):
            self.assertIsNone(ARTIFACT.search(path.read_text()), f"{path} has a stray \\n\\1 / \\1 artifact")

    @unittest.skipIf(shutil.which("deno") is None, "deno not installed")
    def test_entrypoints_parse(self):
        for entry in ("get-values/index.ts", "mcp/index.ts"):
            out = subprocess.run(["deno", "cache", "--no-check", str(FUNCTIONS / entry)],
                                 capture_output=True, text=True, timeout=120)
            self.assertEqual(out.returncode, 0, entry + "\n" + out.stderr)


if __name__ == "__main__":
    unittest.main()
