"""GAP-014 / GAP-038: docs/import-health-schema.md matches the verifier.

The doc said "five" sources while the verifier covered six, then seven
(cbsros, razzball). These checks read both and fail when they drift. Each is
negative-tested against a mutated copy of the doc.
"""
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipelines"))

import verify_import_health as vih  # noqa: E402

DOC = (ROOT / "docs" / "import-health-schema.md").read_text()
WORDS = {5: "five", 6: "six", 7: "seven", 8: "eight"}


def problems(doc):
    out = []
    m = re.search(r"\*\*Sources covered[^\n]*exactly these (\w+), never others\):\*\*\s*\n(.+?)\n", doc)
    if not m:
        return ["no 'Sources covered (... exactly these N ...)' line"]
    listed = re.findall(r"`([a-z_]+)`", m.group(2))
    if listed != list(vih.DASHBOARD_SOURCES):
        out.append(f"sources listed {listed} != verifier {list(vih.DASHBOARD_SOURCES)}")
    if m.group(1) != WORDS.get(len(vih.DASHBOARD_SOURCES)):
        out.append(f"count word {m.group(1)!r} != {len(vih.DASHBOARD_SOURCES)}")
    for wrong in (w for n, w in WORDS.items() if n != len(vih.DASHBOARD_SOURCES)):
        if re.search(rf"\b(all|the|exactly these) {wrong}\b", doc, re.I):
            out.append(f"doc still says '{wrong}' sources somewhere")
    codes = re.search(r"### `failure_reason` codes.*?\n\n(.*?)\n\n", doc, re.S)
    table = codes.group(1) if codes else ""
    for code in vih.FAILURE_CODES:
        if f"`{code}`" not in table:
            out.append(f"failure code {code} missing from the codes table")
    for source, statuses in vih.ADVISORY_FRESHNESS.items():
        for st in statuses:
            if f"`{st}`" not in doc:
                out.append(f"advisory status {st} ({source}) undocumented")
    for name in ("ECR", "Vegas", "prediction markets"):
        if name not in doc:
            out.append(f"hard exclusion {name} undocumented")
    if "**Status:** normative." in doc:
        out.append("whole doc marked normative; mark sections instead")
    return out


class ImportHealthSchemaDocTest(unittest.TestCase):
    def test_doc_matches_verifier(self):
        self.assertEqual([], problems(DOC))

    def test_old_five_source_doc_is_caught(self):
        old = DOC.replace("exactly these seven", "exactly these five").replace(
            "`cbs`, `cbsros`, `razzball`", "`cbs`")
        self.assertNotEqual(DOC, old)
        self.assertTrue(any("sources listed" in p for p in problems(old)))
        self.assertTrue(any("count word" in p for p in problems(old)))

    def test_stale_count_elsewhere_is_caught(self):
        self.assertTrue(problems(DOC + "\nThe verifier checks all six sources.\n"))

    def test_missing_failure_code_is_caught(self):
        self.assertTrue(any("RAZZBALL_STALE" in p for p in problems(DOC.replace("`RAZZBALL_STALE`", "`X`"))))

    def test_blanket_normative_status_is_caught(self):
        self.assertTrue(problems(DOC.replace("**Status:** mixed;", "**Status:** normative. mixed;")))


if __name__ == "__main__":
    unittest.main()
