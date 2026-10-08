r"""Node harnesses must run when started directly, on every OS.

The rendered-gate harnesses compared import.meta.url with "file://" + argv[1]
to decide whether to run. On Windows argv[1] is C:\...\gate.mjs, so the check
never matched and every harness exited 0 without running a single assertion: a
silent pass. They now share tests/rendered_gate/is_main.mjs.

test_is_main_true_for_started_script runs a script from a temp dir (C:\ on
Windows, /tmp on Linux) and needs isMain to recognise it. The static test fails
if any .mjs goes back to the string-built file:// comparison.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IS_MAIN = ROOT / "tests" / "rendered_gate" / "is_main.mjs"
STRING_BUILT_GUARD = re.compile(r"file://\$\{process\.argv\[1\]\}")


def harness_files():
    return [p for d in ("tests", "tools") for p in (ROOT / d).rglob("*.mjs")
            if "node_modules" not in p.parts]


class HarnessMainGuardTests(unittest.TestCase):
    def test_no_string_built_main_check(self):
        offenders = [str(p.relative_to(ROOT)) for p in harness_files()
                     if STRING_BUILT_GUARD.search(p.read_text(encoding="utf-8"))]
        self.assertEqual(offenders, [], "use isMain() from tests/rendered_gate/is_main.mjs")

    def test_is_main_true_for_started_script(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not installed")
        script_body = (
            f"import {{ isMain }} from {IS_MAIN.as_uri()!r};\n"
            "process.exit(isMain(import.meta.url) ? 0 : 7);\n"
        )
        with tempfile.TemporaryDirectory() as tmp:
            script = Path(tmp) / "probe.mjs"
            script.write_text(script_body, encoding="utf-8")
            started = subprocess.run([node, str(script)], capture_output=True, text=True, timeout=60)
            self.assertEqual(started.returncode, 0, started.stderr)
            # Imported rather than started: must not count as main.
            importer = Path(tmp) / "importer.mjs"
            importer.write_text(
                f"import {{ isMain }} from {IS_MAIN.as_uri()!r};\n"
                f"process.exit(isMain({script.as_uri()!r}) ? 7 : 0);\n",
                encoding="utf-8",
            )
            imported = subprocess.run([node, str(importer)], capture_output=True, text=True, timeout=60)
            self.assertEqual(imported.returncode, 0, imported.stderr)


if __name__ == "__main__":
    unittest.main()
