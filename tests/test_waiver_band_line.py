"""JEG-1047: a projection source's waiver line is a 7-player band, not one player.

Jeremy, 2026-10-29 (JEG-1047, option A): average the 7 players around the
first non-rostered seat, with the bar that a 1 PPG change to the waiver-line
player moves no other player at that position by more than 1.0 point in that
source's Adjusted value. Research: docs/research/jeg1047-waiver-line.md.

Fails without the fix: under the one-player rule the same perturbation moves
another player by up to 3.2 points (Razzball QB, 8 teams, on the week 8
build), and `test_band_beats_one_player_rule` compares both rules on the same
cases.
"""
from __future__ import annotations

import json
import random
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "pipelines"))
sys.path.insert(0, str(REPO / "pipelines" / "lib"))

import value_reference as vr  # noqa: E402
from lib.roster_convention import (  # noqa: E402
    WAIVER_BAND_HALF_WIDTH,
    waiver_band_line,
    waiver_line,
)

TOLERANCE = 1.0
PROJECTIONS = ("espn", "cbsros", "razzball")
# The default setting and the setting with the worst one-player moves before
# the fix (8 teams).
CELLS = (("ppr", 12), ("standard", 8))


class BandMathTest(unittest.TestCase):
    def test_band_is_mean_of_seven_around_seat(self):
        values = [20.0, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1]
        self.assertEqual(WAIVER_BAND_HALF_WIDTH, 3)
        # seat 5 (value 10): window 2..8 = 16,14,12,10,8,6,4
        self.assertAlmostEqual(waiver_band_line(values, 5), sum([16, 14, 12, 10, 8, 6, 4]) / 7)
        # seat 9 (value 2), clipped at the bottom of the list: 8,6,4,2,1
        self.assertAlmostEqual(waiver_band_line(values, 9), sum([8, 6, 4, 2, 1]) / 5)

    def test_short_list_keeps_last_value(self):
        self.assertEqual(waiver_band_line([9.0, 8.0], 2), waiver_line([9.0, 8.0], 2))
        self.assertEqual(waiver_band_line([9.0, 8.0], 5), 8.0)
        self.assertIsNone(waiver_band_line([], 3))
        self.assertIsNone(waiver_band_line([1.0], 0))

    def test_one_player_moves_band_by_at_most_a_seventh(self):
        values = [20.0, 18, 16, 14, 12, 10, 8, 6, 4, 2, 1]
        base = waiver_band_line(values, 5)
        bumped = sorted(values[:5] + [values[5] + 1.0] + values[6:], reverse=True)
        self.assertLessEqual(abs(waiver_band_line(bumped, 5) - base), 1.0 / 7 + 1e-12)
        self.assertGreater(abs(waiver_line(bumped, 5) - waiver_line(values, 5)), 1.0 / 7)

    def test_js_twin_matches(self):
        rng = random.Random(1047)
        cases = []
        for _ in range(200):
            n = rng.randint(1, 40)
            vals = sorted((round(rng.uniform(0, 30), 3) for _ in range(rng.randint(0, 45))), reverse=True)
            cases.append({"values": vals, "rostered": n})
        js = (
            "const RC=require(process.argv[1]).RosterConvention;"
            "const cases=JSON.parse(require('fs').readFileSync(0,'utf8'));"
            "process.stdout.write(JSON.stringify(cases.map(c=>RC.waiverBandLine(c.values,c.rostered))));"
        )
        out = subprocess.run(
            ["node", "-e", js, str(REPO / "app" / "trade-value-chart" / "assets" / "roster-convention.js")],
            input=json.dumps(cases), capture_output=True, text=True, check=True,
        )
        got = json.loads(out.stdout)
        for c, g in zip(cases, got):
            want = waiver_band_line(c["values"], c["rostered"])
            if want is None:
                self.assertIsNone(g, c)
            else:
                self.assertAlmostEqual(g, want, places=12, msg=c)

    def test_engine_and_references_use_the_band(self):
        """The engine, the Python reference and the spec reference all call
        the band for projections (one definition per step, JEG-556)."""
        engine = (REPO / "app" / "trade-value-chart" / "assets" / "value-model.js").read_text(encoding="utf-8")
        self.assertIn('family === "projection" ? vpWaiverBand(work, N) : work[N].native', engine)
        spec = (REPO / "pipelines" / "spec_reference" / "value_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("_convention_waiver_band_line(", spec)
        self.assertIs(vr._convention_waiver_band_line, waiver_band_line)


class OnePlayerPerturbationTest(unittest.TestCase):
    """A 1 PPG change to the waiver-line player moves no other player at the
    position by more than 1.0 point in that source's Adjusted value."""

    @classmethod
    def setUpClass(cls):
        cls.inp = vr.Inputs.load()

    def _cases(self):
        inp = self.inp
        out = []
        for scoring, teams in CELLS:
            s = vr.Setting(inp, scoring, teams)
            res = s.result()
            for src in PROJECTIONS:
                if src not in res["sources"]:
                    continue
                natives = s.natives(src)
                for pos in vr.POSITIONS:
                    info = res["sources"][src]["positions"].get(pos) or {}
                    n = info.get("rostered")
                    work = sorted(((k, x) for k, x in natives.items() if inp.players[k]["pos"] == pos),
                                  key=lambda t: (-t[1], t[0]))
                    if n is None or len(work) <= n:
                        continue
                    out.append((scoring, teams, src, pos, work[n][0]))
        return out

    def _worst(self, scoring, teams, src, pos, key, delta):
        inp = self.inp
        field = vr.PPG_FIELD[src]

        def adjusted():
            rows = vr.Setting(inp, scoring, teams).result()["rows"]
            return {i: (r.get("adjusted") or {}).get(src) for i, r in rows.items() if r["pos"] == pos}

        base = adjusted()
        rec = inp.players[key][field]
        old = rec[scoring]
        rec[scoring] = max(0.0, old + delta)
        try:
            new = adjusted()
        finally:
            rec[scoring] = old
        moves = [abs(new[i] - b) for i, b in base.items()
                 if i != key and b is not None and new.get(i) is not None]
        return max(moves, default=0.0)

    def test_fringe_player_moves_no_one_more_than_tolerance(self):
        cases = self._cases()
        self.assertGreaterEqual(len(cases), 20, "expected a waiver line at most source/position cells")
        failures = []
        for scoring, teams, src, pos, key in cases:
            for delta in (-1.0, 1.0):
                worst = self._worst(scoring, teams, src, pos, key, delta)
                if worst > TOLERANCE:
                    failures.append(f"{scoring}/{teams} {src} {pos} {key} {delta:+}: {worst:.3f}")
        self.assertEqual(failures, [], "one fringe player repriced the position:\n" + "\n".join(failures))

    def test_band_beats_one_player_rule(self):
        """Mutation check: the one-player rule, on the same cases, moves some
        other player further than the band does."""
        cases = self._cases()
        band = max(self._worst(*c, d) for c in cases for d in (-1.0, 1.0))
        orig = vr._waiver_value
        vr._waiver_value = lambda src, pos, values, n: values[n]
        try:
            one = max(self._worst(*c, d) for c in cases for d in (-1.0, 1.0))
        finally:
            vr._waiver_value = orig
        self.assertGreater(one, band)
        self.assertGreater(one, TOLERANCE, "the one-player rule should fail the bar on these cells")


if __name__ == "__main__":
    unittest.main()
