"""Doc staleness report (JEG-583/601). The report is non-blocking; these tests
only prove the checker catches what it names and that the README keeps the
Owner and Verified columns on every Maintained row."""
import datetime as dt
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("doc_staleness", ROOT / "scripts" / "doc_staleness.py")
ds = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ds)

TODAY = dt.date(2026, 10, 16)
SAMPLE = """| Doc | Status | Owner | Verified | What it is |
|---|---|---|---|---|
| [fresh.md](fresh.md) | Maintained | JEG-1 | 2026-10-10 | ok |
| [old.md](old.md) | Maintained | JEG-2 | 2026-09-01 | stale |
| [edge.md](edge.md) | Maintained | JEG-3 | 2026-09-16 | exactly 30 days |
| [nodate.md](nodate.md) | Maintained | JEG-4 | unknown | never verified |
| [noowner.md](noowner.md) | Maintained | unknown | 2026-10-15 | no owner |
| [rec.md](rec.md) | Record | - | - | not maintained |
"""


class DocStalenessTests(unittest.TestCase):
    def test_flags_stale_unknown_and_ownerless_only(self):
        got = dict(ds.findings(SAMPLE, TODAY))
        self.assertEqual(sorted(got), ["nodate.md", "noowner.md", "old.md"])
        self.assertIn("days ago", got["old.md"])

    def test_report_is_non_blocking(self):
        self.assertEqual(ds.main(["--today", "2099-01-01"]), 0)

    def test_readme_maintained_rows_have_owner_and_verified_columns(self):
        rows = ds.parse_rows((ROOT / "docs" / "README.md").read_text())
        maintained = [r for r in rows if r[2] == "Maintained"]
        self.assertGreater(len(maintained), 10)
        for _name, path, _status, owner, verified in maintained:
            self.assertTrue(owner == "unknown" or owner.startswith("JEG-"), path)
            self.assertTrue(verified == "unknown" or dt.date.fromisoformat(verified), path)

    def test_report_prints_real_readme_findings(self):
        # Informational: lists what needs a refresh; never fails on age.
        for path, reason in ds.findings((ROOT / "docs" / "README.md").read_text(), dt.date.today()):
            print(f"[doc-staleness] {path}: {reason}")


if __name__ == "__main__":
    unittest.main()
