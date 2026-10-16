"""Every pipelines module that imports `lib.*` / `timestamps` must import on its
own, from a copy of the repo at an arbitrary path, with a clean sys.path.

Regression guard for the checkout-path / import-order dependence: modules did
`from lib.timestamps import ...` with no sys.path setup, so they only imported
when some earlier test (or a CWD hack) had put pipelines/ on sys.path. Run alone
(unittest per module, a fresh worktree, a different checkout) they raised
ModuleNotFoundError: No module named 'lib'.
"""
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_IMPORT = re.compile(r"^\s*(from|import) (lib|timestamps)\b", re.M)
MISSING = re.compile(r"No module named '(lib|timestamps)\b")


def modules_using_lib(pipelines_dir):
    mods = []
    for f in sorted(list(pipelines_dir.glob("*.py")) + list(pipelines_dir.glob("lib/*.py"))):
        if LIB_IMPORT.search(f.read_text(encoding="utf-8")):
            mods.append(".".join(f.relative_to(pipelines_dir.parent).with_suffix("").parts))
    return mods


def import_failures(pipelines_dir):
    """Import each lib-using module in a clean interpreter rooted at the copy."""
    base = pipelines_dir.parent
    failures = []
    for mod in modules_using_lib(pipelines_dir):
        r = subprocess.run(
            [sys.executable, "-I", "-c", f"import sys; sys.path.insert(0, {str(base)!r}); import {mod}"],
            capture_output=True, text=True, cwd=base, timeout=60)
        if MISSING.search(r.stderr):
            failures.append(mod)
    return failures


class PipelinesImportStandalone(unittest.TestCase):
    def copy_pipelines(self, tmp):
        dest = Path(tmp) / "some other checkout dir" / "pipelines"
        shutil.copytree(ROOT / "pipelines", dest, ignore=shutil.ignore_patterns("__pycache__"))
        return dest

    def test_lib_importing_modules_import_from_a_temp_copy(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_pipelines(tmp)
            self.assertGreater(len(modules_using_lib(dest)), 10)
            self.assertEqual([], import_failures(dest))

    def test_guard_catches_a_module_that_assumes_pipelines_on_sys_path(self):
        """Negative test: a module with a bare `from lib.timestamps` is flagged."""
        with tempfile.TemporaryDirectory() as tmp:
            dest = self.copy_pipelines(tmp)
            broken = dest / "broken_probe.py"
            broken.write_text("from lib.timestamps import parse_iso_timestamp\n")
            self.assertEqual(["pipelines.broken_probe"], import_failures(dest))


if __name__ == "__main__":
    unittest.main()
