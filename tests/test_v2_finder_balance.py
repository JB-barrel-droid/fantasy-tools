"""v2 Find a trade v2 (JEG-988), commit 3: roster balance and the generated evaluation, pure rules in app/v2/finder.js.

  * expectedDepth: the engine's seats per team (starters plus bench seats, league-wide rostered / teams), as a range:
    12 teams with the standard allocation give QB 2-3, RB 4-5, WR 5-6, TE 1-2;
  * rosterBalance: a player counts toward a view's depth only with a usable value in that view (>= 0.05); under means
    fewer than the low end, over means two or more above the high end (one extra is normal depth); a partial roster is
    not ready; unusable players are listed, never counted as 0 and never dropped;
  * evalSentence: "Based on <view>, your roster is overweight at ... and underweight at ...", the lineup values in that
    view, a note for players with no usable value; a balanced roster says so.

Discrimination: test_checks_fail_on_broken_builds runs the same checks on copies of finder.js with a rule broken.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_import import FINDER_JS, call

ALLOC = [{"pos": "QB", "lineup": 12, "bench": 15, "rostered": 27}, {"pos": "RB", "lineup": 27, "bench": 28, "rostered": 55},
         {"pos": "WR", "lineup": 33, "bench": 35, "rostered": 68}, {"pos": "TE", "lineup": 12, "bench": 6, "rostered": 18}]
SHAPE = {"QB": 1, "RB": 2, "WR": 2, "TE": 1, "FLEX": 1, "SUPERFLEX": 0}


def row(pos, i, ddf=10.0, market=None):
    values = {"ddf_value": ddf}
    if market is not None or ddf is None:
        values["chart_avg"] = market
    return {"player_key": f"{pos}{i}", "pos": pos, "values": values}


def roster(counts, **kw):
    return [row(pos, i, **kw) for pos, n in counts.items() for i in range(n)]


def check(finder_js: Path) -> list[str]:
    errors = []
    expected = call(finder_js, "expectedDepth", ALLOC, 12)
    got = {pos: (e["lo"], e["hi"]) for pos, e in (expected or {}).items()}
    if got != {"QB": (2, 3), "RB": (4, 5), "WR": (5, 6), "TE": (1, 2)}:
        errors.append(f"expected depth is {got}")
    if expected and abs(expected["RB"]["expected"] - 55 / 12) > 1e-9:
        errors.append("the expected RB count is not rostered / teams")
    if call(finder_js, "expectedDepth", ALLOC, 0) is not None or call(finder_js, "expectedDepth", None, 12) is not None:
        errors.append("expected depth without teams or an allocation is not null")
    # Roster A of the spec: RB-heavy, short at QB / WR; the TE with value 0 is not depth.
    a = roster({"QB": 1, "RB": 6, "WR": 2}) + [row("TE", 0, 5.0), row("TE", 1, 0.0)]
    b = call(finder_js, "rosterBalance", a, expected, "ddf_value", SHAPE)
    if b["under"] != ["QB", "WR"] or b["over"] != []:
        errors.append(f"roster A: under {b['under']} over {b['over']}, want under QB and WR")
    if b["positions"]["TE"]["have"] != 1 or b["positions"]["TE"]["unusable"] != 1 or b["unusable"] != 1:
        errors.append(f"a TE worth 0.0 was counted as depth: {b['positions']['TE']}")
    if not b["ready"]:
        errors.append("a roster with 11 players for 7 slots is not ready")
    # Over: eight RBs where 4-5 are expected; seven is still normal depth plus one.
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 8, "WR": 5, "TE": 2}), expected, "ddf_value", SHAPE)
    if b["over"] != ["RB"] or b["under"] != []:
        errors.append(f"eight RBs: over {b['over']} under {b['under']}")
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 6, "WR": 5, "TE": 2}), expected, "ddf_value", SHAPE)
    if b["over"] or b["under"]:
        errors.append(f"six RBs (one above the range) flagged: over {b['over']} under {b['under']}")
    # The market view: players the charts do not price (null) do not count, so the same roster reads differently.
    full = roster({"QB": 2, "RB": 5, "WR": 6, "TE": 2}, market=3.0)
    thin = [dict(r, values={**r["values"], "chart_avg": None}) if r["pos"] == "WR" and r["player_key"] in ("WR3", "WR4", "WR5") else r for r in full]
    if call(finder_js, "rosterBalance", thin, expected, "chart_avg", SHAPE)["under"] != ["WR"]:
        errors.append("three WRs the charts do not price were counted as market depth")
    if call(finder_js, "rosterBalance", thin, expected, "ddf_value", SHAPE)["under"] != []:
        errors.append("the fundamental view was changed by chart prices")
    # A partial roster is not ready.
    if call(finder_js, "rosterBalance", roster({"QB": 1, "RB": 2, "WR": 2}), expected, "ddf_value", SHAPE)["ready"]:
        errors.append("a partial roster is judged")
    # Sentences.
    b = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 8, "WR": 2, "TE": 2}), expected, "ddf_value", SHAPE)
    s = call(finder_js, "evalSentence", "your", "fundamentals", "DDF Value", b, {"starters": 141.94, "bench": 37.8})
    for need in ("Based on fundamentals, your roster is overweight at RB (8 counted, 4-5 expected) and underweight at WR (2 counted, 5-6 expected).",
                 "Your starting lineup is worth 141.9 in DDF Value; the bench adds 37.8."):
        if need not in s:
            errors.append(f"sentence lacks {need!r}: {s!r}")
    ok = call(finder_js, "rosterBalance", roster({"QB": 2, "RB": 5, "WR": 6, "TE": 2}), expected, "ddf_value", SHAPE)
    s = call(finder_js, "evalSentence", "their", "market pricing", "trade chart average", ok, {"starters": 10, "bench": 2})
    if not s.startswith("Based on market pricing, their roster is balanced by position.") or "Their starting lineup is worth 10.0 in trade chart average" not in s:
        errors.append(f"balanced sentence reads {s!r}")
    s = call(finder_js, "evalSentence", "your", "fundamentals", "DDF Value", call(finder_js, "rosterBalance", a, expected, "ddf_value", SHAPE), {"starters": 1, "bench": 1})
    if "1 player has no usable value in this view and is not counted toward depth." not in s:
        errors.append(f"the unusable note is missing: {s!r}")
    return errors


MUTANTS = {
    "bench seats ignored": ("const expected = a.rostered / teams;", "const expected = a.lineup / teams;"),
    "range lo rounded up": ("lo: Math.floor(expected + 1e-9)", "lo: Math.ceil(expected - 1e-9)"),
    "zero-value counted as depth": ("r.values[valueKey] >= USABLE_MIN", "r.values[valueKey] >= 0"),
    "under rule loose": ("have < e.lo ? \"under\"", "have < e.lo - 1 ? \"under\""),
    "over rule one early": ("have > e.hi + 1 ? \"over\"", "have > e.hi ? \"over\""),
    "partial roster judged": ("includes(r.pos)).length >= slots &&", "includes(r.pos)).length >= 0 &&"),
    "market view reads fundamentals": ("r.values && finite(r.values[valueKey]) && r.values[valueKey] >= USABLE_MIN", "r.values && finite(r.values.ddf_value) && r.values.ddf_value >= USABLE_MIN"),
    "sentence drops the lineup": ("const value = sums ?", "const value = false ?"),
}


class FinderBalanceTests(unittest.TestCase):
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
