"""v2 Find a trade (JEG-1043, Jeremy 2026-10-27: "A"): the pure helpers behind "Show viable offers only" and the
starters line at the positions a side gives up. Run under node against app/v2/finder.js:

  * viableGroups(groups, labelOf) keeps exactly the groups whose label is truthy, in the same order;
  * startersAtGivenPositions(impact, leaving) lists one entry per QB/RB/WR/TE among the leaving players, with the
    team's starters at that position before and after the trade (a FLEX starter counts at his own position), and
    nothing for a position the team does not give up;
  * givenPositionsLine prints "none" for a position left with no starter, never an empty name.

Discrimination: test_checks_fail_on_broken_builds runs the checks against mutated copies of finder.js (the filter
keeping every group, the entry read from the arriving players, FLEX starters left out, an empty position printed
blank) and requires each to fail.
"""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.test_v2_finder_impact import FINDER_JS, SHAPE, node, p, roster

VIABLE = """
const groups = D.labels.map((label, i) => ({id: i, label}));
return F.viableGroups(groups, g => g.label).map(g => g.id);
"""

GIVEN = """
const rows = D.rows;
const leaving = rows.filter(x => D.give.includes(x.player_key));
const imp = F.rosterImpact(rows, leaving, D.recv, D.shape, 'ddf_value');
const entries = F.startersAtGivenPositions(imp, leaving);
return {entries, line: F.givenPositionsLine(entries)};
"""


def checks(finder_js: Path) -> list[str]:
    errors = []
    kept = node(finder_js, VIABLE, {"labels": ["High", None, "Medium", "", "Med-High", None]})
    if kept != [0, 2, 4]:
        errors.append(f"viableGroups kept {kept}, expected [0, 2, 4]")

    # Give R1 (RB starter) and W1 (WR starter) for one WR worth 26. Before: RB R1 R2 + FLEX R3; WR W1 W2.
    # After: RB R2 R3 (+ FLEX W? no: FLEX takes the best of what is left: W3 21 vs R4 5, so W3); WR X1 W2.
    out = node(finder_js, GIVEN, {"rows": roster(), "give": ["R1", "W1"], "recv": [p("X1", "WR", 26)], "shape": SHAPE})
    by_pos = {e["pos"]: e for e in out["entries"]}
    if sorted(by_pos) != ["RB", "WR"]:
        errors.append(f"positions given up {sorted(by_pos)}, expected ['RB', 'WR'] (no QB or TE given)")
    else:
        if by_pos["RB"]["before"] != ["R1", "R2", "R3"] or by_pos["RB"]["after"] != ["R2", "R3"]:
            errors.append(f"RB starters {by_pos['RB']}, expected R1 R2 R3 -> R2 R3 (FLEX counts at RB)")
        if by_pos["WR"]["before"] != ["W1", "W2"] or by_pos["WR"]["after"] != ["X1", "W2", "W3"]:
            errors.append(f"WR starters {by_pos['WR']}, expected W1 W2 -> X1 W2 W3 (W3 moves into FLEX)")
    if out["line"] != "RB R1, R2, R3 → R2, R3; WR W1, W2 → X1, W2, W3":
        errors.append(f"line {out['line']!r}")

    # Give the only TE for a WR: TE starters go to none.
    out = node(finder_js, GIVEN, {"rows": [r for r in roster() if r["player_key"] != "T2"], "give": ["T1"],
                                  "recv": [p("X2", "WR", 9)], "shape": SHAPE})
    if out["line"] != "TE T1 → none":
        errors.append(f"an emptied position prints {out['line']!r}, expected 'TE T1 → none'")
    return errors


class FinderViableTest(unittest.TestCase):
    def test_helpers(self):
        self.assertEqual(checks(FINDER_JS), [])

    def test_checks_fail_on_broken_builds(self):
        js = FINDER_JS.read_text(encoding="utf-8")
        broken = {
            "filter keeps every group": js.replace("groups.filter(g => Boolean(labelOf(g)))", "groups.slice()", 1),
            "entries read from the arriving players": js.replace(
                "function startersAtGivenPositions(impact, leaving) {",
                "function startersAtGivenPositions(impact, leaving) { leaving = impact.after.starters.filter(r => !impact.before.starters.includes(r));", 1),
            "FLEX starters left out": js.replace(
                "const names = (l, pos) => l.starters.filter(r => r.pos === pos).map(r => r.name);",
                "const names = (l, pos) => (l.slots[pos] || []).map(r => r.name);", 1),
            "an emptied position prints blank": js.replace('e.after.join(", ") || "none"', 'e.after.join(", ")', 1),
        }
        for name, body in broken.items():
            with self.subTest(mutation=name):
                self.assertNotEqual(body, js, f"mutation anchor for {name!r} is stale")
                with tempfile.TemporaryDirectory() as tmp:
                    path = Path(tmp) / "finder.js"
                    path.write_text(body, encoding="utf-8")
                    try:
                        errors = checks(path)
                    except Exception as exc:  # a broken build may throw; that counts as caught
                        errors = [str(exc)[:80]]
                self.assertNotEqual(errors, [], f"not caught: {name}")


if __name__ == "__main__":
    unittest.main()
