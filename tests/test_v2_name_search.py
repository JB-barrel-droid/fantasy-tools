"""v2 player-name search: app/v2/namesearch.js (JEG-812, JEG-861).

Live QA (2026-10-22): "Amon Ra", "JaMarr", "Ja’Marr" (curly apostrophe) and the typo "Mcafrey" found no player.
JEG-861: "Nacua Puka" (reversed) found nothing, while "nac" found Arizona Cardinals and De'Von Achane and "cmc"
found Eric McAlister (the query sat inside the spaces-dropped name), and "kelse" put Keleki Latu ahead of
Travis Kelce (fuzzy against a cut shorter than the query).
The matcher ignores case, spaces, hyphens, straight and curly apostrophes, periods, accents and a trailing
Jr./Sr./II/III/IV/V; every match is a word-start match; ranks whole name, name start, word start (spaces in
the query optional), then every query word starting a different name word in any order; and only when nothing
matches that way falls back to a small typo-tolerant match (1 edit for 4 to 6 letters, 2 for 7 or more, none
under 4). It never invents a player.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of namesearch.js with the
spaces-ignored match removed, the any-order match removed, inside-the-name matching allowed again, suffixes not
ignored, the fuzzy cut shorter than the query allowed again, the fuzzy fallback removed, curly apostrophes not
dropped, and the rank order ignored.
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
         "Keleki Latu", "Travis Kelce", "Josh Allen", "Josh Jacobs", "Joshua Palmer", "Allen Robinson", "Allen",
         "Brian Thomason", "Brian Thomas Jr.", "Cam Akers", "Dak Prescott", "Puka Nacua", "Arizona Cardinals",
         "De'Von Achane", "Eric McAlister", "Chase Brown", "Anthony Tyus III"]

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
    "stbrown": ["Amon-Ra St. Brown"],
    # JEG-861: a trailing Jr./III is ignored on both sides, so "Brian Thomas" is the whole name (rank 0),
    # ahead of Brian Thomason (name start) even though Thomason is listed first.
    "Brian Thomas": ["Brian Thomas Jr.", "Brian Thomason"],
    "brian thomas jr": ["Brian Thomas Jr."],
    "Anthony Tyus": ["Anthony Tyus III"],
    "Tyus Anthony": ["Anthony Tyus III"],
    # JEG-861: reversed names and initials (every query word starts a different name word, any order).
    "Nacua Puka": ["Puka Nacua"],
    "Allen Josh": ["Josh Allen"],
    "j chase": ["Ja'Marr Chase"],
    "p nacua": ["Puka Nacua"],
    # exact first, then name start, then word start, then any order
    "allen": ["Allen", "Allen Robinson", "Josh Allen"],
    "josh": ["Josh Allen", "Josh Jacobs", "Joshua Palmer"],
    "chase": ["Chase Brown", "Ja'Marr Chase"],
    # JEG-861: a word-start match only; a query inside a name is not a match ("nac" is not Arizona
    # Cardinals or De'Von Achane; "cmc" is not Eric McAlister, and is too short for a typo match).
    "nac": ["Puka Nacua"],
    "cmc": [],
    "arr": [],
    # JEG-861: the typo match never cuts a name shorter than the query ("kele" would be 1 edit from "kelse").
    "kelse": ["Travis Kelce"],
    # no match, and no fuzzy under 4 letters
    "xyzzy": [],
    "cax": [],
    "": [],
}
# Queries that must find exactly these players and nobody else.
ONLY = {"nac": ["Puka Nacua"], "kelse": ["Travis Kelce"], "Nacua Puka": ["Puka Nacua"]}

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
    for query, want in ONLY.items():
        if result["out"][query] != want:
            errors.append(f"{query!r}: expected only {want}, got {result['out'][query]}")
    if result["kept"] != ["Josh Allen", "Josh Jacobs", "Joshua Palmer"]:
        errors.append(f"filter keeps the rows' own order, got {result['kept']}")
    if result["keys"] != [True, True]:
        errors.append(f"curly and straight apostrophes, and hyphen and space, must normalise alike, got {result['keys']}")
    if any(rank is None for rank in result["exact"]):
        errors.append(f"amonra / JaMarr / Ja’Marr must match without the typo fallback, got ranks {result['exact']}")
    return errors


MUTANTS = {
    "spaces-ignored match removed": ('if (nameWords.slice(i).join("").startsWith(qs)) return i === 0 ? 1 : 2;',
                                     'if (nameWords[i].startsWith(qs)) return i === 0 ? 1 : 2;'),
    "any-order match removed": ("if (wordsAnyOrder(nameWords, queryWords)) return 3;", "if (false) return 3;"),
    "inside-the-name match allowed (as before JEG-861)": ("if (wordsAnyOrder(nameWords, queryWords)) return 3;",
                                                           'if (wordsAnyOrder(nameWords, queryWords) || n.replace(/ /g, "").includes(qs)) return 3;'),
    "suffix not ignored": ("const kept = words.filter(word => !SUFFIXES.has(word));", "const kept = words;"),
    "fuzzy cut shorter than the query allowed (as before JEG-861)": ("for (const cut of [qs.length, qs.length + 1])",
                                                                       "for (const cut of [qs.length - 1, qs.length, qs.length + 1])"),
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
