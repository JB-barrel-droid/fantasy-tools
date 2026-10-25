"""v2 Find a trade v2 (JEG-988), the pure rules of the one box per side, in app/v2/finder.js.

  * looksLikePage: text with two or more non-empty lines, or longer than 120 characters, is a pasted page; a name, a
    "last, first" form, a name with a trailing newline and any single line up to 120 characters is a search;
  * isNotEvaluated: kickers and defenses (K, DEF, DST) are kept but not evaluated; every other position is evaluated.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

LONG = "x" * 121
MUTANTS = {
    "newline not a page": ("lines.length >= PAGE_MIN_LINES ||", "false ||"),
    "length not a page": ("value.trim().length >= PAGE_MIN_LENGTH", "false"),
    "one line is a page": ("const PAGE_MIN_LINES = 2;", "const PAGE_MIN_LINES = 1;"),
    "kicker evaluated": ('const NOT_EVALUATED_POS = ["K", "DEF", "DST"];', 'const NOT_EVALUATED_POS = ["DEF", "DST"];'),
    "defense evaluated": ('const NOT_EVALUATED_POS = ["K", "DEF", "DST"];', 'const NOT_EVALUATED_POS = ["K"];'),
    "everything not evaluated": ("Boolean(row) && NOT_EVALUATED_POS.includes(row.pos)", "Boolean(row)"),
}


def check(finder_js: Path) -> list[str]:
    errors = []
    pages = {"two lines": "Josh Allen\nBijan Robinson", "crlf": "a\r\nb", "long single line": LONG, "page": "QB\nJosh Allen\nBuf - QB\n"}
    for label, text in pages.items():
        if call(finder_js, "looksLikePage", text) is not True:
            errors.append(f"{label} is not read as a page")
    searches = {"name": "Josh Allen", "reversed": "Allen, Josh", "trailing newline": "Josh Allen\n", "blank lines around": "\n\nJosh Allen\n\n",
                "120 characters": "y" * 120, "empty": "", "spaces": "   "}
    for label, text in searches.items():
        if call(finder_js, "looksLikePage", text) is not False:
            errors.append(f"{label} is read as a page")
    for pos in ("K", "DEF", "DST"):
        if call(finder_js, "isNotEvaluated", {"pos": pos}) is not True:
            errors.append(f"{pos} is evaluated")
    for pos in ("QB", "RB", "WR", "TE", None):
        if call(finder_js, "isNotEvaluated", {"pos": pos}) is not False:
            errors.append(f"{pos} is not evaluated")
    if call(finder_js, "isNotEvaluated", None) is not False:
        errors.append("a missing row is not evaluated")
    return errors


class FinderBoxTests(unittest.TestCase):
    def test_rules(self):
        self.assertEqual(check(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = FINDER_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(name):
                self.assertIn(old, source, f"mutant {name!r} no longer applies")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(source.replace(old, new, 1), encoding="utf-8")
                    self.assertTrue(check(path), f"checks passed on a build with: {name}")


if __name__ == "__main__":
    unittest.main()
