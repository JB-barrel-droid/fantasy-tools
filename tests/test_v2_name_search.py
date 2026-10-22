"""v2 player-name search: app/v2/namesearch.js (JEG-812).

Live QA (2026-10-22): "Amon Ra", "JaMarr", "Ja’Marr" (curly apostrophe) and the typo "Mcafrey" found no player.
The matcher ignores case, spaces, hyphens, straight and curly apostrophes, periods and accents; ranks exact
name, name start, word start, inside-the-name, spaces-ignored; and only when nothing matches that way falls back
to a small typo-tolerant match (1 edit for 4 to 6 letters, 2 for 7 or more, none under 4).

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of namesearch.js with the
spaces-ignored match removed, the fuzzy fallback removed, curly apostrophes not dropped, and the rank order ignored.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SEARCH_JS = ROOT / "app" / "v2" / "namesearch.js"

NAMES = ["Amon-Ra St. Brown", "Ja'Marr Chase", "Christian McCaffrey", "Jaxon Smith-Njigba", "Patrick Mahomes",
         "Travis Kelce", "Josh Allen", "Josh Jacobs", "Joshua Palmer", "Allen Robinson", "Allen", "Brian Thomas Jr.",
         "Cam Akers", "Dak Prescott"]

# query -> names expected first (exact, in order); an empty list means no match at all.
CASES = {
    "Amon Ra": ["Amon-Ra St. Brown"],
    "amonra": ["Amon-Ra St. Brown"],
    "AMON-RA": ["Amon-Ra St. Brown"],
    "st brown": ["Amon-Ra St. Brown"],
    "JaMarr": ["Ja'Marr Chase"],
    "Ja’Marr": ["Ja'Marr Chase"],
    "Ja'Marr": ["Ja'Marr Chase"],
    "ja marr": ["Ja'Marr Chase"],
    "Mcafrey": ["Christian McCaffrey"],
    "Mccaffrey": ["Christian McCaffrey"],
    "mahoes": ["Patrick Mahomes"],
    "Njigba": ["Jaxon Smith-Njigba"],
    "Brian Thomas": ["Brian Thomas Jr."],
    # exact first, then name start, then word start
    "allen": ["Allen", "Allen Robinson", "Josh Allen"],
    "josh": ["Josh Allen", "Josh Jacobs", "Joshua Palmer"],
    # no match, and no fuzzy under 4 letters
    "xyzzy": [],
    "cax": [],
    "": [],
}

HARNESS = """
const S = require(process.argv[1]);
const names = JSON.parse(process.argv[2]);
const rows = names.map(name => ({name}));
const out = {};
for (const q of JSON.parse(process.argv[3])) out[q] = S.search(rows, q).map(r => r.name);
const kept = S.filter(rows, "josh").map(r => r.name);
const keys = [S.key("Ja’Marr") === S.key("Ja'Marr"), S.key("Amon-Ra") === S.key("amon ra")];
// Without the fuzzy fallback: these must already match on rank alone.
const exact = [S.rank("Amon-Ra St. Brown", "amonra"), S.rank("Ja'Marr Chase", "JaMarr"), S.rank("Ja'Marr Chase", "Ja’Marr")];
console.log(JSON.stringify({out, kept, keys, exact}));
"""


def run(path: Path):
    if not shutil.which("node"):
        raise unittest.SkipTest("node is not installed")
    out = subprocess.run(["node", "-e", HARNESS, str(path), json.dumps(NAMES), json.dumps(list(CASES))],
                         check=True, capture_output=True, text=True)
    return json.loads(out.stdout)


def check(path: Path) -> list[str]:
    errors = []
    result = run(path)
    for query, want in CASES.items():
        got = result["out"][query]
        if want == []:
            if got:
                errors.append(f"{query!r}: expected no match, got {got}")
        elif got[:len(want)] != want:
            errors.append(f"{query!r}: expected {want} first, got {got}")
    if result["kept"] != ["Josh Allen", "Josh Jacobs", "Joshua Palmer"]:
        errors.append(f"filter keeps the rows' own order, got {result['kept']}")
    if result["keys"] != [True, True]:
        errors.append(f"curly and straight apostrophes, and hyphen and space, must normalise alike, got {result['keys']}")
    if any(rank is None for rank in result["exact"]):
        errors.append(f"amonra / JaMarr / Ja’Marr must match without the typo fallback, got ranks {result['exact']}")
    return errors


MUTANTS = {
    "spaces-ignored match removed": ("return qs && ns.includes(qs) ? 4 : null;", "return null;"),
    "fuzzy fallback removed": ("const allowedEdits = length => (length >= 7 ? 2 : length >= 4 ? 1 : 0);", "const allowedEdits = length => 0;"),
    "curly apostrophe not dropped": ("replace(/[.'’‘`´]/g, \"\")", "replace(/[.']/g, \"\")"),
    "rank order ignored": ("ranked.sort((a, b) => a.r - b.r || a.index - b.index)", "ranked.sort((a, b) => a.index - b.index)"),
}


class NameSearchTest(unittest.TestCase):
    def test_search(self):
        self.assertEqual(check(SEARCH_JS), [])

    def test_checks_fail_on_broken_builds(self):
        source = SEARCH_JS.read_text(encoding="utf-8")
        for name, (old, new) in MUTANTS.items():
            with self.subTest(mutant=name), tempfile.TemporaryDirectory() as tmp:
                self.assertIn(old, source, f"mutation anchor missing for {name}")
                path = Path(tmp) / "namesearch.js"
                path.write_text(source.replace(old, new, 1), encoding="utf-8")
                self.assertNotEqual(check(path), [], f"checks did not catch: {name}")


if __name__ == "__main__":
    unittest.main()
