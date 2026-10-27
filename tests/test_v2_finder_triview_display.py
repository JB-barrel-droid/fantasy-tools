"""JEG-1081 PR 3: pure display helpers of the three views in app/v2/finder.js.

  * hasProjections: true only when some row carries a finite ddf_value_projections;
  * chipTooltip: "DDF Value: a\\nProjections: b\\nMarket: c", a missing view reads "no value";
  * deltaLine: "Starters +4.2 DDF Value (+3.9 projections, -0.6 market)" with a true minus sign; a view with no delta is left out.

Discrimination: test_checks_fail_on_broken_builds runs the checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

MINUS = "−"


def check(finder_js: Path) -> list[str]:
    errors = []
    say = errors.append
    row = lambda v: {"values": v}
    if call(finder_js, "hasProjections", [row({"ddf_value": 1}), row({"ddf_value_projections": None})]):
        say("hasProjections true with no projection value")
    if not call(finder_js, "hasProjections", [row({}), row({"ddf_value_projections": 0})]):
        say("hasProjections false though a row carries 0")
    got = call(finder_js, "chipTooltip", {"ddf": 24.34, "projections": 22.1, "market": 20.8})
    if got != "DDF Value: 24.3\nProjections: 22.1\nMarket: 20.8":
        say(f"chipTooltip {got!r}")
    got = call(finder_js, "chipTooltip", {"ddf": 5, "projections": None, "market": None})
    if got != "DDF Value: 5.0\nProjections: no value\nMarket: no value":
        say(f"chipTooltip missing {got!r}")
    got = call(finder_js, "deltaLine", "Starters", {"ddf": 4.2, "projections": 3.9, "market": -0.64})
    if got != f"Starters +4.2 DDF Value (+3.9 projections, {MINUS}0.6 market)":
        say(f"deltaLine {got!r}")
    got = call(finder_js, "deltaLine", "Bench", {"ddf": -1.1, "projections": None, "market": 0.01})
    if got != f"Bench {MINUS}1.1 DDF Value (0.0 market)":
        say(f"deltaLine missing projections {got!r}")
    got = call(finder_js, "deltaLine", "Bench", {"ddf": 2, "projections": None, "market": None})
    if got != "Bench +2.0 DDF Value":
        say(f"deltaLine only DDF {got!r}")
    got = call(finder_js, "deltaLine", "Starters", {"ddf": None, "projections": 1, "market": 2})
    if got != "Starters: no value":
        say(f"deltaLine no DDF value {got!r}")
    return errors


MUTANTS = {
    "projections ignored": ("const hasProjections = rows => rows.some(r => r && r.values && finite(r.values[PROJECTIONS_KEY]));", "const hasProjections = rows => true;"),
    "tooltip drops projections": ('one("Projections", v.projections), ', ""),
    "tooltip market first": ('[one("DDF Value", v.ddf), one("Projections", v.projections), one("Market", v.market)]', '[one("DDF Value", v.ddf), one("Market", v.market), one("Projections", v.projections)]'),
    "missing reads 0": ('finite(v) ? v.toFixed(1) : "no value"}`;\n    const v = values', 'finite(v) ? v.toFixed(1) : "0.0"}`;\n    const v = values'),
    "plain hyphen minus": ('(n > 0 ? "+" : "\\u2212")', '(n > 0 ? "+" : "-")'),
    "projections shown when missing": ('finite(d.projections) ? `${sign(d.projections)} projections` : ""', '`${sign(d.projections)} projections`'),
}


class TriViewDisplayTests(unittest.TestCase):
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
